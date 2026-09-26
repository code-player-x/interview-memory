"""Answer layout must preserve information, code and learning records."""
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawler" / "questions_v2"))
from answer_structure import AGENT_ANSWER, structure_answer  # noqa: E402
from scripts.format_question_answers import format_database  # noqa: E402


def test_chinese_enumeration_is_a_list_with_separate_conclusion():
    answer = (
        "工程上需要关注以下三件事情：一是给循环设置最大步数和超时，避免一直执行；"
        "二是记录每一步工具调用的输入输出和执行耗时，方便定位错误；"
        "三是为高风险操作增加人工确认，控制执行权限。"
        "因此，需要同时设计可靠性与权限边界，而不是只增加工具数量。"
    )
    result = structure_answer(answer)
    assert len(re.findall(r"(?m)^- ", result)) == 3
    assert "\n\n因此" in result
    assert structure_answer(result) == result


def test_parallel_information_types_and_existing_lists():
    answer = (
        "可以按用途划分三类信息。工作状态保存当前目标、步骤、已确认参数和中间结果，适合结构化表示；"
        "会话历史保存消息与工具交互，保证多轮连贯并支持回查；长期记忆保存跨会话仍有价值的偏好、事实和经验。"
    )
    result = structure_answer(answer)
    assert result.startswith("可以按用途划分三类信息。\n\n- 工作状态")
    assert len(re.findall(r"(?m)^- ", result)) == 3
    existing = "**组件**\n\n1. LLM：推理。\n2. Tools：执行。\n\n**边界**\n\n- 可按需组合。"
    assert structure_answer(existing) == existing


def test_fences_inline_literals_tables_and_quoted_examples_are_untouched():
    answer = """```python
# 1. 先创建一个列表；2. 记录列表内容；3. 输出结果。
print("第一步。第二步。", [1, 2, 3])
```
~~~sql
SELECT '一是不要修改；二是不要丢失；三是保持代码';
~~~

| 第一列 | 第二列 |
| --- | --- |
| 一是原文；二是原文；三是原文 | 3.14 |

示例 `1) 调用函数；2) 处理结果；3) 返回答案` 是行内代码，公式 $a；b；c$ 和（第一，先观察；第二，再处理；第三，返回结果）都不是正文的枚举，不能据此改变代码或公式。
"""
    result = structure_answer(answer)
    for block in re.findall(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`|\$[^$\n]+\$", answer):
        assert block in result
    assert result == answer


def test_reviewed_agent_has_exactly_five_components_and_three_safety_items():
    components, rest = AGENT_ANSWER.split("这是一种便于理解")
    assert len(re.findall(r"(?m)^\d\. ", components)) == 5
    assert len(re.findall(r"(?m)^\d\. ", rest)) == 3
    assert "不必再算作必需的“第六组件”" in rest


def test_section_titles_with_spaces_are_not_cut_at_english_terms():
    text = "一、HTTP 与 HTTPS 的区别：" + "这里解释协议的区别及使用限制。" * 3 + " 二、HTTPS 的好处：" + "这里解释传输安全的保证与边界。" * 3
    result = structure_answer(text)
    assert "**一、HTTP 与 HTTPS 的区别：**" in result
    assert "**二、HTTPS 的好处：**" in result
    assert "**一、HTTP**" not in result
    assert structure_answer(result) == result
    unclear = "一、HTTP 与 HTTPS 的区别 " + "这里没有可靠的标题结束标志。" * 3 + " 二、HTTPS 的好处 " + "这里也没有明确的分隔符。" * 3
    assert "**一、HTTP**" not in structure_answer(unclear)


def test_collapsed_lists_starting_at_column_zero_are_expanded():
    answer = "- 镜像：可交付的运行环境。 - 容器：镜像运行后的实例。 - 仓库：保存和分发镜像。"
    assert structure_answer(answer).splitlines() == [
        "- 镜像：可交付的运行环境。", "- 容器：镜像运行后的实例。", "- 仓库：保存和分发镜像。",
    ]
    numbered = "1. 数据类别： - 文章：按标题分块。 - 代码：按函数分块。 2. 处理阶段： - 清理：去除无效内容。 - 嵌入：向量化并保留元数据。"
    result = structure_answer(numbered)
    assert "\n2. 处理阶段" in result
    assert "\n  - 文章" in result
    assert structure_answer(result) == result


def test_entire_corpus_layout_is_idempotent_and_content_preserving():
    # Only Markdown decoration and whitespace may be added by the general rule.
    normalize = lambda s: re.sub(r"[\s*\-]", "", s)
    for source in (ROOT / "crawler/questions_v2/authored").glob("*.jsonl"):
        if source.name.startswith("_"):
            continue
        for line in source.read_text().splitlines():
            row = json.loads(line)
            old = row["answer"]
            new = structure_answer(old)
            assert normalize(new) == normalize(old), row["id"]
            assert structure_answer(new) == new, row["id"]


def test_database_reformat_is_in_place_backed_up_and_repeatable(tmp_path):
    path = tmp_path / "library.db"
    old = "正文的内容应当保留。" * 30
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE questions (id INTEGER PRIMARY KEY, platform TEXT, question_text TEXT, reference_answer TEXT, tags TEXT);
            CREATE TABLE question_notes (question_id INTEGER, content TEXT);
            INSERT INTO question_notes VALUES (7, '不能丢失的笔记');
        """)
        conn.executemany("INSERT INTO questions VALUES (?, ?, ?, ?, ?)", [
            (7, "questions_v2", "已有自定义补充的题目", old, "原始标签"),
            (8, "manual", "手工添加的题目", old, "保留"),
        ])
    assert format_database(path)["changed"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT reference_answer FROM questions WHERE id=7").fetchone()[0] == old
    report = format_database(path, write=True)
    assert report["written"] and Path(report["backup"]).exists()
    with sqlite3.connect(report["backup"]) as conn:
        assert conn.execute("SELECT reference_answer FROM questions WHERE id=7").fetchone()[0] == old
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id, tags FROM questions ORDER BY id").fetchall() == [(7, "原始标签"), (8, "保留")]
        assert conn.execute("SELECT * FROM question_notes").fetchall() == [(7, "不能丢失的笔记")]
        assert conn.execute("SELECT reference_answer FROM questions WHERE id=8").fetchone()[0] == old
    assert format_database(path, write=True)["changed"] == 0
