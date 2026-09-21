#!/usr/bin/env python3
"""
gen_fine_plan.py — 按「计算机面试题题库」原始细分类目重新归类，每分类一个飞书文档。

目标分类体系（来自用户原始飞书知识库截图）：
  简历专项题库 / 系统设计面试题题库 / Kafka / Golang / Redis / Mysql /
  操作系统 / 计算机网络 / 智力题 / docker / K8s / 分布式 / 设计模式 /
  系统设计题库 / 海量数据处理 / 架构设计题库
+ 补充分类（非飞书来源的 Agent 面经内容）：
  Agent概念基础 / Agent架构设计 / Agent工程落地 / 行为与HR / 项目深挖 / 手撕算法

用法：
  python scripts/gen_fine_plan.py              # 全量
  python scripts/gen_fine_plan.py --only Golang  # 单个验证
"""

import json, os, sys, re, html, time
from collections import OrderedDict, Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(BASE, "data", "questions-bank.json")
TMP_DIR = os.path.join(BASE, "data", "tmp")
PLAN_PATH = os.path.join(TMP_DIR, "fine_category_plan.tsv")

# ── 目标分类（有序） ──────────────────────────────────────────────
FINE_CATEGORIES = [
    # 原始知识库 16 类（保持截图顺序）
    ("简历专项题库",           "简历专项"),
    ("系统设计面试题题库",      "系统设计面试"),
    ("Kafka面试题整理",         "Kafka"),
    ("Golang面试题整理",        "Golang"),
    ("Redis面试题整理",         "Redis"),
    ("Mysql面试题整理",         "MySQL"),
    ("操作系统面试题整理",       "操作系统"),
    ("计算机网络面试题整理",     "计算机网络"),
    ("智力题题库",             "智力题"),
    ("docker面试题整理",        "Docker"),
    ("K8s面试题整理",           "K8s"),
    ("分布式面试题整理",        "分布式"),
    ("设计模式知识库",          "设计模式"),
    ("系统设计题库",            "系统设计题库"),
    ("海量数据处理题库",        "海量数据处理"),
    ("架构设计题库",            "架构设计题库"),
    # 补充：Agent 专项（非原始知识库来源）
    ("Agent概念基础",           "Agent概念"),
    ("Agent架构设计",           "Agent架构"),
    ("Agent工程落地",           "Agent工程"),
    ("行为与HR",                "HR"),
    ("项目深挖",                "项目深挖"),
    ("手撕算法",                "手撕算法"),
]

# ── 分类映射规则 ──────────────────────────────────────────────────

def classify_item(it):
    """
    返回 (fine_category_name, reason)
    优先级: source 字段精确匹配 > 当前粗分类兜底 > tags 兜底
    """
    src = it.get("source", "")
    coarse = it.get("category", "")
    tags = it.get("tags", [])
    content = it.get("content", "")

    # 1) source 精确匹配（飞书知识库来源直接用子文档名）
    source_map = {
        "飞书知识库·简历专项题库":     "简历专项题库",
        "飞书知识库·系统设计面试题题库":  "系统设计面试题题库",
        "飞书知识库·Kafka面试题整理":   "Kafka面试题整理",
        "飞书知识库·Golang面试题整理":   "Golang面试题整理",
        "飞书知识库·Redis面试题整理":   "Redis面试题整理",
        "飞书知识库·Mysql面试题整理":   "Mysql面试题整理",
        "飞书知识库·操作系统面试题整理":  "操作系统面试题整理",
        "飞书知识库·计算机网络面试题整理": "计算机网络面试题整理",
        "飞书知识库·智力题题库":       "智力题题库",
        "飞书知识库·docker面试题整理":  "docker面试题整理",
        "飞书知识库·K8s面试题整理":    "K8s面试题整理",
        "飞书知识库·分布式面试题整理":   "分布式面试题整理",
        "飞书知识库·设计模式知识库":     "设计模式知识库",
        "飞书知识库·系统设计题库":      "系统设计题库",
        "飞书知识库·海量数据处理题库":   "海量数据处理题库",
        "飞书知识库·架构设计题库":      "架构设计题库",
        "飞书知识库·HR面问题准备":      "行为与HR",
        "飞书知识库·MongoDB面试题库":   "分布式面试题整理",  # MongoDB 归入分布式
    }
    if src in source_map:
        return source_map[src], f"source:{src}"

    # 2) 后端八股（Go）→ Golang
    if coarse == "后端八股（Go）":
        return "Golang面试题整理", f"coarse:后端八股（Go）"

    # 3) 非 Agent 的粗分类直接映射
    coarse_map = {
        "行为与HR":   "行为与HR",
        "项目深挖":   "项目深挖",
        "手撕算法":   "手撕算法",
    }
    if coarse in coarse_map:
        return coarse_map[coarse], f"coarse:{coarse}"

    # 4) 原「后端八股」非飞书来源 + 原「概念基础」「架构设计」「工程落地」的 Agent 内容
    if coarse == "后端八股":
        # 这些理论上全是飞书来源（已确认 563/563 有 wiki），但保险起见按 tags 兜底
        return _tag_fallback(tags, content, coarse)

    # 5) 概念基础 / 架构设计 / 工程落地的非飞书内容 → Agent 专项
    if coarse in ("概念基础", "架构设计", "工程落地"):
        agent_map = {
            "概念基础": "Agent概念基础",
            "架构设计": "Agent架构设计",
            "工程落地": "Agent工程落地",
        }
        return agent_map[coarse], f"coarse-agent:{coarse}"

    # 6) 最终兜底
    return _tag_fallback(tags, content, coarse)


# tag 关键词 → 细分类（用于非飞书来源的兜底）
TAG_RULES = [
    (["kafka", "Kafka"],                     "Kafka面试题整理"),
    (["golang", "Go ", "Golang", "goroutine", "channel", "GMP", "GC"],
                                               "Golang面试题整理"),
    (["redis", "Redis"],                      "Redis面试题整理"),
    (["mysql", "Mysql", "SQL", "索引", "事务", "存储引擎"],
                                               "Mysql面试题整理"),
    (["操作系统", "进程", "线程", "内存管理", "文件系统", "锁"],
                                               "操作系统面试题整理"),
    (["网络", "TCP", "HTTP", "DNS", "Socket", "传输层"],
                                               "计算机网络面试题整理"),
    (["docker", "Docker", "容器"],             "docker面试题整理"),
    (["k8s", "kubernetes", "K8s", "Kubernetes"],
                                               "K8s面试题整理"),
    (["分布式", "高可用", "CAP", "一致性", "分片"],
                                               "分布式面试题整理"),
    (["设计模式", "单例", "工厂", "策略", "观察者"],
                                               "设计模式知识库"),
    (["智力", "脑筋急转弯", "逻辑题"],          "智力题题库"),
    (["简历", "自我介绍", "优缺点"],            "简历专项题库"),
]


def _tag_fallback(tags, content, coarse):
    tags_lower = [t.lower() for t in tags]
    content_lower = content.lower() if content else ""
    for keywords, cat in TAG_RULES:
        for kw in keywords:
            if any(kw.lower() in t for t in tags_lower):
                return cat, f"tag:{kw}"
            if kw.lower() in content_lower:
                return cat, f"content-keyword:{kw}"
    # 最终兜底：原后端八股放 MySQL（最大桶），Agent 内容放概念基础
    if coarse == "后端八股":
        return "Mysql面试题整理", f"fallback:后端八股→MySQL"
    return "Agent概念基础", f"fallback:{coarse}→Agent概念"


# ── XML 生成（复用原有逻辑） ───────────────────────────────────────

def esc(text):
    """转义 XML 文本中的 < > & \" '"""
    if not text:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def build_category_xml(cat_display_name, items):
    """生成一个分类汇总 XML（title + h1 + 每题 h2 + 简版/展开/加分点/雷区）"""
    lines = []
    total = len(items)
    title = f"{cat_display_name}（共{total}题）"
    lines.append(f'<title>{esc(title)}</title>')

    # 分类说明引用
    lines.append('<h1>' + esc(title) + '</h1>')
    lines.append('<blockquote>')
    lines.append(esc(f"本分类共收录 {total} 道面试题，涵盖该领域的核心知识点、高频考点及典型场景题。"))
    lines.append('</blockquote>')
    lines.append('<hr/>')

    for idx, it in enumerate(items, 1):
        q = it.get("content", "").strip()
        ans = it.get("answer", {})
        brief = (ans.get("简版") or "").strip()
        detail = (ans.get("展开") or "").strip()
        bonus = (ans.get("加分点") or "").strip()
        pitfall = (ans.get("雷区") or "").strip()

        # 标题行
        lines.append(f'<h2>Q{idx}. {esc(q)}</h2>')

        if brief:
            lines.append(f'<p><b>回答：</b>{esc(brief)}</p>')
        if detail:
            lines.append(f'<p><b>详细展开：</b>{esc(detail)}</p>')
        if bonus:
            lines.append(f'<p><b>加分项：</b>{esc(bonus)}</p>')
        if pitfall:
            lines.append(f'<blockquote><b>⚠️ 雷区：</b>{esc(pitfall)}</blockquote>')

        # 来源标注
        sources = it.get("sources", [])
        src_text = it.get("source", "")
        if sources:
            src_text = "; ".join(str(s) for s in sources[:3])
        elif src_text:
            src_text = src_text
        else:
            src_text = ""
        if src_text:
            lines.append(f'<p><i>来源：{esc(src_text)}</i></p>')
        lines.append('<hr/>')

    return "\n".join(lines)


def sanitize(name):
    """生成文件安全名（用于 XML 路径）"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name


# ── 主流程 ────────────────────────────────────────────────────────

def main():
    only_cat = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_cat = sys.argv[idx + 1]

    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)

    items = bank["items"]
    print(f"题库总计: {len(items)} 题")

    # 载入已有飞书细分类节点，避免重复建节点
    CONFIG_PATH = os.path.join(BASE, "data", "wiki-config.json")
    fine_nodes = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
            fine_nodes = cfg.get("fine_categories", {})
        except Exception:
            fine_nodes = {}

    # 排除「每日推送归档」
    items = [it for it in items if it.get("category") != "每日推送归档"]
    print(f"排除归档后: {len(items)} 题")

    # 分类
    categorized = OrderedDict()
    unclassified = []
    for it in items:
        cat, reason = classify_item(it)
        it["_fine_cat"] = cat
        it["_reason"] = reason
        categorized.setdefault(cat, []).append(it)

    # 打印分布
    print("\n=== 细分类分布 ===")
    total_assigned = sum(len(v) for v in categorized.values())
    for cat_name, _ in FINE_CATEGORIES:
        n = len(categorized.get(cat_name, []))
        if n > 0 or not only_cat:
            print(f"  {cat_name}: {n}")

    # 找出未落入预定义分类的
    predefined = set(c[0] for c in FINE_CATEGORIES)
    for cat in list(categorized.keys()):
        if cat not in predefined:
            print(f"  ⚠️  未预定义分类 [{cat}]: {len(categorized[cat])}")

    print(f"\n已分配: {total_assigned} / {len(items)}")

    # 生成 XML 和计划
    os.makedirs(TMP_DIR, exist_ok=True)
    plan_rows = []  # (cat, doc_token, title, xmlpath, needs_create)

    for cat_display, _ in FINE_CATEGORIES:
        cat_items = categorized.get(cat_display, [])
        if not cat_items:
            continue
        if only_cat and cat_display != only_cat:
            continue

        san = sanitize(cat_display)
        xmlpath = os.path.join(TMP_DIR, f"fine_{san}.xml")
        xml_content = build_category_xml(cat_display, cat_items)
        with open(xmlpath, "w", encoding="utf-8") as f:
            f.write(xml_content)

        existing = fine_nodes.get(cat_display, {}).get("node_token")
        if existing:
            plan_rows.append((cat_display, existing, f"{cat_display}（共{len(cat_items)}题）", xmlpath, "0"))
        else:
            plan_rows.append((cat_display, "NEW", f"{cat_display}（共{len(cat_items)}题）", xmlpath, "1"))
        print(f"  ✅ {xmlpath} ({len(xml_content)} chars, {len(cat_items)} 题)")

    # 写计划 TSV
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        f.write("category\tdoc_token\ttitle\txmlpath\tneeds_create\n")
        for row in plan_rows:
            f.write("\t".join(row) + "\n")

    print(f"\n计划写入: {PLAN_PATH} ({len(plan_rows)} 个分类)")


if __name__ == "__main__":
    main()
