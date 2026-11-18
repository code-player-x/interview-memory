// Isolated behavior checks. No server, database, browser dependencies, or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const elements = new Map();
function element() {
  const classes = new Set();
  return {
    innerHTML: '', textContent: '', value: '', disabled: false, style: {},
    classList: {
      add: name => classes.add(name), remove: name => classes.delete(name),
      toggle(name, forced = !classes.has(name)) { if (forced) classes.add(name); else classes.delete(name); },
      contains: name => classes.has(name),
    },
    querySelectorAll: () => [], appendChild() {}, setAttribute() {}, focus() {},
    addEventListener(type, callback) { this["on" + type] = callback; },
  };
}
const sandbox = {
  document: {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    querySelector: () => element(), querySelectorAll: () => [], createElement: element,
  },
  setInterval: () => 1, clearInterval() {}, setTimeout() {}, clearTimeout() {},
  alert() {}, confirm: () => true, Date, console, AbortController,
  crypto: require('node:crypto').webcrypto,
  fetch: () => { throw new Error('Unexpected network access'); },
};
vm.createContext(sandbox);
// Exclude DOM event wiring/startup, but execute the production function definitions.
const pomStart = source.indexOf('const pom = {');
const pomEnd = source.indexOf('if (document.readyState === "loading")');
vm.runInContext(source.slice(0, source.indexOf('// 手动添加题目')) + source.slice(pomStart, pomEnd), sandbox);
const run = code => vm.runInContext(code, sandbox);

async function check() {
  const rendered = run(`renderMarkdown('![diagram](/api/images/test.png) [docs](https://example.com?a=1&b=2) **缓存**', ['缓存', 'class', 'https'])`);
  assert.match(rendered, /src='\/api\/images\/test.png'/);
  assert.match(rendered, /href='https:\/\/example.com\?a=1&amp;b=2'/);
  assert.match(rendered, /<strong><mark class='kw'>缓存<\/mark><\/strong>/);
  assert.doesNotMatch(rendered, /src='[^']*<mark|href='[^']*<mark/);
  const malicious = run('renderInlineMarkdown("![` onerror=alert(1)`](https://example.com/x) <script>alert(1)</script>")');
  assert.match(malicious, /alt='` onerror=alert\(1\)`'/);
  assert.doesNotMatch(malicious, /<script>|class='md-code'/);
  assert.match(run(`renderInlineMarkdown('[bad](javascript:alert)')`), /href='#'/);
  assert.match(run(`renderInlineMarkdown('\`**literal**\`')`), /<code class='md-code'>\*\*literal\*\*<\/code>/);
  sandbox.codeAnswer = '```html\n<script>alert("x")</script>\n```';
  const code = run('renderMarkdown(codeAnswer, ["script"])');
  assert.match(code, /<pre class='md-pre'>/);
  assert.match(code, /&lt;script&gt;/);
  assert.doesNotMatch(code, /<script>|<mark/);
  sandbox.codeAnswer = '说明\n\n下一段\n```js\n    const a = 1;\n    const b = 2;\n```\n1) 一；2) 二；3) 三';
  const numbered = run('renderMarkdown(codeAnswer, ["0", "L", "K", "F"])');
  assert.equal((numbered.match(/<pre /g) || []).length, 1, 'an explicit fence must not be wrapped again');
  assert.match(numbered, /<p class='md-p'>说明<\/p><p class='md-p'>下一段/);
  assert.match(numbered, /const b = 2;/);
  assert.match(numbered, /<ol class='md-pretty'><li>/);
  assert.match(run("renderInlineMarkdown('[`name`](https://example.com)')"), /<a [^>]*><code class='md-code'>name<\/code><\/a>/);
  sandbox.codeAnswer = '`[literal]()`';
  assert.doesNotMatch(run('renderMarkdown(codeAnswer)'), /md-link-broken/);

  run('pomRenderTimer = () => {}; pomToast = () => {}; pomApplyModeTheme = () => {}; pomBeep = () => {}; pomLoadStats = async () => {}; pomLoadTodos = async () => {};');
  const calls = [];
  sandbox.fetch = async (url, opts) => {
    calls.push({ url, body: JSON.parse(opts.body) });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  await run('pomToggleTodo(7, true)');
  assert.deepEqual(calls.shift(), { url: '/api/todos/7', body: { done: true } });
  assert.equal(run('pom.running'), false, 'toggling a todo must not start the timer');

  for (const mode of ['short', 'long']) {
    run(`pomSetMode('${mode}', false)`);
    await run('pomPhaseDone()');
    assert.equal(calls.shift().body.kind, 'break');
    assert.equal(run('pom.focusDone'), 0, 'manual breaks must not count as focus');
  }
  run('pomSetMode("focus", false); pom.durations.focus = 99;');
  await run('pomPhaseDone()');
  assert.equal(calls.shift().body.minutes, 25, 'record actual configured session duration');
  assert.equal(run('pom.focusDone'), 1);
  run('pomSetMode("focus", false); pomStart(); pom.deadline = Date.now() + 42000; pomTick();');
  assert.ok(run('pom.remaining') <= 42 && run('pom.remaining') >= 41, 'clock must catch up after throttled callbacks');
  run('pomPause()');

  const checkbox = { checked: true, disabled: false };
  sandbox.checkbox = checkbox;
  sandbox.fetch = async () => ({ ok: false, status: 500, json: async () => ({ detail: 'save failed' }) });
  await run('pomToggleTodo(7, true, checkbox)');
  assert.equal(checkbox.checked, false, 'failed writes must restore checkbox state');
  assert.equal(checkbox.disabled, false);

  await run('loadReview()');
  assert.match(elements.get('reviewList').innerHTML, /复习计划加载失败/);
  assert.doesNotMatch(elements.get('reviewList').innerHTML, /没有待复习/);
  await run('loadSettings()');
  assert.equal(elements.get('saveSettings').disabled, true, 'unloaded settings must not be overwritten with defaults');

  let reviewWrites = 0, completeReview;
  sandbox.fetch = () => {
    reviewWrites++;
    return new Promise(resolve => { completeReview = resolve; });
  };
  const firstReview = run('review(5, true)');
  await run('review(5, true)');
  assert.equal(reviewWrites, 1, 'double click must not advance a review twice');
  completeReview({ ok: false, status: 500, json: async () => ({ detail: 'save failed' }) });
  await firstReview;

  const waiting = [];
  sandbox.fetch = () => new Promise(resolve => waiting.push(resolve));
  const oldRequest = run('bank.keyword = "old"; loadBank()');
  const newRequest = run('bank.keyword = "new"; loadBank()');
  waiting[1]({ ok: true, status: 200, json: async () => ({ total: 12, items: [] }) });
  await newRequest;
  waiting[0]({ ok: true, status: 200, json: async () => ({ total: 99, items: [] }) });
  await oldRequest;
  assert.equal(run('bank.total'), 12, 'stale search response must not replace newer results');

  const oldMem = run('mem.category = "old"; memLoadPage()');
  run('memRequestId++; mem.category = "new"; mem.items = []; mem.offset = 0;');
  waiting[2]({ ok: true, status: 200, json: async () => ({ total: 1, items: [{ id: 99 }] }) });
  await oldMem;
  assert.equal(run('mem.items.length'), 0, 'stale memorization response must not mix categories');

  run('mem.items = [{id: 5}]; mem.idx = 1; mem.total = 2; mem.offset = 1;');
  const shrink = run('memLoadPage()');
  waiting[3]({ ok: true, status: 200, json: async () => ({total: 1, items: []}) });
  await shrink;
  assert.equal(run('mem.idx'), 0, 'shrinking question bank must leave the last cached question reachable');

  const response = payload => ({ ok: true, status: 200, json: async () => payload });
  const requests = [];
  sandbox.fetch = (url, options) => new Promise(resolve => requests.push({ url, options, resolve }));
  run('focusOverlay = () => {}; releaseOverlay = () => {};');
  const firstDetail = run('openDetail(1)');
  const secondDetail = run('openDetail(2)');
  requests[1].resolve(response({ id: 2, question_text: 'second', reference_answer: 'answer 2' }));
  await secondDetail;
  requests[0].resolve(response({ id: 1, question_text: 'first', reference_answer: 'answer 1' }));
  await firstDetail;
  assert.equal(run('currentDetailId'), 2, 'late detail response must not change the selected question');
  const closingDetail = run('openDetail(3)');
  run('closeDetail()');
  requests[2].resolve(response({ id: 3, question_text: 'closed' }));
  await closingDetail;
  assert.equal(run('currentDetailId'), null, 'closed drawer must not reopen on a late response');

  run('currentDetailId = 4; currentDetail = {id: 4, reference_answer: "old"}; enterEditMode();');
  elements.get('dqAnswerEdit').value = 'edited A';
  const save = run('saveAnswerEdit()');
  run('detailVersion++; currentDetailId = 5; currentDetail = {id: 5, reference_answer: "answer B"};');
  requests[3].resolve(response({ reference_answer: 'edited A' }));
  await save;
  assert.equal(run('currentDetail.reference_answer'), 'answer B', 'late edit response must not overwrite another question');

  requests.length = 0;
  run('practice.sessionId++; const firstEntry = {id: 10}; practice.current = firstEntry; practice.loading = false;');
  sandbox.document.getElementById('ua').value = 'answer A';
  const firstAnswer = run('pmSubmit()');
  await run('pmSubmit()');
  assert.equal(requests.length, 1, 'rapid answer clicks must send only one request');
  run('practice.current = {id: 10};'); // Same question in a new round.
  sandbox.document.getElementById('res').innerHTML = 'question B result';
  requests[0].resolve(response({ is_correct: true, explanation: 'A correct' }));
  await firstAnswer;
  assert.equal(elements.get('res').innerHTML, 'question B result');
  assert.equal(run('firstEntry.answered.result.is_correct'), true);

  const practiceButton = element();
  const defaultQuery = sandbox.document.querySelector;
  sandbox.document.querySelector = selector => selector === '#res [data-judgment]' ? practiceButton : defaultQuery(selector);
  run(`practice.current = firstEntry; firstEntry.answered.result = {submission_id: 100, source: "pending", is_correct: null};
       bindPracticeRefresh(firstEntry);`);
  const fetchJudgment = practiceButton.onclick();
  await practiceButton.onclick();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].url, '/api/submissions/100/judgment');
  run('practice.current = {id: 10}');
  requests[1].resolve(response({submission_id: 100, source: 'agent', is_correct: true, explanation: 'first answer judged'}));
  await fetchJudgment;
  assert.equal(elements.get('res').innerHTML, 'question B result', 'refresh from another question must only update its cached result');
  assert.equal(run('firstEntry.answered.result.source'), 'agent');
  sandbox.document.querySelector = defaultQuery;

  const submitted = [];
  sandbox.fetch = async (url, opts) => {
    submitted.push(JSON.parse(opts.body));
    if (submitted.length === 1) throw new Error('response lost');
    return response({ is_correct: true });
  };
  run('practice.current = {id: 12};');
  await run('pmSubmit()');
  await run('pmSubmit()');
  assert.equal(submitted[0].request_id, submitted[1].request_id, 'retry must reuse the same answer request id');
  assert.ok(submitted[0].request_id);

  for (const mode of ['random', 'sequential']) {
    const answers = [];
    sandbox.fetch = async (url, opts) => {
      if (url.startsWith('/api/practice/next?')) {
        return response({id: 50, total: 1, remaining: 0, round_complete: answers.length > 0});
      }
      assert.equal(url, '/api/answer');
      answers.push(JSON.parse(opts.body));
      return response({submission_id: answers.length, source: 'heuristic', is_correct: null, explanation: '参考答案无可判定关键词'});
    };
    run(`practice.mode = '${mode}'; practice.scope = 'single'; practice.singleCat = 'one question';`);
    await run('pmStart()');
    elements.get('ua').value = 'my answer';
    await run('pmSubmit()');
    assert.match(elements.get('res').innerHTML, /无法自动评分/);
    assert.doesNotMatch(elements.get('res').innerHTML, /待重试|刷新判题结果/);
    await run('pmNext()');
    assert.doesNotMatch(elements.get('sessionBox').innerHTML, /my answer|无法自动评分/);
    elements.get('ua').value = 'my answer';
    await run('pmSubmit()');
    await run('pmSubmit()');
    assert.equal(answers.length, 2, 'each new round accepts one submission even with unchanged text');
    assert.notEqual(answers[0].request_id, answers[1].request_id);
    run('pmPrev()');
    assert.equal(run('practice.current.answered.result.submission_id'), 1, 'history preserves the first result');
    assert.match(elements.get('sessionBox').innerHTML, /my answer/);
  }

  const loadedUrls = [];
  sandbox.fetch = async url => {
    loadedUrls.push(url);
    if (loadedUrls.length === 1) throw new Error('offline');
    return response({ id: 21, total: 5 });
  };
  run('practice.current = {id: 20}; practice.mode = "sequential"; practice.seqOffset = 0; practice.history = [practice.current]; practice.historyIdx = 0;');
  await run('pmLoadNext()');
  assert.equal(run('practice.seqOffset'), 0, 'failed load must not consume a sequential question');
  await run('pmLoadNext()');
  assert.equal(loadedUrls[0], loadedUrls[1]);
  assert.equal(run('practice.seqOffset'), 1);
  run('practice.history[0].total = 5; practice.history[0].remaining = 4; practice.history[0].attempt = {user_answer: "answer in flight"}; practice.history[0].submitting = true; pmPrev();');
  assert.equal(elements.get('pmSessionProgress').textContent, '1 / 5');
  assert.match(elements.get('sessionBox').innerHTML, /disabled [^>]*>answer in flight<\/textarea>/);

  let longRandomRequest;
  sandbox.fetch = async (url, options) => {
    longRandomRequest = { url, options };
    return response({ id: 1001, total: 2000 });
  };
  run('practice.mode = "random"; practice.seenIds = Array.from({length: 151}, (_, i) => i + 1);');
  await run('pmLoadNext()');
  assert.equal(longRandomRequest.options.method, 'POST', 'large random history must not overflow proxy URL limits');
  assert.doesNotMatch(longRandomRequest.url, /seen_ids=/);
  assert.ok(JSON.parse(longRandomRequest.options.body).seen_ids.length >= 151);

  requests.length = 0;
  sandbox.document.getElementById('qCount').value = '2';
  sandbox.document.getElementById('qCat').value = '';
  sandbox.document.getElementById('qCompany').value = '';
  sandbox.fetch = (url, options) => new Promise(resolve => requests.push({ url, options, resolve }));
  const oldQuiz = run('qStart()');
  const newQuiz = run('qStart()');
  requests[1].resolve(response([{ id: 31, question_text: 'new', difficulty: 1 }]));
  await newQuiz;
  requests[0].resolve(response([{ id: 30, question_text: 'old', difficulty: 1 }]));
  await oldQuiz;
  assert.equal(run('quiz.items[0].id'), 31);

  const quizInputs = [{ dataset: { qid: '31' }, value: 'answer 31', disabled: false }];
  elements.get('quizBox').querySelectorAll = selector => selector === '.qa-input' ? quizInputs : [];
  requests.length = 0;
  const grading = run('qSubmitAll()');
  await run('qSubmitAll()');
  await run('qStart()');
  assert.equal(requests.length, 1, 'submission must block duplicate submission and new generation');
  assert.equal(elements.get('qStart').disabled, true);
  assert.ok(JSON.parse(requests[0].options.body).request_id);
  // Even external state changes must not alter the captured submitted questions.
  run('quiz.items = [{id: 99, question_text: "unrelated"}]; quiz.mode = "interview";');
  requests[0].resolve(response({ results: [{ question_id: 31, user_answer: 'answer 31', is_correct: null, judge_by: 'pending' }] }));
  await grading;
  assert.equal(run('quiz.results[0].q.id'), 31);
  assert.equal(run('quiz.reportMode'), 'practice');
  assert.match(elements.get('quizBox').innerHTML, /待判 1/);
  assert.match(elements.get('quizBox').innerHTML, /未作答 0/);
  run('quiz.reportMode = "interview"; qShowReport();');
  assert.match(elements.get('quizBox').innerHTML, /暂不评级/);
  assert.doesNotMatch(elements.get('quizBox').innerHTML, /需加强/);

  run('quiz.results[0].out.judge_by = "heuristic"; qShowReport();');
  assert.match(elements.get('quizBox').innerHTML, /无法评分 1 题/);
  assert.match(elements.get('quizBox').innerHTML, /无可计分题目/);
  assert.doesNotMatch(elements.get('quizBox').innerHTML, /后台重试|待判题|暂不评级|刷新判题结果/);
  run('quiz.results[0].out.judge_by = "pending";');

  const quizButton = Object.assign(element(), {dataset: {judgment: '301'}});
  elements.get('quizBox').querySelectorAll = selector => selector === '[data-judgment]' &&
    elements.get('quizBox').innerHTML.includes("data-judgment='301'") ? [quizButton] : [];
  run('quiz.results[0].out.submission_id = 301; qShowReport()');
  const refreshQuiz = quizButton.onclick();
  assert.equal(requests.at(-1).url, '/api/submissions/301/judgment');
  requests.at(-1).resolve(response({submission_id: 301, source: 'agent', is_correct: false, explanation: 'retry complete'}));
  await refreshQuiz;
  assert.match(elements.get('quizBox').innerHTML, /需加强/);
  assert.doesNotMatch(elements.get('quizBox').innerHTML, /暂不评级|刷新判题结果/);
  run('quiz.results[0].out.is_correct = null; quiz.results[0].out.source = "pending"; qShowReport()');
  const cancelling = quizButton.onclick();
  requests.at(-1).resolve(response({submission_id: 301, source: 'cancelled', is_correct: null, explanation: '题目已删除'}));
  await cancelling;
  assert.match(elements.get('quizBox').innerHTML, /无可计分题目/);
  assert.doesNotMatch(elements.get('quizBox').innerHTML, /暂不评级|刷新判题结果/);
  run('quiz.results[0].out.source = "pending"; qShowReport()');
  const leaving = quizButton.onclick();
  elements.get('qBackCfg').onclick();
  requests.at(-1).resolve(response({submission_id: 301, source: 'agent', is_correct: true, explanation: 'late result'}));
  await leaving;
  assert.equal(elements.get('quizBox').innerHTML, '', 'refresh must not reopen an abandoned report');

  sandbox.fetch = async () => ({ ok: false, status: 500, json: async () => ({ detail: 'goal failed' }) });
  run('grBindOnce();');
  sandbox.document.getElementById('grGoalInput').value = '120';
  sandbox.document.getElementById('grGoalEditBox').style.display = 'block';
  await elements.get('grGoalSave').onclick();
  assert.equal(elements.get('grGoalEditBox').style.display, 'block', 'failed goal save must leave the editor open');
  assert.equal(elements.get('grGoalSave').disabled, false);

  let reviewPayload;
  sandbox.fetch = async (url, options) => {
    if (options?.method === 'POST') { reviewPayload = JSON.parse(options.body); return response({}); }
    return response([]);
  };
  await run('review(5, true, null, {stage: 2, review_count: 4})');
  assert.equal(reviewPayload.expected_stage, 2);
  assert.equal(reviewPayload.expected_review_count, 4);

  const adminSource = fs.readFileSync(path.join(__dirname, '../frontend/admin/admin.js'), 'utf8');
  const adminElements = new Map();
  const adminDoc = {
    ...element(), body: element(),
    querySelector(sel) {
      if (!adminElements.has(sel)) adminElements.set(sel, element());
      return adminElements.get(sel);
    },
  };
  const admin = vm.createContext({document: adminDoc, URLSearchParams, console});
  const arun = code => vm.runInContext(code, admin);
  arun(adminSource.slice(0, adminSource.indexOf('(async function init()')));
  const adminRequests = [];
  admin.fetch = url => new Promise(resolve => adminRequests.push({url, resolve}));
  const adminResponse = payload => ({...response(payload), headers: {get: () => 'application/json'}});
  const opening = arun('openEditModal(1)');
  arun('renameCat("newer dialog")');
  adminRequests.shift().resolve(adminResponse({id: 1}));
  await opening;
  assert.equal(adminDoc.querySelector('#modalTitle').textContent, '重命名分类');
  adminDoc.querySelector('#rNew').value = 'renamed';
  const savingCategory = adminDoc.querySelector('#rSave').onclick();
  await adminDoc.querySelector('#rSave').onclick();
  assert.equal(adminRequests.length, 1, 'rapid clicks must send only one category write');
  arun('closeModal(); editCatMeta("B", "icon", "description");');
  adminRequests.shift().resolve(adminResponse({}));
  // A completed write refreshes its table, even when another dialog is already open.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(adminRequests[0].url, '/api/categories/meta');
  adminRequests.shift().resolve(adminResponse([]));
  await savingCategory;
  assert.equal(adminDoc.querySelector('#modalMask').classList.contains('hidden'), false, 'late save must leave the new dialog open');
  assert.equal(adminDoc.querySelector('#modalTitle').textContent, '设置图标/描述：B');
  assert.match(adminDoc.querySelector('#modalBody').innerHTML, /id="mDesc" value="description"/);

  const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
  assert.match(html, /sandbox="allow-same-origin"/);
  assert.doesNotMatch(html, /<script[^>]+src="https?:/);
  console.log('Frontend checks passed: Markdown, timers, review, navigation, retries, grade refresh, quiz scores, settings, goals and admin dialogs.');
}
check().catch(error => { console.error(error); process.exitCode = 1; });
