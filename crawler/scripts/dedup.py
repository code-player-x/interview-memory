#!/usr/bin/env python3
"""去重：新题 vs 本地镜像(bank) 的相似度计算。
不依赖飞书语义搜——lark-unified 仅关键词检索，语义去重由本脚本 + 智能体 LLM 判重完成。
阈值：>=0.85 已有；[0.70,0.85) 待复核；<0.70 新题。
"""
import json
import sys
from difflib import SequenceMatcher

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
import bank

# 若环境装了 sentence-transformers 可启用 embedding 余弦（更准），否则退回 difflib 代理。
try:
    from sentence_transformers import SentenceTransformer
    _MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    _EMBED_OK = True
except Exception:
    _MODEL = None
    _EMBED_OK = False

THRESHOLD_EXIST = 0.85
THRESHOLD_REVIEW = 0.70


def _cosine(a, b):
    import numpy as np
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def similarity(text_a: str, text_b: str) -> float:
    if _EMBED_OK:
        ea, eb = _MODEL.encode([text_a, text_b], normalize_embeddings=True)
        return _cosine(ea, eb)
    # 代理：题面归一化后的比值，对长文本/改写较敏感，建议配合 LLM 判重交叉校验
    return SequenceMatcher(None, bank.normalize(text_a), bank.normalize(text_b)).ratio()


def check(new_content: str, first_run: bool = False):
    """返回 {status, best, candidates}。candidates: [{id, score}]"""
    data = bank.load()
    items = data["items"]
    norm_new = bank.normalize(new_content)
    cands = []
    for it in items:
        # 精确归一化一致 -> 直接已有
        if it.get("norm") == norm_new:
            return {"status": "已有", "best": 1.0, "candidates": [{"id": it["id"], "score": 1.0}]}
        s = similarity(new_content, it.get("content", ""))
        cands.append({"id": it["id"], "score": round(s, 3)})
    cands.sort(key=lambda x: -x["score"])
    best = cands[0]["score"] if cands else 0.0
    if best >= THRESHOLD_EXIST:
        status = "已有"
    elif best >= THRESHOLD_REVIEW:
        # 首批(first_run)强制人工复核；之后全自动判已有
        status = "待复核" if first_run else "已有"
    else:
        status = "新增"
    return {"status": status, "best": best, "candidates": cands[:5]}


if __name__ == "__main__":
    # 用法：echo "题面" | python dedup.py   或  python dedup.py "题面"
    first_run = "--first" in sys.argv
    text = sys.stdin.read().strip() if not sys.argv[1:] or first_run and len(sys.argv) == 2 \
        else sys.argv[1]
    print(json.dumps(check(text, first_run), ensure_ascii=False, indent=2))
