#!/usr/bin/env python3
"""每日抽 3 题：跨分类覆盖、避开近 7 天已推、优先 新增/待复核。
输出可直接塞进邮件正文的 markdown。已推 id 写回 bank.meta.last_pushed。
"""
import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
import bank

N = 3
RECENT_DAYS = 7

# 用户指定不推送的分类（纯算法手撕 + 行为/HR），只保留 Agent/后端技术类
EXCLUDE_CATS = {"手撕算法", "行为与HR"}


def pick():
    data = bank.load()
    items = data["items"]
    meta = data.setdefault("meta", {})
    last = meta.get("last_pushed", [])  # [{id, date}]
    recent_ids = {x["id"] for x in last
                  if datetime.fromisoformat(x["date"]) > datetime.now() - timedelta(days=RECENT_DAYS)}

    pool = [it for it in items if it.get("id") not in recent_ids]
    # 过滤掉不参与推送的分类
    pool = [it for it in pool if it.get("category", "未分类") not in EXCLUDE_CATS]
    # 优先级：新增/待复核 优先
    prio = {"新增": 0, "待复核": 1, "已有": 2}
    pool.sort(key=lambda it: prio.get(it.get("status", "已有"), 2))

    # 跨分类贪心：每类轮替取 1 题，直到取满 N
    by_cat = defaultdict(list)
    for it in pool:
        by_cat[it.get("category", "未分类")].append(it)
    selected, used_cats = [], set()
    cats = list(by_cat.keys())
    while len(selected) < N and by_cat:
        progressed = False
        for c in cats:
            if c in used_cats:
                continue
            if by_cat[c]:
                selected.append(by_cat[c].pop(0))
                progressed = True
                if not by_cat[c]:
                    used_cats.add(c)
            if len(selected) >= N:
                break
        if not progressed:
            break
    # 仍不足则补任意
    if len(selected) < N:
        for it in pool:
            if it not in selected:
                selected.append(it)
            if len(selected) >= N:
                break

    # 写回 last_pushed
    today = datetime.now().isoformat(timespec="seconds")
    for it in selected:
        last.append({"id": it["id"], "date": today})
    meta["last_pushed"] = last[-200:]  # 只留最近 200 条
    bank.save(data)
    return selected


def render_md(items):
    lines = ["# 今日 Agent 面试题（3 道）\n"]
    for i, it in enumerate(items, 1):
        lines.append(f"## {i}. [{it.get('category','未分类')}] {it.get('content','')}")
        tags = it.get("tags") or []
        tags_s = "，".join(tags) if isinstance(tags, list) else str(tags)
        lines.append(f"- 来源：{it.get('source','')}　难度：{it.get('difficulty','')}　标签：{tags_s}")
        ans = it.get("answer", {})
        if ans.get("简版"):
            lines.append(f"**简版**：{ans['简版']}")
        if ans.get("展开"):
            lines.append(f"**展开**：{ans['展开']}")
        if ans.get("加分点"):
            lines.append(f"**加分点**：{ans['加分点']}")
        if it.get("leetcode_url"):
            lines.append(f"**力扣**：{it['leetcode_url']}")
        if it.get("sources"):
            lines.append("来源：" + "，".join(it["sources"]))
        lines.append("")
    return "\n".join(lines)


_CAT_COLOR = {
    "概念基础": "#2563eb",
    "架构设计": "#7c3aed",
    "工程落地": "#0891b2",
    "手撕算法": "#db2777",
    "项目深挖": "#ea580c",
    "后端八股（Go）": "#16a34a",
    "行为与HR": "#64748b",
}


def _esc(s):
    return html.escape(str(s), quote=True)


def render_html(items):
    """生成兼容手机/电脑邮箱的 HTML 邮件正文（关键样式全部内联，不依赖 <style>）。"""
    cards = []
    for i, it in enumerate(items, 1):
        cat = it.get("category", "未分类")
        color = _CAT_COLOR.get(cat, "#2563eb")
        ans = it.get("answer", {}) or {}
        tags = it.get("tags") or []
        tags_s = "，".join(tags) if isinstance(tags, list) else str(tags)

        blocks = []
        if ans.get("简版"):
            blocks.append(
                '<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                'border-left:3px solid #e2e8f0;"><span style="font-weight:700;color:#2563eb;'
                f'margin-right:6px;">简版</span>{_esc(ans["简版"])}</div>'
            )
        if ans.get("展开"):
            blocks.append(
                '<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                'border-left:3px solid #e2e8f0;"><span style="font-weight:700;color:#2563eb;'
                f'margin-right:6px;">展开</span>{_esc(ans["展开"])}</div>'
            )
        if ans.get("加分点"):
            blocks.append(
                '<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                'border-left:3px solid #16a34a;"><span style="font-weight:700;color:#16a34a;'
                f'margin-right:6px;">加分点</span>{_esc(ans["加分点"])}</div>'
            )

        links = []
        if it.get("leetcode_url"):
            links.append(
                f'<a href="{_esc(it["leetcode_url"])}" style="color:#2563eb;'
                'text-decoration:none;margin-right:14px;">力扣题目 ↗</a>'
            )
        for s in (it.get("sources") or [])[:2]:
            links.append(
                f'<a href="{_esc(s)}" style="color:#2563eb;text-decoration:none;'
                'margin-right:14px;">来源 ↗</a>'
            )
        links_html = (
            f'<div style="font-size:13px;margin-top:10px;">{" · ".join(links)}</div>'
            if links else ""
        )

        cards.append(f'''
        <div style="background:#ffffff;border-radius:14px;padding:16px 18px;margin-bottom:14px;
                    box-shadow:0 1px 3px rgba(0,0,0,.08);">
          <div style="display:flex;align-items:center;margin-bottom:8px;">
            <span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;
                         border-radius:50%;background:#1e293b;color:#ffffff;font-size:13px;font-weight:700;
                         margin-right:10px;">{i}</span>
            <span style="color:#ffffff;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;
                         background:{color};">{_esc(cat)}</span>
          </div>
          <div style="font-size:16px;font-weight:600;line-height:1.5;margin:6px 0 8px;">{_esc(it.get("content",""))}</div>
          <div style="font-size:12px;color:#64748b;margin-bottom:10px;">来源：{_esc(it.get("source",""))}
            &nbsp;|&nbsp; 难度：{_esc(it.get("difficulty",""))} &nbsp;|&nbsp; 标签：{_esc(tags_s)}</div>
          {''.join(blocks)}
          {links_html}
        </div>''')

    today = datetime.now().strftime("%Y-%m-%d")
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日 Agent 面试题（{today}）</title></head>
<body style="margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#1e293b;">
<div style="max-width:680px;margin:0 auto;padding:16px;">
  <div style="background:linear-gradient(135deg,#2563eb,#7c3aed);color:#ffffff;border-radius:14px;padding:18px 20px;margin-bottom:16px;">
    <div style="font-size:20px;font-weight:700;">今日 Agent 面试题</div>
    <div style="font-size:13px;opacity:.9;margin-top:4px;">{today} · 共 {len(items)} 道</div>
  </div>
  {''.join(cards)}
  <div style="font-size:12px;color:#94a3b8;text-align:center;padding:10px 0 4px;">本邮件由「Agent面经收割机」自动推送 · 题面与答案来自本地题库（AI 整理，建议核对）</div>
</div>
</body></html>'''


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["html", "md"], default="html")
    args = ap.parse_args()
    sel = pick()
    print(render_html(sel) if args.format == "html" else render_md(sel))
