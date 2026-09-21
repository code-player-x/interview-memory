#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知乎面经采集器（CDP 复用已登录 Chrome，登录墙源）。

知乎对未登录/风控访问极严格：
- 搜索结果与回答正文都需登录后才能完整读取，故**务必先在 Chrome 登录知乎**
  （zhihu.com），否则详情页只会拿到"登录后查看"的残缺正文，note_js 会因
  text 过短而被 run_source 跳过。
- 搜索页与详情页都是重 JS 渲染 + 反爬，撞风控会落到"安全验证"页；
  cdp_helper 的 detect_block 已内置"请先登录/扫码登录/滑动验证"等关键词，
  会把这类页保守判为验证页并自动轮询等用户滑掉（最长 verify_wait 秒）。
写入 data/tmp/zhihu/posts.jsonl（append/resume）；进度 data/tmp/zhihu/progress.json。
"""
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_helper import run_source, BASE

OUT = BASE / "data" / "tmp" / "zhihu" / "posts.jsonl"
PROG = BASE / "data" / "tmp" / "zhihu" / "progress.json"

QUERIES = [
    "AI Agent 面经",
    "大模型 Agent 面试",
    "Agent 开发 面试题",
    "RAG 面试",
    "大模型算法工程师 面经",
    "智能体 面试 八股",
    "LLM 面试 八股",
    "Agent 工程师 校招 面经",
]


class ZhihuAdapter:
    domain = "zhihu.com"
    # detect_block 用：命中正文容器才认为"有内容"，否则按验证/登录墙处理
    content_selectors = ("div.RichText", ".RichText", ".ContentItem", ".QuestionHeader", "article")
    # 搜索结果里"问题"与"文章"两种卡片都收
    first_card_selector = "a[href*='/question/'], a[href*='/p/']"
    card_js = r'''(() => {
      const out = []; const seen = new Set();
      // 问题卡片
      document.querySelectorAll('a[href*="/question/"]').forEach(a => {
        const m = (a.getAttribute('href') || '').match(/\/question\/(\d+)/);
        if (!m) return;
        const id = 'question/' + m[1];
        if (seen.has(id)) return; seen.add(id);
        const t = a.querySelector('.ContentItem-title')
                || a.querySelector('.SearchResult-CardTitle')
                || a.querySelector('.title');
        const title = (t || a).innerText.trim();
        if (title) out.push({id: id, title: title});
      });
      // 文章/专栏卡片
      document.querySelectorAll('a[href*="/p/"]').forEach(a => {
        const m = (a.getAttribute('href') || '').match(/\/p\/(\d+)/);
        if (!m) return;
        const id = 'p/' + m[1];
        if (seen.has(id)) return; seen.add(id);
        const t = a.querySelector('.ContentItem-title') || a.querySelector('.title');
        const title = (t || a).innerText.trim();
        if (title) out.push({id: id, title: title});
      });
      return JSON.stringify(out);
    })()'''
    # 标题 + 正文：问题页会合并多个回答 RichText；文章页取主 RichText
    note_js = r'''(() => {
      const titleEl = document.querySelector('.QuestionHeader-title')
              || document.querySelector('.Post-Title')
              || document.querySelector('h1');
      const title = titleEl ? titleEl.innerText.trim() : '';
      const parts = [];
      document.querySelectorAll('div.RichText, .RichText, article').forEach(e => {
        const t = e.innerText;
        if (t && t.length > 30) parts.push(t);
      });
      const text = parts.join('\n\n').slice(0, 60000);
      return JSON.stringify({title: title, text: text, date: ''});
    })()'''

    def search_url(self, q):
        return "https://www.zhihu.com/search?type=content&q=" + urllib.parse.quote(q)

    def note_url(self, nid):
        return "https://www.zhihu.com/" + nid


if __name__ == "__main__":
    # 知乎反爬严格，加长导航间隔、延长验证等待；登录墙源，撞验证原地轮询等用户滑掉
    run_source(ZhihuAdapter(), QUERIES, OUT, PROG, domain=ZhihuAdapter.domain,
               max_per_query=15, nav_gap=(5.0, 9.0), verify_wait=300)
