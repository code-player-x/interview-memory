#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号(面经哥等)面经采集器 — 纯 HTTP，免登录、免 CDP。

与小红书/脉脉不同，微信公众号文章是公开页面，拿到链接即可直接 HTTP 抓取正文，
无需复用已登录 Chrome。难点在"如何枚举出某公众号的所有文章"——微信无公开列表
接口，因此本脚本采用 BFS 滚雪球：抓取正文后提取文末「推荐阅读」卡片里的同号文章
链接，逐层扩展。

用法：
    python scripts/weixin_harvest.py --seeds "https://mp.weixin.qq.com/s/xxxx"
    python scripts/weixin_harvest.py --seeds-file data/tmp/weixin/seeds.txt --depth 2
    python scripts/weixin_harvest.py --seeds "URL1" "URL2" --depth 1 --max 80

产出：
    data/tmp/weixin/posts.jsonl   (append, 按 url 去重, 断点续传)
    data/tmp/weixin/progress.json (状态机 RUNNING/DONE)

落盘 post 结构：
    {"url","title","account","publish_ts","content"(纯文本正文),
     "recommend_links"[...],"depth","crawled_at"}
"""
import sys, os, re, json, time, argparse, urllib.request, hashlib
from pathlib import Path
from html import unescape

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "data" / "tmp" / "weixin"
TMP.mkdir(parents=True, exist_ok=True)
POSTS = TMP / "posts.jsonl"
PROGRESS = TMP / "progress.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 微信文章正文锚点；结束标记优先选 </article> 或 ct_mpda(底部条) 或 js_sg_bar
_CONTENT_RE = re.compile(
    r'id="js_content"[^>]*>(.*?)(?:</article>|class="ct_mpda|id="js_sg_bar"|<!--)',
    re.S)
_CONTENT_RE2 = re.compile(r'id="js_content"[^>]*>(.*)</div>\s*</div>\s*</div>', re.S)
# 同时兼容两种微信文章 URL 形态：
#   1) 永久链接  https://mp.weixin.qq.com/s/<ID>
#   2) 搜狗中转  https://mp.weixin.qq.com/s?src=11&timestamp=...&signature=...&new=1
# （中转链接带新鲜 signature 时，纯 HTTP 可直接抓到正文；signature 过期则失效）
_LINK_RE = re.compile(
    r'https://mp\.weixin\.qq\.com/s(?:/[A-Za-z0-9_-]{8,}|\?src=11[^\s"\'>]*)')


def content_fp(text):
    """正文指纹：同一篇文章无论用哪种 URL 形态，正文一致 → 指纹一致，用于去重。"""
    if not text:
        return "empty"
    return hashlib.md5(re.sub(r'\s+', '', text).encode('utf-8')).hexdigest()[:16]


def fetch(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def parse(html, url):
    # 标题：优先 og:title（干净），否则 <title>
    title = ""
    og = re.search(r'<meta\s+property="og:title"\s+content="(.*?)"', html, re.S)
    if og:
        title = unescape(og.group(1).strip())
    if not title:
        tm = re.search(r'<title>(.*?)</title>', html, re.S)
        title = unescape(tm.group(1).strip()) if tm else ""

    acc = re.search(r'id="js_name"[^>]*>(.*?)</a>', html, re.S)
    if not acc:
        acc = re.search(r'class="account_nickname[^"]*"[^>]*>(.*?)<', html, re.S)
    account = unescape(acc.group(1).strip()) if acc else ""

    pt = re.search(r'var\s+publish_time\s*=\s*["\']?(\d+)', html)
    if not pt:
        pt = re.search(r'publish_timestamp\s*[:=]\s*["\']?(\d+)', html)
    publish_ts = int(pt.group(1)) if pt else None

    cm = _CONTENT_RE.search(html)
    if not cm:
        cm = _CONTENT_RE2.search(html)
    content_html = cm.group(1) if cm else ""
    text = re.sub(r'<script[\s\S]*?</script>', '', content_html)
    text = re.sub(r'<style[\s\S]*?</style>', '', text)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text).strip()

    # 文末推荐链接（同号其他文章），排除当前/专辑
    seen = set()
    recs = []
    for l in _LINK_RE.findall(html):
        if l == url or "appmsgalbum" in l:
            continue
        if l in seen:
            continue
        seen.add(l)
        recs.append(l)
        if len(recs) >= 6:
            break

    return {
        "title": title, "account": account, "publish_ts": publish_ts,
        "content": text, "recommend_links": recs, "url": url,
    }


def post_key(post):
    """稳定去重键：优先 公众号+标题（跨提取方式一致）；标题缺失时回退正文指纹。"""
    acc = (post.get("account") or "").strip()
    title = (post.get("title") or "").strip()
    if acc or title:
        return ("T", acc, title)
    return ("F", content_fp(post.get("content", "")))


def load_seen():
    """返回 (url 集合, 去重键集合) 用于去重。"""
    urls, keys = set(), set()
    if POSTS.exists():
        with open(POSTS, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                p = json.loads(l)
                urls.add(p.get("url", ""))
                keys.add(post_key(p))
    return urls, keys


def append_post(post):
    post["crawled_at"] = time.strftime("%Y-%m-%d %H:%M")
    with open(POSTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(post, ensure_ascii=False) + "\n")


def set_progress(status, crawled, seen_n):
    PROGRESS.write_text(json.dumps(
        {"status": status, "crawled": crawled, "seen": seen_n,
         "updated": time.strftime("%H:%M")}, ensure_ascii=False),
        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="*", default=[])
    ap.add_argument("--seeds-file", default=str(TMP / "seeds.txt"))
    ap.add_argument("--depth", type=int, default=1, help="BFS 层数(0=只抓种子)")
    ap.add_argument("--max", type=int, default=50, help="最多落盘篇数")
    args = ap.parse_args()

    seeds = list(args.seeds)
    sf = Path(args.seeds_file)
    if not seeds and sf.exists():
        seeds = [l.strip() for l in open(sf, encoding="utf-8")
                 if l.strip().startswith("http")]
    if not seeds:
        print("NO SEEDS provided"); sys.exit(1)

    visited_urls, seen_keys = load_seen()
    visited = visited_urls
    queue = [(s, 0) for s in seeds if s not in visited]
    crawled = 0
    set_progress("RUNNING", 0, len(visited))

    while queue and crawled < args.max:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        try:
            html = fetch(url)
        except Exception as e:
            print("ERR", url, repr(e)); continue
        post = parse(html, url)
        post["depth"] = depth
        # 去重：同一篇文章（无论真实链接还是中转链接）只落盘一次
        k = post_key(post)
        if k in seen_keys:
            print(f"[SKIP 重复] {post['account']} | {post['title'][:34]}")
            visited.add(url)
            continue
        append_post(post)
        seen_keys.add(k)
        visited.add(url)
        crawled += 1
        print(f"[{crawled}] {post['account']} | {post['title'][:34]} "
              f"| len={len(post['content'])} | recs={len(post['recommend_links'])}")
        if depth < args.depth:
            for r in post["recommend_links"]:
                if r not in visited:
                    queue.append((r, depth + 1))
        time.sleep(1.5)  # 礼貌限速，避免风控

    set_progress("DONE", crawled, len(visited))
    print("DONE crawled=", crawled, "seen=", len(visited))


if __name__ == "__main__":
    main()
