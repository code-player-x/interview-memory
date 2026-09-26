"""Conservative answer layout: preserve prose, split explicit lists, protect code.

This is deliberately not a summarizer. Only the separately reviewed Agent
answer changes wording; the general formatter only adds layout/Markdown.
"""
from __future__ import annotations

import re


AGENT_TITLE = "介绍一下 Agent 的核心组件，以及它和普通 LLM 应用的核心区别是什么？"
# Workflow/agent control-flow distinction cross-checked against:
# https://www.anthropic.com/engineering/building-effective-agents
AGENT_ANSWER = """**核心组件：按职责理解为五部分**

1. **LLM（推理内核）**：理解目标、推理当前状态，并决定下一步行动。
2. **Memory（记忆与状态）**：保存本轮任务状态、会话历史；需要跨会话复用的信息可放入长期记忆，并按需取回上下文。
3. **Tools（工具）**：提供搜索、计算、读写等外部能力，可通过函数、API 或 MCP 接入。
4. **Planner（规划）**：拆分任务、安排步骤，并根据反馈调整计划。它可以由同一个 LLM 实现，不一定是独立模块。
5. **Executor（执行器）**：执行工具调用、更新任务状态，并把结果或错误反馈给模型，推动下一轮决策。

这是一种便于理解的职责划分，并非所有 Agent 都必须有五个独立模块。Reflection（反思与自我修正）可作为可选策略融入规划或执行后的检查，不必再算作必需的“第六组件”。

**与普通 LLM 应用的核心区别**

- **普通调用或固定工作流**：可以是一次问答，也可以包含多次模型调用和工具调用，但执行路径主要由预先编写的代码决定。
- **Agent**：由模型根据目标、当前状态和环境反馈动态决定下一步，在“观察—决策—行动—再观察”的循环中推进任务。

判断重点是模型是否参与控制后续行动，而不只是“有没有调用工具”。固定工作流同样可以循环，因此也不能仅凭存在循环来判定。

**工程上需要注意三点**

1. **终止条件**：设置最大步数、超时、成本预算和明确的完成条件，防止无效循环。
2. **可观测性**：记录关键决策、工具输入输出、错误和耗时，便于回放与定位问题。
3. **人工确认**：对不可逆或高风险操作设置权限检查与 human-in-the-loop，必要时暂停并请求确认。"""

_CN = "一二三四五六七八九十"
_ENUM = re.compile(
    r"(?P<arabic>[1-9]\d?)(?:[.)）](?=\s|[^\d\x00-\x7f])|[、：:])\s*"
    r"|第(?P<ordinal>[一二三四五六七八九十])(?P<suffix>步|点|是|[，、])"
    r"|(?P<chinese>[一二三四五六七八九十])(?P<ending>是|、)"
)
_BLOCK = re.compile(r"^(?:\s{4}|\t|\s*(?:[-*+] |\d+[.)、] |>|#|\||\$\$))")
_TRANSITION = re.compile(
    r"(?:因此|所以|总之|总体|总结|实际|实践|工程上|需要注意|注意|最后|"
    r"核心区别|两者|它和|它与|最容易|常见误区|适用场景|选型|修复上|例如|举例|例子|"
    r"回答结构|通俗类比|从概念|从实现|分层关系)"
)


def _surface(text: str) -> str:
    """Same-length mask of inline literals and parenthesized/quoted examples."""
    masked = list(text)
    # Do not split examples inside code, links, URLs, or inline math.
    for match in re.finditer(r"(`+)[\s\S]*?\1|!?\[[^\]\n]*\]\([^\n]*?\)|https?://\S+|\$[^$\n]+\$", text):
        masked[match.start():match.end()] = " " * len(match[0])
    stack = []
    pairs = {"（": "）", "(": ")", "[": "]", "{": "}", "「": "」", "『": "』", "“": "”", "《": "》"}
    for i, char in enumerate(masked):
        if char in pairs:
            stack.append(pairs[char])
            masked[i] = " "
        elif stack:
            masked[i] = " "
            if char == stack[-1]:
                stack.pop()
    return "".join(masked)


def _paragraphs(text: str) -> str:
    """Break long prose at sentence ends, preferably at a change of topic."""
    surface = _surface(text)
    parts, start = [], 0
    for end in re.finditer(r"[。！？](?:\s*)", surface):
        stop = end.end()
        if stop == len(text):
            continue
        if stop - start >= 140 or _TRANSITION.match(surface[stop:]):
            parts.append(text[start:stop].strip())
            start = stop
    parts.append(text[start:].strip())
    return "\n\n".join(filter(None, parts))


def _enumeration(text: str) -> str | None:
    surface = _surface(text)
    groups = []
    for match in _ENUM.finditer(surface):
        before = surface[:match.start()].rstrip()
        if before and before[-1] not in "。；;：:！？!?" and not (match['arabic'] and surface[match.start() - 1].isspace()):
            continue
        if match['arabic']:
            number, kind = int(match['arabic']), 'arabic'
        else:
            number = _CN.index(match['ordinal'] or match['chinese']) + 1
            kind = (match['suffix'] or match['ending']) + ('第' if match['ordinal'] else '')
        if groups and groups[-1][-1][1:] == (number - 1, kind):
            groups[-1].append((match, number, kind))
        elif number == 1:
            groups.append([(match, number, kind)])
    valid = [group for group in groups if len(group) >= 2]
    if not valid:
        return None
    group = valid[0]
    start = group[0][0].start()
    stops = [entry[0].start() for entry in group[1:]] + [len(text)]
    items = [text[entry[0].start():stop].strip() for entry, stop in zip(group, stops)]
    # Keep explanations with their item; detach only a signposted conclusion.
    tail = ""
    last_surface = _surface(items[-1])
    candidates = []
    for sentence in re.finditer(r"[。！？]\s*", last_surface):
        if _TRANSITION.match(last_surface[sentence.end():]):
            candidates.append(sentence.end())
            break
    # A second numbered sequence belongs to a separate paragraph/list.
    if len(valid) > 1:
        split = valid[1][0][0].start() - group[-1][0].start()
        # Include the next list's introductory sentence in its prose prefix.
        sentences = list(re.finditer(r"[。！？]\s*", last_surface[:split]))
        candidates.append(sentences[-1].end() if sentences else split)
    if candidates:
        split = min(candidates)
        tail, items[-1] = items[-1][split:].strip(), items[-1][:split].strip()
    prefix = text[:start].strip()
    listing = "\n".join(("" if re.match(r"\d+[.)] ", item) else "- ") + item for item in items)
    return "\n\n".join(filter(None, [_prose(prefix), listing, _prose(tail)]))


def _parallel_clauses(text: str) -> str | None:
    surface = _surface(text)
    # Only an uninterrupted sentence containing 3+ substantial semicolon
    # clauses is clearly a parallel list. Never split commas or code syntax.
    boundaries = [0] + [m.end() for m in re.finditer(r"[。！？]\s*", surface)] + [len(text)]
    run = next(((a, b) for a, b in zip(boundaries, boundaries[1:]) if len(re.findall(r"[；;]", surface[a:b])) >= 2), None)
    if run is None:
        return None
    start, end = run
    stops = [start + m.end() for m in re.finditer(r"[；;]", surface[start:end])]
    parts = [text[a:b].strip() for a, b in zip([start] + stops, stops + [end])]
    if min(map(len, parts)) < 10:
        return None
    intro = ""
    colon = re.search(r"[：:]", _surface(parts[0]))
    if colon and colon.start() <= 28 and re.search(r"(?:包括|如下|分为|要点|有|方面|步骤)[^。]*[：:]$", parts[0][:colon.end()]):
        intro, parts[0] = parts[0][:colon.end()], parts[0][colon.end():].strip()
    if not parts[0]:
        return None
    return "\n\n".join(filter(None, [_prose(text[:start].strip()), intro, "\n".join("- " + part for part in parts), _prose(text[end:].strip())]))


def _sections(text: str) -> str | None:
    surface = _surface(text)
    markers = list(re.finditer(r"(?:^|(?<=[\s。；]))([一二三四五六七八九十])、", surface))
    if len(markers) < 2 or [m[1] for m in markers] != list(_CN[:len(markers)]):
        return None
    parts = [_prose(text[:markers[0].start()].strip())]
    for match, end in zip(markers, [m.start() for m in markers[1:]] + [len(text)]):
        section = text[match.start():end].strip()
        # Spaces can belong to titles (e.g. HTTP 与 HTTPS), not just delimiters.
        # Only explicit punctuation or the start of a list reliably ends one.
        boundary = re.search(r"[：:]|(?=\s+\d+[.)、]\s)", _surface(section))
        if not boundary or boundary.start() > 40:
            return None
        stop = boundary.end()
        parts.extend(["**" + section[:stop].strip() + "**", _prose(section[stop:].strip())])
    return "\n\n".join(filter(None, parts))


def _inline_bullets(text: str) -> str | None:
    markers = list(re.finditer(r"(?<!\S)- (?=[^：:。\n]{1,30}[：:])", _surface(text)))
    if len(markers) < 2:
        return None
    parts = [text[m.start():end].strip() for m, end in zip(markers, [m.start() for m in markers[1:]] + [len(text)])]
    tail = ""
    surface = _surface(parts[-1])
    for sentence in re.finditer(r"[。！？]\s*", surface):
        if _TRANSITION.match(surface[sentence.end():]):
            tail, parts[-1] = parts[-1][sentence.end():].strip(), parts[-1][:sentence.end()].strip()
            break
    return "\n\n".join(filter(None, [_prose(text[:markers[0].start()].strip()), "\n".join(parts), _prose(tail)]))


def _collapsed_list(text: str) -> str:
    """A scraper may collapse an entire Markdown list onto one physical line."""
    if text.startswith("- "):
        return _inline_bullets(text) or text
    numbered = re.match(r"^(\d+[.)] )(.*)$", text)
    if numbered:
        sequence = _enumeration(text)
        if sequence:
            return sequence
        children = _inline_bullets(numbered[2])
        if children:
            return re.sub(r"(?m)^ +$", "", numbered[1] + children.replace("\n", "\n  "))
    return text


def _prose(text: str) -> str:
    if len(text) < 70 or len(re.findall(r"[\u4e00-\u9fff]", text)) < 10:
        return text
    # Existing standalone bold section labels should not share a prose line.
    label = re.match(r"^(\*\*[^*\n]{1,35}[：:]\*\*)\s*(.+)$", text)
    if label:
        return label[1] + "\n\n" + _prose(label[2])
    return _sections(text) or _inline_bullets(text) or _enumeration(text) or _parallel_clauses(text) or _paragraphs(text)


def _structure_once(answer: str) -> str:
    lines, fence = [], None
    for line in answer.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not stripped[marker.end():].strip():
                fence = None
            lines.append(line)
        elif fence:
            lines.append(line)
        else:
            body = line.rstrip("\r\n")
            formatted = _collapsed_list(body) if _BLOCK.match(line) else _prose(body)
            lines.append(formatted + line[len(body):])
    return "".join(lines)


def structure_answer(answer: str) -> str:
    """Idempotent, lossless layout for prose; keep existing blocks untouched."""
    while True:
        result = _structure_once(answer)
        if result == answer:
            return result
        answer = result
