#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过已登录的 Chrome(CDP 9222) 调用牛客站内搜索 API 抓取面经帖子正文。
输出: data/tmp/nowcoder/posts.jsonl  (每行 {id,title,url,text,query,stats})
用法（项目根目录）:
  python crawler/scripts/nowcoder_harvest.py
  python crawler/scripts/nowcoder_harvest.py --config crawler/config/nowcoder-ai-infra.json \
      --output crawler/data/tmp/nowcoder-ai-infra/posts.jsonl --existing-browser
配置：queries 为搜索词，pages/page_size 为分页，include_patterns 中每条正则均需命中正文或标题。
"""
import json
import argparse
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta, date as calendar_date
from pathlib import Path
from websocket import create_connection
from browser_startup import ensure_browser, ready

CDP = "http://127.0.0.1:9222"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "tmp" / "nowcoder" / "posts.jsonl"

DEFAULT_CONFIG = HERE.parent / "config" / "nowcoder-default.json"
PAGE_SIZE = 20


def connect(existing_browser=False):
    if existing_browser:
        if not ready():
            raise RuntimeError("未发现已启动的调试浏览器；本次不会自动启动浏览器。")
    else:
        ensure_browser()
    targets = json.load(urllib.request.urlopen(CDP + "/json", timeout=10))
    pages = [t for t in targets if t.get("type") == "page"]
    page = next((t for t in pages if "www.nowcoder.com/" in t.get("url", "")), None)
    if page is None:
        request = urllib.request.Request(CDP + "/json/new?https://www.nowcoder.com", method="PUT")
        page = json.load(urllib.request.urlopen(request, timeout=10))
    return create_connection(page["webSocketDebuggerUrl"], timeout=40)


def make_rpc(ws):
    ctr = [0]

    def send(method, params=None):
        ctr[0] += 1
        ws.send(json.dumps({"id": ctr[0], "method": method, "params": params or {}}))
        return ctr[0]

    def wait(mid, to=40):
        end = time.time() + to
        while time.time() < end:
            r = json.loads(ws.recv())
            if r.get("id") == mid:
                return r
        return None

    return send, wait


def fetch_search(send, wait, query, page):
    body = {"query": query, "tab": "post", "page": page, "pageSize": PAGE_SIZE}
    js = (
        "(async () => {"
        "  const r = await fetch('https://gw-c.nowcoder.com/api/sparta/pc/search',"
        "    {method:'POST',credentials:'include',"
        "     headers:{'Content-Type':'application/json'},"
        "     body:JSON.stringify(" + json.dumps(body, ensure_ascii=False) + ")});"
        "  return await r.text();"
        "})()"
    )
    mid = send("Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": True})
    r = wait(mid, 45)
    if not r or "result" not in r:
        return None
    val = r["result"]["result"].get("value")
    try:
        return json.loads(val)
    except Exception:
        return None


def strip_html(html):
    if not html:
        return ""
    html = re.sub(r"(?is)<script.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?</style>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p>", "\n", html)
    html = re.sub(r"(?is)<li>", "\n- ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#x27;|&#39;", "'", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_time(obj):
    """递归在 nowcoder 搜索记录里找一个毫秒时间戳字段（ctime/createTime/publishTime 等）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and ("time" in k.lower()) and v > 1e12:
                return v
            if isinstance(v, (dict, list)):
                r = _find_time(v)
                if r:
                    return r
    elif isinstance(obj, list):
        for it in obj:
            r = _find_time(it)
            if r:
                return r
    return None


def extract_post(rec, query):
    data = rec.get("data") or {}
    md = data.get("momentData")
    ie = data.get("contentData") or data.get("interviewExp")
    cid = data.get("contentId")
    if md:
        title = md.get("title") or ""
        content = strip_html(md.get("content") or "")
        url = f"https://www.nowcoder.com/feed/main/detail/{md.get('uuid') or md.get('id')}"
    elif ie:
        title = ie.get("title") or ""
        content = strip_html(ie.get("content") or "")
        url = f"https://www.nowcoder.com/discuss/{ie.get('id') or cid}"
    else:
        return None
    fd = data.get("frequencyData") or {}
    # 仅使用帖子本身的创建时间，不能取编辑时间或作者信息中的时间。
    post_data = md or ie or {}
    field = next((key for key in ("createdAt", "createTime", "publishTime")
                  if isinstance(post_data.get(key), (int, float)) and post_data[key] > 0), None)
    ts = post_data[field] if field else None
    date = datetime.fromtimestamp(ts / (1000 if ts > 1e12 else 1),
                                  timezone(timedelta(hours=8))).strftime("%Y-%m-%d") if ts else ""
    return {
        "id": str(cid),
        "title": title.strip(),
        "url": url,
        "text": content,
        "query": query,
        "date": date,
        "date_field": field,
        "text_kind": "search_excerpt",
        "stats": {
            "like": fd.get("likeCnt"), "comment": fd.get("totalCommentCnt"),
            "view": fd.get("viewCnt"),
        },
    }


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    queries = config.get("queries")
    if not isinstance(queries, list) or not queries or any(not isinstance(q, str) or not q.strip() for q in queries):
        raise ValueError("queries 必须是非空字符串列表")
    config["queries"] = list(dict.fromkeys(q.strip() for q in queries))
    for key, default, maximum in (("pages", 3, 100), ("page_size", 20, 100)):
        value = config.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{key} 必须是 1–{maximum} 的整数")
        config[key] = value
    patterns = config.get("include_patterns", [])
    if not isinstance(patterns, list) or any(not isinstance(p, str) or not p for p in patterns):
        raise ValueError("include_patterns 必须是正则表达式字符串列表")
    config["patterns"] = [re.compile(p, re.I) for p in patterns]
    for key in ("date_from", "date_to"):
        if config.get(key):
            calendar_date.fromisoformat(config[key])
    if config.get("date_from") and config.get("date_to") and config["date_from"] > config["date_to"]:
        raise ValueError("date_from 不能晚于 date_to")
    return config


def in_date_range(post, config):
    if not config.get("date_from") and not config.get("date_to"):
        return True
    value = post.get("date")
    return bool(value and (not config.get("date_from") or value >= config["date_from"])
                and (not config.get("date_to") or value <= config["date_to"]))


def matches_config(post, config):
    text = post.get("text") or ""
    content = (post.get("title") or "") + "\n" + text
    return (len(text) >= 60 and in_date_range(post, config)
            and all(pattern.search(content) for pattern in config["patterns"]))


def main():
    global PAGE_SIZE
    parser = argparse.ArgumentParser(description="牛客面经采集：JSON 配置关键词、页数和内容过滤")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--existing-browser", action="store_true", help="只复用现有浏览器，不自动启动")
    args = parser.parse_args()
    config = load_config(args.config)
    output = args.output
    PAGE_SIZE = config["page_size"]
    print(f"CONFIG {args.config}: {len(config['queries'])} queries, {config['pages']} pages each", flush=True)
    ws = connect(args.existing_browser)
    send, wait = make_rpc(ws)
    send("Runtime.enable")
    send("Page.enable")
    # 先落到 nowcoder 域，确保后续 fetch 同源、携带 cookie（否则跨域 no-resp）
    nid = send("Page.navigate", {"url": "https://www.nowcoder.com"})
    wait(nid, 15)
    time.sleep(2.5)
    seen = {}
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                previous = json.loads(line)
                if matches_config(previous, config):
                    seen[previous["id"]] = previous
    initial_count = len(seen)
    successful_pages = 0
    login_deadline = time.monotonic() + 300
    for q in config["queries"]:
        for pg in range(1, config["pages"] + 1):
            j = fetch_search(send, wait, q, pg)
            while (not j or not j.get("success")) and successful_pages == 0 and time.monotonic() < login_deadline:
                print("[login] 搜索暂不可用，请立即在专用浏览器登录牛客/完成验证；每 5 秒重试，最多等 5 分钟。", file=sys.stderr, flush=True)
                time.sleep(5)
                j = fetch_search(send, wait, q, pg)
            if not j or not j.get("success"):
                print(f"[skip] {q} p{pg}: {j.get('msg') if j else 'no-resp'}", file=sys.stderr)
                continue
            successful_pages += 1
            recs = (j.get("data") or {}).get("records") or []
            got = 0
            for rec in recs:
                p = extract_post(rec, q)
                if not p or not matches_config(p, config) or p["id"] in seen:
                    continue
                seen[p["id"]] = p
                got += 1
            print(f"[ok] {q} p{pg}: +{got} (total {len(seen)})", file=sys.stderr)
            time.sleep(0.6)
    ws.close()
    if not successful_pages:
        raise SystemExit("牛客搜索未成功，原采集文件保持不变。")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jsonl.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        for p in seen.values():
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    temporary.replace(output)
    print(f"NEW {len(seen) - initial_count} posts")
    print(f"SAVED {len(seen)} posts -> {output}")


if __name__ == "__main__":
    main()
