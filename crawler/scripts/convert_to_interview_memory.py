#!/usr/bin/env python3
"""将 agent-mianshi-harvester 的 questions-bank.json 转换为 interview-memory 的导入格式，
并做两级去重：
  (1) 源库自身归一化去重 —— 防止同一题面在源库里重复出现；
  (2) 与练习系统现有库交叉去重 —— 读取 interview_memory.db 的 question_text，
      先按归一化精确相等跳过，再按 SequenceMatcher >= fuzzy(默认0.85) 模糊跳过，
      避免把练习系统里已经存在的题（之前从 Claw 副本导入过）再导一遍。

输出 data/tmp/interview_memory_import.json，结构 {"questions":[...]}，
可直接 POST 给 interview-memory 的 /api/questions/import-batch（path 指该文件）。

字段映射：
  content           -> question   (question_text)
  answer.展开(+简版/加分点/雷区) -> reference_answer
  tags              -> key_points (import-batch 会把 category+key_points 拼成 tags)
  difficulty 星标   -> difficulty(int 1-5)
  source            -> platform   (限长48，DB 列 String(50))
  category          -> category
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup import resolve_spec, DedupRunner

PROJ = Path(__file__).resolve().parent.parent
DEFAULT_BANK = PROJ / "data" / "questions-bank.json"
DEFAULT_TARGET_DB = PROJ.parent / "data" / "interview_memory.db"  # 仓库根/data（与 crawler 同级）
DEFAULT_OUT = PROJ / "data" / "tmp" / "interview_memory_import.json"


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)  # 去标点，保留中英文数字
    return s


def star_to_int(d: str) -> int:
    full = (d or "").count("★")
    return max(1, min(5, full + 1))


def build_reference(a: dict) -> str:
    parts = []
    for k in ("简版", "展开", "加分点", "雷区", "评分要点"):
        v = (a or {}).get(k)
        if isinstance(v, list):
            v = "\n".join(str(x).strip() for x in v if str(x).strip())
        v = (v or "").strip()
        if v:
            parts.append(f"【{k}】\n{v}")
    return "\n\n".join(parts)


def convert(items):
    out = []
    for it in items:
        content = (it.get("content") or "").strip()
        if not content:
            continue
        a = it.get("answer") or {}
        ref = build_reference(a)
        src = it.get("source", "") or ""
        platform = (src[:48] if src else "WorkBuddy爬取")
        out.append({
            "question": content,
            "category": it.get("category", "") or "",
            "key_points": [str(t).strip() for t in it.get("tags", []) if str(t).strip()],
            "reference_answer": ref or content,
            "difficulty": star_to_int(it.get("difficulty", "")),
            "platform": platform,
        })
    return out


def load_target_texts(db_path: Path):
    if not db_path.exists():
        print(f"[warn] 目标库不存在: {db_path}，跳过交叉去重", file=sys.stderr)
        return [], []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = con.execute("SELECT question_text FROM questions").fetchall()
        con.close()
        texts = [r[0] for r in rows if r[0]]
        return texts, [norm(t) for t in texts]
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 读取目标库失败: {e}，跳过交叉去重", file=sys.stderr)
        return [], []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(DEFAULT_BANK))
    ap.add_argument("--target-db", default=str(DEFAULT_TARGET_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--fuzzy", type=float, default=0.85,
                    help="规则策略的字符模糊阈值（仅 rule 用）")
    ap.add_argument("--dedup", default="rule",
                    help="去重策略插件: rule | semantic | none | all | rule+semantic")
    ap.add_argument("--semantic-backend", default="ollama", help="ollama | st")
    ap.add_argument("--semantic-model", default="nomic-embed-text")
    ap.add_argument("--semantic-threshold", type=float, default=0.9,
                    help="语义相似度阈值（仅 semantic 用）")
    ap.add_argument("--no-cross", action="store_true", help="不做与练习系统的交叉去重")
    ap.add_argument("--category", default="", help="仅导出分类含该子串的题")
    args = ap.parse_args()

    bank = json.loads(Path(args.bank).read_text(encoding="utf-8"))
    items = bank.get("items", [])
    if args.category:
        items = [i for i in items if args.category in (i.get("category") or "")]
    print(f"源库题目数(筛选后): {len(items)}")

    conv = convert(items)
    print(f"转换后(含源内可能重复): {len(conv)}")

    # 交叉去重基线：练习系统现有题面（--no-cross 时为空，仅做源内去重）
    if args.no_cross:
        baseline = []
        print("已跳过交叉去重（--no-cross）")
    else:
        target_texts, _ = load_target_texts(Path(args.target_db))
        baseline = target_texts
        print(f"交叉基线(练习系统现有题数): {len(target_texts)}")
        if not baseline:
            print("[warn] 交叉基线为空，仅做源内去重")

    # 解析去重策略插件（rule / semantic / none / all / rule+semantic）
    strat = resolve_spec(
        args.dedup,
        fuzzy=args.fuzzy,
        backend_name=args.semantic_backend,
        model=args.semantic_model,
        threshold=args.semantic_threshold,
    )

    # 语义后端可用性探测：不可用则优雅退出，避免静默产错结果
    if args.dedup not in ("rule", "none"):
        try:
            ok = strat.available()
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[warn] 后端探测异常: {e}", file=sys.stderr)
        if not ok:
            sys.exit(
                "[X] 语义去重后端不可用。请确认：\n"
                "    (1) Ollama 已启动且已拉取模型: ollama pull nomic-embed-text\n"
                "    (2) 或改用本地模型: --semantic-backend st（需 pip install sentence-transformers）\n"
                "    (3) 或暂用纯规则去重: --dedup rule")

    runner = DedupRunner(strat, baseline=baseline)
    records = [(c["question"], c["question"]) for c in conv]
    kept_ids, dups = runner.process(records)
    kept_set = {k[0] for k in kept_ids}
    final = [c for c in conv if c["question"] in kept_set]

    print(f"去重(策略={args.dedup}) 共剔除: {len(conv) - len(final)} | 余: {len(final)}")
    if dups:
        print("  重复样例(新题 -> 命中基线):")
        for d in dups[:15]:
            print(f"    [{d['score']:.3f}] {d['text'][:38]}  ~  {str(d['matched'])[:38]}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"questions": final}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n输出 {len(final)} 题 -> {out_path}")
    print("   这些题均为练习系统当前没有的净新增，可直接交给 import-batch 导入。")


if __name__ == "__main__":
    main()
