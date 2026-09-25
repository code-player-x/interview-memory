// 前端逻辑：题库 / 练习 / 错题本 / 复习 / 热力图 / 设置
// 全部通过 fetch 调用后端 API。设计目标：复刻面试题库浏览体验 + 保留原有记忆训练能力。

function escapeHtml(s) {
  return (s == null ? "" : String(s)).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function splitKeywords(kw) {
  if (!kw) return [];
  return String(kw).split(/[,，]/).map(x => x.trim()).filter(Boolean);
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function diffMeta(d) {
  if (d <= 2) return { label: "简单", cls: "easy" };
  if (d === 3) return { label: "中等", cls: "medium" };
  return { label: "困难", cls: "hard" };
}
function tagsHtml(tags) {
  if (!tags) return "";
  return tags.split(",").filter(t => t.trim()).map(t =>
    "<span class='tag'>" + escapeHtml(t.trim()) + "</span>"
  ).join("");
}

// 大厂面经平台集合（命中则题目卡片展示平台来源）
const BIG_COMPANIES = new Set([
  "字节", "字节跳动", "抖音", "TikTok",
  "美团", "阿里", "阿里巴巴", "蚂蚁", "蚂蚁金服", "淘宝", "天猫", "支付宝",
  "腾讯", "微信", "QQ",
  "百度",
  "京东",
  "滴滴", "DiDi",
  "快手",
  "拼多多", "PDD",
  "华为", "Huawei",
  "小米", "Xiaomi",
  "小红书", "RedBook",
  "蔚来", "NIO",
  "网易", "NetEase",
  "Bilibili", "哔哩哔哩", "B站",
  "携程", "Ctrip",
  "猿辅导", "作业帮", "知乎",
  "Shopee", "虾皮",
  "Google", "Amazon", "Meta", "Facebook", "Apple", "Microsoft"
]);

function isBigCompany(platform) {
  if (!platform) return false;
  const p = String(platform).toLowerCase();
  for (const c of BIG_COMPANIES) {
    if (p.includes(c.toLowerCase())) return true;
  }
  return false;
}

function companyName(platform) {
  if (!platform) return "";
  const p = String(platform).toLowerCase();
  for (const c of BIG_COMPANIES) {
    if (p.includes(c.toLowerCase())) return c;
  }
  return platform;
}

// 题目卡片 tag 精简：难度徽章 + 分类 +（大厂来源）+ 剩余关键字，最多 4 个
function curatedTagsHtml(category, platform, tags, max) {
  max = max || 4;
  const used = new Set();
  const out = [];
  if (category) {
    out.push("<span class='tag'>" + escapeHtml(category) + "</span>");
    used.add(category);
  }
  if (platform && isBigCompany(platform)) {
    const name = companyName(platform);
    if (!used.has(name)) {
      out.push("<span class='tag company'>" + escapeHtml(name) + "</span>");
      used.add(name);
    }
  }
  if (tags) {
    tags.split(",").map(t => t.trim()).filter(Boolean).forEach(t => {
      if (used.has(t) || out.length >= max) return;
      out.push("<span class='tag'>" + escapeHtml(t) + "</span>");
      used.add(t);
    });
  }
  return out.join("");
}

// 依赖无关的轻量 Markdown 渲染：图片 / 链接 / 行内代码 / 加粗 / 换行。
// 先整体转义，再还原受信任的 markdown 片段；同源路径只允许图片上传目录。
function _safeUrl(u) {
  const url = u.trim();
  return /^(https?:|data:image\/)/i.test(url) ||
    /^\/data\/images\/[a-f0-9]{32}\.(png|jpe?g|gif|webp|svg|bmp)$/i.test(url)
    ? url : "#";
}
function _safeUrlAttr(u) {
  // 此时 Markdown 文本已整体 escapeHtml；再转义会把查询参数中的 &amp; 变成 &amp;amp;。
  return _safeUrl(u);
}
const _MD_IMG = /!\[([^\]]*)\]\(([^)\s]+)\)/g;
const _MD_LINK = /\[([^\]]+)\]\(([^)\s]+)\)/g;
// 残缺链接：URL 部分为空或缺失（飞书导入时大量 [text]( 被截断），但意图是链接。
// 两种形态：[text]() / [text]( ) —— 空 URL + 闭合括号
//          [text]($ / [text](\n —— 没有 URL 也没有闭合括号，到行/字符串末尾
const _MD_LINK_BROKEN_CLOSED = /\[([^\]\n]{2,200})\]\(\s*\)/g;
const _MD_LINK_BROKEN_OPEN   = /\[([^\]\n]{2,200})\]\(\s*$/gm;
const _MD_CODE = /`([^`]+)`/g;
const _MD_BOLD = /\*\*([^*]+)\*\*/g;

function renderInlineMarkdown(text) {
  let s = escapeHtml(text == null ? "" : String(text));
  s = s.replace(_MD_IMG, (m, alt, url) =>
    "<img class='md-img' src='" + _safeUrlAttr(url) + "' alt='" + alt + "' loading='lazy'>");
  s = s.replace(_MD_CODE, "<code class='md-code'>$1</code>");
  s = s.replace(_MD_BOLD, "<strong>$1</strong>");
  s = s.replace(_MD_LINK, (m, label, url) =>
    "<a class='md-link' href='" + _safeUrlAttr(url) + "' target='_blank' rel='noopener'>" + label + "</a>");
  return s.replace(/\r?\n+/g, " ");
}

function _paragraphizeMarkdownHtml(html, blockToken) {
  return html.split(blockToken).map(part => {
    if (!part) return "";
    if (blockToken.test(part)) return part;
    return part.split(/\n{2,}/).map(paragraph => {
      if (!paragraph.trim()) return "";
      return "<p class='md-p'>" + paragraph.replace(/\n/g, "<br>") + "</p>";
    }).join("");
  }).join("");
}
// 启发式：把「连续 2+ 行、每行以 ≥4 空格/Tab 缩进、且含代码特征、无中文标点」的段落
// 包成 ``` 围栏，便于统一渲染为高亮代码块（飞书导入的纯文本代码题也能识别）。
function _wrapIndentedCode(text) {
  return text.replace(/((?:^[ \t]{4,}.*(?:\r?\n|$)){2,})/gm, (block) => {
    const looksLikeCode = /(func\s|package\s|import\s|class\s|def\s|return\s|=>|var\s|let\s|const\s|if\s|for\s|while\s|#include|public\s|private\s|protected\s|<\?php|print\(|console\.|system\.|SELECT\s|INSERT\s|UPDATE\s|DELETE\s|CREATE\s|FROM\s|echo\s)/i.test(block)
      && !/[，。；：！？、（）《》「」]/u.test(block);
    if (!looksLikeCode) return block;
    const lang = /(func\s|package\s|import\s|var\s|\bgo\b)/i.test(block) ? "go"
               : /(def\s|import\s|print\(|self\.)/i.test(block) ? "python"
               : /(class\s|public\s|private\s|#include|System\.|@Override)/i.test(block) ? "java"
               : /(<\?php|echo\s|\$[a-zA-Z_])/i.test(block) ? "php"
               : /(function\s|const\s|let\s|=>|console\.|document\.)/i.test(block) ? "javascript"
               : /(SELECT\s|INSERT\s|UPDATE\s|DELETE\s|CREATE\s|FROM\s|WHERE\s)/i.test(block) ? "sql"
               : "";
    return "```" + lang + "\n" + block.replace(/[ \t]+$/gm, "") + "\n```";
  });
}

// 启发式：识别「零缩进 / 无围栏」的纯文本代码段（典型：手写代码题的参考答案）。
// 规则：
//   - 累积行：code 强信号 / blank 空行 / ambiguous 模糊行（保留作缓冲不计入 codeCount，避免"代码+描述"被截断）
//   - codeCount >= 3 时整段包成 ```lang 围栏
//   - 遇到中文段落（cn）立即结束 buf 并原样输出该行
//   - 已有 ``` 围栏的行整段原样跳过，避免被再次识别
function _wrapUnindentedCode(text) {
  // 含中文 = 段落分隔（结束当前代码段）
  const hasCN = (s) => /[\u4e00-\u9fff]/.test(s);
  // 判断单行「是否像代码」（启发式）
  // 返回值：
  //   "code"       强信号行（计入 codeCount）
  //   "blank"      空行（保留作段内分隔，不计入 codeCount）
  //   "ambiguous"  模糊行（如纯英文段落，保留在 buf 内但不计入 codeCount；避免"代码+描述"被截断）
  //   "cn"         中文段落（立即结束 buf）
  const looksCodeLine = (s) => {
    const t = s.trim();
    if (!t) return "blank";
    // 注释行（// 行内 / # Python / -- SQL / /* 块注释起始）即使含中文也不算段落分隔
    // 注意：不要把 markdown 加粗 **xx** 误判成注释，所以 * 单独不识别
    if (/^\s*(\/\/|#\s|--\s|\/\*)/.test(t)) return "code";
    // 优先识别 SQL 关键字开头：即使后面有中文表名/字段名（"FROM 表名;"）
    // 也算 code，不要被 hasCN 误判为段落分隔
    if (/^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|EXPLAIN|DESCRIBE|SHOW|GRANT|REVOKE|COMMIT|ROLLBACK|BEGIN|START|VALUES|FIELDS|LINES|TERMINATED|ENCLOSED|OPTIONALLY|FROM|WHERE|GROUP|ORDER|HAVING|LIMIT|OFFSET|JOIN|UNION|INTO|ON|USING|AS|AND|OR|NOT|NULL|DEFAULT|PRIMARY|KEY|INDEX|CONSTRAINT|REFERENCES)\b/i.test(t)) return "code";
    // 剥掉行尾 // / # / -- 注释后再判断是否含中文
    const withoutTailComment = t.replace(/(\s\/\/.*|\s#.*|\s--.*)$/, "").trim();
    if (hasCN(withoutTailComment)) return "cn";
    // 强代码信号
    if (/^(func|package|import|def|class|return|var|const|let|for|if|else|while|switch|case|default|defer|go|wg\.|fmt\.|println|print\(|print\s|console\.|echo\s|<\?php|#include|@interface|@protocol|wg\.Add|wg\.Done|wg\.Wait|ch\s*<-|->\s*ch|:=|^\s*[}\])\]]\s*$|^\s*[{}\[\(]\s*$)/i.test(t)) return "code";
    if (/^[{}\[\]()]/.test(t)) return "code";
    if (/^[a-zA-Z_]\w*\s*[:=]/.test(t)) return "code";
    if (/^[a-zA-Z_]\w*\(/.test(t)) return "code";
    if (/^[a-zA-Z_][\w.]*\.\w+\s*\(/.test(t)) return "code";
    if (/^[a-zA-Z_]\w*\.\w+/.test(t)) return "code";
    return "ambiguous";
  };
  // 探测语言
  const detectLang = (block) => {
    if (/(func\s|package\s|import\s|\bgo\b|:=|wg\.|ch\s*<-)/i.test(block)) return "go";
    if (/(def\s|import\s|self\.|print\(|__init__|:\s*$)/i.test(block)) return "python";
    if (/(class\s|public\s|private\s|#include|System\.|@Override|@interface|@protocol)/i.test(block)) return "java";
    if (/(<\?php|echo\s|\$[a-zA-Z_])/i.test(block)) return "php";
    if (/(function\s|const\s|let\s|=>|console\.|document\.|require\(|module\.)/i.test(block)) return "javascript";
    if (/(SELECT\s|INSERT\s|UPDATE\s|DELETE\s|CREATE\s|FROM\s|WHERE\s)/i.test(block)) return "sql";
    if (/(<\s*template|<\s*div|<\s*span|class=")/i.test(block)) return "html";
    if (/(<\?xml|<\s*[a-zA-Z]+:[a-zA-Z]+)/i.test(block)) return "xml";
    return "";
  };

  let result = text;
  // 单轮扫描：处理"零缩进纯文本代码"已经够；多轮会导致 ``` 围栏被再次识别为代码
  // 遇到 ``` 围栏行整段跳过，避免被误判
  const lines = result.split("\n");
  const out = [];
  let buf = []; // 累积行（code/blank/ambiguous 都进）
  let codeCount = 0; // 强信号行计数（决定是否真包成围栏）
  let inFence = false; // 是否在已有 ``` 围栏内
  const flush = () => {
    // 去掉首尾空行
    while (buf.length && !buf[0].trim()) buf.shift();
    let end = buf.length;
    while (end > 0 && !buf[end - 1].trim()) end--;
    if (codeCount >= 2) {
      const block = buf.slice(0, end).join("\n");
      out.push("```" + detectLang(block) + "\n" + block + "\n```");
      for (let i = end; i < buf.length; i++) out.push(buf[i]);
    } else if (buf.length) {
      out.push(buf.join("\n"));
    }
    buf = [];
    codeCount = 0;
  };
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (/^\s*```/.test(ln)) {
      flush();
      inFence = !inFence;
      out.push(ln);
      continue;
    }
    if (inFence) {
      out.push(ln);
      continue;
    }
    const c = looksCodeLine(ln);
    if (c === "code") {
      buf.push(ln);
      codeCount++;
    } else if (c === "blank" || c === "ambiguous") {
      // 空行/模糊行：累积到 buf 但不计数（让"代码+描述"不被截断）
      buf.push(ln);
    } else {
      // "cn" 中文段落：立即结束 buf
      flush();
      out.push(ln);
    }
  }
  flush();
  return out.join("\n");
}

// 注意：lang 接受任意非换行字符（包括空格、+、- 等），让 ```Plain Text / ```c++ / ```objective-c 等都生效。
// 之前用 \w* 会把含空格的 lang 漏识别，导致下一个空 lang 围栏被错认成"开"，吞掉中间正文。
const _FENCE = /```([^\n]*)\r?\n([\s\S]*?)```/g;

// 把「1) xxx；2) xxx；3) xxx；4) ...」这种中文括号编号一整段，
// 自动拆成美观的 <ol class="md-pretty"> 块（每条独立成行，绕开 markdown）。
// 规则：
//   - 必须 ≥3 个连续编号（1,2,3... 顺序连续）才拆
//   - 编号格式：1) / 1. / 1、 / 1: / 1： 都识别
//   - 分隔符：上一项结尾必须是 ；;。!！?？ 或行首；禁止逗号（太容易误伤）
//   - 跳过 ``` 围栏区和行内代码
// 私有区占位符字符（和原 _FENCE 占位符保持一致）
const _P0 = "", _P1 = "";

function _beautifyAnswer(text) {
  // 抽离围栏 + 行内代码（占位符隔离，避免被正则误识）
  const fences = [];
  text = text.replace(/```[\s\S]*?```/g, (m) => { fences.push(m); return _P0 + "K" + (fences.length - 1) + _P1; });
  const codes = [];
  text = text.replace(/`[^`\n]+`/g, (m) => { codes.push(m); return _P0 + "C" + (codes.length - 1) + _P1; });

  // 把占位符还原为原始围栏/行内代码（用于列表项 content 还原）
  const _restorePh = (s) => s
    .replace(new RegExp(_P0 + "K(\\d+)" + _P1, "g"), (m, i) => fences[+i] != null ? fences[+i] : m)
    .replace(new RegExp(_P0 + "C(\\d+)" + _P1, "g"), (m, i) => codes[+i] != null ? codes[+i] : m);

  // 匹配：(起始分隔符)(编号)(括号)(内容)，内容到下一编号前
  // 起始：^ 或 ；;。!！?？：\n（中文冒号也常见于"关键要素：1) ..."）
  // 编号括号：) / . / 、 / : / ：
  // 结束：下一编号前 或 串尾
  const SEQ_RE = /(?:^|[；;。！!？?：\n])\s*(\d+)\s*[\)\.、:：]\s*([\s\S]+?)(?=(?:[；;。！!？?：]\s*\d+\s*[\)\.、:：])|$)/g;
  const ranges = []; // {start, end, items:[{num,content}]}
  let m;
  while ((m = SEQ_RE.exec(text)) !== null) {
    const matchStart = m.index;
    const matchEnd = matchStart + m[0].length;
    const headChar = text.slice(matchStart, matchStart + 1);
    const tailChar = text.slice(matchEnd - 1, matchEnd);
    if (headChar === _P0 || tailChar === _P0) continue;
    const num = parseInt(m[1], 10);
    // 先把 content 里的占位符还原成原文（含 `` `code` `` 和围栏），再存入 items。
    // 否则后续 renderMarkdown 步骤 4 的 _MD_CODE 永远碰不到被吃掉的 `` `code` ``。
    const content = _restorePh(m[2].trim());
    const cur = ranges.length ? ranges[ranges.length - 1] : null;
    if (cur && cur.end === matchStart && num === cur.items[cur.items.length - 1].num + 1) {
      cur.items.push({ num, content });
      cur.end = matchEnd;
    } else if (num === 1) {
      // 起始必须是 1；半截不收
      ranges.push({ start: matchStart, end: matchEnd, items: [{ num, content }] });
    }
  }
  const valid = ranges.filter(r => {
    if (r.items.length < 3) return false;
    for (let i = 0; i < r.items.length; i++) if (r.items[i].num !== i + 1) return false;
    return true;
  });
  valid.sort((a, b) => b.start - a.start);
  let out = text;
  valid.forEach((r, vi) => {
    // content 不在此处 escapeHtml，由调用方在最终统一处理（避免双重转义）
    out = out.slice(0, r.start) + _P0 + "L" + vi + _P1 + out.slice(r.end);
  });
  out = _restorePh(out);
  return { out, valid, count: valid.length };
}

// 语法高亮（highlight.js 可用时在字符串阶段内联高亮，调用方零改动）
function _highlightCode(code, lang) {
  try {
    if (window.hljs) {
      if (lang && hljs.getLanguage(lang)) return hljs.highlight(code, { language: lang }).value;
      return hljs.highlightAuto(code).value;
    }
  } catch (e) {}
  return escapeHtml(code);
}

async function writeClipboardText(value) {
  const text = String(value == null ? "" : value);
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {}
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0;";
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try { copied = document.execCommand("copy"); } catch (e) {}
  textarea.remove();
  return copied;
}

// 代码块「复制」按钮回调
function copyCode(btn) {
  const c = btn.getAttribute("data-c") || "";
  const old = btn.textContent;
  writeClipboardText(c).then(copied => {
    btn.textContent = copied ? "已复制" : "复制失败";
    setTimeout(() => { btn.textContent = old; }, 1200);
  });
}

function renderMarkdown(text, keywords) {
  if (!text) return "";
  // 1) 启发式把缩进代码 + 零缩进纯文本代码都包成围栏（顺序：先零缩进，避免它和缩进判断冲突）
  let raw = _wrapUnindentedCode(text);
  raw = _wrapIndentedCode(raw);
  // 1.5) 把「1) xxx；2) xxx；...」连续编号段拆成美观的 <ol> 块
  //      占位符用 _P0/_P1 私有区字符保护（不含 HTML 标签，不受 escapeHtml 影响）
  //      列表 content 待 escapeHtml + 关键词高亮之后再生成最终 HTML
  const beautify = _beautifyAnswer(raw);
  const prettyItems = beautify.valid; // [{items:[{num,content}]}] —— content 仍是原文
  raw = beautify.out; // beautify.out 已用 _P0 L<num> _P1 占位符替换
  // 2) 抽离围栏代码块，用私有区占位符替换，避免被转义/换行破坏
  const blocks = [];
  raw = raw.replace(_FENCE, (m, lang, code) => {
    const idx = blocks.length;
    blocks.push({ lang: (lang || "").toLowerCase(), code: code.replace(/\n$/, "") });
    return "K" + idx + "";
  });
  // 2.5) 抽离残缺链接 [text]() / [text]($ —— URL 缺失但意图明显是链接
  //      （飞书/外部源导入时常出现这种截断，全题库有上千条）。
  //      渲染时给个可点击的 a.md-link-broken，点击触发百度搜索兜底。
  const brokenLinks = [];
  const _markBroken = (t) => {
    brokenLinks.push(t);
    return "\x00BL" + (brokenLinks.length - 1) + "\x00";
  };
  raw = raw.replace(_MD_LINK_BROKEN_CLOSED, (m, t) => _markBroken(t));
  raw = raw.replace(_MD_LINK_BROKEN_OPEN,   (m, t) => _markBroken(t));
  // 3) 转义 + 关键词高亮（仅非代码区）
  let s = escapeHtml(raw);
  if (keywords && keywords.length) {
    keywords.forEach(kw => {
      kw = String(kw).trim();
      if (!kw) return;
      try {
        const re = new RegExp(escapeRegExp(kw), "g");
        s = s.replace(re, "<mark class='kw'>" + escapeHtml(kw) + "</mark>");
      } catch (e) {}
    });
  }
  // 4) 图片 / 行内代码 / 加粗 / 链接
  s = s.replace(_MD_IMG, (m, alt, url) =>
    "<img class='md-img' src='" + _safeUrlAttr(url) + "' alt='" + alt + "' loading='lazy'>");
  s = s.replace(_MD_CODE, "<code class='md-code'>$1</code>");
  s = s.replace(_MD_BOLD, "<strong>$1</strong>");
  s = s.replace(_MD_LINK, (m, t, url) =>
    "<a class='md-link' href='" + _safeUrlAttr(url) + "' target='_blank' rel='noopener'>" + t + "</a>");
  // 5) 文本段落与代码/列表块作为同级节点，避免把 block 元素塞进 <p>。
  s = _paragraphizeMarkdownHtml(s, new RegExp("(" + _P0 + "[KL]\\d+" + _P1 + ")"));
  // 6) 还原代码块为高亮 <pre>
  s = s.replace(/K(\d+)/g, (m, i) => {
    const b = blocks[+i];
    if (!b) return m;
    const hl = _highlightCode(b.code, b.lang);
    const label = b.lang ? "<span class='code-lang'>" + escapeHtml(b.lang) + "</span>" : "";
    return "<div class='md-pre-wrap'>" + label +
      "<button class='code-copy' type='button' onclick='copyCode(this)' data-c='" + escapeHtml(b.code) + "'>复制</button>" +
      "<pre class='md-pre'><code class='md-code-block'>" + hl + "</code></pre></div>";
  });
  // 6.5) 还原美化的 <ol class="md-pretty"> 块
  //      content 是 raw 文本（未 escapeHtml/未跑过 markdown 渲染），
  //      必须在还原时单独走一遍 escapeHtml + 关键词高亮 + 行内 markdown，
  //      否则 **bold** / `code` / [link] / ![img] 都会原样漏出。
  //      还要处理 ```围栏``` —— 这些是 _wrapUnindentedCode 在 _beautifyAnswer
  //      之前就已经包好的，外层 _FENCE 抽离不到，需要在列表项内单独抽离 + 还原。
  s = s.replace(new RegExp(_P0 + "L(\\d+)" + _P1, "g"), (m, i) => {
    const r = prettyItems[+i];
    if (!r) return m;
    const li = r.items.map(it => {
      let c = it.content;
      // 抽离列表项内的围栏代码块（复用外层 _FENCE 正则；占位符用更罕见的串避免冲突）
      const itemFences = [];
      c = c.replace(_FENCE, (mm, lang, code) => {
        itemFences.push({ lang: (lang || "").toLowerCase(), code: code.replace(/\n$/, "") });
        return "\x00F" + (itemFences.length - 1) + "\x00";
      });
      c = escapeHtml(c);
      if (keywords && keywords.length) {
        keywords.forEach(kw => {
          kw = String(kw).trim();
          if (!kw) return;
          try {
            const re = new RegExp(escapeRegExp(kw), "g");
            c = c.replace(re, "<mark class='kw'>" + escapeHtml(kw) + "</mark>");
          } catch (e) {}
        });
      }
      // 行内 markdown（顺序与外层 step 4 一致：img > code > bold > link）
      c = c.replace(_MD_IMG, (mm, alt, url) =>
        "<img class='md-img' src='" + _safeUrlAttr(url) + "' alt='" + alt + "' loading='lazy'>");
      c = c.replace(_MD_CODE, "<code class='md-code'>$1</code>");
      c = c.replace(_MD_BOLD, "<strong>$1</strong>");
      c = c.replace(_MD_LINK, (mm, t, url) =>
        "<a class='md-link' href='" + _safeUrlAttr(url) + "' target='_blank' rel='noopener'>" + t + "</a>");
      // 段落/换行：围栏代码占位符必须保持为段落同级节点。
      c = _paragraphizeMarkdownHtml(c, /(\x00F\d+\x00)/);
      // 还原围栏代码块为高亮 <pre>
      c = c.replace(/\x00F(\d+)\x00/g, (mm, idx) => {
        const b = itemFences[+idx];
        if (!b) return mm;
        const hl = _highlightCode(b.code, b.lang);
        const label = b.lang ? "<span class='code-lang'>" + escapeHtml(b.lang) + "</span>" : "";
        return "<div class='md-pre-wrap'>" + label +
          "<button class='code-copy' type='button' onclick='copyCode(this)' data-c='" + escapeHtml(b.code) + "'>复制</button>" +
          "<pre class='md-pre'><code class='md-code-block'>" + hl + "</code></pre></div>";
      });
      return "<li>" + c + "</li>";
    }).join("");
    return "<ol class='md-pretty'>" + li + "</ol>";
  });
  // 7) 还原残缺链接占位符为可点击的 a.md-link-broken（点击触发百度搜索兜底）
  s = s.replace(/\x00BL(\d+)\x00/g, (m, i) => {
    const t = brokenLinks[+i];
    if (t == null) return m;
    const et = escapeHtml(t);
    return "<a class='md-link md-link-broken' href='#' data-q='" + et +
      "' title='链接 URL 缺失，点击用百度搜索：&#10;" + et + "'>" + et + "</a>";
  });
  return "<div class='md'>" + s + "</div>";
}

const TITLES = {
  bank:     ["题库", "浏览全部面试题，按难度、分类、标签筛选"],
  memorize: ["背题", "大页面逐题展示问题与参考答案，← / → 翻页"],
  practice: ["练习", "作答后由判题引擎评分"],
  wrong:    ["错题本", "答错的题自动归集，按错误原因聚类"],
  review:   ["复习", "艾宾浩斯遗忘曲线调度"],
  quiz:     ["智能组卷", "按薄弱点/目标公司出题，模拟面试出复盘报告"],
  exp:      ["面经", "真实面试经历与真题分享"],
  heatmap:  ["热力图", "GitHub 风格作答记录"],
  settings: ["设置", "邮件推送与间隔策略"],
  articles: ["技术文章摘抄", "内嵌 lianglianglee.com 文章站，可一键新窗口打开"],
  pomodoro: ["番茄待办", "番茄钟 + 待办清单 + 专注统计"],
  growth:   ["成长中心", "连续学习天数 · 成就徽章 · 学习报告 · 本月目标"],
};

// ---------------- 视图切换 ----------------
function switchView(name) {
  if (name === "admin") { window.location.href = "/admin/"; return; }
  const navName = name === "practiceSession" ? "practice" : name;
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b.dataset.view === navName));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === name));
  const t = TITLES[navName];
  document.getElementById("viewTitle").textContent = t[0];
  document.getElementById("viewSub").textContent = t[1];
  if (name === "bank") {
    if (!bank.inList) { bank.category = ""; bank.offset = 0; }
    loadCategoryGrid();
    if (bank.inList) loadBank();
  }
  else if (name === "memorize") loadMemorize();
  else if (name === "wrong") loadWrongBook();
  else if (name === "review") loadReview();
  else if (name === "heatmap") loadHeatmap();
  else if (name === "practice") {
    document.getElementById("pmConfig").style.display = "";
    document.getElementById("pmAction").style.display = "";
    loadPracticeCats();
  }
  else if (name === "quiz") loadQuizCats();
  else if (name === "exp") loadExperiences();
  else if (name === "settings") loadSettings();
  else if (name === "articles") loadArticles();
  else if (name === "pomodoro") loadPomodoro();
  else if (name === "growth") loadGrowth();
}

// ---------------- 题库 ----------------
const bank = { keyword: "", category: "", tags: "", level: 0, offset: 0, limit: 10, total: 0, inList: false };

async function loadCategoryGrid() {
  let cats = [];
  let detailOk = false;
  try { cats = await (await fetch("/api/categories/detail")).json(); detailOk = true; }
  catch (e) {
    // 兼容旧后端：降级到 /api/categories
    try {
      const names = await (await fetch("/api/categories")).json();
      cats = (names || []).map(n => ({ name: n, count: null, icon: "📄", description: n + " 面试题" }));
    } catch (e2) { cats = []; }
  }
  const wrap = document.getElementById("catGrid");
  const header = document.getElementById("bankCatHeader");
  const list = document.getElementById("bankList");
  const pager = document.getElementById("bankPager");
  const total = detailOk ? cats.reduce((sum, c) => sum + (c.count || 0), 0) : null;

  // 列表模式：隐藏分类网格，显示头部 + 题目列表
  if (bank.inList) {
    wrap.style.display = "none";
    header.style.display = "block";
    const activeCat = cats.find(c => c.name === bank.category) || {};
    const titleText = bank.category
      ? (activeCat.icon || "📄") + " " + bank.category
      : "📚 全部分类";
    document.getElementById("bankCatTitle").textContent = titleText;
    const selectedCount = bank.category ? activeCat.count : total;
    document.getElementById("bankCatSub").textContent =
      (bank.category
        ? (activeCat.description || bank.category + " 面试题")
        : "全部分类面试题合集") +
      (selectedCount != null ? " · 共 " + selectedCount + " 题" : "");
    list.style.display = "";
    pager.style.display = "";
  } else {
    // 网格模式：只展示分类，隐藏题目列表
    header.style.display = "none";
    list.style.display = "none";
    list.innerHTML = "";
    pager.style.display = "none";
    pager.innerHTML = "";
    wrap.style.display = "grid";
  }

  // 构建分类卡片
  wrap.innerHTML = "";

  const mk = (label, val, icon, count, desc) => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "cat-card";
    el.innerHTML =
      "<div class='cat-icon'>" + icon + "</div>" +
      "<div class='cat-name'>" + escapeHtml(label) + "</div>" +
      "<div class='cat-desc'>" + escapeHtml(desc || label + " 面试题") + "</div>" +
      "<div class='cat-count'>" + (count == null ? "-" : count) + " 题</div>";
    el.onclick = () => {
      bank.category = val;
      bank.inList = true;
      bank.offset = 0;
      loadCategoryGrid();
      loadBank();
    };
    return el;
  };

  wrap.appendChild(mk("全部分类", "", "📚", total, "全部分类面试题合集"));
  cats.forEach(c => wrap.appendChild(mk(c.name, c.name, c.icon || "📄", c.count, c.description)));

  if (!detailOk && cats.length) {
    const tip = document.createElement("div");
    tip.className = "muted";
    tip.style.cssText = "width:100%;margin-bottom:12px;padding:10px 12px;background:#fff3cd;border:1px solid #ffeaa7;border-radius:8px;color:#856404;font-size:13px;";
    tip.innerHTML = "<b>分类题数不可用</b>：当前后端可能未返回题数统计。请刷新页面（Ctrl+F5）重试；若仍不可用，请确认后端已用最新代码启动。";
    wrap.insertBefore(tip, wrap.firstChild);
  }

  // 绑定返回按钮
  const back = document.getElementById("bankCatBack");
  if (back) back.onclick = () => {
    bank.inList = false;
    bank.category = "";
    bank.offset = 0;
    loadCategoryGrid();
    loadBank();
  };
}

async function loadBank() {
  const qs = [];
  if (bank.keyword) qs.push("keyword=" + encodeURIComponent(bank.keyword));
  if (bank.category) qs.push("category=" + encodeURIComponent(bank.category));
  if (bank.tags) qs.push("tags=" + encodeURIComponent(bank.tags));
  if (bank.level) qs.push("level=" + bank.level);
  qs.push("limit=" + bank.limit + "&offset=" + bank.offset);
  let data = { total: 0, items: [] };
  try {
    data = await (await fetch("/api/questions?" + qs.join("&"))).json();
  } catch (e) { data = { total: 0, items: [] }; }
  bank.total = data.total;

  const list = document.getElementById("bankList");
  list.innerHTML = "";
  if (!data.items.length) {
    list.innerHTML = "<div class='empty'>没有匹配的题目，换个关键词或筛选条件试试。</div>";
  } else {
    data.items.forEach((q, i) => {
      const dm = diffMeta(q.difficulty);
      const card = document.createElement("div");
      card.className = "qcard";
      card.innerHTML =
        "<div class='idx'>" + (bank.offset + i + 1) + "</div>" +
        "<div class='body'>" +
          "<div class='qt'>" + escapeHtml(q.question_text) + "</div>" +
          "<div class='meta'>" +
            "<span class='badge " + dm.cls + "'>" + dm.label + "</span>" +
            curatedTagsHtml(q.category, q.platform, q.tags, 4) +
          "</div>" +
        "</div>" +
        "<div class='actions'>" +
          "<button class='btn sm' data-act='practice' data-id='" + q.id + "'>练习</button>" +
          "<button class='btn ghost sm' data-act='detail' data-id='" + q.id + "'>解析</button>" +
        "</div>";
      list.appendChild(card);
    });
  }
  renderPager();
  list.querySelectorAll("button[data-act]").forEach(b => {
    b.onclick = () => {
      const id = b.dataset.id;
      if (b.dataset.act === "detail") openDetail(id);
      else startPractice(id);
    };
  });
}

function renderPager() {
  const pager = document.getElementById("bankPager");
  const pages = Math.max(1, Math.ceil(bank.total / bank.limit));
  const cur = Math.floor(bank.offset / bank.limit) + 1;
  pager.innerHTML = "";
  const prev = document.createElement("button");
  prev.className = "btn ghost sm"; prev.textContent = "上一页";
  prev.disabled = cur <= 1;
  prev.onclick = () => { bank.offset = Math.max(0, bank.offset - bank.limit); loadBank(); };
  const info = document.createElement("span");
  info.textContent = "第 " + cur + " / " + pages + " 页 · 共 " + bank.total + " 题";
  const next = document.createElement("button");
  next.className = "btn ghost sm"; next.textContent = "下一页";
  next.disabled = cur >= pages;
  next.onclick = () => { bank.offset += bank.limit; loadBank(); };
  pager.appendChild(prev); pager.appendChild(info); pager.appendChild(next);
}

// ---------------- 背题模式 ----------------
const mem = { category: "", level: 0, items: [], idx: 0, total: 0, offset: 0, limit: 5, pageSize: 5, loading: false };
const memCategoryPicker = { items: [] };

function selectedMemCategory() {
  const value = document.getElementById("memCat").value;
  return memCategoryPicker.items.find(item => item.value === value) || memCategoryPicker.items[0];
}

function updateMemCategoryTrigger() {
  const selected = selectedMemCategory();
  const total = memCategoryPicker.items
    .filter(item => item.value)
    .reduce((sum, item) => sum + (Number.isFinite(item.count) ? item.count : 0), 0);
  const label = document.getElementById("memCatLabel");
  const meta = document.getElementById("memCatMeta");
  const totalEl = document.getElementById("memCatTotal");
  if (label) label.textContent = selected ? selected.name : "全部分类";
  if (meta) {
    meta.textContent = selected && selected.value
      ? (Number.isFinite(selected.count) ? "共 " + selected.count + " 题" : "该分类题目")
      : (total ? "全部 " + total + " 题" : "全部题目");
  }
  if (totalEl) totalEl.textContent = total ? total + " 题" : "按分类浏览";
}

function renderMemCategoryOptions() {
  const options = document.getElementById("memCatOptions");
  const search = document.getElementById("memCatSearch");
  if (!options) return;
  const query = (search ? search.value : "").trim().toLocaleLowerCase();
  const selectedValue = document.getElementById("memCat").value;
  const items = memCategoryPicker.items.filter(item => !query || item.name.toLocaleLowerCase().includes(query));
  options.innerHTML = "";
  if (!items.length) {
    options.innerHTML = "<div class='mem-category-empty'>没有匹配的分类</div>";
    return;
  }
  items.forEach(item => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mem-category-option";
    button.dataset.value = item.value;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(item.value === selectedValue));
    const name = document.createElement("span");
    name.className = "mem-category-option-name";
    name.textContent = item.name;
    const count = document.createElement("span");
    count.className = "mem-category-option-count";
    count.textContent = item.value && Number.isFinite(item.count) ? item.count + " 题" : "全部";
    button.append(name, count);
    options.appendChild(button);
  });
}

function visibleMemCategoryOptions() {
  return Array.from(document.querySelectorAll("#memCatOptions .mem-category-option"));
}

function focusMemCategoryOption(where = "selected") {
  const items = visibleMemCategoryOptions();
  if (!items.length) return;
  const activeIndex = items.indexOf(document.activeElement);
  const selectedIndex = items.findIndex(item => item.getAttribute("aria-selected") === "true");
  let index = selectedIndex >= 0 ? selectedIndex : 0;
  if (where === "first") index = 0;
  else if (where === "last") index = items.length - 1;
  else if (where === "next") index = activeIndex >= 0 ? Math.min(activeIndex + 1, items.length - 1) : 0;
  else if (where === "previous") index = activeIndex >= 0 ? Math.max(activeIndex - 1, 0) : items.length - 1;
  items[index].focus();
}

function positionMemCategoryMenu() {
  const picker = document.getElementById("memCatPicker");
  const trigger = document.getElementById("memCatTrigger");
  if (!picker || !trigger) return;
  const bounds = trigger.getBoundingClientRect();
  const roomBelow = window.innerHeight - bounds.bottom;
  picker.classList.toggle("opens-up", roomBelow < 310 && bounds.top > roomBelow);
}

function closeMemCategoryPicker({ focus = false } = {}) {
  const picker = document.getElementById("memCatPicker");
  const trigger = document.getElementById("memCatTrigger");
  const menu = document.getElementById("memCatMenu");
  if (!trigger || !menu) return;
  trigger.setAttribute("aria-expanded", "false");
  menu.hidden = true;
  if (picker) picker.classList.remove("is-open", "opens-up");
  if (focus) trigger.focus();
}

function openMemCategoryPicker({ focusSearch = false } = {}) {
  const picker = document.getElementById("memCatPicker");
  const trigger = document.getElementById("memCatTrigger");
  const menu = document.getElementById("memCatMenu");
  const search = document.getElementById("memCatSearch");
  if (!trigger || !menu) return;
  if (search) search.value = "";
  trigger.setAttribute("aria-expanded", "true");
  menu.hidden = false;
  if (picker) picker.classList.add("is-open");
  positionMemCategoryMenu();
  renderMemCategoryOptions();
  requestAnimationFrame(() => {
    const selected = document.querySelector("#memCatOptions .mem-category-option[aria-selected='true']");
    if (selected) selected.scrollIntoView({ block: "nearest" });
    if (focusSearch && search) search.focus();
  });
}

function chooseMemCategory(value) {
  const select = document.getElementById("memCat");
  select.value = value;
  updateMemCategoryTrigger();
  closeMemCategoryPicker({ focus: true });
  memStart();
}

function setupMemCategoryPicker() {
  const picker = document.getElementById("memCatPicker");
  const trigger = document.getElementById("memCatTrigger");
  const search = document.getElementById("memCatSearch");
  const options = document.getElementById("memCatOptions");
  if (!picker || !trigger || !search || !options) return;
  trigger.onclick = () => {
    if (trigger.getAttribute("aria-expanded") === "true") closeMemCategoryPicker();
    else openMemCategoryPicker({ focusSearch: false });
  };
  search.oninput = renderMemCategoryOptions;
  options.onclick = event => {
    const option = event.target.closest(".mem-category-option");
    if (option) chooseMemCategory(option.dataset.value || "");
  };
  picker.onkeydown = event => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMemCategoryPicker({ focus: true });
    }
  };
  trigger.onkeydown = event => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    openMemCategoryPicker();
    focusMemCategoryOption(event.key === "ArrowDown" ? "selected" : "last");
  };
  search.onkeydown = event => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusMemCategoryOption("first");
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusMemCategoryOption("last");
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      focusMemCategoryOption(event.key === "Home" ? "first" : "last");
    }
  };
  options.onkeydown = event => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusMemCategoryOption("next");
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusMemCategoryOption("previous");
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      focusMemCategoryOption(event.key === "Home" ? "first" : "last");
    }
  };
  document.addEventListener("pointerdown", event => {
    if (!picker.contains(event.target)) closeMemCategoryPicker();
  });
  window.addEventListener("resize", () => {
    if (trigger.getAttribute("aria-expanded") === "true") positionMemCategoryMenu();
  });
}

async function loadMemorize() {
  let cats = [];
  try { cats = await (await fetch("/api/categories/detail")).json(); } catch (e) { cats = []; }
  const sel = document.getElementById("memCat");
  const cur = sel.value;
  sel.innerHTML = "<option value=''>全部分类</option>";
  memCategoryPicker.items = [{ value: "", name: "全部分类", count: null }];
  cats.forEach(c => {
    const o = document.createElement("option");
    o.value = c.name;
    o.textContent = c.name + " (" + (c.count == null ? "-" : c.count) + ")";
    sel.appendChild(o);
    memCategoryPicker.items.push({ value: c.name, name: c.name, count: c.count });
  });
  if (cur && cats.some(c => c.name === cur)) sel.value = cur;
  updateMemCategoryTrigger();
  renderMemCategoryOptions();
  memStart();
}

async function memLoadPage() {
  const qs = [];
  if (mem.category) qs.push("category=" + encodeURIComponent(mem.category));
  if (mem.level) qs.push("level=" + mem.level);
  qs.push("limit=" + mem.limit + "&offset=" + mem.offset + "&order=asc");
  const data = await (await fetch("/api/questions?" + qs.join("&"))).json();
  mem.total = data.total || 0;
  mem.items = mem.items.concat(data.items || []);
  mem.offset += (data.items || []).length;
}

async function memStart() {
  mem.category = document.getElementById("memCat").value;
  mem.level = parseInt(document.getElementById("memDiff").value, 10) || 0;
  mem.pageSize = parseInt(document.getElementById("memSize").value, 10) || 5;
  mem.limit = mem.pageSize;
  mem.items = []; mem.offset = 0; mem.idx = 0; mem.total = 0; mem.loading = false;
  await memLoadPage();
  memRender();
}

async function memRender() {
  // 单题文章式：mem.idx 是题索引（不再是页索引），mem.pageSize 仅用于后端一次拉多少
  const endIdx = mem.idx + 1;
  while (endIdx > mem.items.length && mem.items.length < mem.total && !mem.loading) {
    mem.loading = true;
    await memLoadPage();
    mem.loading = false;
  }
  const box = document.getElementById("memCard");
  const q = mem.items[mem.idx];
  if (!q) {
    box.innerHTML = "<div class='empty'>该分类下暂无题目</div>";
    document.getElementById("memProgress").textContent = "0 / 0";
    document.getElementById("memPrev").disabled = true;
    document.getElementById("memNext").disabled = true;
    return;
  }
  const dm = diffMeta(q.difficulty);
  const kws = splitKeywords(q.keywords);
  const kwHtml = kws.length
    ? "<div class='mem-kws'>" + kws.map(k => "<span class='kw-pill'>" + escapeHtml(k) + "</span>").join("") + "</div>"
    : "";
  const statsHtml =
    "<div class='mem-stats'>" +
      "<button class='mem-share' type='button' title='复制链接' data-qid='" + q.id + "' onclick='copyShareLink(this)'>🔗 分享题目</button>" +
    "</div>";
  const tagsHtml =
    "<div class='mem-tags'>" +
      "<span class='badge " + dm.cls + "'>" + dm.label + "</span>" +
      "<span class='pill'>" + escapeHtml(q.category || "") + "</span>" +
      curatedTagsHtml(q.category, q.platform, q.tags, 4) +
    "</div>";
  box.innerHTML =
    "<article class='mem-article'>" +
      "<h1 class='mem-title'>" +
        "<span class='mem-qid'>#" + q.id + "</span>" +
        "<span class='md-inline'>" + renderInlineMarkdown(q.question_text || "") + "</span>" +
      "</h1>" +
      tagsHtml +
      statsHtml +
      "<div class='mem-tabs'>" +
        "<div class='mem-tab active'>📖 推荐答案</div>" +
        "<div class='mem-tab muted'>🎙️ 开始面试（自测模式）</div>" +
      "</div>" +
      "<section class='mem-answer' id='memAnswerSection'>" +
        kwHtml +
        "<div class='mem-a-body'>" + renderMarkdown(q.reference_answer || "（暂无参考答案）", kws) + "</div>" +
      "</section>" +
      "<section class='mem-notes' id='memNotesSection'>" +
        "<div class='mem-notes-head'>📝 我的笔记 <span class='muted'>（保存到当前应用实例）</span></div>" +
        "<div class='mem-note-editor'>" +
          "<textarea id='memNoteInput' placeholder='写点自己的理解 / 记忆口诀 / 易错点…'></textarea>" +
          "<div class='mem-note-actions'>" +
            "<button class='btn ghost sm' id='memNoteClear'>清空</button>" +
            "<button class='btn primary sm' id='memNoteSave'>保存笔记</button>" +
          "</div>" +
          "<div class='mem-note-tip muted' id='memNoteTip'></div>" +
        "</div>" +
        "<div class='mem-note-list' id='memNoteList'><div class='muted' style='font-size:12px'>加载中…</div></div>" +
      "</section>" +
    "</article>";
  document.getElementById("memNoteSave").onclick = () => memNoteSave(q.id);
  document.getElementById("memNoteClear").onclick = () => { document.getElementById("memNoteInput").value = ""; };
  memNoteLoad(q.id);
  document.getElementById("memPrev").disabled = mem.idx <= 0;
  document.getElementById("memNext").disabled = mem.idx + 1 >= mem.total;
  document.getElementById("memProgress").textContent = "第 " + (mem.idx + 1) + " / " + mem.total + " 题";
}

function memPrev() {
  if (mem.idx > 0) {
    mem.idx -= 1;
    memRender();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}
function memNext() {
  if (mem.idx + 1 < mem.total) {
    mem.idx += 1;
    memRender();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

// ---------------- 笔记：增/查/改/删（落库） ----------------
function formatNoteTimestamp(value) {
  if (!value) return "";
  const normalized = String(value).trim().replace(" ", "T");
  if (!normalized) return "";
  // SQLite 等后端常返回无时区的 UTC 时间；显式补 Z，避免浏览器按本地时间错误解析。
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const date = new Date(hasTimezone ? normalized : normalized + "Z");
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function memNoteLoad(qid) {
  const list = document.getElementById("memNoteList");
  if (!list) return;
  list.innerHTML = "<div class='muted' style='font-size:12px'>加载中…</div>";
  try {
    const r = await fetch("/api/questions/" + qid + "/notes");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const notes = await r.json();
    if (!notes.length) {
      list.innerHTML = "<div class='muted' style='font-size:12px;padding:6px 0'>还没有笔记，写下第一笔吧～</div>";
      return;
    }
    list.innerHTML = notes.map(n =>
      "<div class='mem-note' data-nid='" + n.id + "'>" +
        "<div class='mem-note-meta'>" +
          "<span class='mem-note-dot'></span>" +
          "<span>" + formatNoteTimestamp(n.created_at) + "</span>" +
          "<button class='mem-note-del' type='button' onclick='memNoteDelete(" + qid + "," + n.id + ")'>删除</button>" +
        "</div>" +
        "<div class='mem-note-text'>" + escapeHtml(n.content).replace(/\n/g, "<br>") + "</div>" +
      "</div>"
    ).join("");
  } catch (e) {
    list.innerHTML = "<div class='muted' style='font-size:12px;color:#d33'>加载失败：" + e.message + "</div>";
  }
}
async function memNoteSave(qid) {
  const inp = document.getElementById("memNoteInput");
  const tip = document.getElementById("memNoteTip");
  const v = inp.value.trim();
  if (!v) { tip.textContent = "请先写点内容"; setTimeout(()=>tip.textContent="", 1500); return; }
  tip.textContent = "保存中…";
  try {
    const r = await fetch("/api/questions/" + qid + "/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: v }),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    inp.value = "";
    tip.textContent = "已保存";
    setTimeout(()=>tip.textContent="", 1200);
    memNoteLoad(qid);
  } catch (e) {
    tip.textContent = "保存失败：" + e.message;
  }
}
async function copyShareLink(el) {
  const qid = el.getAttribute('data-qid');
  const url = new URL(location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("q", qid);
  const copied = await writeClipboardText(url.toString());
  if (copied) {
    const old = el.textContent;
    el.textContent = '✓ 已复制';
    setTimeout(() => { el.textContent = old; }, 1200);
  } else {
    prompt('复制失败，请手动复制：', url.toString());
  }
}

async function memNoteDelete(qid, nid) {
  if (!confirm("删除这条笔记？")) return;
  try {
    const r = await fetch("/api/questions/" + qid + "/notes/" + nid, { method: "DELETE" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    memNoteLoad(qid);
  } catch (e) {
    alert("删除失败：" + e.message);
  }
}

// ---------------- 手动添加题目 ----------------
async function openAddModal() {
  let cats = [];
  try { cats = await (await fetch("/api/categories/detail")).json(); } catch (e) { cats = []; }
  const dl = document.getElementById("catList");
  dl.innerHTML = "";
  cats.forEach(c => { const o = document.createElement("option"); o.value = c.name; dl.appendChild(o); });
  document.getElementById("addCat").value = bank.inList ? bank.category : "";
  document.getElementById("addDiff").value = "3";
  document.getElementById("addPlatform").value = "";
  document.getElementById("addTags").value = "";
  document.getElementById("addQuestion").value = "";
  document.getElementById("addAnswer").value = "";
  document.getElementById("addErr").textContent = "";
  document.getElementById("addMask").classList.add("show");
  document.getElementById("addModal").style.display = "flex";
  document.getElementById("addQuestion").focus();
}

function closeAddModal() {
  document.getElementById("addMask").classList.remove("show");
  document.getElementById("addModal").style.display = "none";
}

async function addSave() {
  const question_text = document.getElementById("addQuestion").value.trim();
  const reference_answer = document.getElementById("addAnswer").value.trim();
  const category = document.getElementById("addCat").value.trim();
  const err = document.getElementById("addErr");
  if (!category) { err.textContent = "请填写分类"; return; }
  if (!question_text) { err.textContent = "请填写题目"; return; }
  if (!reference_answer) { err.textContent = "请填写参考答案"; return; }
  const payload = {
    question_text,
    reference_answer,
    category,
    tags: document.getElementById("addTags").value.trim(),
    platform: document.getElementById("addPlatform").value.trim(),
    difficulty: parseInt(document.getElementById("addDiff").value, 10) || 1,
  };
  err.textContent = "保存中…";
  try {
    const r = await fetch("/api/questions/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      err.textContent = "保存失败：" + (e.detail || ("HTTP " + r.status));
      return;
    }
    closeAddModal();
    loadCategoryGrid();
    if (bank.inList) loadBank();
  } catch (e) {
    err.textContent = "保存失败，请检查后端服务";
  }
}

// ---------------- 题目详情抽屉 ----------------
let currentDetailId = null;
let currentDetail = null;   // 原始题目对象（含 reference_answer 原始 markdown）
async function openDetail(id) {
  currentDetailId = id;
  let q;
  try {
    const response = await fetch("/api/question/" + id);
    if (!response.ok) throw new Error("HTTP " + response.status);
    q = await response.json();
  } catch (e) {
    alert("题目不存在或暂时无法加载");
    return;
  }
  currentDetail = q;
  const dm = diffMeta(q.difficulty);
  const badge = document.getElementById("dqBadge");
  badge.className = "badge " + (dm.cls || "easy");
  badge.textContent = dm.label || "";
  document.getElementById("dqText").textContent = q.question_text || "";
  document.getElementById("dqTags").innerHTML =
    (q.category ? "<span class='tag'>" + escapeHtml(q.category) + "</span>" : "") +
    tagsHtml(q.tags);
  const ans = document.getElementById("dqAnswer");
  ans.style.display = "none";
  document.getElementById("dqAnswerBody").innerHTML = renderMarkdown(q.reference_answer || "（暂无参考答案）", splitKeywords(q.keywords));
  if (document.getElementById("dqReveal")) document.getElementById("dqReveal").textContent = "查看答案";
  // 复位编辑态
  exitEditMode();
  document.getElementById("drawerMask").classList.add("show");
  document.getElementById("detailDrawer").classList.add("show");
}
function closeDetail() {
  document.getElementById("drawerMask").classList.remove("show");
  document.getElementById("detailDrawer").classList.remove("show");
}
function revealAnswer() {
  document.getElementById("dqAnswer").style.display = "block";
  document.getElementById("dqReveal").textContent = "已显示答案";
}
function enterEditMode() {
  if (!currentDetail) return;
  const edit = document.getElementById("dqEdit");
  const ans = document.getElementById("dqAnswer");
  ans.style.display = "none";
  document.getElementById("dqReveal").style.display = "none";
  edit.style.display = "block";
  document.getElementById("dqAnswerEdit").value = currentDetail.reference_answer || "";
  document.getElementById("dqEditBtn").style.display = "none";
  document.getElementById("dqPractice").style.display = "none";
  document.getElementById("dqSave").style.display = "";
  document.getElementById("dqCancel").style.display = "";
}
function exitEditMode() {
  const edit = document.getElementById("dqEdit");
  if (!edit) return;
  edit.style.display = "none";
  document.getElementById("dqAnswerEdit").value = "";
  if (document.getElementById("dqReveal")) document.getElementById("dqReveal").style.display = "";
  if (document.getElementById("dqEditBtn")) document.getElementById("dqEditBtn").style.display = "";
  if (document.getElementById("dqPractice")) document.getElementById("dqPractice").style.display = "";
  if (document.getElementById("dqSave")) document.getElementById("dqSave").style.display = "none";
  if (document.getElementById("dqCancel")) document.getElementById("dqCancel").style.display = "none";
  const tip = document.getElementById("dqImgTip");
  if (tip) tip.textContent = "";
}
async function saveAnswerEdit() {
  if (!currentDetailId) return;
  const text = document.getElementById("dqAnswerEdit").value;
  const tip = document.getElementById("dqImgTip");
  tip.textContent = "保存中…";
  try {
    const r = await fetch("/api/questions/" + currentDetailId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reference_answer: text })
    });
    if (!r.ok) throw new Error("保存失败");
    const data = await r.json();
    currentDetail.reference_answer = data.reference_answer;
    currentDetail.images = data.images;
    document.getElementById("dqAnswerBody").innerHTML = renderMarkdown(data.reference_answer || "（暂无参考答案）");
    document.getElementById("dqAnswer").style.display = "block";
    if (document.getElementById("dqReveal")) document.getElementById("dqReveal").textContent = "已显示答案";
    exitEditMode();
    tip.textContent = "已保存";
    setTimeout(() => { if (tip) tip.textContent = ""; }, 1500);
  } catch (e) {
    tip.textContent = "保存失败：" + e;
  }
}
async function uploadAnswerImage() {
  const fileInput = document.getElementById("dqImgFile");
  if (!fileInput.files || !fileInput.files.length) return;
  const tip = document.getElementById("dqImgTip");
  tip.textContent = "上传中…";
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  try {
    const r = await fetch("/api/images/upload", { method: "POST", body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "上传失败");
    }
    const data = await r.json();
    const ta = document.getElementById("dqAnswerEdit");
    const token = "\n![图片](" + data.url + ")\n";
    const start = ta.selectionStart, end = ta.selectionEnd;
    ta.value = ta.value.slice(0, start) + token + ta.value.slice(end);
    ta.focus();
    tip.textContent = "已插入图片";
    setTimeout(() => { if (tip) tip.textContent = ""; }, 1500);
  } catch (e) {
    tip.textContent = "上传失败：" + e;
  }
  fileInput.value = "";
}

// ---------------- 练习 / 刷题模式 ----------------
const practice = {
  mode: "random",          // random | sequential
  scope: "single",         // single | multi
  singleCat: "",
  multiCats: new Set(),
  cats: [],
  catTotals: {},
  seenIds: [],             // random 模式：本轮已见题目 id
  seqOffset: 0,            // sequential 模式：序号
  current: null,
  total: 0,
  history: [],             // 已加载题目队列（含当前题）
  historyIdx: -1,          // 当前题在 history 中的索引
  answered: {},            // id -> {user_answer, result}
  isSingleQuestion: false, // 从题库"练习"按钮进入的指定单题模式
};

// 进入刷题页
function enterPracticeSession() {
  document.getElementById("pmConfig").style.display = "none";
  document.getElementById("pmAction").style.display = "none";
  switchView("practiceSession");
}

// 返回刷题配置页
function exitPracticeSession() {
  switchView("practice");
  document.getElementById("pmConfig").style.display = "";
  document.getElementById("pmAction").style.display = "";
}

// 渲染刷题页当前题目
function renderSessionQuestion() {
  const box = document.getElementById("sessionBox");
  const q = practice.history[practice.historyIdx];
  if (!q) {
    box.innerHTML = "<p class='muted'>暂无题目</p>";
    return;
  }
  practice.current = q;
  practice.total = q.total || 1;

  const cached = practice.answered[q.id];
  const answeredHtml = cached ? buildResultHtml(cached.result) : "";

  box.innerHTML =
    "<div class='qbox session-qbox'>" +
      "<div class='qmeta'>" +
        "<span class='pill'>" + escapeHtml(q.category || "练习") + "</span>" +
        "<span class='muted'>#" + q.id + "</span>" +
      "</div>" +
      "<div class='qtext'>" + renderMarkdown(q.question_text) + "</div>" +
      "<textarea id='ua' rows='5' placeholder='在此输入你的答案…'>" + escapeHtml(cached ? cached.user_answer : "") + "</textarea>" +
      "<div class='result" + (cached ? " show" : "") + "' id='res'>" + answeredHtml + "</div>" +
    "</div>";

  updateSessionMeta();
  updateSessionNav();
}

function buildResultHtml(out) {
  let cls = out.is_correct === true ? "ok" : out.is_correct === false ? "bad" : "";
  let txt = out.is_correct === true ? "✅ 答对了" : out.is_correct === false ? "❌ 答错了" : "⏳ 判题待重试（已记录）";
  txt += "<br>" + escapeHtml(out.explanation || "");
  if (out.error_reason) txt += "<br><span class='muted'>错误原因：" + escapeHtml(out.error_reason) + "</span>";
  txt += "<br><span class='src'>判题来源：" + escapeHtml(out.source || "") + "</span>";
  if (out.reference_answer) {
    txt += "<div class='ref-answer'>" +
      "<div class='ref-title'>参考答案</div>" +
      "<div class='md'>" + renderMarkdown(out.reference_answer) + "</div></div>";
  }
  return "<div class='" + cls + "'>" + txt + "</div>";
}

async function pmSubmit() {
  const q = practice.current;
  if (!q) return;
  const uaEl = document.getElementById("ua");
  if (!uaEl) return;
  const ua = uaEl.value;
  if (!ua.trim()) { alert("请先输入答案"); return; }
  let out;
  try {
    const r = await fetch("/api/answer", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: q.id, user_answer: ua })
    });
    const payload = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(payload.detail || ("HTTP " + r.status));
    out = payload;
  } catch (e) {
    const resEl = document.getElementById("res");
    resEl.className = "result show bad";
    resEl.innerHTML = "<div class='bad'>提交失败：" + escapeHtml(e.message || "请检查后端服务") + "。答案未记录，可修改后重试。</div>";
    return;
  }
  practice.answered[q.id] = { user_answer: ua, result: out };

  const resEl = document.getElementById("res");
  resEl.className = "result show " + (out.is_correct === true ? "ok" : out.is_correct === false ? "bad" : "");
  resEl.innerHTML = buildResultHtml(out);
}

async function startPractice(id) {
  // 从题库“练习”按钮进入：指定单题，但仍使用刷题页
  practice.isSingleQuestion = true;
  practice.history = [];
  practice.historyIdx = -1;
  practice.current = null;
  practice.answered = {};
  practice.seenIds = [];
  practice.seqOffset = 0;
  enterPracticeSession();
  const box = document.getElementById("sessionBox");
  box.innerHTML = "<p class='muted'>加载中…</p>";
  let q;
  try {
    const response = await fetch("/api/question/" + id);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || ("HTTP " + response.status));
    q = payload;
  } catch (e) {
    box.innerHTML = "<p class='muted'>加载失败：" + escapeHtml(e.message || "请检查后端服务") + "</p>";
    return;
  }
  q.total = 1;
  practice.history = [q];
  practice.historyIdx = 0;
  renderSessionQuestion();
}

// 刷题模式：分类下拉与多选
async function loadPracticeCats() {
  let cats = [];
  let detailOk = false;
  try {
    cats = await (await fetch("/api/categories/detail")).json();
    detailOk = true;
  } catch (e) {
    // 兼容旧后端：降级到 /api/categories（只有名字，没有题数）
    try {
      const names = await (await fetch("/api/categories")).json();
      cats = (names || []).map(n => ({ name: n, count: null }));
    } catch (e2) { cats = []; }
  }
  practice.cats = cats;
  practice.catTotals = {};
  cats.forEach(c => practice.catTotals[c.name] = c.count || 0);

  const wrap = document.getElementById("pmCatGrid");
  wrap.innerHTML = "";

  if (!cats.length) {
    wrap.innerHTML = "<p class='muted'>分类加载失败，请检查后端服务是否已重启。</p>";
    practice.singleCat = "";
    practice.multiCats.clear();
    syncPracticeSelection();
    return;
  }

  if (!detailOk) {
    const tip = document.createElement("div");
    tip.className = "muted";
    tip.style.cssText = "width:100%;margin-bottom:12px;padding:10px 12px;background:#fff3cd;border:1px solid #ffeaa7;border-radius:8px;color:#856404;font-size:13px;";
    tip.innerHTML = "<b>分类题数不可用</b>：当前后端可能未返回题数统计与组卷接口。请刷新页面（Ctrl+F5）重试；若仍不可用，请确认后端已用最新代码启动。";
    wrap.appendChild(tip);
  }

  // 全部选项（仅单分类模式）
  const all = document.createElement("div");
  all.className = "cat-chip" + (practice.scope === "single" && practice.singleCat === "" ? " active" : " disabled");
  const totalCount = cats.reduce((s, c) => s + (c.count || 0), 0);
  all.textContent = "全部" + (detailOk ? "（" + totalCount + "）" : "");
  all.dataset.cat = "";
  all.onclick = () => togglePracticeCat("");
  wrap.appendChild(all);

  cats.forEach(c => {
    const el = document.createElement("div");
    el.className = "cat-chip";
    el.textContent = c.name + (detailOk ? "（" + c.count + "）" : "");
    el.dataset.cat = c.name;
    el.onclick = () => togglePracticeCat(c.name);
    wrap.appendChild(el);
  });

  // 默认选中第一个真实分类
  if (cats.length && !practice.singleCat && practice.scope === "single") {
    practice.singleCat = cats[0].name;
  }
  if (practice.multiCats.size === 0 && cats.length && practice.scope === "multi") {
    practice.multiCats.add(cats[0].name);
  }
  syncPracticeSelection();
}

function togglePracticeCat(cat) {
  if (practice.scope === "multi" && cat === "") return; // 多分类下「全部」禁用
  if (practice.scope === "single") {
    practice.singleCat = cat;
  } else {
    if (practice.multiCats.has(cat)) practice.multiCats.delete(cat);
    else practice.multiCats.add(cat);
  }
  syncPracticeSelection();
}

function syncPracticeSelection() {
  const single = practice.scope === "single";
  let selected = single ? [practice.singleCat] : Array.from(practice.multiCats);
  const allCategories = single && practice.singleCat === "";
  const total = allCategories
    ? Object.values(practice.catTotals).reduce((sum, count) => sum + count, 0)
    : selected.reduce((sum, category) => sum + (practice.catTotals[category] || 0), 0);

  document.querySelectorAll("#pmCatGrid .cat-chip").forEach(el => {
    const cat = el.dataset.cat;
    const isActive = single ? (practice.singleCat === cat) : practice.multiCats.has(cat);
    el.classList.toggle("active", isActive);
    el.classList.toggle("disabled", !single && cat === ""); // 全部只在单分类下可用
  });

  document.getElementById("pmSelLabel").textContent = allCategories ? "" : "已选";
  document.getElementById("pmSelCount").textContent = allCategories ? "全部分类" : selected.length;
  document.getElementById("pmSelUnit").textContent = allCategories ? "· 共" : "个分类 · 共";
  document.getElementById("pmSelTotal").textContent = total;
}

function setPracticeMode(mode) {
  practice.mode = mode;
  document.querySelectorAll(".opt-card[data-mode]").forEach(c => c.classList.toggle("active", c.dataset.mode === mode));
}
function setPracticeScope(scope) {
  practice.scope = scope;
  document.querySelectorAll(".opt-pill[data-scope]").forEach(p => p.classList.toggle("active", p.dataset.scope === scope));
  if (scope === "single") {
    if (!practice.singleCat) practice.singleCat = practice.cats[0]?.name || "";
  }
  if (scope === "multi" && practice.multiCats.size === 0) {
    if (practice.singleCat) practice.multiCats.add(practice.singleCat);
  }
  syncPracticeSelection();
}

function practiceScopeParam() {
  if (practice.scope === "multi") {
    const arr = Array.from(practice.multiCats);
    if (!arr.length) return null;
    return "categories=" + encodeURIComponent(arr.join(","));
  }
  return "category=" + encodeURIComponent(practice.singleCat);
}

async function pmStart() {
  const sp = practiceScopeParam();
  if (sp === null) { alert("请先勾选至少一个分类"); return; }
  practice.isSingleQuestion = false;
  practice.seenIds = [];
  practice.seqOffset = 0;
  practice.history = [];
  practice.historyIdx = -1;
  practice.current = null;
  practice.total = 0;
  practice.answered = {};
  document.getElementById("pmRoundTip").textContent = "";
  enterPracticeSession();
  await pmLoadNext();
}

// 加载下一道新题（从后端取）
async function pmLoadNext() {
  const sp = practiceScopeParam();
  if (sp === null) { alert("请先勾选至少一个分类"); return; }
  if (practice.current) {
    if (practice.mode === "random") practice.seenIds.push(practice.current.id);
    else practice.seqOffset += 1;
  }

  const box = document.getElementById("sessionBox");
  box.innerHTML = "<p class='muted'>加载中…</p>";
  let url = "/api/practice/next?" + sp + "&mode=" + practice.mode;
  if (practice.mode === "random") {
    url += "&seen_ids=" + encodeURIComponent(practice.seenIds.join(","));
  } else {
    url += "&offset=" + practice.seqOffset;
  }
  let q;
  try {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail || ("HTTP " + res.status);
      const restartTip = res.status === 404
        ? "<br><small>后端接口未找到（HTTP 404）。请确认后端服务已用最新代码启动并正常监听。</small>"
        : "";
      box.innerHTML = "<p class='muted'>" + escapeHtml(detail) + restartTip + "</p>";
      return;
    }
    q = await res.json();
  } catch (e) { box.innerHTML = "<p class='muted'>加载失败，请检查后端服务。</p>"; return; }

  if (practice.mode === "random" && q.round_complete) {
    practice.seenIds = [q.id];
  }
  document.getElementById("pmRoundTip").textContent =
    q.round_complete ? "（本轮已刷完，已开启新一轮）" : "";

  practice.history.push(q);
  practice.historyIdx = practice.history.length - 1;
  renderSessionQuestion();
}

// 下一题：优先走历史前进，否则加载新题
async function pmNext() {
  if (practice.isSingleQuestion) {
    alert("当前是指定单题练习，返回配置后可选择分类刷题");
    return;
  }
  if (practice.historyIdx < practice.history.length - 1) {
    practice.historyIdx++;
    renderSessionQuestion();
  } else {
    await pmLoadNext();
  }
}

// 上一题：从历史记录回退
function pmPrev() {
  if (practice.historyIdx > 0) {
    practice.historyIdx--;
    renderSessionQuestion();
  }
}

function updateSessionMeta() {
  const q = practice.current;
  if (!q) return;
  let shown;
  if (practice.isSingleQuestion) {
    shown = 1;
  } else if (practice.mode === "random") {
    shown = q.total - q.remaining;
  } else {
    shown = (practice.seqOffset % q.total) + 1;
  }
  const scopeText = practice.isSingleQuestion
    ? "指定题目练习"
    : (practice.scope === "multi" ? "多分类" : (practice.singleCat ? "单分类" : "全部分类"))
      + " · " + (practice.mode === "random" ? "随机" : "顺序");
  document.getElementById("pmSessionScope").textContent = scopeText;
  document.getElementById("pmSessionProgress").textContent = shown + " / " + q.total;
}

function updateSessionNav() {
  document.getElementById("pmPrev").disabled = practice.historyIdx <= 0;
}

// ---------------- 错题本 ----------------
async function loadWrongBook() {
  const cat = document.getElementById("wbCategory").value.trim();
  const only = document.getElementById("wbOnlyReviewing").checked;
  const group = document.getElementById("wbGroupReason").checked;
  let url = "/api/wrong-book?";
  if (cat) url += "category=" + encodeURIComponent(cat) + "&";
  if (only) url += "only_reviewing=true&";
  if (group) url += "group_by_reason=true";
  let data = [];
  try { data = await (await fetch(url)).json(); } catch (e) { data = []; }

  const body = document.getElementById("wbBody");
  const groups = document.getElementById("wbGroups");
  body.innerHTML = "";
  groups.innerHTML = "";
  const badge = { mastered: "badge easy", learning: "badge medium", reviewing: "badge hard" };
  const zh = { mastered: "已掌握", learning: "学习中", reviewing: "复习中" };

  if (group && data.groups) {
    body.parentElement.style.display = "none";
    data.groups.forEach(g => {
      const wrap = document.createElement("div");
      wrap.className = "reason-group";
      wrap.innerHTML =
        "<div class='reason-head'><span>" + escapeHtml(g.reason || "未归类") + "</span><span class='muted'>" + g.items.length + " 题</span></div>" +
        "<div class='reason-body'>" + g.items.map(it =>
          "<div class='reason-item'><div class='rt'>" + escapeHtml(it.question_text) + "</div>" +
          "<div class='meta'>" + escapeHtml(it.category) + " · 错 " + it.wrong_count + " 次 · " + (zh[it.mastery] || it.mastery) + "</div></div>"
        ).join("") + "</div>";
      groups.appendChild(wrap);
    });
    return;
  }

  body.parentElement.style.display = "";
  data.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + escapeHtml(r.question_text) +
        "<div class='muted'>曾答：" + escapeHtml(r.last_user_answer || "") + "</div></td>" +
      "<td>" + escapeHtml(r.category) + "</td>" +
      "<td>" + escapeHtml(r.error_reason || "—") + "</td>" +
      "<td>" + r.wrong_count + "</td>" +
      "<td>" + (r.first_wrong_at || "").slice(0, 10) + "</td>" +
      "<td><span class='badge " + (badge[r.mastery] || "easy") + "'>" + (zh[r.mastery] || r.mastery) + "</span></td>" +
      "<td><button class='btn ghost sm' data-id='" + r.question_id + "'>标记掌握</button></td>";
    body.appendChild(tr);
  });
  body.querySelectorAll("button[data-id]").forEach(b => {
    b.onclick = async () => {
      await fetch("/api/wrong-book/" + b.dataset.id + "/master", { method: "POST" });
      loadWrongBook();
    };
  });
}

async function exportWrongBookPDF() {
  try {
    const res = await fetch("/api/wrong-book/export-pdf");
    const data = await res.json();
    if (data.download_url) {
      window.open(data.download_url, "_blank");
    } else {
      alert("导出失败");
    }
  } catch (e) {
    alert("导出失败：" + e);
  }
}

async function exportWrongBookMD() {
  const cat = document.getElementById("wbCategory").value.trim();
  const only = document.getElementById("wbOnlyReviewing").checked;
  const group = document.getElementById("wbGroupReason").checked;
  const qs = [];
  if (cat) qs.push("category=" + encodeURIComponent(cat));
  if (only) qs.push("only_reviewing=true");
  if (group) qs.push("group_by_reason=true");
  const url = "/api/wrong-book/export-md" + (qs.length ? "?" + qs.join("&") : "");
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const md = await res.text();
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "wrong_book_export.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    alert("导出 Markdown 失败：" + e);
  }
}

// ---------------- 复习 ----------------
async function loadReview() {
  let items = [];
  try { items = await (await fetch("/api/review/due")).json(); } catch (e) { items = []; }
  const list = document.getElementById("reviewList");
  list.innerHTML = "";
  if (!items.length) { list.innerHTML = "<div class='empty'>🎉 当前没有待复习的题目。</div>"; return; }
  items.forEach(it => {
    const el = document.createElement("div");
    el.className = "review-item";
    el.innerHTML =
      "<div class='qt'>" + escapeHtml(it.question_text) + "</div>" +
      "<div class='meta'><span class='tag'>" + escapeHtml(it.category) + "</span>" +
      "<span class='muted'>已错 " + it.wrong_count + " 次</span></div>" +
      "<div class='acts'><button class='btn sm' data-r='1'>记住了</button>" +
      "<button class='btn ghost sm' data-r='0'>还没记住</button></div>";
    list.appendChild(el);
    el.querySelector("[data-r='1']").onclick = () => review(it.question_id, true);
    el.querySelector("[data-r='0']").onclick = () => review(it.question_id, false);
  });
}
async function review(id, remembered) {
  try {
    await fetch("/api/review/" + id, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remembered })
    });
  } catch (e) {}
  loadReview();
}

// ---------------- 热力图（GitHub 风格 + 多年历史） ----------------
async function loadHeatmap() {
  let data = [];
  try { data = await (await fetch("/api/activity")).json(); } catch (e) { data = []; }
  const map = {};
  data.forEach(d => { map[d.day] = d; });

  const range = document.getElementById("hmRange").value;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  let weeks = 53;
  if (range === "2") weeks = 106;
  if (range === "all") {
    // 根据最早记录或默认近两年
    const first = data.length ? parseLocalDay(data[0].day) : new Date(today);
    const daysSpan = Math.ceil((today - first) / (1000 * 60 * 60 * 24));
    weeks = Math.max(53, Math.ceil(daysSpan / 7) + 2);
  }

  // 结束于本周六，确保今天落在图内
  const end = new Date(today);
  end.setDate(today.getDate() + (6 - today.getDay()));
  const start = new Date(end);
  start.setDate(end.getDate() - weeks * 7 + 1);

  document.getElementById("hmRangeInfo").textContent =
    "展示 " + formatDate(start) + " 至 " + formatDate(end);

  const visible = data.filter(d => {
    const day = parseLocalDay(d.day);
    return day >= start && day <= today;
  });
  const total = visible.reduce((sum, d) => sum + (d.answered || 0), 0);
  const correct = visible.reduce((sum, d) => sum + (d.correct || 0), 0);
  const wrong = visible.reduce((sum, d) => sum + (d.wrong || 0), 0);
  const judged = correct + wrong;
  let streak = 0;
  const cursor = new Date(today);
  while ((map[formatDate(cursor)] || {}).answered > 0) {
    streak++;
    cursor.setDate(cursor.getDate() - 1);
  }
  document.getElementById("hmTotal").textContent = total;
  document.getElementById("hmAccuracy").textContent = judged ? Math.round(correct * 100 / judged) + "%" : "—";
  document.getElementById("hmStreak").textContent = streak;
  document.getElementById("hmNote").textContent = total
    ? "颜色越深，代表当天完成的题目越多。悬停可查看详情。"
    : "从今天开始答第一题，点亮属于你的学习轨迹。";

  const daysEl = document.getElementById("heatmapDays");
  const grid = document.getElementById("heatmapGrid");
  daysEl.innerHTML = "";
  grid.innerHTML = "";
  const tip = document.getElementById("tip");
  const lv = ["var(--lv0)", "var(--lv1)", "var(--lv2)", "var(--lv3)", "var(--lv4)"];
  const lvl = n => (n === 0 ? 0 : n <= 2 ? 1 : n <= 5 ? 2 : n <= 9 ? 3 : 4);

  const dnames = ["日", "一", "二", "三", "四", "五", "六"];
  const showLabel = [false, true, false, true, false, true, false];
  for (let d = 0; d < 7; d++) {
    const el = document.createElement("div");
    el.className = "dlabel";
    el.textContent = showLabel[d] ? dnames[d] : "";
    daysEl.appendChild(el);
  }

  let prevMonth = null;
  for (let w = 0; w < weeks; w++) {
    const col = document.createElement("div");
    col.className = "week";
    const weekStart = new Date(start);
    weekStart.setDate(start.getDate() + w * 7);
    const mname = (weekStart.getMonth() + 1) + "月";
    const monthLabel = document.createElement("div");
    monthLabel.className = "month-label";
    monthLabel.textContent = mname !== prevMonth ? mname : "";
    col.appendChild(monthLabel);
    prevMonth = mname;

    for (let d = 0; d < 7; d++) {
      const dt = new Date(start);
      dt.setDate(start.getDate() + w * 7 + d);
      const cell = document.createElement("div");
      cell.className = "day";
      if (dt > today) { cell.classList.add("is-future"); col.appendChild(cell); continue; }
      const key = dt.getFullYear() + "-" + String(dt.getMonth() + 1).padStart(2, "0") + "-" + String(dt.getDate()).padStart(2, "0");
      const rec = map[key];
      const n = rec ? rec.answered : 0;
      cell.style.background = lv[lvl(n)];
      const c = rec ? rec.correct : 0, wn = rec ? rec.wrong : 0;
      cell.title = key + " · 答题 " + n + " 道（对" + c + "/错" + wn + "）";
      cell.addEventListener("mousemove", ev => {
        tip.style.opacity = 1;
        tip.textContent = key + " · 答题 " + n + " 道（对" + c + "/错" + wn + "）";
        tip.style.left = (ev.clientX + 12) + "px";
        tip.style.top = (ev.clientY + 12) + "px";
      });
      cell.addEventListener("mouseleave", () => { tip.style.opacity = 0; });
      col.appendChild(cell);
    }
    grid.appendChild(col);
  }

  // 自动滚动到最右侧（今天）
  setTimeout(() => {
    const scroll = document.getElementById("heatmapScroll");
    if (scroll) scroll.scrollLeft = scroll.scrollWidth;
  }, 0);
}

function parseLocalDay(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDate(d) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

// ---------------- 设置 ----------------
async function loadSettings() {
  let s = {};
  try { s = await (await fetch("/api/settings")).json(); } catch (e) { s = {}; }
  document.getElementById("setEmail").value = s.email || "";
  document.getElementById("setPush").value = s.push_time || "09:00";
  document.getElementById("setSteps").value = s.ebbinghaus_steps || "1,2,4,7,15,30,60";
  document.getElementById("setBase").value = s.app_base_url || "";
}
async function saveSettings() {
  const payload = {
    email: document.getElementById("setEmail").value,
    push_time: document.getElementById("setPush").value,
    ebbinghaus_steps: document.getElementById("setSteps").value,
    app_base_url: document.getElementById("setBase").value
  };
  try {
    const response = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || ("HTTP " + response.status));
    }
    document.getElementById("setMsg").textContent = "已保存";
  } catch (e) {
    document.getElementById("setMsg").textContent = "保存失败：" + (e.message || "请检查后端服务");
  }
}

// ---------------- 智能组卷 / 模拟面试 ----------------
// 一次性渲染全部题 -> 底部一次性提交 -> 整卷复盘。
const quiz = { items: [], mode: "practice", results: [], box: null };

async function loadQuizCats() {
  let cats = [];
  try { cats = await (await fetch("/api/categories")).json(); } catch (e) { cats = []; }
  const sel = document.getElementById("qCat");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = "<option value=''>全部</option>";
  cats.forEach(c => {
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    sel.appendChild(o);
  });
  if (cur) sel.value = cur;
}

function setQuizMode(m) {
  quiz.mode = m;
  document.querySelectorAll(".qmode").forEach(b => b.classList.toggle("active", b.dataset.qmode === m));
}

async function qStart() {
  const count = parseInt(document.getElementById("qCount").value, 10) || 10;
  const category = document.getElementById("qCat").value;
  const company = document.getElementById("qCompany").value.trim();
  const strategy = document.querySelector("input[name='qstrategy']:checked").value;
  const box = document.getElementById("quizBox");
  quiz.box = box;
  box.innerHTML = "<p class='muted'>组卷中…</p>";
  document.getElementById("qProgress").textContent = "";
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 8000);
  let items;
  try {
    const url = "/api/quiz/generate?count=" + count +
      "&category=" + encodeURIComponent(category) +
      "&company=" + encodeURIComponent(company) +
      "&mode=" + encodeURIComponent(strategy);
    const res = await fetch(url, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) {
      box.innerHTML = "<p class='muted'>组卷失败：后端返回 HTTP " + res.status + "，请确认后端服务正常运行。</p>";
      return;
    }
    items = await res.json();
  } catch (e) {
    clearTimeout(timer);
    const msg = (e && e.name === "AbortError")
      ? "组卷超时（8 秒无响应），请检查后端服务是否已启动。"
      : ("组卷失败：" + (e.message || e));
    box.innerHTML = "<p class='muted'>" + msg + "</p>";
    return;
  }
  if (!items.length) { box.innerHTML = "<p class='muted'>该范围内没有题目，换个条件试试。</p>"; return; }
  quiz.items = items;
  quiz.results = [];
  qRenderAll();
}

// 一次性渲染整卷：每题一个 #qa-{id} 锚点 + 答案输入框；底部"提交整卷"按钮。
function qRenderAll() {
  const box = quiz.box;
  const N = quiz.items.length;
  const prog = document.getElementById("qProgress");
  if (prog) prog.textContent = "共 " + N + " 题 · 一次性作答后提交";

  // 顶部：题目导航条
  const nav = quiz.items.map((q, i) =>
    "<a class='qnav-chip' href='#qa-" + q.id + "' data-id='" + q.id + "'>" + (i + 1) + "</a>"
  ).join("");

  // 每题：题面 + 答案框
  const list = quiz.items.map((q, i) => {
    const dm = diffMeta(q.difficulty);
    const badge = dm && dm.label ? "<span class='badge " + dm.cls + "'>" + dm.label + "</span>" : "";
    return ""
      + "<div class='qbox session-qbox' id='qa-" + q.id + "'>"
      +   "<div class='qmeta'>"
      +     "<span class='pill'>第 " + (i + 1) + " / " + N + " 题</span>"
      +     (q.category ? "<span class='pill'>" + escapeHtml(q.category) + "</span>" : "")
      +     (q.platform ? "<span class='tag company'>" + escapeHtml(q.platform) + "</span>" : "")
      +     badge
      +     "<span class='muted'>#" + q.id + "</span>"
      +   "</div>"
      +   "<div class='qtext'>" + renderMarkdown(q.question_text || "") + "</div>"
      +   "<textarea class='qa-input' data-qid='" + q.id + "' rows='4' placeholder='在此输入你的答案…'></textarea>"
      +   "<div class='qresult' data-qid='" + q.id + "'></div>"
      + "</div>";
  }).join("");

  box.innerHTML =
      "<div class='qnav'>" + nav + "</div>"
    + "<div id='qList'>" + list + "</div>"
    + "<div class='qbar'>"
    +   "<button class='btn ghost' id='qCancel'>取消重出卷</button>"
    +   "<button class='btn' id='qSubmitAll'>提交整卷</button>"
    + "</div>";

  // 提交按钮
  const submitBtn = document.getElementById("qSubmitAll");
  if (submitBtn) submitBtn.onclick = qSubmitAll;
  const cancelBtn = document.getElementById("qCancel");
  if (cancelBtn) cancelBtn.onclick = qReset;

  // 导航 chip：点击平滑滚动到对应题
  box.querySelectorAll(".qnav-chip").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      const target = document.getElementById("qa-" + chip.dataset.id);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function qReset() {
  if (!confirm("确定放弃当前卷面，重新出卷？")) return;
  quiz.items = []; quiz.results = [];
  if (quiz.box) quiz.box.innerHTML = "";
  document.getElementById("qProgress").textContent = "";
}

async function qSubmitAll() {
  const box = quiz.box;
  const inputs = box.querySelectorAll(".qa-input");
  const payload = {
    items: Array.from(inputs).map(inp => ({
      question_id: parseInt(inp.dataset.qid, 10),
      user_answer: inp.value || "",
    })),
  };
  const answered = payload.items.filter(it => (it.user_answer || "").trim()).length;
  if (!answered) { alert("请至少回答一题再提交"); return; }
  if (answered < payload.items.length) {
    if (!confirm("还有 " + (payload.items.length - answered) + " 题未作答，仍要提交吗？")) return;
  }

  const submitBtn = document.getElementById("qSubmitAll");
  const cancelBtn = document.getElementById("qCancel");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "判题中…"; }
  if (cancelBtn) cancelBtn.disabled = true;
  // 锁住所有输入框
  inputs.forEach(inp => inp.disabled = true);

  let data = { results: [] };
  try {
    const r = await fetch("/api/quiz/submit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error("HTTP " + r.status + " " + t.slice(0, 200));
    }
    data = await r.json();
  } catch (e) {
    alert("提交失败：" + e.message);
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "提交整卷"; }
    if (cancelBtn) cancelBtn.disabled = false;
    inputs.forEach(inp => inp.disabled = false);
    return;
  }
  quiz.results = (data.results || []).map((res, i) => ({ q: quiz.items[i], out: res }));
  qShowReport();
}

// 整卷复盘：每题展示【题面 / 我的答案 / 参考答案 / 判题结果】
function qShowReport() {
  const box = quiz.box;
  const results = quiz.results;
  const total = results.length;
  const correct = results.filter(r => r.out.is_correct === true).length;
  const wrong = results.filter(r => r.out.is_correct === false).length;
  const skipped = total - correct - wrong;
  const acc = total ? Math.round(correct / total * 100) : 0;
  const grade = quiz.mode === "interview"
    ? (acc >= 80 ? "优秀" : acc >= 60 ? "良好" : "需加强")
    : null;

  // 统计
  let html = "<div class='report'>";
  if (quiz.mode === "interview") {
    html += "<h3>🎤 模拟面试报告</h3>";
    html += "<div class='rp-score'>得分 <b>" + acc + "</b> 分 · 评级 <b>" + grade +
      "</b> · 答对 " + correct + " / " + total + "</div>";
  } else {
    html += "<h3>🎯 智能组卷复盘</h3>";
    html += "<div class='rp-score'>答对 <b>" + correct + "</b> / " + total +
      " · 答错 " + wrong + " · 未作答 " + skipped +
      " · 正确率 <b>" + acc + "%</b></div>";
  }

  // 薄弱点统计
  const weakCats = {};
  results.filter(r => r.out.is_correct === false).forEach(r => {
    const c = (r.q && r.q.category) || "未分类";
    weakCats[c] = (weakCats[c] || 0) + 1;
  });
  const catList = Object.entries(weakCats).sort((a, b) => b[1] - a[1]);
  if (catList.length) {
    html += "<div class='rp-sec'><div class='ref-title'>薄弱点（建议重点复习）</div>";
    html += catList.map(([c, n]) => "<span class='tag company'>" + escapeHtml(c) + " ×" + n + "</span>").join(" ");
    html += "</div>";
  }

  // 导航条（复盘用）
  const nav = results.map((r, i) => {
    const cls = r.out.is_correct === true ? "ok"
              : r.out.is_correct === false ? "bad"
              : "skip";
    return "<a class='qnav-chip " + cls + "' href='#qr-" + r.q.id + "'>" + (i + 1) + "</a>";
  }).join("");
  html += "<div class='qnav'>" + nav + "</div>";

  // 逐题详情
  html += "<div class='rp-sec'><div class='ref-title'>逐题复盘</div>";
  results.forEach((r, i) => {
    const o = r.out;
    const tag = o.is_correct === true ? "✅ 答对"
              : o.is_correct === false ? "❌ 答错"
              : "⚠️ 未作答";
    const tagCls = o.is_correct === true ? "ok" : o.is_correct === false ? "bad" : "skip";
    html += "<div class='rp-wrong' id='qr-" + r.q.id + "'>"
      + "<div class='rt'>"
      +   "<span class='pill'>第 " + (i + 1) + " 题</span>"
      +   "<span class='badge " + tagCls + "'>" + tag + "</span>"
      +   (r.q.category ? "<span class='pill'>" + escapeHtml(r.q.category) + "</span>" : "")
      + "</div>"
      + "<div class='qtext' style='margin-top:6px'>" + renderMarkdown(r.q.question_text || "") + "</div>"
      + "<div class='ref-answer'>"
      +   "<div class='ref-title'>我的答案</div>"
      +   "<div class='md'>"
      +     (o.user_answer && o.user_answer.trim()
            ? ("<pre style='white-space:pre-wrap;margin:0'>" + escapeHtml(o.user_answer) + "</pre>")
            : "<span class='muted'>（未作答）</span>")
      +   "</div>"
      + "</div>";
    if (o.explanation) {
      html += "<div class='ref-answer'>"
        +   "<div class='ref-title'>判官评语</div>"
        +   "<div class='md'>" + escapeHtml(o.explanation) + "</div>"
        + "</div>";
    }
    if (o.error_reason) {
      html += "<div class='muted' style='margin-top:4px'>错误原因：" + escapeHtml(o.error_reason) + "</div>";
    }
    html += "<div class='ref-answer'>"
      +   "<div class='ref-title'>参考答案</div>"
      +   "<div class='md'>" + renderMarkdown(o.reference_answer || "（暂无参考答案）") + "</div>"
      + "</div>"
      + "</div>";
  });
  html += "</div>";

  html += "<div style='margin-top:12px'>"
        +   "<button class='btn' id='qAgain'>再来一组</button>"
        +   "<button class='btn ghost' id='qBackCfg' style='margin-left:8px'>返回配置</button>"
        + "</div>";

  box.innerHTML = html;
  document.getElementById("qProgress").textContent = "本轮已结束";
  document.getElementById("qAgain").onclick = qStart;
  document.getElementById("qBackCfg").onclick = () => { box.innerHTML = ""; document.getElementById("qProgress").textContent = ""; };

  // 复盘 chip 平滑滚动
  box.querySelectorAll(".qnav-chip").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.preventDefault();
      const href = chip.getAttribute("href") || "";
      const m = href.match(/^#qr-(\d+)$/);
      if (!m) return;
      const target = document.getElementById("qr-" + m[1]);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

// ---------------- 面经社区 ----------------
async function loadExperiences() {
  const company = document.getElementById("expCompany").value.trim();
  let url = "/api/experiences";
  if (company) url += "?company=" + encodeURIComponent(company);
  let data = [];
  try { data = await (await fetch(url)).json(); } catch (e) { data = []; }
  const list = document.getElementById("expList");
  if (!list) return;
  list.innerHTML = "";
  if (!data.length) {
    list.innerHTML = "<div class='empty'>还没有面经，点右上角「+ 添加面经」分享一条吧。</div>";
    return;
  }
  data.forEach(e => {
    const el = document.createElement("div");
    el.className = "exp-card";
    let head = "<span class='exp-company'>" + escapeHtml(e.company || "") + "</span>";
    if (e.role) head += "<span class='tag'>" + escapeHtml(e.role) + "</span>";
    if (e.offer_result) head += "<span class='tag company'>" + escapeHtml(e.offer_result) + "</span>";
    head += "<span class='muted'>" + (e.created_at ? e.created_at.slice(0, 10) : "") + "</span>";
    let body = "<div class='exp-head'>" + head + "</div>";
    if (e.position) body += "<div class='muted'>" + escapeHtml(e.position) + "</div>";
    body += "<div class='exp-content'>" + escapeHtml(e.content || "") + "</div>";
    if (e.questions) body += "<div class='exp-q'><b>被问到的题：</b>" + escapeHtml(e.questions).replace(/\n/g, "<br>") + "</div>";
    el.innerHTML = body;
    list.appendChild(el);
  });
}

async function addExperience() {
  const payload = {
    company: document.getElementById("expCompanyIn").value.trim(),
    role: document.getElementById("expRoleIn").value.trim(),
    position: document.getElementById("expPosIn").value.trim(),
    offer_result: document.getElementById("expResultIn").value.trim(),
    content: document.getElementById("expContentIn").value.trim(),
    questions: document.getElementById("expQIn").value.trim(),
  };
  if (!payload.company || !payload.content) { alert("公司和经历描述必填"); return; }
  try {
    const r = await fetch("/api/experiences", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!r.ok) throw new Error("提交失败");
    document.getElementById("expForm").style.display = "none";
    ["expCompanyIn", "expRoleIn", "expPosIn", "expResultIn", "expContentIn", "expQIn"]
      .forEach(id => { document.getElementById(id).value = ""; });
    loadExperiences();
  } catch (e) { alert("提交失败：" + e); }
}

// 手动添加题目
document.getElementById("addQuestionBtn").onclick = openAddModal;
document.getElementById("addClose").onclick = closeAddModal;
document.getElementById("addCancel").onclick = closeAddModal;
document.getElementById("addMask").onclick = closeAddModal;
document.getElementById("addSave").onclick = addSave;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const m = document.getElementById("addModal");
    if (m && m.style.display === "flex") closeAddModal();
  }
});

// ---------------- 初始化 ----------------
document.querySelectorAll("nav button").forEach(b => b.onclick = () => switchView(b.dataset.view));
// 刷题模式
document.getElementById("pmModeRandom").onclick = () => setPracticeMode("random");
document.getElementById("pmModeSeq").onclick = () => setPracticeMode("sequential");
document.getElementById("pmScopeSingle").onclick = () => setPracticeScope("single");
document.getElementById("pmScopeMulti").onclick = () => setPracticeScope("multi");
document.getElementById("pmStart").onclick = pmStart;
document.getElementById("pmNext2").onclick = pmNext;
document.getElementById("pmPrev").onclick = pmPrev;
document.getElementById("pmSubmit").onclick = pmSubmit;
document.getElementById("pmExit").onclick = exitPracticeSession;
document.getElementById("saveSettings").onclick = saveSettings;
document.getElementById("wbRefresh").onclick = loadWrongBook;
document.getElementById("wbExport").onclick = exportWrongBookPDF;
document.getElementById("wbExportMd").onclick = exportWrongBookMD;
document.getElementById("wbCategory").addEventListener("input", debounce(loadWrongBook, 300));
document.getElementById("wbOnlyReviewing").addEventListener("change", loadWrongBook);
document.getElementById("wbGroupReason").addEventListener("change", loadWrongBook);
document.getElementById("bankSearch").addEventListener("input", debounce(() => {
  bank.keyword = document.getElementById("bankSearch").value.trim();
  bank.offset = 0;
  bank.inList = true;
  loadCategoryGrid();
  loadBank();
}, 300));
document.getElementById("diffFilter").addEventListener("change", () => {
  bank.level = parseInt(document.getElementById("diffFilter").value, 10) || 0;
  bank.offset = 0;
  bank.inList = true;
  loadCategoryGrid();
  loadBank();
});
// 背题模式
setupMemCategoryPicker();
document.getElementById("memCat").addEventListener("change", memStart);
document.getElementById("memDiff").addEventListener("change", memStart);
document.getElementById("memSize").addEventListener("change", memStart);
document.getElementById("memPrev").onclick = memPrev;
document.getElementById("memNext").onclick = memNext;
document.addEventListener("keydown", (e) => {
  const memView = document.getElementById("memorize");
  if (!memView || !memView.classList.contains("active")) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
  if (e.key === "ArrowLeft") { e.preventDefault(); memPrev(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); memNext(); }
});
document.getElementById("drawerClose").onclick = closeDetail;
document.getElementById("drawerMask").onclick = closeDetail;
document.getElementById("dqReveal").onclick = revealAnswer;
document.getElementById("dqPractice").onclick = () => { const id = currentDetailId; closeDetail(); startPractice(id); };
document.getElementById("dqEditBtn").onclick = enterEditMode;
document.getElementById("dqSave").onclick = saveAnswerEdit;
document.getElementById("dqCancel").onclick = exitEditMode;
document.getElementById("dqImgBtn").onclick = () => document.getElementById("dqImgFile").click();
document.getElementById("dqImgFile").onchange = uploadAnswerImage;
document.getElementById("hmRange").addEventListener("change", loadHeatmap);

// 残缺链接兜底：data-q 是链接原文，点击后用百度搜索（URL 源数据丢失，
// 至少保证用户能点开看到原文资料）
document.addEventListener("click", (e) => {
  const link = e.target.closest("a.md-link-broken");
  if (!link) return;
  e.preventDefault();
  const q = link.dataset.q;
  if (!q) return;
  window.open("https://www.baidu.com/s?wd=" + encodeURIComponent(q), "_blank", "noopener");
});

// 智能组卷 / 模拟面试
document.querySelectorAll(".qmode").forEach(b => b.onclick = () => setQuizMode(b.dataset.qmode));
document.getElementById("qStart").onclick = qStart;
// 面经社区
document.getElementById("expAddBtn").onclick = () => {
  const f = document.getElementById("expForm");
  f.style.display = f.style.display === "none" ? "" : "none";
};
document.getElementById("expSave").onclick = addExperience;
document.getElementById("expCancel").onclick = () => { document.getElementById("expForm").style.display = "none"; };
document.getElementById("expCompany").addEventListener("input", debounce(loadExperiences, 300));

function openSharedQuestionFromUrl() {
  const rawId = new URLSearchParams(window.location.search).get("q");
  if (!rawId || !/^\d+$/.test(rawId)) return;
  const id = Number(rawId);
  if (!Number.isSafeInteger(id) || id <= 0) return;
  openDetail(id);
}

switchView("bank");
openSharedQuestionFromUrl();

// ==================== 番茄待办（抽象自番茄Todo：待办清单 + 番茄钟 + 专注统计） ====================
const pom = {
  mode: "focus",                 // focus | short | long（用户选择的模式）
  durations: { focus: 25, short: 5, long: 15 },
  longInterval: 4,               // 每完成 N 个专注后进入长休
  focusDone: 0,                  // 本轮已完成专注数（用于决定长休）
  phase: "focus",                // 当前计时阶段 focus | break
  remaining: 25 * 60,            // 秒
  total: 25 * 60,
  running: false,
  timerId: null,
  todoId: null,
  filterCat: "",
  _bound: false,
  initialized: false,
};

function pomClampInt(v, lo, hi, dflt) {
  const n = parseInt(v, 10);
  if (isNaN(n)) return dflt;
  return Math.max(lo, Math.min(hi, n));
}
function pomFormat(s) {
  s = Math.max(0, Math.round(s));
  const m = Math.floor(s / 60), ss = s % 60;
  return String(m).padStart(2, "0") + ":" + String(ss).padStart(2, "0");
}
function pomLevel(m) {
  if (m <= 0) return 0;
  if (m < 25) return 1;
  if (m < 50) return 2;
  if (m < 90) return 3;
  return 4;
}
function pomToast(msg) {
  let t = document.getElementById("pomToast");
  if (!t) {
    t = document.createElement("div");
    t.id = "pomToast";
    t.className = "pom-toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._tid);
  t._tid = setTimeout(() => t.classList.remove("show"), 2200);
}

async function loadPomodoro() {
  pom.durations.focus = pomClampInt(document.getElementById("cfgFocus").value, 1, 120, 25);
  pom.durations.short = pomClampInt(document.getElementById("cfgShort").value, 1, 60, 5);
  pom.durations.long = pomClampInt(document.getElementById("cfgLong").value, 1, 60, 15);
  pom.longInterval = pomClampInt(document.getElementById("cfgInterval").value, 1, 12, 4);
  pomBindOnce();
  // 仅首次进入初始化。之后切换视图时保留正在运行或已暂停的剩余时间。
  if (!pom.initialized) {
    pom.initialized = true;
    pomSetMode("focus", false);
  } else {
    pomRenderTimer();
  }
  await Promise.all([pomLoadCats(), pomLoadTodos(), pomLoadStats()]);
}

function pomBindOnce() {
  if (pom._bound) return;
  pom._bound = true;
  document.getElementById("pomAddForm").addEventListener("submit", (e) => {
    e.preventDefault();
    pomAdd();
  });
  document.getElementById("pomStart").onclick = pomToggle;   // 开始 / 暂停 合一
  document.getElementById("pomReset").onclick = () => pomReset(true);
  document.getElementById("pomTodoSel").onchange = (e) => { pom.todoId = e.target.value ? parseInt(e.target.value, 10) : null; };
  // 模式切换 tab
  document.querySelectorAll("#pomModes .pomo-mode").forEach(b => {
    b.onclick = () => pomSetMode(b.dataset.mode, true);
  });
  // 时长设置
  const onCfg = () => {
    pom.durations.focus = pomClampInt(document.getElementById("cfgFocus").value, 1, 120, 25);
    pom.durations.short = pomClampInt(document.getElementById("cfgShort").value, 1, 60, 5);
    pom.durations.long = pomClampInt(document.getElementById("cfgLong").value, 1, 60, 15);
    pom.longInterval = pomClampInt(document.getElementById("cfgInterval").value, 1, 12, 4);
    if (!pom.running) pomSetMode(pom.mode, false);
  };
  ["cfgFocus", "cfgShort", "cfgLong", "cfgInterval"].forEach(id => {
    document.getElementById(id).onchange = onCfg;
  });
}

async function pomLoadCats() {
  let cats = [];
  try { cats = await (await fetch("/api/todo/categories")).json(); } catch (e) { cats = []; }
  const wrap = document.getElementById("pomCats");
  const sel = document.getElementById("pomCat");
  const chips = [{ name: "", count: 0 }].concat(cats);
  wrap.innerHTML = chips.map(c => {
    const active = (c.name === pom.filterCat) ? " active" : "";
    const label = c.name === "" ? "全部" : c.name;
    const cnt = c.name === "" ? "" : ` <i>${c.count}</i>`;
    return `<button class="pom-chip${active}" data-cat="${escapeHtml(c.name)}">${escapeHtml(label)}${cnt}</button>`;
  }).join("");
  wrap.querySelectorAll(".pom-chip").forEach(b => b.onclick = () => {
    pom.filterCat = b.dataset.cat;
    pomLoadCats();
    pomLoadTodos();
  });
  const cur = sel.value;
  sel.innerHTML = ['<option>默认</option>'].concat(
    cats.map(c => `<option>${escapeHtml(c.name)}</option>`)
  ).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

async function pomLoadTodos() {
  let list = [];
  try {
    const q = pom.filterCat ? `?category=${encodeURIComponent(pom.filterCat)}` : "";
    list = await (await fetch("/api/todos" + q)).json();
  } catch (e) { list = []; }
  const ul = document.getElementById("pomList");
  if (!list.length) {
    ul.innerHTML = `<li class="pomo-empty">还没有待办，添加第一个吧 🍅</li>`;
  } else {
    ul.innerHTML = list.map(t => {
      const pri = t.priority;
      const due = t.due_date ? new Date(t.due_date + "T00:00:00") : null;
      let dueHtml = "";
      if (due) {
        const today = new Date(); today.setHours(0, 0, 0, 0);
        const overdue = !t.done && due < today;
        dueHtml = `<span class="pomo-due${overdue ? " overdue" : ""}">📅 ${t.due_date.slice(5)}</span>`;
      }
      const noteHtml = t.note ? `<div class="pomo-note">${escapeHtml(t.note)}</div>` : "";
      return `<li class="pomo-item${t.done ? " done" : ""}" data-id="${t.id}">
        <input type="checkbox" class="pomo-check" ${t.done ? "checked" : ""}>
        <div class="pomo-main">
          <div class="pomo-title">${escapeHtml(t.title)}</div>
          ${noteHtml}
          <div class="pomo-meta">
            <span class="p-pri p-pri-${pri}">P${pri}</span>
            <span class="pomo-cat">${escapeHtml(t.category)}</span>
            ${dueHtml}
          </div>
        </div>
        <button class="pomo-del" title="删除">🗑</button>
      </li>`;
    }).join("");
    ul.querySelectorAll(".pomo-item").forEach(li => {
      const id = parseInt(li.dataset.id, 10);
      li.querySelector(".pomo-check").onchange = (e) => pomToggle(id, e.target.checked);
      li.querySelector(".pomo-del").onclick = () => pomDelete(id);
    });
  }
  // 关联待办下拉：仅未完成的
  const sel = document.getElementById("pomTodoSel");
  const curTodo = sel.value;
  const open = list.filter(t => !t.done);
  sel.innerHTML = '<option value="">自由专注（不关联待办）</option>' +
    open.map(t => `<option value="${t.id}">${escapeHtml(t.title.slice(0, 24))}</option>`).join("");
  if ([...sel.options].some(o => o.value === curTodo)) sel.value = curTodo;
  else pom.todoId = null;
}

async function pomAdd() {
  const title = document.getElementById("pomTitle").value.trim();
  if (!title) return;
  const body = {
    title,
    category: document.getElementById("pomCat").value || "默认",
    priority: parseInt(document.getElementById("pomPri").value, 10) || 2,
    due_date: document.getElementById("pomDue").value || "",
  };
  try {
    await fetch("/api/todos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    document.getElementById("pomTitle").value = "";
    document.getElementById("pomDue").value = "";
    await pomLoadCats();
    await pomLoadTodos();
  } catch (e) { pomToast("添加失败"); }
}

async function pomToggle(id, done) {
  try {
    await fetch(`/api/todos/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done }),
    });
    await pomLoadTodos();
  } catch (e) { pomToast("更新失败"); }
}

async function pomDelete(id) {
  try {
    await fetch(`/api/todos/${id}`, { method: "DELETE" });
    await Promise.all([pomLoadCats(), pomLoadTodos()]);
  } catch (e) { pomToast("删除失败"); }
}

// ----------------- 番茄钟计时（Pomotroid 风格：模式 tab + 开始/暂停合一） -----------------
function pomModeMinutes(mode) {
  if (mode === "short") return pom.durations.short;
  if (mode === "long") return pom.durations.long;
  return pom.durations.focus;
}
function pomApplyModeTheme() {
  const card = document.querySelector(".pomo-timer");
  if (!card) return;
  card.classList.remove("mode-focus", "mode-short", "mode-long");
  card.classList.add("mode-" + pom.mode);
}
function pomSetMode(mode, notify) {
  pom.mode = mode;
  pom.phase = "focus";
  const mins = pomModeMinutes(mode);
  pom.total = mins * 60;
  pom.remaining = pom.total;
  pom.running = false;
  clearInterval(pom.timerId);
  pom.timerId = null;
  pomApplyModeTheme();
  document.querySelectorAll("#pomModes .pomo-mode").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  pomRenderTimer();
  if (notify) pomToast(mode === "focus" ? "专注模式 🍅" : (mode === "short" ? "短休模式 ☕" : "长休模式 💤"));
}
function pomRenderTimer() {
  document.getElementById("pomTime").textContent = pomFormat(pom.remaining);
  const phaseLabel = pom.phase === "focus"
    ? (pom.mode === "focus" ? "专注" : (pom.mode === "short" ? "短休" : "长休"))
    : "休息中";
  document.getElementById("pomPhase").textContent = phaseLabel;
  document.getElementById("pomRound").textContent =
    pom.phase === "focus" ? `已完成 ${pom.focusDone} / ${pom.longInterval} 个后长休` : "休息一下 ☕";
  const arc = document.getElementById("pomArc");
  const r = 52, C = 2 * Math.PI * r;
  const elapsed = pom.total - pom.remaining;
  const frac = pom.total > 0 ? Math.max(0, Math.min(1, elapsed / pom.total)) : 0;
  arc.style.strokeDasharray = C;
  arc.style.strokeDashoffset = C * (1 - frac);
  arc.classList.toggle("break", pom.phase !== "focus");
  const btn = document.getElementById("pomStart");
  if (btn) btn.textContent = pom.running ? "暂停" : (pom.remaining < pom.total ? "继续" : "开始");
}
function pomToggle() {
  if (pom.running) pomPause(); else pomStart();
}
function pomStart() {
  if (pom.running) return;
  pom.running = true;
  pom.timerId = setInterval(pomTick, 1000);
  pomRenderTimer();
  pomToast(pom.phase === "focus"
    ? (pom.mode === "focus" ? "开始专注 🍅" : "开始休息 ☕") : "继续 ⏱");
}
function pomPause() {
  pom.running = false;
  clearInterval(pom.timerId);
  pom.timerId = null;
  pomRenderTimer();
}
function pomReset(notify) {
  pomSetMode(pom.mode, false);
  if (notify) pomToast("已重置");
}
function pomTick() {
  pom.remaining--;
  if (pom.remaining <= 0) {
    pom.remaining = 0;
    pomRenderTimer();
    pomPhaseDone();
    return;
  }
  pomRenderTimer();
}
async function pomPhaseDone() {
  pomPause();
  if (pom.phase === "focus") {
    await pomRecord("focus", pomModeMinutes(pom.mode), true);
    pom.focusDone++;
    // 达到长休间隔 → 长休，否则短休
    const nextMode = (pom.focusDone % pom.longInterval === 0) ? "long" : "short";
    pom.phase = "break";
    pom.mode = nextMode;
    pom.total = pomModeMinutes(nextMode) * 60;
    pom.remaining = pom.total;
    pomApplyModeTheme();
    document.querySelectorAll("#pomModes .pomo-mode").forEach(b => b.classList.toggle("active", b.dataset.mode === nextMode));
    pomRenderTimer();
    pomBeep();
    pomToast(nextMode === "long" ? "🍅 专注达成，来个长休 💤" : "🍅 专注完成，短休一下 ☕");
  } else {
    await pomRecord("break", pomModeMinutes(pom.mode), true);
    pomSetMode("focus", false);
    pomToast("休息结束，继续加油 💪");
  }
  await pomLoadStats();
}
async function pomRecord(kind, minutes, completed) {
  try {
    await fetch("/api/pomodoro/complete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ todo_id: pom.todoId || null, kind, minutes, completed }),
    });
  } catch (e) { /* 静默：计时器不依赖网络 */ }
}
function pomBeep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.type = "sine"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    o.start(); o.stop(ctx.currentTime + 0.5);
    setTimeout(() => ctx.close(), 600);
  } catch (e) {}
}

// ----------------- 专注统计 -----------------
async function pomLoadStats() {
  let s = null;
  try { s = await (await fetch("/api/pomodoro/stats")).json(); } catch (e) { s = null; }
  if (!s) return;
  document.getElementById("stTodayMin").textContent = s.today.minutes;
  document.getElementById("stWeekMin").textContent = s.week.minutes;
  document.getElementById("stMonthMin").textContent = s.month.minutes;
  document.getElementById("pomTodayCount").textContent = s.today.count;
  // 热力图（17 周 × 7 天，列优先）
  const heat = document.getElementById("pomHeat");
  heat.innerHTML = (s.heatmap || []).map(d => {
    const lv = pomLevel(d.minutes);
    const tip = `${d.day} · ${d.minutes} 分钟`;
    return `<span class="h l${lv}" title="${tip}"></span>`;
  }).join("");
  // 本周纵览（周一~周日）
  const wk = document.getElementById("pomWeek");
  const maxMin = Math.max(1, ...(s.week_overview || []).map(d => d.minutes));
  const wd = ["一", "二", "三", "四", "五", "六", "日"];
  wk.innerHTML = (s.week_overview || []).map((d, i) => {
    const h = d.minutes > 0 ? Math.max(6, Math.round(d.minutes / maxMin * 64)) : 2;
    return `<div class="wbar">
      <div class="wbar-fill" style="height:${h}px" title="${d.minutes} 分钟"></div>
      <div class="wbar-lab">${wd[i] || ""}</div>
      <div class="wbar-num">${d.minutes || ""}</div>
    </div>`;
  }).join("");
}

// ----------------- 成长中心 -----------------
const gr = { _bound: false };
async function loadGrowth() {
  grBindOnce();
  let data = null;
  try { data = await (await fetch("/api/growth/summary")).json(); } catch (e) { data = null; }
  if (!data) { document.getElementById("grBadgeGrid").innerHTML = `<div class="muted">加载失败</div>`; return; }

  // Hero：连胜
  document.getElementById("grStreak").textContent = data.streak;
  document.getElementById("grLongest").textContent = data.longest_streak;
  document.getElementById("grTotal").textContent = data.total_submissions;
  document.getElementById("grFocus").textContent = data.focus_minutes_total;
  document.getElementById("grBadges").textContent = data.badges_unlocked + "/" + data.badges_total;
  const flame = document.getElementById("grFlame");
  flame.classList.toggle("off", data.streak === 0);
  flame.textContent = data.streak === 0 ? "💤" : "🔥";

  // 本月目标
  const g = data.goal;
  document.getElementById("grGoalText").textContent = `${g.current} / ${g.target} 题`;
  document.getElementById("grGoalPct").textContent = g.percent + "%";
  const fill = document.getElementById("grGoalFill");
  fill.style.width = Math.min(100, g.percent) + "%";
  fill.classList.toggle("done", g.percent >= 100);

  // 学习报告
  const w = data.report.week, m = data.report.month;
  document.getElementById("grWeekAns").textContent = w.answered;
  document.getElementById("grWeekAcc").textContent = w.accuracy + "%";
  document.getElementById("grWeekFocus").textContent = w.focus_minutes;
  document.getElementById("grMonthAns").textContent = m.answered;
  document.getElementById("grMonthAcc").textContent = m.accuracy + "%";
  document.getElementById("grMonthFocus").textContent = m.focus_minutes;

  // 成就徽章
  document.getElementById("grBadgeCount").textContent = data.badges_unlocked + "/" + data.badges_total;
  document.getElementById("grBadgeGrid").innerHTML = data.badges.map(b => {
    const pct = b.target > 0 ? Math.round(b.progress / b.target * 100) : (b.unlocked ? 100 : 0);
    return `<div class="badge-card${b.unlocked ? " unlocked" : ""}" title="${escapeHtml(b.desc)}">
      <div class="badge-ic">${b.icon}</div>
      <div class="badge-name">${escapeHtml(b.name)}</div>
      <div class="badge-desc">${escapeHtml(b.desc)}</div>
      <div class="badge-bar"><div class="badge-fill" style="width:${pct}%"></div></div>
      <div class="badge-pct">${b.unlocked ? "已解锁 ✔" : b.progress + "/" + b.target}</div>
    </div>`;
  }).join("");
}

function grBindOnce() {
  if (gr._bound) return;
  gr._bound = true;
  document.getElementById("grGoalEdit").onclick = () => {
    const box = document.getElementById("grGoalEditBox");
    box.style.display = box.style.display === "none" ? "block" : "none";
    if (box.style.display === "block") document.getElementById("grGoalInput").focus();
  };
  document.getElementById("grGoalSave").onclick = async () => {
    const target = parseInt(document.getElementById("grGoalInput").value, 10) || 100;
    try {
      await fetch("/api/growth/goal", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target }),
      });
      document.getElementById("grGoalEditBox").style.display = "none";
      loadGrowth();
    } catch (e) { alert("保存失败"); }
  };
}

// ================ 技术文章 iframe 宽度 override ================
// lianglianglee 模板的 .book-content 在 HTML 里写了 inline style="max-width:960px"，
// 而 .off-canvas-content 的 margin-left:12rem + padding:2.2rem + .book-content
// padding:0 4rem 三层一起把正文挤到 ~360px。后端 ArticleRewriteMiddleware 已注入
// CSS !important，但部分浏览器对 inline style + !important 的优先级处理不一致，
// 这里走 DOM API 直接改写 .book-content 的 style 属性（最高优先级），并把侧栏
// 压窄一截以换取正文宽度。
const _ART_OVERRIDE_CSS = `
  html, body { overflow-x: auto !important; }
  .book-sidebar { width: 12rem !important; }
  .off-canvas-content { margin-left: 12rem !important; padding: 1rem 1rem !important; overflow-y: auto !important; overflow-x: hidden !important; }
  .off-canvas-content .book-content { margin-left: 0 !important; padding: 0 0.75rem !important; max-width: none !important; width: 100% !important; box-sizing: border-box !important; overflow-x: hidden !important; overflow-y: auto !important; }
  .off-canvas-content .book-content .book-post { max-width: none !important; width: 100% !important; }
  .off-canvas-content .book-content .book-post pre { max-width: 100% !important; overflow-x: auto !important; }
  .book-content img, .book-content video, .book-content canvas, .book-content svg, .book-content table { max-width: 100% !important; height: auto !important; box-sizing: border-box !important; display: block !important; }
  .book-content-inner, .book-content > * { max-width: none !important; width: 100% !important; }
  @media (max-width: 820px) {
    .book-sidebar { display: none !important; }
    .off-canvas-content { margin-left: 0 !important; padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    .off-canvas-content .book-content { padding-left: 0 !important; padding-right: 0 !important; }
  }
`;
function _applyArticleOverride() {
  const f = document.querySelector(".art-frame");
  if (!f) return false;
  const doc = f.contentDocument;
  if (!doc || !doc.head || !doc.body) return false;
  // 1) 注入 <style>（双保险，覆盖非 inline CSS）
  if (!doc.getElementById("im-art-override")) {
    const s = doc.createElement("style");
    s.id = "im-art-override";
    s.textContent = _ART_OVERRIDE_CSS;
    doc.head.appendChild(s);
  }
  // 2) DOM API 直接改写 .book-content inline style —— 比 CSS !important 优先级更高
  //    注意：lianglianglee 文章页在 .book-content 上有 inline style="overflow-y:hidden"，
  //    不覆盖这一项会导致正文超长时直接被切、不出滚动条（用户报"底部没滑动条"）
  const contents = doc.querySelectorAll(".book-content");
  contents.forEach(c => {
    c.style.maxWidth = "none";
    c.style.width = "100%";
    c.style.marginLeft = "0";
    c.style.marginRight = "0";
    c.style.paddingLeft = "0.5rem";
    c.style.paddingRight = "0.5rem";
    c.style.boxSizing = "border-box";
    c.style.overflowX = "hidden";
    c.style.overflowY = "auto";
  });
  // 3) 兜底改父级 off-canvas-content —— 万一某篇文档 .book-content 找不到，父级至少能滚
  const off = doc.querySelectorAll(".off-canvas-content");
  off.forEach(o => {
    o.style.overflowY = "auto";
    o.style.overflowX = "hidden";
  });
  // 4) 兜底改所有正文容器：book-content-inner / book-post，确保渲染层不限宽
  doc.querySelectorAll(".book-content-inner, .book-post, .book-content > *").forEach(el => {
    el.style.maxWidth = "none";
    el.style.width = "100%";
  });
  // 5) 兜底：所有正文内可能过宽的元素（流程图/表格/代码块/图片/视频）强制自适应
  //    不让它撑爆 iframe 视口产生横滚
  doc.querySelectorAll(".book-content img, .book-content video, .book-content canvas, .book-content svg, .book-content table, .book-content pre").forEach(el => {
    el.style.maxWidth = "100%";
    el.style.height = "auto";
    el.style.boxSizing = "border-box";
  });
  return true;
}

async function loadArticles() {
  const frame = document.querySelector(".art-frame");
  const unavailable = document.getElementById("articlesUnavailable");
  if (!frame || !unavailable) return;
  // 新版后端会显式说明文章资源是否已配置；旧版/网络失败时保留原 iframe，保证兼容。
  try {
    const response = await fetch("/api/articles/status");
    if (!response.ok) return;
    const status = await response.json();
    if (status && status.available === false) {
      unavailable.textContent = status.message || "技术文章资源尚未配置，暂时无法打开。";
      unavailable.hidden = false;
      frame.hidden = true;
      return;
    }
    unavailable.hidden = true;
    frame.hidden = false;
  } catch (e) {}
}
function installArticleFrameHooks() {
  const f = document.querySelector(".art-frame");
  if (!f || f.__imHooked) return;
  f.__imHooked = true;
  // iframe 内每次跳转文档（点目录切换文章）都会触发 load
  f.addEventListener("load", () => {
    // 偶尔 contentDocument 还没就绪，重试 3 次
    let tries = 0;
    const tick = () => {
      if (_applyArticleOverride() || ++tries >= 3) return;
      setTimeout(tick, 60);
    };
    tick();
  });
  // 首次如果已加载，立即补一次
  if (f.contentDocument && f.contentDocument.readyState === "complete") {
    setTimeout(_applyArticleOverride, 0);
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", installArticleFrameHooks);
} else {
  installArticleFrameHooks();
}
// 也兜底切到 articles 视图时跑一次（switchView 调用前 iframe 可能未加载）
(function () {
  const orig = window.switchView;
  if (typeof orig === "function") {
    window.switchView = function (name) {
      const r = orig.apply(this, arguments);
      if (name === "articles") setTimeout(_applyArticleOverride, 30);
      return r;
    };
  }
})();
