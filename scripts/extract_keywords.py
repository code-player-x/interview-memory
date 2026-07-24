#!/usr/bin/env python
"""批量用 LLM 提取每题重点关键词，写回 questions.keywords（逗号分隔）。

用法：
  .venv/Scripts/python scripts/extract_keywords.py            # 仅提取尚未提取的题
  .venv/Scripts/python scripts/extract_keywords.py --force    # 全量重提
  .venv/Scripts/python scripts/extract_keywords.py --dry-run  # 只打印将发送的 prompt，不调 LLM、不写库

依赖环境变量（同 judge.py）：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
"""
import os
import sys
import re
import json
import argparse
import sqlite3
import textwrap

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import httpx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "interview_memory.db")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

PROMPT_TMPL = """你是一位面试备考助手。请从下面题目的【参考答案】中提取 3-6 个最关键的「记忆锚点」——也就是面试回答时**必须提到、能体现你掌握核心概念**的术语/机制/模式名（如"信号量"、"channel+close"、"原子操作"、"对象头 mark word"等）。

【约束 1 - 字面匹配】提取的每个关键词都必须真实出现在参考答案原文里（逐字匹配，不要改写、不要同义替换、不要造词）。前端会按字面高亮这些词。

【约束 2 - 绝对不要提取这些"实现细节"，它们不是记忆锚点】
- Go 标准库的包名/函数名/类型名：fmt / Printf / Println / make / len / cap / new / panic / recover / context / http / json / sync.WaitGroup / time.Sleep / strings. / bytes. / log. / os. / bufio. 等
- Go 内置类型与关键字：int / string / struct / func / map / chan / interface / nil / true / false / for / range / go / defer / select / case
- 通用变量名/参数名：wg / ctx / ch / done / quit / data / err / buf / tmp / i / j / n / k / v / mu / lock / rw / result / num / count / flag / ok / ret / res / val / key
- 短驼峰命名的局部标识符：counterMutex / wg.Add / ch <- 等

【约束 3 - 应当提取什么】概念 / 机制 / 算法 / 模式名：
- 并发原语：信号量、原子操作、CAS、自旋锁、互斥锁、读写锁、内存屏障、有序性、可见性、happens-before
- Go 特性：goroutine、channel 通信、close 通知、range 遍历、select 多路复用、context 取消传播、Worker Pool、生产者消费者
- 模式名：限流、令牌桶、滑动窗口、单例、双检锁、对象池、发布订阅
- 中间/底层概念：对象头、monitor、Mark Word、偏向锁、轻量级锁、重量级锁、STW、三色标记、写屏障

题目：
{question_text}

参考答案：
{reference_answer}

仅返回 JSON 数组，如：["关键词1","关键词2","关键词3"]"""


# 兜底黑名单：即便 LLM 偶尔抽到这些"代码味儿"的词，也直接过滤掉。
# 原则：只放「确凿是 Go 标识符 / 标准库符号 / 经典短变量名」的。
# 看似 Go 关键字但常作为概念出现的（lock / gc / range / map / context / select / append / defer / func / struct / interface / chan / nil / err / fd）不杀，交给 LLM 的 prompt 控制。
BLOCKLIST_KW = {
    # Go stdlib 函数 / 包名
    "fmt", "Printf", "Println", "Print", "Sprintf", "Fprintf", "Errorf", "Fprintln",
    "make", "len", "cap", "new", "copy", "delete", "close", "panic", "recover", "append",
    "time.Sleep", "time.Now", "time.After", "time.Tick", "time.Since", "time.Second", "time.Minute",
    "sync.WaitGroup", "sync.Mutex", "sync.RWMutex", "sync.Once", "sync.Pool", "sync.Map", "sync.Cond",
    "log.Println", "log.Printf", "log.Fatal", "log.Fatal", "log.Print",
    "context.Background", "context.WithCancel", "context.WithTimeout", "context.WithDeadline",
    # Go 内置类型（func/struct/interface/chan/map/defer/select/range/for/case 等作为概念保留）
    "int", "int32", "int64", "uint", "uint32", "uint64", "byte", "rune", "string", "bool", "error",
    "float32", "float64", "iota",
    # 确凿是变量名缩写的（ch 是 channel 缩写作为概念保留；只放明显占位/局部变量）
    "wg", "wg1", "wg2", "wgp", "wgc", "wgg", "wgAdd", "wgDone", "wgWait",
    "counterMutex", "counter", "mutex", "rwm", "rw",
    # 占位符 / 调试残留
    "xx", "xxx", "todo", "tmp", "buf", "num", "ret", "res", "val", "k", "v", "i", "j", "vs", "fp",
}


def is_blocked(kw: str) -> bool:
    k = kw.strip()
    if not k:
        return True
    if k in BLOCKLIST_KW:
        return True
    # 含 . 操作符前缀的（"http.Get" / "fmt.Println" 等）一律视为标准库调用
    if "." in k and k.split(".", 1)[0] in {"fmt", "log", "os", "io", "http", "json", "time", "sync", "context", "strings", "bytes", "bufio", "errors", "sort", "strconv", "reflect", "runtime"}:
        return True
    return False


def migrate(db):
    try:
        db.execute("ALTER TABLE questions ADD COLUMN keywords TEXT DEFAULT ''")
        db.commit()
        print("[migrate] 已添加 keywords 列")
    except Exception:
        db.rollback()  # 列已存在则忽略


def parse_keywords(content):
    content = (content or "").strip()
    if content.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\[.*\]", content, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    if isinstance(data, list):
        kws = [str(x).strip() for x in data if str(x).strip()][:6]
        # 兜底：黑名单词直接丢弃
        kws = [k for k in kws if not is_blocked(k)]
        # 查重保序
        seen, out = set(), []
        for k in kws:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out[:6]
    return []


def extract_one(q_text, ref):
    prompt = PROMPT_TMPL.format(question_text=q_text or "", reference_answer=ref or "")
    messages = [
        {"role": "system", "content": "你是一个面试备考助手。只输出 JSON 数组，不要解释。"},
        {"role": "user", "content": prompt},
    ]
    resp = httpx.post(
        LLM_BASE_URL.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
        json={"model": LLM_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 256},
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    return parse_keywords(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="全量重提（忽略已有 keywords）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 prompt，不调 LLM、不写库")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reclean", action="store_true", help="仅清空含黑名单词的题的 keywords（不动数据库结构），然后退出；可加 --dry-run 预览")
    args = ap.parse_args()

    if not args.dry_run and not args.reclean and not (LLM_BASE_URL and LLM_API_KEY and LLM_MODEL):
        print("缺少 LLM 配置（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL），无法提取。可加 --dry-run 预览，或 --reclean 仅清理。")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    migrate(db)

    if args.reclean:
        cleaned = 0
        for qid, kws in db.execute("SELECT id, keywords FROM questions WHERE keywords IS NOT NULL AND keywords != ''").fetchall():
            parts = [k.strip() for k in kws.split(",") if k.strip()]
            bad = [k for k in parts if is_blocked(k)]
            if bad:
                cleaned += 1
                if args.dry_run:
                    print(f"  [dry] id={qid}  将清空（bad={bad}）  原={kws}")
                else:
                    db.execute("UPDATE questions SET keywords='' WHERE id=?", (qid,))
        if not args.dry_run:
            db.commit()
        print(f"--reclean 完成：{'将清空' if args.dry_run else '已清空'} {cleaned} 题的 keywords")
        return

    if args.force:
        rows = db.execute("SELECT id, question_text, reference_answer FROM questions").fetchall()
    else:
        rows = db.execute(
            "SELECT id, question_text, reference_answer FROM questions "
            "WHERE keywords IS NULL OR TRIM(keywords)=''"
        ).fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"待处理题目：{len(rows)} 题")
    if not rows:
        print("没有需要提取的题目。")
        return

    if args.dry_run:
        for i, (qid, q_text, ref) in enumerate(rows, 1):
            print(f"\n--- [{i}/{len(rows)}] id={qid} prompt 预览 ---")
            print(textwrap.fill(PROMPT_TMPL.format(question_text=q_text or "", reference_answer=(ref or "")[:160]), 100))
        return

    done = 0
    for i, (qid, q_text, ref) in enumerate(rows, 1):
        try:
            kws = extract_one(q_text, ref)
            if kws:
                db.execute("UPDATE questions SET keywords=? WHERE id=?", (",".join(kws), qid))
                db.commit()
                done += 1
                print(f"[{i}/{len(rows)}] id={qid} -> {kws}")
            else:
                print(f"[{i}/{len(rows)}] id={qid} -> 未提取到关键词")
        except Exception as e:
            print(f"[{i}/{len(rows)}] id={qid} 失败：{str(e)[:80]}")
    print(f"\n完成：成功写入 {done}/{len(rows)} 题的关键词。")


if __name__ == "__main__":
    main()
