"""从公开 GitHub 仓库增量采集 Markdown，供 process_source.py 使用。"""
import argparse
from contextlib import closing
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from harvest_output import output_lock, save


DEFAULT_REPOS = ["caomaolufei/AIInfraGuide", "bojieli/ai-infra-book", "lyy-ai/ai_infra"]
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data/tmp/github/posts.jsonl"
INTERVIEW_PATH = re.compile(r"面试|面经|真题|题库|interview|questions?", re.I)


class RateLimitError(RuntimeError):
    pass


def api(endpoint, accept="application/vnd.github+json", limit=12 * 1024 * 1024):
    headers = {"User-Agent": "interview-memory", "Accept": accept}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request("https://api.github.com/repos/" + endpoint, headers=headers)
    try:
        with urlopen(request, timeout=25) as response:
            data = response.read(limit + 1)
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        if exc.code == 429 or (exc.code == 403 and (
            exc.headers.get("X-RateLimit-Remaining") == "0" or "rate limit" in detail.lower()
        )):
            raise RateLimitError("GitHub 限流，已采集的文件会保存，稍后重跑即可续传") from exc
        raise
    if len(data) > limit:
        raise ValueError("GitHub 响应超过大小限制")
    return json.loads(data) if accept == "application/vnd.github+json" else data


def markdown_files(repo, commit, cache):
    # Walk one directory at a time: some of the book repositories contain
    # tens of thousands of generated assets. Cache immutable tree listings so
    # bounded runs can resume without spending quota on unchanged directories.
    stack = [("", {"type": "tree", "sha": commit})]
    while stack:
        path, item = stack.pop()
        if item["type"] == "blob":
            yield path, item["sha"], item["size"]
            continue
        key = item["sha"]
        cached = cache.execute("SELECT entries FROM trees WHERE sha = ?", (key,)).fetchone()
        if cached:
            entries = json.loads(cached[0])
        else:
            result = api(f"{repo}/git/trees/{key}")
            if result["truncated"]:
                raise ValueError(f"GitHub 返回不完整的目录 {path}")
            entries = [entry for entry in result["tree"]
                       if entry["type"] == "tree" or (
                           entry["type"] == "blob" and entry["mode"] in ("100644", "100755")
                           and entry["path"].lower().endswith((".md", ".markdown", ".mdx"))
                       )]
            cache.execute("INSERT OR REPLACE INTO trees VALUES (?, ?)", (key, json.dumps(entries)))
            cache.commit()
        children = sorted(entries, key=lambda entry: (
            not bool(INTERVIEW_PATH.search(entry["path"])),
            # ai-infra-book keeps its interview archive under references/interviews.
            not (repo.lower() == "bojieli/ai-infra-book" and not path and entry["path"] == "references"),
            entry["path"].lower() not in ("docs", "manuscripts"),
            entry["type"] != "blob", entry["path"],
        ))
        for entry in reversed(children):
            child = path + "/" + entry["path"] if path else entry["path"]
            stack.append((child, entry))


def harvest_repo(repo, rows, max_files, max_bytes, cache):
    if os.environ.get("GITHUB_TOKEN") and api(repo)["private"]:
        raise ValueError("仅采集公开仓库")
    commit = api(f"{repo}/commits/HEAD", "application/vnd.github.sha").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("无法解析 GitHub 的 HEAD 提交")
    changed = 0
    seen = set()
    for path, sha, size in markdown_files(repo, commit, cache):
        key = f"{repo.lower()}:{path}"
        seen.add(key)
        previous = rows.get(key, {})
        if previous.get("blob_sha") == sha and previous.get("blob_verified"):
            continue
        if not 0 < size <= max_bytes:
            continue
        data = api(f"{repo}/git/blobs/{sha}", "application/vnd.github.raw+json", max_bytes)
        digest = hashlib.sha1(f"blob {len(data)}\0".encode("ascii"))
        digest.update(data)
        if digest.hexdigest() != sha:
            raise ValueError(f"下载内容与 Git blob SHA 不符: {path}")
        body = data.decode("utf-8-sig", errors="replace")
        heading = re.search(r"^#\s+([^\n]+)", body, re.M)
        rows[key] = {
            "id": key, "source": "github", "repo": repo, "path": path,
            "commit": commit, "blob_sha": sha, "blob_verified": True, "text_kind": "markdown",
            "title": heading.group(1).strip() if heading else path,
            "url": f"https://github.com/{repo}/blob/{commit}/{quote(path)}",
            "text": body,
        }
        changed += 1
        if changed == max_files:
            break
    else:
        # Only a complete walk proves an old path is absent from this snapshot.
        removed = [key for key, row in rows.items()
                   if row["repo"].lower() == repo.lower() and key not in seen]
        for key in removed:
            del rows[key]
    print(f"[github] {repo}: {changed} Markdown files fetched", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", help="owner/repo，可重复指定")
    parser.add_argument("--max-files", type=int, default=10, help="每个仓库本次最多新增或更新的文件数")
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024, help="单个文件字节上限")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    repos = args.repo or DEFAULT_REPOS
    if args.max_files <= 0 or args.max_bytes <= 0:
        parser.error("--max-files 和 --max-bytes 必须大于 0")
    if any(not re.fullmatch(r"[\w-]+/[\w.-]+", repo, re.ASCII)
           or repo.split("/")[1] in (".", "..") for repo in repos):
        parser.error("--repo 应为 owner/repo")
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with output_lock(output), closing(sqlite3.connect(str(output) + ".trees.sqlite")) as cache:
        cache.execute("CREATE TABLE IF NOT EXISTS trees (sha TEXT PRIMARY KEY, entries TEXT NOT NULL)")
        rows = {}
        if output.exists():
            with output.open(encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        row = json.loads(line)
                        rows[row["id"]] = row
        try:
            for repo in dict.fromkeys(repos):
                try:
                    harvest_repo(repo, rows, args.max_files, args.max_bytes, cache)
                except (HTTPError, URLError, HTTPException, TimeoutError, ValueError) as exc:
                    print(f"[github] {repo}: {exc}", file=sys.stderr)
                    failed = True
        finally:
            save(output, rows)
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RateLimitError, OSError, ValueError) as exc:
        sys.exit(f"[github] {exc}")
