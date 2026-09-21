#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日面试题选题 + 排版。
读取题库，挑 5 道今天尚未发送过的题（分类均衡），输出 HTML 邮件正文到 stdout，
并把选中的 id 写入 data/tmp/email_last_pick.json 供调用方发送成功后记录。

调用方（人或自动化）负责：① 读 stdout 作为邮件 body；② SendMessage；③ 发送成功后
把 email_last_pick.json 里的 ids 追加进 data/tmp/email_sent.json。
"""
import html as _html
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BANK = ROOT / "data" / "questions-bank.json"
SENT = ROOT / "data" / "tmp" / "email_sent.json"
PICK = ROOT / "data" / "tmp" / "email_last_pick.json"

CAT_ORDER = ["概念基础", "架构设计", "工程落地",
             "后端八股（Go）", "项目深挖", "行为与HR"]
N = 5

# 邮件只推技术类：排除「手撕算法」（用户明确不要发）与「行为与HR」
EXCLUDE_CATS = {"手撕算法", "行为与HR"}


def load_bank():
    b = json.load(open(BANK, encoding="utf-8"))
    return b.get("items") or b.get("questions") or []


def load_sent():
    if SENT.exists():
        try:
            return json.load(open(SENT, encoding="utf-8"))
        except Exception:
            return []
    return []


def pick(items, sent_ids):
    by_cat = {c: [] for c in CAT_ORDER}
    for it in items:
        by_cat.setdefault(it.get("category"), []).append(it)
    pool = [it for it in items
            if it.get("id") not in sent_ids
            and it.get("category") not in EXCLUDE_CATS]

    chosen = []
    # 第一轮：每类各取 1 道（按 CAT_ORDER，优先最新爬到的），直到满 N
    for c in CAT_ORDER:
        if len(chosen) >= N:
            break
        if c in EXCLUDE_CATS:
            continue
        avail = [it for it in by_cat.get(c, []) if it.get("id") not in sent_ids]
        if avail:
            chosen.append(avail[-1])
    # 第二轮：仍有空缺则从任意未发送的题里补（保持类别多样，按 CAT_ORDER 轮询，优先最新）
    if len(chosen) < N:
        i = 0
        while len(chosen) < N and pool:
            c = CAT_ORDER[i % len(CAT_ORDER)]
            i += 1
            avail = [it for it in by_cat.get(c, []) if it.get("id") not in sent_ids and it not in chosen]
            if avail:
                chosen.append(avail[-1])
            # 兜底：随便补
            if i > len(CAT_ORDER) * 3:
                for it in pool:
                    if it not in chosen:
                        chosen.append(it)
                        break
    return chosen[:N]


_CAT_COLOR = {
    "概念基础": "#2563eb",
    "架构设计": "#7c3aed",
    "工程落地": "#0891b2",
    "手撕算法": "#db2777",
    "项目深挖": "#ea580c",
    "后端八股（Go）": "#16a34a",
    "行为与HR": "#64748b",
}


def esc(s):
    return _html.escape(str(s or ""), quote=True)


def src_url(it):
    u = it.get("wiki_url") or ""
    if not u and it.get("sources"):
        s0 = it["sources"][0]
        u = s0.get("url") if isinstance(s0, dict) else str(s0)
    return u


def render(items):
    """渲染为 daily.py 同款风格：渐变紫头 + 圆形编号 + 彩色 pill + 左侧色条答案块。"""
    today = date.today().isoformat()
    cards = []
    for i, it in enumerate(items, 1):
        cat = it.get("category", "未分类")
        color = _CAT_COLOR.get(cat, "#2563eb")
        a = it.get("answer", {}) or {}
        tags = it.get("tags") or []
        tags_s = "，".join(tags) if isinstance(tags, list) else str(tags)

        # 答案块（左侧色条区分）
        blocks = []
        if a.get("简版"):
            blocks.append(
                f'<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                f'border-left:3px solid #2563eb;"><span style="font-weight:700;color:#2563eb;'
                f'margin-right:6px;">简版</span>{esc(a["简版"])}</div>'
            )
        if a.get("展开"):
            blocks.append(
                f'<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                f'border-left:3px solid #7c3aed;"><span style="font-weight:700;color:#7c3aed;'
                f'margin-right:6px;">展开</span>{esc(a["展开"])}</div>'
            )
        if a.get("加分点"):
            blocks.append(
                f'<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                f'border-left:3px solid #16a34a;"><span style="font-weight:700;color:#16a34a;'
                f'margin-right:6px;">加分点</span>{esc(a["加分点"])}</div>'
            )
        if a.get("雷区"):
            blocks.append(
                f'<div style="font-size:14px;line-height:1.65;margin:8px 0;padding-left:10px;'
                f'border-left:3px solid #dc2626;"><span style="font-weight:700;color:#dc2626;'
                f'margin-right:6px;">雷区</span>{esc(a["雷区"])}</div>'
            )

        # 来源链接
        links = []
        for s in (it.get("sources") or [])[:2]:
            links.append(
                f'<a href="{esc(s)}" style="color:#2563eb;text-decoration:none;'
                f'margin-right:14px;">来源 &nearr;</a>'
            )
        links_html = (
            f'<div style="font-size:13px;margin-top:10px;">{" · ".join(links)}</div>'
            if links else ""
        )

        cards.append(f'''
    <div style="background:#ffffff;border-radius:14px;padding:16px 18px;margin-bottom:14px;
                box-shadow:0 1px 3px rgba(0,0,0,.08);">
      <div style="display:flex;align-items:center;margin-bottom:8px;">
        <span style="display:inline-flex;align-items:center;justify-content:center;
                     width:24px;height:24px;border-radius:50%;background:#1e293b;
                     color:#ffffff;font-size:13px;font-weight:700;margin-right:10px;">{i}</span>
        <span style="color:#ffffff;font-size:12px;font-weight:600;padding:3px 10px;
                     border-radius:999px;background:{color};">{esc(cat)}</span>
      </div>
      <div style="font-size:16px;font-weight:600;line-height:1.5;margin:6px 0 8px;">
        {esc(it.get("content",""))}
      </div>
      <div style="font-size:12px;color:#64748b;margin-bottom:10px;">
        来源：{esc(it.get("source",""))}&nbsp;|&nbsp; 难度：{esc(it.get("difficulty",""))}
        &nbsp;|&nbsp; 标签：{esc(tags_s)}
      </div>
      {''.join(blocks)}
      {links_html}
    </div>''')

    body = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日 Agent 面试题（{today}）</title></head>
<body style="margin:0;background:#f1f5f9;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
color:#1e293b;">
<div style="max-width:680px;margin:0 auto;padding:16px;">
  <div style="background:linear-gradient(135deg,#2563eb,#7c3aed);color:#ffffff;
              border-radius:14px;padding:18px 20px;margin-bottom:16px;">
    <div style="font-size:20px;font-weight:700;">今日 Agent 面试题</div>
    <div style="font-size:13px;opacity:.9;margin-top:4px;">{today} · 共 {len(items)} 道</div>
  </div>
  {''.join(cards)}
  <div style="font-size:12px;color:#94a3b8;text-align:center;padding:10px 0 4px;">
    本邮件由「Agent面经收割机」自动推送 · 题面与答案来自本地题库（AI 整理，建议核对）
  </div>
</div>
</body></html>'''
    return today, body


def main():
    items = load_bank()
    sent = load_sent()
    sent_ids = {s.get("id") for s in sent if isinstance(s, dict)}
    chosen = pick(items, sent_ids)
    # 全发完了则重置循环
    if not chosen:
        chosen = pick(items, set())
        reset_note = True
    else:
        reset_note = False
    if not chosen:
        print("题库为空，无法生成。", file=sys.stderr)
        sys.exit(1)
    today, body = render(chosen)
    PICK.write_text(json.dumps({"date": today, "ids": [c.get("id") for c in chosen],
                                "reset": reset_note}, ensure_ascii=False), encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
