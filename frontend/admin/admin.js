// 管理后台前端逻辑（vanilla JS，与主站技术栈一致）
"use strict";

// ----------------------------- 基础工具 -----------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function setMsg(el, text, kind) {
  el.className = "msg" + (kind ? " " + kind : "");
  el.textContent = text || "";
}

const DIFF_TXT = { 1: "简单", 2: "简单", 3: "中等", 4: "困难", 5: "困难" };
function diffHtml(d) {
  return `<span class="diff d${d}">${DIFF_TXT[d] || d} (${d})</span>`;
}
function tagsHtml(t) {
  return (t || "").split(",").map((x) => x.trim()).filter(Boolean)
    .map((t) => `<span class="tag-pill">${esc(t)}</span>`).join("");
}

// ----------------------------- Tab 切换 -----------------------------
$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "categories") loadCategories();
    if (btn.dataset.tab === "overview") loadOverview();
  });
});

// ----------------------------- 弹窗 -----------------------------
function openModal(title, bodyHtml, footHtml) {
  $("#modalTitle").textContent = title;
  $("#modalBody").innerHTML = bodyHtml;
  $("#modalFoot").innerHTML = footHtml || "";
  $("#modalMask").classList.remove("hidden");
}
function closeModal() { $("#modalMask").classList.add("hidden"); }
$("#modalClose").addEventListener("click", closeModal);
$("#modalMask").addEventListener("click", (e) => { if (e.target.id === "modalMask") closeModal(); });

// ============================================================
// A. 题目管理
// ============================================================
const Q = { page: 1, limit: 20, keyword: "", category: "", level: 0, total: 0 };

async function loadCategoriesInto(sel, withAll) {
  const metas = await api("/api/categories/meta");
  sel.innerHTML = (withAll ? `<option value="">全部分类</option>` : "") +
    metas.map((m) => `<option value="${esc(m.name)}">${esc(m.icon)} ${esc(m.name)} (${m.count})</option>`).join("");
  return metas;
}

async function loadQuestions() {
  const msg = $("#qMsg");
  setMsg(msg, "加载中…");
  try {
    const params = new URLSearchParams({
      limit: Q.limit, offset: (Q.page - 1) * Q.limit,
      keyword: Q.keyword, category: Q.category, level: Q.level,
    });
    const data = await api("/api/questions?" + params.toString());
    Q.total = data.total;
    const body = $("#qBody");
    if (!data.items.length) {
      body.innerHTML = `<tr><td colspan="6" style="color:var(--muted);padding:24px;text-align:center">暂无题目</td></tr>`;
    } else {
      body.innerHTML = data.items.map((q) => `
        <tr>
          <td>${q.id}</td>
          <td><span class="cat-tag">${esc(q.category)}</span></td>
          <td>${diffHtml(q.difficulty)}</td>
          <td>${tagsHtml(q.tags)}</td>
          <td class="cell-q">${esc(q.question_text)}</td>
          <td><div class="row-actions">
            <button class="btn sm" data-edit="${q.id}">编辑</button>
            <button class="btn sm danger" data-del="${q.id}">删除</button>
          </div></td>
        </tr>`).join("");
    }
    const pages = Math.max(1, Math.ceil(Q.total / Q.limit));
    $("#qPageInfo").textContent = `第 ${Q.page}/${pages} 页 · 共 ${Q.total} 题`;
    $("#qPrev").disabled = Q.page <= 1;
    $("#qNext").disabled = Q.page >= pages;
    setMsg(msg, "", "");
  } catch (e) {
    setMsg(msg, "加载失败：" + e.message, "err");
  }
}

$("#qSearch").addEventListener("click", () => {
  Q.keyword = $("#qKeyword").value.trim();
  Q.category = $("#qCategory").value;
  Q.level = parseInt($("#qLevel").value, 10) || 0;
  Q.page = 1;
  loadQuestions();
});
$("#qReset").addEventListener("click", () => {
  $("#qKeyword").value = ""; $("#qCategory").value = ""; $("#qLevel").value = "0";
  Q.keyword = ""; Q.category = ""; Q.level = 0; Q.page = 1; loadQuestions();
});
$("#qPrev").addEventListener("click", () => { if (Q.page > 1) { Q.page--; loadQuestions(); } });
$("#qNext").addEventListener("click", () => { Q.page++; loadQuestions(); });

// 编辑 / 删除（事件委托）
$("#qBody").addEventListener("click", async (e) => {
  const ed = e.target.getAttribute("data-edit");
  const dl = e.target.getAttribute("data-del");
  if (ed) return openEditModal(parseInt(ed, 10));
  if (dl) return deleteQuestion(parseInt(dl, 10));
});

async function openEditModal(id) {
  const q = await api("/api/question/" + id);
  const body = `
    <div class="form-row"><label>来源平台</label><input id="ePlatform" value="${esc(q.platform)}"></div>
    <div class="form-row"><label>分类</label><input id="eCategory" value="${esc(q.category)}"></div>
    <div class="form-row"><label>标签（逗号分隔）</label><input id="eTags" value="${esc(q.tags)}"></div>
    <div class="form-row"><label>难度（1-5）</label>
      <select id="eDiff">${[1,2,3,4,5].map((d)=>`<option value="${d}" ${d===q.difficulty?"selected":""}>${d}</option>`).join("")}</select></div>
    <div class="form-row"><label>题目</label><textarea id="eText">${esc(q.question_text)}</textarea></div>
    <div class="form-row"><label>参考答案（支持 ![alt](url) 配图）</label><textarea id="eAnswer">${esc(q.reference_answer)}</textarea></div>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn primary" id="eSave">保存</button>`;
  openModal("编辑题目 #" + id, body, foot);
  $("#eSave").addEventListener("click", async () => {
    try {
      await api("/api/questions/" + id, {
        method: "PUT",
        body: JSON.stringify({
          platform: $("#ePlatform").value.trim(),
          category: $("#eCategory").value.trim(),
          tags: $("#eTags").value.trim(),
          difficulty: parseInt($("#eDiff").value, 10),
          question_text: $("#eText").value,
          reference_answer: $("#eAnswer").value,
        }),
      });
      closeModal();
      setMsg($("#qMsg"), "已保存 #" + id, "ok");
      loadQuestions();
    } catch (err) { setMsg($("#qMsg"), "保存失败：" + err.message, "err"); }
  });
}

async function deleteQuestion(id) {
  if (!confirm("确认删除题目 #" + id + "？（将同步清理其错题本与复习计划）")) return;
  try {
    await api("/api/questions/" + id, { method: "DELETE" });
    setMsg($("#qMsg"), "已删除 #" + id, "ok");
    loadQuestions();
  } catch (e) { setMsg($("#qMsg"), "删除失败：" + e.message, "err"); }
}

// 新增
$("#qAdd").addEventListener("click", () => {
  const body = `
    <div class="form-row"><label>来源平台</label><input id="nPlatform" placeholder="如：牛客"></div>
    <div class="form-row"><label>分类</label><input id="nCategory" placeholder="如：MySQL"></div>
    <div class="form-row"><label>标签（逗号分隔）</label><input id="nTags"></div>
    <div class="form-row"><label>难度（1-5）</label>
      <select id="nDiff">${[1,2,3,4,5].map((d)=>`<option value="${d}">${d}</option>`).join("")}</select></div>
    <div class="form-row"><label>题目 *</label><textarea id="nText"></textarea></div>
    <div class="form-row"><label>参考答案</label><textarea id="nAnswer"></textarea></div>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn primary" id="nSave">创建</button>`;
  openModal("新增题目", body, foot);
  $("#nSave").addEventListener("click", async () => {
    const text = $("#nText").value.trim();
    if (!text) { setMsg($("#qMsg"), "题目内容必填", "err"); return; }
    try {
      await api("/api/questions/import", {
        method: "POST",
        body: JSON.stringify({
          platform: $("#nPlatform").value.trim(),
          category: $("#nCategory").value.trim(),
          tags: $("#nTags").value.trim(),
          difficulty: parseInt($("#nDiff").value, 10),
          question_text: text,
          reference_answer: $("#nAnswer").value,
        }),
      });
      closeModal();
      setMsg($("#qMsg"), "已新增题目", "ok");
      loadQuestions();
    } catch (err) { setMsg($("#qMsg"), "创建失败：" + err.message, "err"); }
  });
});

// 导出
$("#qExport").addEventListener("click", async () => {
  const params = new URLSearchParams({ keyword: Q.keyword, category: Q.category, level: Q.level });
  try {
    const res = await fetch("/api/questions/export?" + params.toString());
    if (!res.ok) throw new Error("导出失败");
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "questions_export.json";
    a.click();
    URL.revokeObjectURL(a.href);
    setMsg($("#qMsg"), "已导出", "ok");
  } catch (e) { setMsg($("#qMsg"), e.message, "err"); }
});

// 导入
$("#qImportFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const txt = await file.text();
    let arr = JSON.parse(txt);
    if (!Array.isArray(arr)) arr = arr.items || [];
    const r = await api("/api/questions/import-json", {
      method: "POST", body: JSON.stringify({ items: arr }),
    });
    setMsg($("#qMsg"), `导入完成：新增 ${r.imported}，跳过 ${r.skipped}`, "ok");
    loadQuestions();
  } catch (err) { setMsg($("#qMsg"), "导入失败：" + err.message, "err"); }
  e.target.value = "";
});

// ============================================================
// B. 分类管理
// ============================================================
async function loadCategories() {
  const msg = $("#cMsg");
  setMsg(msg, "加载中…");
  try {
    const metas = await api("/api/categories/meta");
    const body = $("#cBody");
    if (!metas.length) {
      body.innerHTML = `<tr><td colspan="5" style="color:var(--muted);padding:24px;text-align:center">暂无分类</td></tr>`;
    } else {
      body.innerHTML = metas.map((m) => `
        <tr>
          <td style="font-size:22px">${esc(m.icon)}</td>
          <td><strong>${esc(m.name)}</strong></td>
          <td>${m.count}</td>
          <td class="cell-clip" title="${esc(m.description)}">${esc(m.description)}</td>
          <td><div class="row-actions">
            <button class="btn sm" data-meta="${esc(m.name)}">图标/描述</button>
            <button class="btn sm" data-rename="${esc(m.name)}">重命名</button>
            <button class="btn sm" data-merge="${esc(m.name)}">合并</button>
            <button class="btn sm danger" data-cdel="${esc(m.name)}">删除</button>
          </div></td>
        </tr>`).join("");
    }
    setMsg(msg, "", "");
  } catch (e) { setMsg(msg, "加载失败：" + e.message, "err"); }
}

$("#cBody").addEventListener("click", (e) => {
  const t = e.target;
  if (t.dataset.meta) return editCatMeta(t.dataset.meta);
  if (t.dataset.rename) return renameCat(t.dataset.rename);
  if (t.dataset.merge) return mergeCat(t.dataset.merge);
  if (t.dataset.cdel) return deleteCat(t.dataset.cdel);
});

function editCatMeta(name) {
  const body = `
    <div class="form-row"><label>分类</label><input value="${esc(name)}" disabled></div>
    <div class="form-row"><label>图标（单个 emoji）</label><input id="mIcon" placeholder="如：🐬"></div>
    <div class="form-row"><label>描述</label><input id="mDesc" placeholder="一句话描述"></div>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn primary" id="mSave">保存</button>`;
  openModal("设置图标/描述：" + name, body, foot);
  $("#mSave").addEventListener("click", async () => {
    try {
      await api("/api/categories/meta/" + encodeURIComponent(name), {
        method: "PUT",
        body: JSON.stringify({ icon: $("#mIcon").value.trim(), description: $("#mDesc").value.trim() }),
      });
      closeModal(); setMsg($("#cMsg"), "已更新 " + name, "ok"); loadCategories();
    } catch (err) { setMsg($("#cMsg"), "失败：" + err.message, "err"); }
  });
}

function renameCat(oldName) {
  const body = `
    <div class="form-row"><label>原分类</label><input value="${esc(oldName)}" disabled></div>
    <div class="form-row"><label>新名称</label><input id="rNew" placeholder="新分类名"></div>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn primary" id="rSave">重命名</button>`;
  openModal("重命名分类", body, foot);
  $("#rSave").addEventListener("click", async () => {
    const nw = $("#rNew").value.trim();
    if (!nw) { setMsg($("#cMsg"), "新名称必填", "err"); return; }
    try {
      await api("/api/categories/rename", { method: "POST", body: JSON.stringify({ old_name: oldName, new_name: nw }) });
      closeModal(); setMsg($("#cMsg"), `已重命名 ${oldName} → ${nw}`, "ok"); loadCategories();
    } catch (err) { setMsg($("#cMsg"), "失败：" + err.message, "err"); }
  });
}

async function mergeCat(fromName) {
  const metas = await api("/api/categories/meta");
  const opts = metas.filter((m) => m.name !== fromName)
    .map((m) => `<option value="${esc(m.name)}">${esc(m.name)} (${m.count})</option>`).join("");
  const body = `
    <div class="form-row"><label>源分类（将被合并并删除）</label><input value="${esc(fromName)}" disabled></div>
    <div class="form-row"><label>合并到</label><select id="mgTo">${opts}</select></div>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn primary" id="mgSave">合并</button>`;
  openModal("合并分类", body, foot);
  $("#mgSave").addEventListener("click", async () => {
    const to = $("#mgTo").value;
    if (!to) { setMsg($("#cMsg"), "请选择目标分类", "err"); return; }
    try {
      await api("/api/categories/merge", { method: "POST", body: JSON.stringify({ from_name: fromName, to_name: to }) });
      closeModal(); setMsg($("#cMsg"), `已合并 ${fromName} → ${to}`, "ok"); loadCategories();
    } catch (err) { setMsg($("#cMsg"), "失败：" + err.message, "err"); }
  });
}

async function deleteCat(name) {
  const metas = await api("/api/categories/meta");
  const opts = `<option value="">未分类（空）</option>` +
    metas.filter((m) => m.name !== name)
      .map((m) => `<option value="${esc(m.name)}">${esc(m.name)} (${m.count})</option>`).join("");
  const body = `
    <div class="form-row"><label>待删除分类</label><input value="${esc(name)}" disabled></div>
    <div class="form-row"><label>题目迁移到</label><select id="cTarget">${opts}</select></div>
    <p style="color:var(--muted);font-size:12px">删除后该分类下的题目会迁移到目标分类，分类元数据一并清除。</p>`;
  const foot = `<button class="btn ghost" onclick="closeModal()">取消</button>
    <button class="btn danger" id="cDel">删除分类</button>`;
  openModal("删除分类：" + name, body, foot);
  $("#cDel").addEventListener("click", async () => {
    const target = $("#cTarget").value;
    try {
      await api("/api/categories/" + encodeURIComponent(name) + "?target=" + encodeURIComponent(target), { method: "DELETE" });
      closeModal(); setMsg($("#cMsg"), `已删除分类 ${name}`, "ok"); loadCategories();
    } catch (err) { setMsg($("#cMsg"), "失败：" + err.message, "err"); }
  });
}

// ============================================================
// C. 面经 & 概览
// ============================================================
async function loadOverview() {
  const msg = $("#ovMsg");
  setMsg(msg, "加载中…");
  try {
    const [stats, exps] = await Promise.all([api("/api/admin/stats"), api("/api/experiences")]);
    renderStats(stats);
    renderHeatmap(stats.activity);
    renderCatBars(stats.by_category);
    renderExps(exps);
    setMsg(msg, "", "");
  } catch (e) { setMsg(msg, "加载失败：" + e.message, "err"); }
}

function renderStats(s) {
  const cards = [
    ["题目总数", s.total_questions],
    ["分类数", s.total_categories],
    ["面经数", s.total_experiences],
    ["作答总数", s.total_submissions],
    ["正确率", s.accuracy + "%"],
    ["错题数", s.wrong_book_count],
    ["待复习", s.review_due_count],
  ];
  $("#statCards").innerHTML = cards.map(([l, n]) =>
    `<div class="stat"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");
}

function renderHeatmap(activity) {
  const map = {};
  (activity || []).forEach((a) => { map[a.day] = a.answered; });
  const cells = [];
  const today = new Date();
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    const n = map[key] || 0;
    let lvl = 0;
    if (n >= 1) lvl = 1;
    if (n >= 3) lvl = 2;
    if (n >= 6) lvl = 3;
    if (n >= 10) lvl = 4;
    cells.push(`<div class="hm-cell l${lvl}" title="${key}: ${n} 题">${n || ""}</div>`);
  }
  $("#heatmap").innerHTML = cells.join("");
}

function renderCatBars(byCategory) {
  const max = (byCategory[0] && byCategory[0].count) || 1;
  $("#catBars").innerHTML = byCategory.slice(0, 15).map((c) => `
    <div class="bar-row">
      <div class="bar-name" title="${esc(c.name)}">${esc(c.name)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, c.count / max * 100)}%"></div></div>
      <div class="bar-val">${c.count}</div>
    </div>`).join("");
}

function renderExps(exps) {
  const body = $("#expBody");
  if (!exps.length) {
    body.innerHTML = `<tr><td colspan="5" style="color:var(--muted);padding:24px;text-align:center">暂无面经</td></tr>`;
    return;
  }
  body.innerHTML = exps.map((e) => `
    <tr>
      <td><strong>${esc(e.company)}</strong></td>
      <td>${esc(e.role || "-")}</td>
      <td>${esc(e.offer_result || "-")}</td>
      <td class="cell-clip" title="${esc(e.content)}">${esc(e.content)}</td>
      <td><button class="btn sm danger" data-expdel="${e.id}">删除</button></td>
    </tr>`).join("");
}

$("#expBody").addEventListener("click", async (e) => {
  const id = e.target.getAttribute("data-expdel");
  if (!id) return;
  if (!confirm("确认删除该面经？")) return;
  try {
    await api("/api/experiences/" + id, { method: "DELETE" });
    setMsg($("#ovMsg"), "已删除面经 #" + id, "ok");
    loadOverview();
  } catch (err) { setMsg($("#ovMsg"), "删除失败：" + err.message, "err"); }
});

// ----------------------------- 初始化 -----------------------------
(async function init() {
  try { await loadCategoriesInto($("#qCategory"), true); } catch (_) {}
  loadQuestions();
})();
