#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掘金面经采集器（CDP 复用已登录 Chrome，开放源无需登录）。

掘金搜索 API 从沙箱直连被风控（路由不存在），但经用户 Chrome 出口可正常渲染。
写入 data/tmp/juejin/posts.jsonl（append/resume）；进度 data/tmp/juejin/progress.json。
"""
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_helper import run_source, BASE

OUT = BASE / "data" / "tmp" / "juejin" / "posts.jsonl"
PROG = BASE / "data" / "tmp" / "juejin" / "progress.json"

QUERIES = [
    "AI Agent 面经",
    "大模型 Agent 面试",
    "Agent 开发 面试题",
    "RAG 面试",
    "LLM 算法工程师 面经",
    "智能体 面试 八股",
    "大模型 校招 面经",
]


class JuejinAdapter:
    domain = "juejin.cn"
    content_selectors = ("#articleContent", ".markdown-body", ".article-content", "h1")
    first_card_selector = "a[href^='/post/']"
    card_js = r'''(() => {
      const out = []; const seen = new Set();
      document.querySelectorAll("a[href*='/post/']").forEach(a => {
        const m = (a.getAttribute('href') || '').match(/\/post\/([0-9a-zA-Z]+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return; seen.add(id);
        const title = (a.querySelector('.title') || a).innerText.trim();
        if (title) out.push({id: id, title: title});
      });
      return JSON.stringify(out);
    })()'''
    note_js = r'''(() => {
      const titleEl = document.querySelector('h1.article-title') || document.querySelector('h1');
      const title = titleEl ? titleEl.innerText.trim() : '';
      const el = document.querySelector('#articleContent') || document.querySelector('.markdown-body')
              || document.querySelector('.article-content');
      const text = el ? el.innerText : '';
      // 发布时间：优先 <time>，其次含 date 类的元信息文本
      const dEl = document.querySelector('time')
              || document.querySelector('[class*="date"]')
              || document.querySelector('.article-meta')
              || document.querySelector('.meta');
      const date = dEl ? (dEl.getAttribute('datetime') || dEl.innerText || '').trim() : '';
      return JSON.stringify({title: title, text: text.slice(0, 60000), date: date});
    })()'''

    def search_url(self, q):
        return "https://juejin.cn/search?query=" + urllib.parse.quote(q)

    def note_url(self, nid):
        return "https://juejin.cn/post/" + nid


if __name__ == "__main__":
    run_source(JuejinAdapter(), QUERIES, OUT, PROG, domain=JuejinAdapter.domain,
               max_per_query=15, nav_gap=(4.0, 8.0))
