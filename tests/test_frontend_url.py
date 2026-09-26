"""Exercise the browser's URL allow-list without loading the full DOM app."""

import shutil
import subprocess
from pathlib import Path

import pytest


APP_JS = Path(__file__).resolve().parents[1] / "frontend" / "app.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_memorization_share_action_stays_with_question_tags():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function memRender() {');
const end = source.indexOf('function memPrev() {', start);
assert(start >= 0 && end > start);
const elements = {};
const state = {idx: 0, total: 2, loading: false, items: [
  {id: 1, category: 'Agent', question_text: '第一题'},
  {id: 42, category: 'Frontend', question_text: '第二题'},
]};
const render = vm.runInNewContext(source.slice(start, end) + '; memRender', {
  mem: state,
  document: {getElementById: id => elements[id] ||= {}},
  diffMeta: () => ({cls: 'easy', label: '简单'}),
  splitKeywords: () => [], escapeHtml: s => s,
  curatedTagsHtml: () => "<span class='tag'>高频</span>",
  renderInlineMarkdown: s => s, renderMarkdown: s => s,
  memNoteLoad: () => {},
});
(async () => {
  for (state.idx = 0; state.idx < state.total; state.idx++) {
    await render();
    const html = elements.memCard.innerHTML;
    const tags = html.match(/<div class='mem-tags'>([\s\S]*?)<\/div>/)[1];
    assert(tags.includes("class='mem-share'"), 'Share belongs in the tags row');
    assert(tags.includes("type='button'"));
    assert(tags.includes("data-qid='" + state.items[state.idx].id + "'"));
    assert(tags.includes("onclick='copyShareLink(this)'"));
    assert.equal((html.match(/class='mem-share'/g) || []).length, 1);
    assert(!html.includes("class='mem-stats'"), 'No separate share-only row');
  }
})().catch(err => { console.error(err); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", script, str(APP_JS)], check=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_uploaded_local_image_url_is_allowed_without_opening_other_paths():
    script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("function _safeUrl(u) {");
const end = source.indexOf("function _safeUrlAttr(u) {", start);
if (start < 0 || end < 0) throw new Error("_safeUrl not found");
const safeUrl = vm.runInNewContext(source.slice(start, end) + "; _safeUrl");
const name = "a".repeat(32) + ".png";
const cases = [
  ["/data/images/" + name, "/data/images/" + name],
  ["/data/images/../wrong_book_export.pdf", "#"],
  ["/data/wrong_book_export.pdf", "#"],
  ["javascript:alert(1)", "#"],
  ["https://example.com/image.png", "https://example.com/image.png"],
];
for (const [input, expected] of cases) {
  if (safeUrl(input) !== expected) throw new Error(input + " => " + safeUrl(input));
}
"""
    subprocess.run(["node", "-e", script, str(APP_JS)], check=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_existing_fenced_code_and_copy_payload_are_not_rewrapped():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const api = vm.runInNewContext(source.slice(0, source.indexOf('const TITLES =')) + ';({renderMarkdown, _wrapIndentedCode})', {window:{}});
const code = 'def f():\n    x = 1\n    return x';
const fence = '```python\n' + code + '\n```';
assert.equal(api._wrapIndentedCode(fence), fence);
const html = api.renderMarkdown(fence + '\n\n正文。\n\n' + fence);
assert.equal((html.match(/md-code-block/g) || []).length, 2);
assert(html.includes("data-c='" + code + "'"));
assert(!html.includes('```'));
assert(html.includes("<p class='md-p'>正文。</p>"));
assert(api._wrapIndentedCode('    x = 1\n    return x\n').startsWith('```'));
const root = require('path').resolve(require('path').dirname(process.argv[1]), '../crawler/questions_v2/authored');
for (const f of fs.readdirSync(root).filter(f => f.endsWith('.jsonl'))) {
  for (const line of fs.readFileSync(root + '/' + f, 'utf8').trim().split('\n')) {
    const row = JSON.parse(line);
    for (const match of row.answer.matchAll(/```[^\n]*\n[\s\S]*?```/g)) {
      assert.equal(api._wrapIndentedCode(match[0]), match[0], row.id);
    }
  }
}
"""
    subprocess.run(["node", "-e", script, str(APP_JS)], check=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_answer_sections_lists_and_code_render_without_swallowing_text():
    script = r"""
const fs = require("fs");
const vm = require("vm");
const assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
const renderer = vm.runInNewContext(source.slice(0, source.indexOf("const TITLES =")) + "; renderMarkdown", {window: {}});
const html = renderer("**五个组件**\n\n1. **LLM**：推理。\n2. Memory：状态。\n3. Tools：工具。\n4. Planner：规划。\n5. Executor：执行。\n\n**区别**\n\n- 固定工作流。\n- 模型动态决策。\n\n**注意事项**\n\n1. 超时。\n2. 观测。\n3. 审批。");
assert.equal((html.match(/<ol /g) || []).length, 2);
assert.equal((html.match(/<ul /g) || []).length, 1);
assert.equal((html.match(/<li>/g) || []).length, 10);
assert.equal((html.match(/class='md-section'/g) || []).length, 3);
assert(html.includes("</ol><p class='md-section'><strong>区别</strong>"));
assert(!/<p[^>]*>\s*<(ol|ul|pre|div)/.test(html));
assert(!html.includes(""));
const sections = renderer("这是一段完整解释，用于验证段落之间的空行会被保留。\n\n**与普通应用的区别**\n\n这是下一段的独立解释。\n\n**工程注意事项**\n\n1. 第一点。\n2. 第二点。");
assert.equal((sections.match(/class='md-section'/g) || []).length, 2);
assert(sections.includes("空行会被保留。</p><p class='md-section'>"));
const two = renderer("1. 第一个选项。\n\n2. 第二个选项。\n\n独立结论。");
assert.equal((two.match(/<ol /g) || []).length, 1);
assert(two.includes("</ol><p class='md-p'>独立结论。"));
const nested = renderer("- 第一层\n  - 第二层\n  - 同级\n- 另一项");
assert.equal((nested.match(/<ul /g) || []).length, 2);
assert.equal((nested.match(/<li>/g) || []).length, 4);
const code = renderer("**代码**\n\n```python\nprint('1. 不是列表；2. 不是列表；3. 不是列表')\n```\n\n<script>alert(1)</script>");
assert(code.includes("md-code-block"));
assert(!code.includes("<ol "));
assert(!code.includes("<script>"));
assert(code.includes("&lt;script&gt;"));
const legacy = renderer("要点：1) 第一个要点；2) 第二个要点；3) 第三个要点");
assert(legacy.includes("<ol class='md-pretty'>"));
"""
    subprocess.run(["node", "-e", script, str(APP_JS)], check=True)
