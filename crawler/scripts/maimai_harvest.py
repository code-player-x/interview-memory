#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脉脉面经采集器（CDP 复用已登录 Chrome；脉脉为强登录墙 + 风控源，需用户在浏览器登录）。

脉脉 web 端反爬严格、且多数内容需登录。本脚本与小红书同源思路：搜索 -> 收卡片 -> 进详情。
登录墙检测命中后会在原地等待用户在浏览器登录/滑验证；若超时则写 NEED_VERIFY，重跑即 resume 续传。
写入 data/tmp/maimai/posts.jsonl（append/resume）；进度 data/tmp/maimai/progress.json。
"""
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_helper import run_source, BASE

OUT = BASE / "data" / "tmp" / "maimai" / "posts.jsonl"
PROG = BASE / "data" / "tmp" / "maimai" / "progress.json"

QUERIES = [
    "AI Agent 面经",
    "大模型 面试",
    "算法 面试 经历",
    "AI 工程师 面经",
    "校招 面经",
    "跳槽 面经",
]


class MaimaiAdapter:
    domain = "maimai.cn"
    # 脉脉详情正文容器（命中说明已登录且渲染出内容）
    content_selectors = (".feed-content", ".content", ".topic-content", "h1")
    first_card_selector = "a[href*='/feed/'], a[href*='/web/feed'], .feed-item"
    card_js = r'''(() => {
      const out = []; const seen = new Set();
      document.querySelectorAll("a[href*='/feed/']").forEach(a => {
        const m = (a.getAttribute('href') || '').match(/\/feed\/([0-9a-zA-Z]+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return; seen.add(id);
        const title = (a.querySelector('.feed-title') || a).innerText.trim();
        if (title) out.push({id: id, title: title});
      });
      return JSON.stringify(out);
    })()'''
    note_js = r'''(() => {
      const titleEl = document.querySelector('.feed-title') || document.querySelector('h1');
      const title = titleEl ? titleEl.innerText.trim() : '';
      const el = document.querySelector('.feed-content') || document.querySelector('.content')
              || document.querySelector('.topic-content');
      const text = el ? el.innerText : document.body.innerText;
      return JSON.stringify({title: title, text: text.slice(0, 30000), date: ''});
    })()'''

    def search_url(self, q):
        return "https://maimai.cn/web/search?type=feed&query=" + urllib.parse.quote(q)

    def note_url(self, nid):
        return "https://maimai.cn/web/feed/" + nid


if __name__ == "__main__":
    # 脉脉未登录时没必要久等，验证等待缩短到 120s，超时即 NEED_VERIFY 提示用户登录
    run_source(MaimaiAdapter(), QUERIES, OUT, PROG, domain=MaimaiAdapter.domain,
               max_per_query=12, nav_gap=(5.0, 9.0), verify_wait=120)
