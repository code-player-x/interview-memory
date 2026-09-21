#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜狗微信搜索采集入口 — 用于"枚举某公众号(如面经哥)的全部面经文章"。

背景：微信公众号无公开列表接口；且实测面经哥不放置「推荐阅读」卡片、不建专辑，
导致 weixin_harvest.py 的 BFS 滚雪球失效（文末只有微信官方投诉指引链接）。
因此改用搜狗微信搜索(weixin.sogou.com)按关键词搜文章 -> 解析结果转链 ->
还原为永久的 mp.weixin.qq.com/s/ 真实链接 -> 交给 weixin_harvest.py 抓正文入库。

⚠️ 实测硬限制（2026-07-16）：搜狗对 link 跳转访问做了 antispider 风控。
无论纯 HTTP 还是 CDP 真实 Chrome(全新 profile)，打开 /link?url= 都会被 302 到
`weixin.sogou.com/antispider/` 验证页，真实文章链接无法自动还原。因此本脚本
的"搜索 + 输出标题/转链清单"可用，但"自动还原真实永久链接"在当前自动环境下
大概率失败。可靠的批量采集路径是：用户在「自己的常用浏览器」(搜狗不拦)打开
文章 -> 复制地址栏 `mp.weixin.qq.com/s/<ID>` 永久链接 -> 交给 weixin_harvest.py。

用法：
    # 仅搜+还原，产出真实链接列表(不抓正文)，便于先审查质量
    python scripts/sogou_weixin_search.py --keywords "面经哥 Agent" "面经哥 大模型 面试"

    # 搜完直接抓正文(抓到 posts.jsonl，再做后处理入库)
    python scripts/sogou_weixin_search.py --keywords "面经哥 Agent" --crawl

    # 只保留某账号的结果(按块文本子串匹配，最稳)
    python scripts/sogou_weixin_search.py --keywords "面经哥" --account-filter "面经哥" --crawl

产出：
    data/tmp/weixin/sogou_urls.txt  (真实 mp 链接, 跨次运行累加去重)
    (--crawl) data/tmp/weixin/posts.jsonl

风控提示：搜狗对频繁访问会出验证码，已加随机延时(2~4s/条)。若遇验证码需人工过
一次，或降低 --max-per / 拉长间隔后重试。链接 token 在同一次搜索会话内有效。
"""
import sys, re, json, time, argparse, urllib.request, urllib.parse, subprocess, random
import http.cookiejar
from pathlib import Path
from html import unescape

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "data" / "tmp" / "weixin"
TMP.mkdir(parents=True, exist_ok=True)
URLS_OUT = TMP / "sogou_urls.txt"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 搜狗对「跳转链接 /link?url=」单独做了反爬：必须带着搜索时设置的 SNUID
# cookie 才能通过，否则返回 antispider 验证页。因此全程复用同一 cookie jar。
_CJ = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_CJ))


def fetch(url, ref=None, timeout=25):
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if ref:
        headers["Referer"] = ref
    req = urllib.request.Request(url, headers=headers)
    with _OPENER.open(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def search_sogou(keyword, max_per=10):
    """返回 [{title, sogou_url, block_text}]，block_text 用于账号过滤。"""
    q = urllib.parse.quote(keyword)
    url = f"https://weixin.sogou.com/weixin?type=2&query={q}&page=1"
    try:
        html = fetch(url)
    except Exception as e:
        print("  ERR search fetch:", repr(e))
        return []
    if "请输入验证码" in html or "antispider" in html:
        print("  WARN 搜狗验证码拦截，请稍后重试/降低频率")
        return []
    blocks = re.split(r'<div class="txt-box">', html)[1:]
    items = []
    for b in blocks:
        lm = re.search(r'href="(/link\?url=[^"]+)"', b)
        if not lm:
            continue
        tm = (re.search(r'<a[^>]*uigs="article_title[^>]*>(.*?)</a>', b, re.S)
              or re.search(r'<h3><a[^>]*>(.*?)</a>', b, re.S))
        title = unescape(re.sub(r'<[^>]+>', '', tm.group(1))).strip() if tm else ""
        if not title:
            continue
        link = "https://weixin.sogou.com" + unescape(lm.group(1))
        link = link.replace(" ", "%20")  # 修正搜狗 HTML 属性里的字面空格
        block_text = unescape(re.sub(r'<[^>]+>', ' ', b))
        items.append({"title": title, "sogou_url": link, "block_text": block_text})
        if len(items) >= max_per:
            break
    return items


def _follow(url, ref):
    """请求 url 并返回最终地址(geturl)，用于解析搜狗中转页的 302 跳转。"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Referer": ref,
                          "Accept-Language": "zh-CN,zh;q=0.9"})
        with _OPENER.open(req, timeout=25) as r:
            return r.geturl()
    except Exception as e:
        print("  ERR follow:", repr(e))
        return url


def resolve_real_url(sogou_url, ref):
    """把搜狗转链还原为永久的 mp.weixin.qq.com/s/<文章ID> 真实链接。

    搜狗 link 页 JS 拼出的往往是中转统计页
    (mp.weixin.qq.com/s?src=11&timestamp=...)，需再跟随一次 302 重定向
    才能拿到真正的文章地址。
    """
    try:
        html = fetch(sogou_url, ref=ref)
    except Exception as e:
        print("  ERR resolve:", repr(e))
        return None
    # 模式1: JS 拼接 url += '...'（拼出的是中转页）
    parts = re.findall(r"""url\s*\+=\s*['"]([^'"]+)['"]""", html)
    if parts:
        mid = "".join(parts).replace("@", "")
        if "%" in mid:
            mid = urllib.parse.unquote(mid)
        if mid.startswith("http"):
            final = _follow(mid, ref)
            # 真实文章形如 /s/<ID>；中转页是 /s?src=... 或纯 /s
            if final and "/s/" in final and not final.rstrip("/").endswith("/s"):
                return final
            return final
    # 模式2: 直链命中
    m = re.findall(r'https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_\-]{8,}', html)
    if m:
        return m[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", nargs="*", default=[])
    ap.add_argument("--keywords-file", default=None)
    ap.add_argument("--max-per", type=int, default=10, help="每个关键词最多取几条结果")
    ap.add_argument("--account-filter", default=None,
                    help="只保留块文本含该子串的结果(如 '面经哥')")
    ap.add_argument("--crawl", action="store_true",
                    help="搜完后直接调 weixin_harvest.py 抓正文落盘")
    args = ap.parse_args()

    keywords = list(args.keywords)
    if args.keywords_file and Path(args.keywords_file).exists():
        keywords += [l.strip() for l in open(args.keywords_file, encoding="utf-8") if l.strip()]
    if not keywords:
        print("NO KEYWORDS provided"); sys.exit(1)

    collected = {}  # real_url -> title
    for kw in keywords:
        print(f"== 搜索: {kw} ==")
        items = search_sogou(kw, args.max_per)
        print(f"  搜到 {len(items)} 条结果")
        for it in items:
            if args.account_filter and args.account_filter not in it["block_text"]:
                continue
            ref = "https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote(kw)
            time.sleep(random.uniform(2, 4))  # 限速防搜狗风控
            real = resolve_real_url(it["sogou_url"], ref)
            if real:
                collected[real] = it["title"]
                print(f"  ✓ {it['title'][:32]} -> {real[:50]}")
            else:
                print(f"  ✗ 还原失败: {it['title'][:32]}")

    # 跨次运行累加去重
    existing = set()
    if URLS_OUT.exists():
        existing = set(l.strip() for l in open(URLS_OUT, encoding="utf-8") if l.strip())
    new_urls = [u for u in collected if u not in existing]
    with open(URLS_OUT, "a", encoding="utf-8") as f:
        for u in new_urls:
            f.write(u + "\n")
    print(f"\n新增真实链接 {len(new_urls)} 条；文件累计 "
          f"{len(existing) + len(new_urls)} 条 -> {URLS_OUT}")

    if args.crawl and new_urls:
        print("\n== 调用 weixin_harvest 抓正文 ==")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "weixin_harvest.py"),
             "--seeds-file", str(URLS_OUT), "--depth", "0"],
            check=False)
    elif args.crawl and not new_urls:
        print("\n无新增链接，跳过抓取(已有链接请直接调 weixin_harvest.py)")


if __name__ == "__main__":
    main()
