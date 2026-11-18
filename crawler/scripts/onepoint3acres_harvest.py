"""从一亩三分地海外面经版的公开列表建立标题索引。"""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


if __package__:
    from .harvest_output import output_lock, save
else:
    from harvest_output import output_lock, save


SITE = "https://www.1point3acres.com"
BOARD = SITE + "/bbs/forum-145-{}.html"
AGENT = "InterviewMemoryBot"
OUTPUT = Path(__file__).resolve().parents[1] / "data/tmp/onepoint3acres/index.jsonl"
KEYWORDS = ("infra", "inference", "serving", "cuda", "vllm", "sglang", "gpu",
            "kv cache", "triton", "推理", "算子", "分布式训练")


def thread_id(href):
    url = urlsplit(urljoin(BOARD.format(1), href))
    if url.scheme not in ("http", "https") or url.netloc.lower() not in (
        "1point3acres.com", "www.1point3acres.com"
    ):
        return None
    match = re.fullmatch(r"/bbs/thread-([0-9]+)-[0-9]+-[0-9]+\.html", url.path)
    if match:
        return match[1]
    params = parse_qs(url.query)
    if url.path == "/bbs/forum.php" and params.get("mod") == ["viewthread"]:
        tid = params.get("tid", [""])[0]
        if re.fullmatch(r"[0-9]+", tid):
            return tid
    return None


class ThreadTitles(HTMLParser):
    def __init__(self):
        super().__init__()
        self.titles = {}
        self.list_table_depth = 0
        self.current = None
        self.label = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.list_table_depth or attrs.get("id") == "threadlisttableid":
                self.list_table_depth += 1
        elif tag == "a" and self.list_table_depth == 1:
            self.current = None
            if "xst" in (attrs.get("class") or "").split():
                self.current = thread_id(attrs.get("href") or "")
            self.label = []

    def handle_data(self, data):
        if self.current:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "table" and self.list_table_depth:
            self.list_table_depth -= 1
            self.current = None
        elif tag == "a" and self.current:
            title = " ".join("".join(self.label).split())
            if title and not title.isdecimal():
                self.titles.setdefault(self.current, title)
            self.current = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, *, robots=False):
    request = Request(url, headers={"User-Agent": AGENT})
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError(f"响应超过大小限制 {url}")
        if robots and (response.headers.get_content_type() == "text/html" or
                       data.lstrip().startswith(b"<")):
            raise ValueError("robots.txt 返回了 HTML")
        return data.decode(response.headers.get_content_charset() or "utf-8-sig")


def online_pages(count):
    from protego import Protego

    policy = Protego.parse(fetch(SITE + "/robots.txt", robots=True))
    delay = max(2, policy.crawl_delay(AGENT) or 0)
    for page in range(1, count + 1):
        url = BOARD.format(page)
        if not policy.can_fetch(url, AGENT):
            raise ValueError(f"robots.txt 禁止访问 {url}")
        time.sleep(delay)
        yield fetch(url)


def update_index(pages, keywords, output):
    found = {}
    for html in pages:
        parser = ThreadTitles()
        parser.feed(html)
        parser.close()
        if not parser.titles:
            raise ValueError("未识别到论坛列表中的帖子标题，可能是验证页或页面结构已变化")
        for tid, title in parser.titles.items():
            hits = [word for word in keywords if word.casefold() in title.casefold()]
            if hits:
                found[tid] = dict(id=tid, source="onepoint3acres", title=title,
                                  url=f"{SITE}/bbs/thread-{tid}-1-1.html", keywords=hits)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Lock only the merge so simultaneous imports can fetch pages independently.
    with output_lock(output):
        records = {}
        if output.exists():
            for line in output.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                records[row["id"]] = row
        before = len(records)
        records.update(found)
        save(output, records)
    print(f"匹配 {len(found)} 条，新增 {len(records) - before} 条，共 {len(records)} 条 -> {output}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--html", type=Path, action="append", help="读取本地保存的公开列表 HTML，可重复")
    group.add_argument("--pages", type=int, default=1, help="在线采集的列表页数，默认 1")
    ap.add_argument("--keyword", action="append", help="标题关键词，可重复；默认使用 AI Infra 词表")
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()
    if not 1 <= args.pages <= 50:
        ap.error("--pages 取值 1 到 50")
    words = [word.strip() for word in args.keyword or KEYWORDS]
    if not all(words):
        ap.error("关键词不能为空")
    try:
        pages = (path.read_text(encoding="utf-8-sig") for path in args.html) if args.html else online_pages(args.pages)
        update_index(pages, words, args.output)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        ap.exit(1, f"索引采集未完成：{exc}\n")


if __name__ == "__main__":
    main()
