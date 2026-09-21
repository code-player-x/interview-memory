#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给 B+ 树综合大题(q0490 / 练习库 id 609)补上「评分要点」，并让它能随 convert 传播。

1) 题库 q0490.answer 增加「评分要点」键；
2) convert_to_interview_memory.build_reference 的取键元组加入「评分要点」；
   ——只影响带该键的题目（当前仅此一道），其余题目不受影响；
3) 同步刷新练习库 id=609 的 reference_answer。

用法：python scripts/add_rubric_bplustree.py [--apply]
"""
import argparse
import json
import re
import shutil
import sqlite3
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
BANK = PROJ / "data" / "questions-bank.json"
CONVERT = PROJ / "scripts" / "convert_to_interview_memory.py"
DB = Path("G:/interview-memory/data/interview_memory.db")
ANCHOR = "q0490"
PRAC_ANCHOR = 609

SCORE = """
【评分要点】（合计 100 分；另设加分项，可突破上限）

（1）结构关 · 20 分
- 说出 B+ 树三个特性，每个 3 分：①全量数据只在叶子、非叶子仅存索引键；②叶子用双向指针串成有序链表；③所有叶子同层、树高平衡。（共 9 分）
- 横向对比答出「节点存储内容」差异 4 分、「叶子是否相连」3 分、「树的高度」4 分。
- 只答「它们都是平衡树」不得分（过于笼统，未触及差异）。

（2）定量关 · 15 分
- 给出 16KB 页 / 约 15KB 有效空间、索引项 12B（主键 8B + 页号 4B），3 分。
- 算出扇出 15×1024/12 ≈ 1280，4 分；叶子页 15 行/页，2 分。
- 代入 Total = x^(z-1) × y，得出 z=3 时约 2457 万 > 2000 万，4 分。
- 说明「树高直接等于检索路径节点数 → 决定磁盘 I/O 次数」，2 分。
- 只背「三层」而不给出推导过程，该问扣一半分。

（3）查询关 · 20 分
- 等值查找：B+ 树 O(log_m N)、B 树不稳定、哈希平均 O(1)，每种 3 分（共 9 分）。
- 范围查找：B+ 树定位后沿叶子链表顺序扫、B 树需中序遍历回溯、哈希不支持，每种 3 分（共 9 分）。
- 点出根因「哈希值不保序 → between / order by / >、< 全部失效，且不支持最左前缀」，2 分。

（4）写入关 · 15 分
- 自增主键：顺序追加到最右侧叶子页、不移动已有数据，5 分。
- 随机主键（UUID）：随机位置插入 → 页内移动数据 → 页满触发页分裂 → 产生碎片与写放大，7 分。
- 给出结论「主键应自增 / 顺序递增」，3 分。

（5）选型关 · 20 分
- 相对 B 树的两点：①非叶子不存数据 → 扇出更大 → 树更矮 → I/O 更少；②叶子链表 → 范围查询退化为顺序读。（各 5 分，共 10 分）
- 相对哈希的两点：①支持范围查询与排序；②支持最左前缀 / 前缀模糊匹配；（③无 rehash 抖动；④叶子逻辑连续，契合磁盘顺序读与预读）。（共 10 分）
- 只答「MySQL 就是这么做的」「业界主流」不得分——未给出技术原因。

（6）边界关 · 10 分
- 给出适用 / 不适配场景的判断准则，5 分。
- 澄清「InnoDB 自适应哈希索引（AHI）是在 B+ 树之上对热点页再建的哈希，是补充不是替代」，5 分。

加分项（每题 2–3 分，上限 10 分）
- 提到 AHI 的生效范围与自动建立机制；提到 MySQL Memory 引擎支持显式 HASH 索引；
- 指出「单表不超过 2000 万行」的前提是行宽与树高，不是固定常数；
- 了解 LSM-Tree（LevelDB / RocksDB）是「顺序写换写吞吐」的不同取舍路线；
- 能用联合索引 / 覆盖索引消灭回表。

扣分项（命中即扣）
- 断言「哈希等值 O(1) 所以整体最优」：扣 10 分。
- 断言「B 树更快」且未提查询稳定性与范围查询代价：扣 8 分。
- 把 B+ 树高度当固定常数、拒绝推导：扣 5 分。
- 认为 UUID 主键只是「稍微慢一点」、未提页分裂与碎片：扣 5 分。
""".strip()


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


def star_to_int(d: str) -> int:
    return max(1, min(5, (d or "").count("★") + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(BANK, encoding="utf-8") as f:
        data = json.load(f)
    it = next((x for x in data["items"] if x["id"] == ANCHOR), None)
    if it is None:
        print(f"[error] 找不到 {ANCHOR}")
        return

    ans = it.setdefault("answer", {})
    has = "评分要点" in ans
    print(f"[plan] 题库 {ANCHOR}.answer 增加『评分要点』 ({len(SCORE)} 字)")

    txt = CONVERT.read_text(encoding="utf-8")
    old_tuple = 'for k in ("简版", "展开", "加分点", "雷区"):'
    new_tuple = 'for k in ("简版", "展开", "加分点", "雷区", "评分要点"):'
    print(f"[plan] convert_to_interview_memory.build_reference 取键元组 {'已含' if new_tuple in txt else '将加入'}『评分要点』")

    reference = build_reference({**ans, "评分要点": SCORE})
    print(f"[plan] 练习库 id={PRAC_ANCHOR} 的 reference_answer 刷新为 {len(reference)} 字")

    if not args.apply:
        print("[info] dry-run，未改动。确认后加 --apply")
        return

    bak1 = str(BANK) + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(BANK, bak1)
    ans["评分要点"] = SCORE
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[write] 题库已更新，备份 {bak1}")

    if new_tuple not in txt and old_tuple in txt:
        shutil.copy2(CONVERT, str(CONVERT) + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
        CONVERT.write_text(txt.replace(old_tuple, new_tuple), encoding="utf-8")
        print("[write] build_reference 已扩展")
    elif new_tuple in txt:
        print("[write] build_reference 已是新元组，跳过")
    else:
        print("[warn] 未匹配到目标元组，请人工确认 convert_to_interview_memory.py")

    bak2 = str(DB) + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB, bak2)
    con = sqlite3.connect(DB)
    con.execute("UPDATE questions SET reference_answer=? WHERE id=?", (reference, PRAC_ANCHOR))
    con.commit()
    n = con.execute("SELECT LENGTH(reference_answer) FROM questions WHERE id=?", (PRAC_ANCHOR,)).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    con.close()
    print(f"[verify] 练习库 id={PRAC_ANCHOR} 答案长度 {n} | 总题数 {total}")
    print(f"[done] 备份 {bak2}")


if __name__ == "__main__":
    main()
