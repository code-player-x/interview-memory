#!/usr/bin/env python3
"""补全牛客主帖全文，不读取评论/推荐，不启动或导航浏览器。

python crawler/scripts/nowcoder_details.py --input posts.jsonl --output details.jsonl
优先读取公开页面的 SSR 数据；--cdp-fallback 可用已有登录标签的 fetch 重试。
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlparse

from nowcoder_harvest import CDP, make_rpc, strip_html


def extract_detail(page, row):
    marker = re.search(r"window\.__INITIAL_STATE__\s*=\s*", page)
    if not marker:
        raise ValueError("页面缺少结构化主帖数据，可能需要登录或验证")
    state, _ = json.JSONDecoder().raw_decode(page[marker.end():])
    expected = {str(row.get("id", "")), urlparse(row["url"]).path.rstrip("/").split("/")[-1]}
    for payload in state.get("prefetchData", {}).values():
        if not isinstance(payload, dict):
            continue
        content = (payload.get("ssrCommonData") or {}).get("contentData")
        if not isinstance(content, dict):
            continue
        identities = {str(content.get(k, "")) for k in ("id", "uuid", "entityId")}
        if not (expected - {""}) & identities:
            continue
        body = content.get("richText") or content.get("content") or ""
        result = {
            "detail_title": content.get("title") or row.get("title", ""),
            "detail_text": strip_html(body),
            "detail_images": [i["src"] for i in content.get("imgMoment") or [] if i.get("src")],
        }
        timestamp = content.get("createdAt") or content.get("createTime")
        if isinstance(timestamp, (int, float)) and timestamp > 1e12:
            result["detail_date"] = datetime.fromtimestamp(timestamp / 1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
            result["detail_date_field"] = "createdAt" if content.get("createdAt") else "createTime"
        result["detail_status"] = "full_text" if result["detail_text"] else "image_only" if result["detail_images"] else "empty"
        return result
    raise ValueError("SSR 数据中没有与来源 ID/URL 对应的主帖")


def is_nowcoder_url(url):
    if not isinstance(url, str) or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc.lower() in {"www.nowcoder.com", "www.nowcoder.com:443"}


def require_nowcoder_url(url):
    if not is_nowcoder_url(url):
        raise ValueError("仅允许牛客 HTTPS 来源链接")


class NowcoderRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_nowcoder_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_fetch(url):
    require_nowcoder_url(url)
    request = urllib.request.Request(url)
    with urllib.request.build_opener(NowcoderRedirect()).open(request, timeout=20) as response:
        return response.read().decode("utf-8")


def cdp_fetch(url):
    """在已有牛客标签内 fetch；不启动浏览器、不导航、不创建标签。"""
    require_nowcoder_url(url)
    from websocket import create_connection
    with urllib.request.urlopen(CDP + "/json", timeout=3) as response:
        targets = json.load(response)
    target = next((t for t in targets if t.get("type") == "page" and is_nowcoder_url(t.get("url"))), None)
    if not target:
        raise RuntimeError("没有可复用的牛客标签")
    ws = create_connection(target["webSocketDebuggerUrl"], timeout=25)
    try:
        send, wait = make_rpc(ws)
        expression = ("fetch(" + json.dumps(url) +
                      ",{credentials:'same-origin',mode:'same-origin',redirect:'error'}).then(r=>r.text())")
        response = wait(send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True}), 25)
        value = ((response or {}).get("result", {}).get("result") or {}).get("value")
        if not isinstance(value, str):
            raise RuntimeError("已登录浏览器未返回页面正文")
        return value
    finally:
        ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cdp-fallback", action="store_true")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay 不能为负数")
    rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for index, source in enumerate(rows, 1):
            row = dict(source)
            try:
                require_nowcoder_url(row["url"])
                try:
                    detail = extract_detail(public_fetch(row["url"]), row)
                    detail["detail_method"] = "public_ssr"
                except Exception:
                    if not args.cdp_fallback:
                        raise
                    detail = extract_detail(cdp_fetch(row["url"]), row)
                    detail["detail_method"] = "logged_in_ssr"
                row.update(detail)
            except Exception as error:
                row.update(detail_status="failed", detail_error=f"{type(error).__name__}: {error}")
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{index}/{len(rows)}] {row['id']}: {row['detail_status']}", flush=True)
            if index < len(rows):
                time.sleep(args.delay)
    temporary.replace(args.output)
    print(f"SAVED {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
