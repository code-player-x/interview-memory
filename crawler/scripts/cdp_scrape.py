#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过本地 CDP(9222) 连接已登录的 Chrome，抓取指定页面正文与链接。
用法:
  python cdp_scrape.py "<url>" [wait_seconds]
依赖: websocket-client
"""
import json
import sys
import time
import urllib.request
from websocket import create_connection

CDP = "http://127.0.0.1:9222"


def http_get(path):
    with urllib.request.urlopen(CDP + path, timeout=10) as r:
        return r.read().decode("utf-8")


def open_tab(url):
    # 新建标签页并打开目标 URL
    raw = http_get("/json/new?" + urllib.parse.quote(url, safe=":"))
    return json.loads(raw)


def main():
    import urllib.parse
    url = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    # 取第一个 page target 的 webSocketDebuggerUrl
    targets = json.loads(http_get("/json"))
    page = next((t for t in targets if t.get("type") == "page"), None)
    if not page:
        print("NO_PAGE", file=sys.stderr)
        sys.exit(1)
    ws_url = page["webSocketDebuggerUrl"]
    ws = create_connection(ws_url, timeout=30)
    _id = [0]

    def send(method, params=None):
        _id[0] += 1
        msg = {"id": _id[0], "method": method, "params": params or {}}
        ws.send(json.dumps(msg))
        return _id[0]

    def wait_resp(msg_id, timeout=25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = json.loads(ws.recv())
            except Exception:
                continue
            if r.get("id") == msg_id:
                return r
        return None

    send("Page.enable")
    send("Runtime.enable")
    nav_id = send("Page.navigate", {"url": url})
    wait_resp(nav_id)
    time.sleep(wait)

    # 懒加载页面：滚动到底触发加载
    for _ in range(6):
        sid = send("Runtime.evaluate", {
            "expression": "window.scrollTo(0, document.body.scrollHeight);",
            "returnByValue": True,
        })
        wait_resp(sid, timeout=8)
        time.sleep(1.2)

    # 取可见正文 + 所有链接
    expr = (
        "(() => {"
        "  const links = [...document.querySelectorAll('a')].map(a => ({"
        "    text: (a.innerText||'').trim().slice(0,120),"
        "    href: a.href"
        "  })).filter(l => l.href && l.text);"
        "  return JSON.stringify({"
        "    title: document.title,"
        "    url: location.href,"
        "    text: (document.body? document.body.innerText : '').slice(0, 60000),"
        "    links"
        "  });"
        "})()"
    )
    ev_id = send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    r = wait_resp(ev_id)
    ws.close()
    if not r or "result" not in r:
        print("EVAL_FAIL", file=sys.stderr)
        sys.exit(1)
    val = r["result"].get("result", {}).get("value")
    data = json.loads(val) if isinstance(val, str) else val
    out = {
        "title": data.get("title"),
        "url": data.get("url"),
        "text": data.get("text"),
        "links": data.get("links", [])[:200],
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
