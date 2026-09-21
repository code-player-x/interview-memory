#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录墙 / 反爬站点的通用 CDP 采集骨架。

所有源（小红书 / 掘金 / V2EX / 脉脉 …）共用同一套 Chrome DevTools Protocol 逻辑：
- 复用本机已登录 Chrome 的远程调试端口（默认 127.0.0.1:9222），全程只读 DOM、不存凭据。
- 内置「滑块验证自动等待」：验证页会阻塞 JS 上下文导致 Runtime.evaluate 超时，本模块把
  "eval 超时" 保守判为验证页，原地轮询等待用户在浏览器滑掉后自动续抓。
- 断点续传：posts.jsonl 以 append 模式写，restart 自动跳过已采。

只用 websocket-client（venv 内），无 chrome-remote-interface 依赖。
"""
import json
import time
import urllib.request
from pathlib import Path

try:
    from websocket import create_connection
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 websocket-client：在 venv 内 `pip install websocket-client`")

CDP = "http://127.0.0.1:9222"
BASE = Path(__file__).resolve().parent.parent

# 风控 / 验证特征词（命中且页面无正文 => 判定为验证页）
VERIFY_KEYWORDS = (
    "安全验证|滑动验证|请拖动|拖动滑块|操作太频繁|人机验证|验证失败|异常请求|"
    "请完成安全验证|网络异常请|滑块验证|请先登录|扫码登录|登录后查看|未登录"
)


def connect(domain=None):
    """连接到合适的 page 标签。优先 domain 匹配的已开标签，否则取第一个 page。"""
    targets = json.load(urllib.request.urlopen(CDP + "/json", timeout=10))
    pages = [t for t in targets if t.get("type") == "page"]
    if domain:
        xs = [t for t in pages if domain in (t.get("url") or "")]
        if xs:
            return create_connection(xs[0]["webSocketDebuggerUrl"], timeout=30)
    return create_connection(pages[0]["webSocketDebuggerUrl"], timeout=30)


class Browser:
    def __init__(self, domain=None):
        self.ws = connect(domain)
        self._ctr = 0
        self._send("Runtime.enable")
        self._send("Page.enable")

    # ---- 底层 ----
    def _send(self, method, params=None):
        self._ctr += 1
        self.ws.send(json.dumps({"id": self._ctr, "method": method, "params": params or {}}))
        return self._ctr

    def _wait(self, mid, to=20):
        end = time.time() + to
        while time.time() < end:
            try:
                r = json.loads(self.ws.recv())
            except Exception:
                continue
            if r.get("id") == mid:
                return r
        return None

    def eval_js(self, expr, await_p=False, to=20):
        mid = self._send("Runtime.evaluate",
                         {"expression": expr, "returnByValue": True, "awaitPromise": await_p})
        r = self._wait(mid, to)
        if not r or "result" not in r:
            return None
        v = r["result"]["result"].get("value")
        return json.loads(v) if isinstance(v, str) else v

    def navigate(self, url):
        nid = self._send("Page.navigate", {"url": url})
        self._wait(nid, 15)
        time.sleep(1.0)

    def wait_for_selector(self, sel, max_t=12):
        end = time.time() + max_t
        while time.time() < end:
            r = self.eval_js("!!document.querySelector(%s)" % json.dumps(sel), to=6)
            if r is True:
                return True
            time.sleep(0.8)
        return False

    def scroll_to_bottom(self, times=5, gap=(0.7, 1.4)):
        import random
        for _ in range(times):
            self.eval_js("window.scrollTo(0, document.body.scrollHeight);", to=6)
            time.sleep(random.uniform(*gap))

    # ---- 风控识别 ----
    def detect_block(self, content_selectors=("#detail-desc", "section.note-item", ".note-content")):
        """返回 dict{strong, hasContent, verify, snippet}。eval 超时(None) => 视为验证页。"""
        sel_js = "||".join("document.querySelector(%s)" % json.dumps(s) for s in content_selectors)
        expr = r'''(() => {
          const t = (document.body ? document.body.innerText : '');
          const strong = /%s/.test(t);
          const hasContent = %s;
          return JSON.stringify({strong: strong, hasContent: !!hasContent, snippet: t.slice(0, 120)});
        })()''' % (VERIFY_KEYWORDS, sel_js)
        r = self.eval_js(expr, to=8)
        if r is None:
            return {"strong": True, "hasContent": False, "verify": True,
                    "snippet": "(eval 超时：疑似验证页/JS 阻塞)"}
        r["verify"] = bool(r.get("strong")) and not bool(r.get("hasContent"))
        return r

    def wait_verify_clear(self, progress_cb, max_wait=300, poll=15):
        """撞验证后原地轮询，最长 max_wait 秒。progress_cb(status) 用于写进度文件。"""
        import sys
        print("[等待验证解除] 最长 %ds，请在浏览器里把验证滑掉…" % max_wait, file=sys.stderr)
        end = time.time() + max_wait
        while time.time() < end:
            time.sleep(poll)
            progress_cb(status="WAIT_VERIFY")
            if not self.detect_block().get("verify"):
                print("[验证已解除] 继续采集", file=sys.stderr)
                progress_cb(status="RUNNING")
                return True
        return False

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def load_seen(path):
    seen = set()
    if path.exists():
        for l in open(path, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            try:
                seen.add(json.loads(l).get("id"))
            except Exception:
                pass
    return seen


def write_progress(path, state):
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def run_source(adapter, queries, out_path, prog_path, domain=None,
               max_per_query=15, nav_gap=(4.0, 8.0), verify_wait=300, max_retry=3):
    """通用采集驱动：搜索 -> 收卡片 -> 逐篇详情 -> 落盘（append/resume）。

    adapter 需提供：
        search_url(query) -> str
        first_card_selector -> str          （用于 wait_for_selector 判断是否渲染）
        card_js -> str                       （返回 JSON 数组 [{id,title}]）
        note_url(id) -> str
        note_js -> str                       （返回 JSON {title,text,date}|null）
        content_selectors -> tuple          （用于 detect_block 判断有无正文）
    """
    import sys
    import random
    out_path = Path(out_path)
    prog_path = Path(prog_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    b = Browser(domain=domain)
    seen = load_seen(out_path)
    total = len(seen)
    state = {"status": "RUNNING", "query_index": 0, "query": "", "total": total,
             "updated": time.strftime("%H:%M:%S")}
    write_progress(prog_path, state)
    f = open(out_path, "a", encoding="utf-8")

    def set_status(status):
        state["status"] = status
        state["updated"] = time.strftime("%H:%M:%S")
        write_progress(prog_path, state)

    qi = 0
    while qi < len(queries):
        q = queries[qi]
        retry = 0
        while True:  # 内层：当前 query 重试，直到无验证/达上限/放弃
            retry += 1
            b.navigate(adapter.search_url(q))
            blk = b.detect_block(adapter.content_selectors)
            if blk.get("verify"):
                if retry > max_retry:
                    print("[skip] %s 重试%d次仍异常" % (q, retry - 1), file=sys.stderr)
                    break
                if not b.wait_verify_clear(set_status, verify_wait):
                    state.update(query_index=qi, query=q, total=total,
                                 msg="验证等待超时，请浏览器解开后重跑（resume 续传）",
                                 updated=time.strftime("%H:%M:%S"))
                    write_progress(prog_path, state)
                    f.close()
                    return
                continue
            b.wait_for_selector(adapter.first_card_selector, max_t=12)
            # 收卡片前滚动加载更多结果：很多站点首屏只渲染少量卡片，
            # 不滚动会导致只拿到最热门的几条（可能全是已采的），造成 +0。
            time.sleep(1.5)
            b.scroll_to_bottom(times=getattr(adapter, "search_scroll", 5), gap=(0.8, 1.5))
            time.sleep(1.0)
            cards = b.eval_js(adapter.card_js) or []
            if not cards:  # 0 卡片 => 很可能验证/风控，按 verify 处理
                if retry > max_retry:
                    print("[skip] %s 无卡片" % q, file=sys.stderr)
                    break
                if not b.wait_verify_clear(set_status, verify_wait):
                    state.update(query_index=qi, query=q, total=total,
                                 msg="无卡片且验证超时", updated=time.strftime("%H:%M:%S"))
                    write_progress(prog_path, state)
                    f.close()
                    return
                continue
            got = 0
            progressed = True
            for c in cards[:max_per_query]:
                if c["id"] in seen:
                    continue
                b.navigate(adapter.note_url(c["id"]))
                blk = b.detect_block(adapter.content_selectors)
                if blk.get("verify"):
                    if retry > max_retry:
                        # 重试用尽：跳过这一篇继续下一篇，避免因单页验证放弃整组
                        continue
                    if not b.wait_verify_clear(set_status, verify_wait):
                        state.update(query_index=qi, query=q, total=total,
                                     msg="详情页验证超时", updated=time.strftime("%H:%M:%S"))
                        write_progress(prog_path, state)
                        f.close()
                        return
                    progressed = False
                    break
                data = b.eval_js(adapter.note_js, to=12)
                if not data or not data.get("text") or len(data["text"]) < 60:
                    continue
                if not data.get("title") and c.get("title"):
                    data["title"] = c["title"]
                data["id"] = c["id"]
                data["url"] = adapter.note_url(c["id"])
                data["query"] = q
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                f.flush()
                seen.add(c["id"])
                got += 1
                total += 1
                state["total"] = total
                state["query"] = q
                state["query_index"] = qi
                state["updated"] = time.strftime("%H:%M:%S")
                write_progress(prog_path, state)
                time.sleep(random.uniform(*nav_gap))
            if progressed:
                print("[ok] %s +%d (累计 %d)" % (q, got, total), file=sys.stderr)
                break
        qi += 1
    state["status"] = "DONE"
    state["total"] = total
    state["updated"] = time.strftime("%H:%M:%S")
    write_progress(prog_path, state)
    f.close()
    print("DONE total=%d" % total, file=sys.stderr)
