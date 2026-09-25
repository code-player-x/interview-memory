"""Regression checks for deterministic corpus cleanup helpers."""
import sys
import json
import re
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


def test_followup_corrections_preserve_ids_and_rendered_domains():
    authored = CURATION_DIR / "authored"
    rendered = CURATION_DIR / "full_v2"
    rows = {}
    for source in authored.glob("*.jsonl"):
        if source.name.startswith("_"):
            continue
        items = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        markdown = (rendered / f"{source.stem}.md").read_text(encoding="utf-8")
        assert re.findall(r"原题 ID：`([^`]+)`", markdown) == [item["id"] for item in items]
        for item in items:
            assert item["id"] not in rows
            rows[item["id"]] = (source.stem, item)

    assert len(rows) == 2586
    assert all(rows[qid][0] == "redis" for qid in ("q0411", "q0412", "q0413"))
    assert rows["q0583"][0] == "mysql"
    assert "score < :last_score" in rows["q0583"][1]["answer"]
    assert "默认值是 1" in rows["q0413"][1]["answer"]
    assert "并非“零拷贝”" in rows["q0007"][1]["answer"]
    assert all("<cite" not in item["answer"] for _, item in rows.values())
