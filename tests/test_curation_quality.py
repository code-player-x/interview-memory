"""Regression checks for deterministic corpus cleanup helpers."""
import sys
from pathlib import Path


CURATION_DIR = Path(__file__).resolve().parents[1] / "crawler" / "questions_v2"
if str(CURATION_DIR) not in sys.path:
    sys.path.insert(0, str(CURATION_DIR))

from curate_full_v2 import collapse_accidental_leading_repeat  # noqa: E402


def test_collapse_only_an_exact_adjacent_leading_repeat():
    repeated = (
        "开头这句话足够长，用来模拟抓取器重复拼接的正文。"
        "开头这句话足够长，用来模拟抓取器重复拼接的正文。"
        "后续说明仍应保留。"
    )
    assert collapse_accidental_leading_repeat(repeated) == (
        "开头这句话足够长，用来模拟抓取器重复拼接的正文。后续说明仍应保留。"
    )

    expanded = "这是一个简短结论，后面会用不同措辞展开。后续内容并不重复，应保留。"
    assert collapse_accidental_leading_repeat(expanded) == expanded
