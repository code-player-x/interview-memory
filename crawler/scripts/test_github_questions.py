"""Offline coverage for extracting GitHub Markdown into the existing shortlist."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import process_source


class GitHubQuestionsTests(unittest.TestCase):
    def test_question_headings_inline_answers_and_coding_lists(self):
        markdown = '''### Q1.2 TP=2 时的显存如何变化？⭐⭐⭐ [​](#q1-2-tp)
- **"PagedAttention 减少计算量吗？"** ❌ 不减，优化的是显存。
1. torch.repeat 与 torch.expand 的内存行为有何差异？
## CUDA 编程题
1. 向量化实现 elementwise 乘法
2. 给定 A[i] = B[i]，设计一个融合算子
## PyTorch 编程题
1. 实现 LoRA Adapter
## 解答
1. 这里是计算步骤
'''
        self.assertEqual(list(process_source.markdown_questions(markdown)), [
            "TP=2 时的显存如何变化？", "PagedAttention 减少计算量吗？",
            "torch.repeat 与 torch.expand 的内存行为有何差异？", "向量化实现 elementwise 乘法",
            "给定 A[i] = B[i]，设计一个融合算子", "实现 LoRA Adapter",
        ])

    def test_markdown_prompts_and_false_positives(self):
        text = """## 3. **Q1：解释 KV Cache 的内存布局**
- How does continuous batching work?
2. 请介绍一种推理服务的调度策略。
3. 延迟随并发上升而增长？给出可能的原因。
> 说说 CUDA 的内存模型
- [为什么需要分页？](#paging)
答案：为什么会有这个现象？
````python
```
# 什么是示例代码里的问题？
````
    What is an indented code example?
"""
        self.assertEqual(list(process_source.markdown_questions(text)), [
            "解释 KV Cache 的内存布局", "How does continuous batching work?",
            "请介绍一种推理服务的调度策略。", "延迟随并发上升而增长？给出可能的原因。", "说说 CUDA 的内存模型",
        ])

    def test_sources_survive_dedup(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "data" / "tmp" / "github"
            output.mkdir(parents=True)
            bank = root / "data" / "questions-bank.json"
            bank.write_text('{"items":[]}', encoding="utf-8")
            urls = ["https://github.com/org/repo/blob/abc/a.md",
                    "https://github.com/org/repo/blob/abc/b.md"]
            rows = [json.dumps({"url": url, "date": "2000-01-01", "text": "- 为什么需要 KV Cache？"})
                    for url in urls]
            for path in ["manuscripts/00-前言.md", "目录.md", "archive/table-of-contents.md"]:
                rows.append(json.dumps({"url": urls[0], "path": path, "text": "如何阅读本书？"}))
            (output / "posts.jsonl").write_text("\n".join(rows), encoding="utf-8")
            with patch.object(process_source, "BASE", root), patch.object(process_source, "BANK", bank):
                self.assertEqual(process_source.process("github"), 1)
            question = json.loads((output / "refined.jsonl").read_text(encoding="utf-8"))
            self.assertCountEqual(question["sources"], urls)
            self.assertEqual(question["src_count"], 2)

            # A clean checkout contains the authored JSONL files and no local master bank.
            bank.unlink()
            authored = root / "questions_v2" / "authored"
            authored.mkdir(parents=True)
            (authored / "llm-basics.jsonl").write_text(
                json.dumps({"title": question["question"]}), encoding="utf-8")
            (authored / "_draft.jsonl").write_text("unpublished", encoding="utf-8")
            with patch.object(process_source, "BASE", root), patch.object(process_source, "BANK", bank):
                self.assertEqual(process_source.process("github"), 0)
            self.assertEqual((output / "refined.jsonl").read_text(encoding="utf-8"), "")

    def test_cached_levels_match_both_original_thresholds(self):
        keys = ["abcdefghij", "tide", "1234567890"]  # difflib can be asymmetric
        matcher = process_source.BankMatcher(keys)
        for q in ["abcdefghij", "abcdefghi", "abcdefghxxxx", "diet", "xyz", "abcdefghxxxx"]:
            with self.subTest(q=q):
                level = matcher.match_level(q)
                for threshold in [process_source.SIM, process_source.STRICT]:
                    expected = any(process_source.similar(q, key) >= threshold for key in keys)
                    self.assertEqual(level >= threshold, expected)
