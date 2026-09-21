#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 B+ 树对比相关的 6 道独立题整合为 1 道综合大题。

合并对象：q0489(特性) q0490(B+ vs B树) q0491(为何 MySQL 用 B+ 树)
          q0492(为何不用红黑树) q0499(insert 结构变化/页分裂) q0500(两千万行树高推算)
整合原则：原有 6 道的实质答案要点全部收进新答案（不降级），
          并补齐库中缺失的「B+ 树 vs 哈希索引」与「适用/不适用场景」。
锚点：保留 q0490 作为存活 id，其余 5 道删除并在 q0490.merged_from 留痕。

用法：python scripts/merge_bplustree.py [--apply]
"""
import argparse
import json
import os
import shutil
import time

BANK = "G:/interview-memory/crawler/data/questions-bank.json"
MERGE_IDS = ["q0489", "q0491", "q0492", "q0499", "q0500"]
ANCHOR = "q0490"

CONTENT = (
    "公司订单履约系统的订单表 t_order 预计存量 2000 万行，单行约 1KB，主键 order_id 为 bigint。"
    "日常读写画像为：订单详情等值查询 select * from t_order where order_id = ? 占 70%；"
    "时间范围扫描 select * from t_order where create_time between ? and ? order by create_time limit N 占 25%；"
    "下单/改单写入占 5%。\n\n"
    "技术评审会上三位同事各执一词：\n"
    "- 甲：上哈希索引，等值查询平均 O(1)，比任何树都快；\n"
    "- 乙：上 B 树，它的非叶子节点也存数据，命中间节点就直接返回，比每次都要走到叶子的 B+ 树更快；\n"
    "- 丙：上 B+ 树，MySQL InnoDB 默认就是它，跟着主流走。\n\n"
    "作为技术负责人，请你从结构、代价到场景做一次完整分析，并给出最终的索引选型结论。"
)

SUBQ = (
    "（1）（结构关）先说明 B+ 树自身的三个核心特性；再从「节点存储内容」「叶子节点是否相连」"
    "「树的高度/形态」三个维度，横向对比 B+ 树、B 树、哈希索引三者的结构差异。\n"
    "（2）（定量关）已知 InnoDB 页大小 16KB（有效约 15KB），索引项 = 主键 8B + 页号 4B，"
    "叶子页约存 15 行。请估算这张 2000 万行表的 B+ 树高度，说明推导过程，并解释树高如何决定磁盘 I/O 次数；"
    "再给出同等数据量下红黑树、哈希索引的检索代价量级。\n"
    "（3）（查询关）给出三种结构在「等值查找」与「范围查找」上的时间复杂度并说明原因。"
    "特别地：哈希索引等值 O(1)，为何满足不了占 25% 的范围扫描？\n"
    "（4）（写入关）向 B+ 树插入一条记录会发生什么？对比自增主键与随机主键（如 UUID）下的表现差异，"
    "说明页分裂的成因与代价，并指出主键选型对「叶子相连」结构的连锁影响。\n"
    "（5）（选型关）综合上述结论，说明为什么数据库索引通常优先选择 B+ 树，而不是 B 树或哈希索引"
    "——要求分别给出相对 B 树、相对哈希的决定性优势。\n"
    "（6）（边界关）是否存在不该用 B+ 树的场景？哈希索引在什么场景下反而更合适？"
    "请给出一套适用/不适用的判断准则。"
)

ANSWER = {
    "简版": (
        "结论：选 B+ 树。\n"
        "- 相比 B 树：非叶子节点不存数据 → 扇出更大、树更矮 → 磁盘 I/O 更少；叶子用双向链表串联 → "
        "范围查询是顺序读，而 B 树只能中序遍历反复回溯父节点。\n"
        "- 相比哈希：哈希虽等值 O(1)，但哈希值不保序，between/order by/>/< 全部失效，"
        "也不支持最左前缀，占 25% 的范围扫描会退化成全表扫描。\n"
        "- 2000 万行、1KB/行的表，B+ 树约 3 层，一次检索最多 3 次磁盘 I/O。"
    ),
    "展开": (
        "【(1) B+ 树的三个核心特性】\n"
        "1. 全量数据在叶子：所有具体数据（或指向数据的指针）都存储在叶子节点，非叶子节点只存储用于导航的索引键。"
        "这使得非叶子节点能容纳更多键值，降低树的高度。\n"
        "2. 叶子节点成链表：所有叶子节点通过双向指针串联，形成有序双向链表。这对范围查询和排序遍历至关重要，"
        "可以避免回溯到父节点。\n"
        "3. 树高平衡且稳定：所有叶子节点都在同一层，任何数据的检索路径等长，查询效率稳定；"
        "千万级数据表通常 3-4 层，即 3-4 次磁盘 I/O 即可完成查询。\n\n"
        "结构横向对比：\n\n"
        "| 维度 | B+ 树 | B 树 | 哈希索引 |\n"
        "| --- | --- | --- | --- |\n"
        "| 节点存储内容 | 非叶子只存索引键（键值+页号），**数据只在叶子** | **所有节点**（含非叶子）都存索引键+数据 | 不存节点，按 hash(key) 映射到桶，桶内存指针/链表 |\n"
        "| 叶子是否相连 | **是**，双向指针串成有序链表 | 否，叶子之间无链表 | 不适用，桶之间无顺序关系 |\n"
        "| 树的高度 | 多叉矮胖，千万级 3-4 层 | 同为多叉，但因非叶子也存数据，**同数据量下比 B+ 树更高** | 无树高概念，一层桶数组 |\n"
        "| 是否有序 | 叶子天然有序，支持 ORDER BY / BETWEEN | 中序遍历可得有序，但需遍历 | **无序**，哈希值不保序 |\n"
        "| 能否提前返回 | 不能，必须走到叶子 | **能**，命中非叶子节点即可返回 | 不适用 |\n\n"
        "【(2) 树高定量推导】\n"
        "MySQL 数据页大小 16KB，去掉头信息约 15KB 可存数据。\n"
        "- 索引页记录主键与页号：主键 bigint 占 8 字节，页号固定 4 字节，一条索引项 12 字节；"
        "一个索引页可存 15*1024/12 ≈ 1280 个页号，即扇出 x = 1280。\n"
        "- 叶子节点存真正的行数据，受字段类型与数量影响；按 1KB/行算，一页存 15KB/1KB = 15 行，即 y = 15。\n"
        "- 公式 Total = x^(z-1) * y。设 z = 3，Total = 1280^2 * 15 = 24,576,000 ≈ 2457 万 > 2000 万。\n"
        "结论：**三层高度即可容纳 2000 万行**（约 2457 万条余量），检索一条记录最多约 3 次磁盘 I/O；"
        "实践中根节点常驻内存，往往降到 1-2 次 I/O。树高直接等于检索路径上的节点数，也就直接决定 I/O 次数。\n"
        "对照：红黑树是二叉树，同等 2000 万数据量树高约 log2(2e7) ≈ 25 层，约 25 次 I/O；"
        "哈希索引理论上一次桶定位（冲突时退化）。\n\n"
        "【(3) 时间复杂度对比】\n\n"
        "| 操作 | B+ 树 | B 树 | 哈希索引 |\n"
        "| --- | --- | --- | --- |\n"
        "| 等值查找 | O(log_m N)，通常 3-4 次 I/O，稳定 | O(1)~O(log_m N)，命中非叶子可提前返回，**不稳定** | 平均 O(1)，冲突严重退化到 O(n) |\n"
        "| 范围查找 | O(log_m N + K)，定位首元素后**沿叶子链表顺序扫** K 条 | O(log_m N + K) 但需**中序遍历**，反复回溯父节点，随机 I/O 多 | **不支持**，本质是 O(N) 全表扫描 |\n"
        "| 插入/删除 | O(log_m N)，可能触发页分裂或页合并 | O(log_m N)，节点分裂更频繁 | 平均 O(1)，但 rehash 需整体重建 |\n\n"
        "哈希为何扛不住范围扫描：hash(key) 打散了键的自然顺序，相邻键值落进互不相邻的桶，"
        "因此 between、order by、>、< 统统无法利用索引，只能全表扫描后再排序；"
        "同理也不支持最左前缀匹配（如 like 'abc%'）与索引覆盖扫描。\n\n"
        "【(4) 写入：页分裂与主键选型】\n"
        "B+ 树数据有序，插入位置取决于主键是否有序：\n"
        "- **自增主键（顺序递增）**：新数据总是顺序追加到叶子节点最右边的页；该页满则自动开辟新页继续追加。"
        "因为每次插入都是追加操作、不需要移动已有数据，这种插入效率非常高，几乎不产生碎片。\n"
        "- **随机主键（如 UUID）**：每次插入的索引值是随机的，新数据可能落进现有数据页中间的某个位置，"
        "为保证有序必须移动页内其它数据；当该页已满，就发生**页分裂**——把一个页的数据复制到另一个页，"
        "以保证后一个数据页中所有行的主键值都大于前一个数据页。代价是：产生大量内存碎片，"
        "索引结构不再紧凑，从而影响查询效率；同时造成写放大。\n"
        "因此设计主键时最好采用自增方式（或顺序递增的主键值）。连锁影响：频繁的随机插入与页分裂会打散"
        "第(1)问提到的叶子双向链表的物理连续性，使范围扫描从顺序读退化为更多随机 I/O。\n\n"
        "【(5) 为什么数据库索引优先选 B+ 树】\n"
        "相对 **B 树** 的两个决定性优势：\n"
        "1. **更矮胖、I/O 更少**：非叶子节点不存数据，单个索引页能放下更多索引项，扇出更大、树高更低，"
        "意味着更少的磁盘 I/O。B 树非叶子也存数据，同等数据量下树更高，且中间层难以全部常驻内存，"
        "一旦放不下就意味着查询非叶子节点也要走磁盘 I/O。\n"
        "2. **范围查询碾压**：叶子双链表让范围扫描变成一次定位 + 顺序读；B 树没有把所有叶子串成链表，"
        "只能中序遍历完成范围查询，会涉及更多节点的磁盘 I/O，效率不如 B+ 树。\n"
        "（B 树的唯一优势：查找的值恰好处在非叶子节点时可提前返回，最快 O(1) 结束；"
        "但这让查询延迟不稳定，且上述两点损失远大于这点偶然收益。）\n\n"
        "相对 **哈希索引** 的决定性优势：\n"
        "1. 支持**范围查询与排序**，哈希无序使 between/order by 全部失效；\n"
        "2. 支持**最左前缀与前缀模糊匹配**，哈希只能全键等值；\n"
        "3. **冲突与扩容可控**：哈希冲突退化为链表遍历、扩容需整体 rehash，B+ 树始终维持稳定的 O(log N)；\n"
        "4. **磁盘友好**：叶子页逻辑连续，契合磁盘顺序读与预读机制。\n\n"
        "补充两组长尾对比：\n"
        "- 相对**红黑树/平衡二叉树**：它们是二叉树，同等数据量下树高远大于多叉的 B+ 树，"
        "磁盘 I/O 次数更多；并且会频繁执行再平衡来维持树形，总体性能更差。\n"
        "- 相对**跳表**：跳表在极端情况下可能退化为链表、时间不可预期，且节点在磁盘上存储不连续，"
        "范围查询会产生大量随机 I/O；内存中表现优异（如 Redis zset），磁盘场景不如 B+ 树。\n\n"
        "【(6) 适用与不适用场景】\n\n"
        "| 结构 | 适合 | 不适合 |\n"
        "| --- | --- | --- |\n"
        "| B+ 树 | 磁盘/SSD 上的通用数据库索引；等值 + 范围/排序/分页混合；要求延迟稳定可预期 | 纯内存、只需极简单点查的场景（有更轻的结构可选） |\n"
        "| 哈希索引 | 纯等值点查与 KV 场景（MySQL Memory 引擎、Redis、NoSQL KV）、缓存、精确去重 | 任何需要范围扫描、排序、ORDER BY/GROUP BY、最左前缀匹配的场景 |\n"
        "| B 树 | 单次点查、命中即可返回且无范围需求（如部分 KV 存储） | 需要频繁范围扫描的场景 |\n\n"
        "判断准则：\n"
        "- 查询里出现 BETWEEN、>、<、ORDER BY、GROUP BY、LIKE 'x%' → **排除哈希**，选 B+ 树；\n"
        "- 查询纯 = / IN，且数据集可全放内存 → 哈希索引可用（MySQL Memory 引擎就支持显式 HASH 索引）；\n"
        "- 需澄清一个常见误会：**InnoDB 的自适应哈希索引（AHI）并不是用哈希替代 B+ 树**——"
        "它是在 B+ 树之上对热点页再建一层哈希，把树检索降为一次定位，用于加速热点等值查询，"
        "由引擎自动建立；范围查询仍走 B+ 树叶子链表。"
    ),
    "加分点": (
        "- 能说出 InnoDB **自适应哈希索引（AHI）**是对 B+ 树的补充而非替代：只对热点页等值查询生效，"
        "由引擎自动建立，范围查询仍走叶子链表。\n"
        "- 能解释「单表不要超过 2000 万行」这一经验值的来源与前提：它由行大小与树高共同决定，"
        "行变窄时这个阈值会相应抬高，不是固定常数。\n"
        "- 知道 MySQL Memory 引擎支持显式 HASH 索引；并了解 LSM-Tree（LevelDB / RocksDB）"
        "走的是「顺序写换写吞吐」的另一条路线，取舍方向不同。\n"
        "- 能把实际的 SQL（如按 create_time 做 between + order by + limit）与"
        "「叶子链表 + 顺序读」直接挂钩，说明会用联合索引与覆盖索引消灭回表。\n"
        "- 延伸阅读：为什么 MySQL 采用 B+ 树作为索引（小林 coding）；MySQL 数据页与页分裂机制。"
    ),
    "雷区": (
        "1. **「哈希等值 O(1) 所以整体最快」**——最典型的翻车点，只盯等值忽略了范围与排序；"
        "真实业务里范围/排序占比常不低（本题 25%），一旦有 between/order by，哈希直接退化成全表扫描。\n"
        "2. **「B 树命中非叶子就返回所以更快」**——那只是个别查询的偶然加速，代价是查询延迟不稳定，"
        "同时牺牲了扇出（树更高）与范围查询能力，总体得不偿失。\n"
        "3. **把 B+ 树高度当成固定值**——高度取决于索引项大小与行大小，"
        "不存在「千万级一定 3 层」这种结论，必须给出推导过程。\n"
        "4. **低估 UUID 主键的危害**——不只是「稍微慢一点」，页分裂会造成碎片与写放大，"
        "并拖累整个索引结构的紧凑度，进而影响读性能。\n"
        "5. 混淆 InnoDB 自适应哈希索引（AHI）与「哈希索引是 B+ 树的替代方案」。"
    ),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(BANK, encoding="utf-8") as f:
        data = json.load(f)
    items = {it["id"]: it for it in data["items"]}

    missing = [i for i in MERGE_IDS + [ANCHOR] if i not in items]
    if missing:
        print(f"[error] 缺失题: {missing}")
        return

    anchor = items[ANCHOR]
    merged_from = [ANCHOR] + MERGE_IDS

    # 汇总 sources / wiki 溯源（去重保序）
    srcs = []
    wiki = anchor.get("wiki_node_token") or ""
    for i in merged_from:
        for s in items[i].get("sources") or []:
            if s not in srcs:
                srcs.append(s)
        w = items[i].get("wiki_node_token")
        if w and not wiki:
            wiki = w

    tags = ["Mysql", "索引结构（重要）", "B+树", "索引选型", "综合题"]
    difficulty = "★★★"

    new_item = dict(anchor)
    new_item.update({
        "content": CONTENT,
        "type": items[ANCHOR].get("type", "问答"),
        "difficulty": difficulty,
        "tags": tags,
        "answer": ANSWER,
        "sources": srcs,
        "merged_from": merged_from,
        "sub_questions": SUBQ,
        "wiki_node_token": wiki,
        "wiki_url": items[ANCHOR].get("wiki_url"),
    })

    print(f"[plan] 删除 {MERGE_IDS}")
    print(f"[plan] 保留并改写 {ANCHOR} -> 综合大题")
    print(f"[plan] 题库 {len(data['items'])} -> {len(data['items']) - len(MERGE_IDS)}")
    print(f"[plan] 新答案长度 简版={len(ANSWER['简版'])} 展开={len(ANSWER['展开'])} "
          f"加分点={len(ANSWER['加分点'])} 雷区={len(ANSWER['雷区'])}")

    if not args.apply:
        print("[info] dry-run，未写库。确认后加 --apply")
        return

    bak = BANK + ".bak_" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(BANK, bak)
    print(f"[backup] {bak}")

    kept = [it for it in data["items"] if it["id"] not in MERGE_IDS]
    for idx, it in enumerate(kept):
        if it["id"] == ANCHOR:
            kept[idx] = new_item
    data["items"] = kept
    data["meta"]["total"] = len(kept)
    data["meta"]["last_merged"] = {
        "merged_into": ANCHOR,
        "merged_from": merged_from,
        "reason": "B+树对比考点整合为综合大题",
        "date": time.strftime("%Y-%m-%d"),
    }

    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[write] 已写回，题库 {len(kept)} 题")

    # 校验
    with open(BANK, encoding="utf-8") as f:
        chk = json.load(f)
    ids = [it["id"] for it in chk["items"]]
    print(f"[verify] 题数 {len(ids)} | 唯一 id {len(set(ids))} | meta.total={chk['meta']['total']}")
    print(f"[verify] 已删除项是否全部消失: {all(i not in ids for i in MERGE_IDS)}")
    print(f"[verify] 综合题存在: {ANCHOR in ids}")
    print(f"[done] 备份 {bak}")


if __name__ == "__main__":
    main()
