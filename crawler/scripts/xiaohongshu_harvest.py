#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书面经采集器 v5（修复：验证页 JS 阻塞导致 eval 超时误判 + 0 卡片保护 + 重试上限）。

依赖：websocket-client（venv 内）
写入：data/tmp/xiaohongshu/posts.jsonl（append/resume 模式）
进度：data/tmp/xiaohongshu/progress.json（实时可读，绕开 stderr 缓冲）
状态机：RUNNING / WAIT_VERIFY（验证等待中）/ NEED_VERIFY（超时未解，需人工）/ DONE
"""
import json
import random
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from websocket import create_connection

CDP = "http://127.0.0.1:9222"
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "tmp" / "xiaohongshu" / "posts.jsonl"
PROG = BASE / "data" / "tmp" / "xiaohongshu" / "progress.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

QUERIES = [
    "AI Agent 面经",
    "大模型 Agent 面试",
    "Agent 开发 面试题",
    "RAG 面经",
    "LLM 算法工程师 面经",
    "智能体 面试 八股",
    "大模型 校招 面经",
    "Agent 实习 面经",
]
MAX_NOTES_PER_QUERY = 20
NAV_GAP = (5.0, 9.0)          # 每篇详情页之间的访问间隔
VERIFY_WAIT = 300             # 验证最长等待秒数
VERIFY_POLL = 15              # 验证检测间隔
MAX_RETRY_PER_QUERY = 3       # 单 query 重试上限，超过则跳过


def connect():
    targets = json.load(urllib.request.urlopen(CDP + "/json", timeout=10))
    xs = [t for t in targets if t.get("type") == "page" and "xiaohongshu" in (t.get("url") or "")]
    page = xs[0] if xs else next(t for t in targets if t.get("type") == "page")
    return create_connection(page["webSocketDebuggerUrl"], timeout=30)


def send(ws, method, params=None, ctr=[0]):
    ctr[0] += 1
    ws.send(json.dumps({"id": ctr[0], "method": method, "params": params or {}}))
    return ctr[0]


def wait(ws, mid, to=20):
    end = time.time() + to
    while time.time() < end:
        try:
            r = json.loads(ws.recv())
        except Exception:
            continue
        if r.get("id") == mid:
            return r
    return None


def eval_js(ws, expr, await_p=False, to=20):
    mid = send(ws, "Runtime.evaluate",
               {"expression": expr, "returnByValue": True, "awaitPromise": await_p})
    r = wait(ws, mid, to)
    if not r or "result" not in r:
        return None
    v = r["result"]["result"].get("value")
    return json.loads(v) if isinstance(v, str) else v


def navigate(ws, url):
    send(ws, "Page.enable")
    nid = send(ws, "Page.navigate", {"url": url})
    wait(ws, nid, 15)
    time.sleep(1.0)


def wait_for_selector(ws, sel, max_t=12):
    end = time.time() + max_t
    while time.time() < end:
        r = eval_js(ws, "!!document.querySelector(%s)" % json.dumps(sel), to=6)
        if r is True:
            return True
        time.sleep(0.8)
    return False


def detect_block(ws):
    """精准风控识别。重要：evaluate 超时(None)视为验证页（JS 阻塞是验证页典型特征）。"""
    r = eval_js(ws, r'''(() => {
      const t = (document.body ? document.body.innerText : '');
      const strong = /安全验证|滑动验证|请拖动|拖动滑块|操作太频繁|人机验证|验证失败|异常请求|请完成安全验证|网络异常请|滑块验证/.test(t);
      const hasContent = !!document.querySelector('#detail-desc')
                        || !!document.querySelector('section.note-item')
                        || !!document.querySelector('.note-content');
      return JSON.stringify({strong: strong, hasContent: hasContent, snippet: t.slice(0, 120)});
    })()''', to=8)
    if r is None:
        return {"strong": True, "hasContent": False, "verify": True,
                "snippet": "(eval 超时：疑似验证页/JS 阻塞)"}
    r["verify"] = bool(r.get("strong")) and not bool(r.get("hasContent"))
    return r


def wait_verify_clear(ws, state, total):
    """撞验证后原地轮询，最长 VERIFY_WAIT 秒；用户在浏览器滑掉即继续。"""
    print("[等待验证解除] 最长 %ds，请在浏览器里把滑动验证滑掉…" % VERIFY_WAIT, file=sys.stderr)
    end = time.time() + VERIFY_WAIT
    while time.time() < end:
        time.sleep(VERIFY_POLL)
        state.update(status="WAIT_VERIFY", total=total, updated=time.strftime("%H:%M:%S"))
        write_progress(state)
        blk = detect_block(ws)
        if blk and not blk.get("verify"):
            print("[验证已解除] 继续采集", file=sys.stderr)
            state.update(status="RUNNING", total=total, updated=time.strftime("%H:%M:%S"))
            write_progress(state)
            return True
    return False


def load_seen():
    seen = set()
    if OUT.exists():
        for l in open(OUT, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            try:
                d = json.loads(l)
                seen.add(d.get("id"))
            except Exception:
                pass
    return seen


def collect_cards(ws, query, max_cards):
    url = "https://www.xiaohongshu.com/search_result?keyword=" + urllib.parse.quote(query) + "&source=web_search_result_notes"
    navigate(ws, url)
    blk = detect_block(ws)
    if blk and blk.get("verify"):
        print("[风控] 搜索页疑似验证/频繁: %s" % blk.get("snippet"), file=sys.stderr)
        return "BLOCK"
    ok = wait_for_selector(ws, "section.note-item", max_t=12)
    if not ok:
        blk = detect_block(ws)
        if blk and blk.get("verify"):
            return "BLOCK"
    for _ in range(5):
        eval_js(ws, "window.scrollTo(0, document.body.scrollHeight);", to=6)
        time.sleep(random.uniform(0.7, 1.4))
    js = r'''(() => {
      const out = [];
      const seen = new Set();
      document.querySelectorAll('section.note-item').forEach(sec => {
        const a = sec.querySelector('a.cover') || sec.querySelector('a.title');
        const href = a ? a.getAttribute('href') : '';
        const m = href.match(/\/search_result\/([0-9a-zA-Z]+)\?xsec_token=([^&]+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return;
        seen.add(id);
        const token = decodeURIComponent(m[2]);
        const tEl = sec.querySelector('a.title span') || sec.querySelector('.title');
        const title = tEl ? tEl.innerText.trim() : '';
        out.push({id: id, token: token, title: title});
      });
      return JSON.stringify(out);
    })()'''
    cards = eval_js(ws, js) or []
    if not cards:
        # 0 卡片：搜索页未渲染（很可能在验证/风控中），按 BLOCK 处理
        return "BLOCK"
    return cards[:max_cards]


def scrape_note(ws, note_id, token):
    url = "https://www.xiaohongshu.com/explore/%s?xsec_token=%s&xsec_source=pc_search" % (
        note_id, urllib.parse.quote(token, safe="="))
    navigate(ws, url)
    blk = detect_block(ws)
    if blk and blk.get("verify"):
        return "BLOCK"
    ok = False
    for _ in range(12):
        time.sleep(1.0)
        st = eval_js(ws, r'''(() => {
          const t = document.body ? document.body.innerText : '';
          const desc = (document.querySelector('#detail-desc') && document.querySelector('#detail-desc').innerText)
                    || (document.querySelector('.note-content') && document.querySelector('.note-content').innerText) || '';
          const has404 = /页面不见了|你访问的页面|404/.test(t) && t.length < 1000;
          return JSON.stringify({has404: has404, descLen: (desc||'').length});
        })()''', to=6)
        if st and not st["has404"] and st["descLen"] > 100:
            ok = True
            break
    if not ok:
        return None
    eval_js(ws, r'''(() => {
      const btns = [...document.querySelectorAll('span,button,div')].filter(e => /^(展开|查看全文|全文)$/.test((e.textContent||'').trim()));
      if (btns.length) btns[0].click();
      return true;
    })()''', to=6)
    time.sleep(1.0)
    data = eval_js(ws, r'''(() => {
      const titleEl = document.querySelector('#detail-title') || document.querySelector('h1');
      const title = titleEl ? titleEl.innerText.trim() : '';
      const descEl = document.querySelector('#detail-desc') || document.querySelector('.note-content');
      let text = descEl ? descEl.innerText : '';
      text = text.replace(/^(展开|查看全文|全文)\s*/, '');
      const dateEl = document.querySelector('#detail-date') || document.querySelector('.date');
      const date = dateEl ? dateEl.innerText.trim() : '';
      return JSON.stringify({title: title, text: text.slice(0, 60000), date: date});
    })()''', to=8)
    if not data or not data.get("text"):
        return None
    return {"id": note_id, "title": (data.get("title") or "").strip(),
            "url": url, "text": data["text"].strip(), "date": data.get("date", "")}


def write_progress(state):
    PROG.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def main():
    ws = connect()
    send(ws, "Runtime.enable")
    seen = load_seen()
    total = len(seen)
    state = {"status": "RUNNING", "query_index": 0, "query": "", "total": total, "updated": time.strftime("%H:%M:%S")}
    write_progress(state)
    mode = "resume" if total else "fresh"
    f = open(OUT, "a", encoding="utf-8")
    print("[start] %s, 已有 %d 篇" % (mode, total), file=sys.stderr)

    qi = 0
    while qi < len(QUERIES):
        q = QUERIES[qi]
        retry = 0
        while True:  # 内层：当前 query 重试，直到无 BLOCK / 达上限 / 放弃
            retry += 1
            cards = collect_cards(ws, q, MAX_NOTES_PER_QUERY)
            if cards == "BLOCK":
                if retry > MAX_RETRY_PER_QUERY:
                    print("[skip] %s 重试 %d 次仍异常，跳过" % (q, retry - 1), file=sys.stderr)
                    break
                if not wait_verify_clear(ws, state, total):
                    state.update(status="NEED_VERIFY", query_index=qi, query=q, total=total,
                                 msg="验证等待超时（%ds），请在浏览器解开后重跑本脚本（resume 自动续传）" % VERIFY_WAIT,
                                 updated=time.strftime("%H:%M:%S"))
                    write_progress(state)
                    f.close()
                    print("[stop] NEED_VERIFY timeout @ %s" % q, file=sys.stderr)
                    return
                continue  # 重试当前 query 的 collect
            got = 0
            progressed = True
            for c in cards:
                if c["id"] in seen:
                    continue
                d = scrape_note(ws, c["id"], c["token"])
                if d == "BLOCK":
                    if retry > MAX_RETRY_PER_QUERY:
                        progressed = False
                        break
                    if not wait_verify_clear(ws, state, total):
                        state.update(status="NEED_VERIFY", query_index=qi, query=q, total=total,
                                     msg="详情页验证等待超时（%ds），请浏览器解开后重跑（resume 续传）" % VERIFY_WAIT,
                                     updated=time.strftime("%H:%M:%S"))
                        write_progress(state)
                        f.close()
                        print("[stop] NEED_VERIFY timeout @ note %s" % c["id"], file=sys.stderr)
                        return
                    progressed = False
                    break  # 跳出 for，回到内层 while 重 collect 当前 query
                if not d or len(d["text"]) < 60:
                    continue
                if not d["title"] and c["title"]:
                    d["title"] = c["title"]
                d["query"] = q
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                f.flush()
                seen.add(c["id"])
                got += 1
                total += 1
                state.update(status="RUNNING", query_index=qi, query=q, total=total, updated=time.strftime("%H:%M:%S"))
                write_progress(state)
                time.sleep(random.uniform(*NAV_GAP))
            if progressed:
                print(f"[ok] {q}: 入库 +{got} (累计 {total})", file=sys.stderr)
                break
            # else 内层 while 重新 collect 当前 query
        qi += 1

    state.update(status="DONE", total=total, updated=time.strftime("%H:%M:%S"))
    write_progress(state)
    f.close()
    print(f"DONE total={total}", file=sys.stderr)


if __name__ == "__main__":
    main()
