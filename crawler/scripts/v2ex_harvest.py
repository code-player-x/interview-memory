#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2EX 面经采集器（CDP 复用已登录 Chrome；沙箱直连 V2EX 超时，故走 Chrome 出口）。

V2EX 为开放论坛，无需登录。面经多分布在 /go/jobs、/go/career 与搜索结果。
写入 data/tmp/v2ex/posts.jsonl（append/resume）；进度 data/tmp/v2ex/progress.json。
"""
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_helper import run_source, BASE

OUT = BASE / "data" / "tmp" / "v2ex" / "posts.jsonl"
PROG = BASE / "data" / "tmp" / "v2ex" / "progress.json"

QUERIES = [
    "Agent 面经",
    "大模型 面试",
    "算法 面试 经历",
    "AI 工程师 面经",
    "校招 面经",
    "跳槽 面经",
]


class V2EXAdapter:
    domain = "v2ex.com"
    content_selectors = ("#topic_content", ".topic_content", "h1")
    first_card_selector = "a[href^='/t/']"
    card_js = r'''(() => {
      const out = []; const seen = new Set();
      document.querySelectorAll("a[href^='/t/']").forEach(a => {
        const m = (a.getAttribute('href') || '').match(/\/t\/(\d+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return; seen.add(id);
        const title = (a.querySelector('.topic-link') || a).innerText.trim();
        if (title) out.push({id: id, title: title});
      });
      return JSON.stringify(out);
    })()'''
    note_js = r'''(() => {
      const titleEl = document.querySelector('h1');
      const title = titleEl ? titleEl.innerText.trim() : '';
      const el = document.querySelector('#topic_content') || document.querySelector('.topic_content')
              || document.querySelector('.content');
      const text = el ? el.innerText : '';
      return JSON.stringify({title: title, text: text.slice(0, 30000), date: ''});
    })()'''

    def search_url(self, q):
        return "https://www.v2ex.com/search?q=" + urllib.parse.quote(q) + "&s=1"

    def note_url(self, nid):
        return "https://www.v2ex.com/t/" + nid


if __name__ == "__main__":
    run_source(V2EXAdapter(), QUERIES, OUT, PROG, domain=V2EXAdapter.domain,
               max_per_query=15, nav_gap=(3.0, 6.0))
