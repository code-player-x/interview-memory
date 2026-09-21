#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过已登录的 Chrome(CDP 9222) 调用牛客站内搜索 API 抓取面经帖子正文。
输出: data/tmp/nowcoder/posts.jsonl  (每行 {id,title,url,text,query,stats})
用法: python nowcoder_harvest.py
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from websocket import create_connection

CDP = "http://127.0.0.1:9222"
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "tmp" / "nowcoder" / "posts.jsonl"

QUERIES = [
    "AI Agent 面经",
    "大模型 Agent 面经",
    "LLM 应用开发 面经",
    "大模型算法工程师 面经",
    "RAG 面经",
    "Agent 开发 面试",
    "Go 大模型 后端 面经",
    "AI 应用 后端 面经",
]
PAGES = 3          # 每个 query 抓前 N 页
PAGE_SIZE = 20


def connect():
    targets = json.load(urllib.request.urlopen(CDP + "/json"))
    page = next(t for t in targets if t.get("type") == "page")
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
    ie = data.get("interviewExp")
    cid = data.get("contentId")
    if md:
        title = md.get("title") or ""
        content = strip_html(md.get("content") or "")
        url = f"https://www.nowcoder.com/feed/main/detail/{md.get('id')}"
    elif ie:
        title = ie.get("title") or ""
        content = strip_html(ie.get("content") or "")
        url = f"https://www.nowcoder.com/discuss/{ie.get('id') or cid}"
    else:
        return None
    fd = data.get("frequencyData") or {}
    # 发布时间（用于近一月过滤）
    ts = _find_time(data)
    date = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
    return {
        "id": str(cid),
        "title": title.strip(),
        "url": url,
        "text": content,
        "query": query,
        "date": date,
        "stats": {
            "like": fd.get("likeCnt"), "comment": fd.get("totalCommentCnt"),
            "view": fd.get("viewCnt"),
        },
    }


def main():
    ws = connect()
    send, wait = make_rpc(ws)
    send("Runtime.enable")
    send("Page.enable")
    # 先落到 nowcoder 域，确保后续 fetch 同源、携带 cookie（否则跨域 no-resp）
    nid = send("Page.navigate", {"url": "https://www.nowcoder.com"})
    wait(nid, 15)
    time.sleep(2.5)
    seen = {}
    for q in QUERIES:
        for pg in range(1, PAGES + 1):
            j = fetch_search(send, wait, q, pg)
            if not j or not j.get("success"):
                print(f"[skip] {q} p{pg}: {j.get('msg') if j else 'no-resp'}", file=sys.stderr)
                continue
            recs = (j.get("data") or {}).get("records") or []
            got = 0
            for rec in recs:
                p = extract_post(rec, q)
                if not p or not p["text"]:
                    continue
                if p["id"] in seen:
                    continue
                # 只保留有实质内容的
                if len(p["text"]) < 60:
                    continue
                seen[p["id"]] = p
                got += 1
            print(f"[ok] {q} p{pg}: +{got} (total {len(seen)})", file=sys.stderr)
            time.sleep(0.6)
    ws.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for p in seen.values():
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"SAVED {len(seen)} posts -> {OUT}")


if __name__ == "__main__":
    main()
