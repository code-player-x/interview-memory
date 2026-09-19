"""interview-memory · 全流程图验证脚本（对临时 DB 跑通，不污染线上数据）。

覆盖：
  1. 题库导入 (import)
  2. 随机抽题 (random)
  3. 提交作答 + 判题降级 (answer / heuristic)
  4. 热力图聚合 (activity)
  5. 错题本 (wrong-book / master)
  6. 待复习查询 (review/due)
  7. 复习反馈 + 艾宾浩斯推进 (review/{id})
  8. 设置读写 + 调度重排 (settings)
  9. 每日邮件推送 (scheduler / emailer 模板渲染 + 缺失跳过)
 10. 判题三分支 (heuristic / agent成功 / agent不可用降级)
"""
import os
import sys
import tempfile
import asyncio
from datetime import datetime, timedelta

# ---- 0. 指向临时 DB，必须在 import backend.app 之前 ----
TMP_DB = os.path.join(tempfile.gettempdir(), "im_verify_%d.db" % os.getpid())
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
os.environ["DATABASE_URL"] = "sqlite:///" + TMP_DB
os.environ["AGENT_JUDGE_URL"] = ""  # 默认走启发式
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""

PROJECT = os.path.dirname(os.path.abspath(__file__))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from fastapi.testclient import TestClient  # noqa: E402
import backend.app as appmod  # noqa: E402  (触发 init_db + start_scheduler)
from backend.db import SessionLocal  # noqa: E402
from backend import models as M  # noqa: E402
from backend import judge as J  # noqa: E402
from backend import emailer as E  # noqa: E402
from backend import scheduler as S  # noqa: E402
from backend.ebbinghaus import get_steps  # noqa: E402

client = TestClient(appmod.app)

PASS, FAIL = [], []
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (("  — " + extra) if extra else ""))

print("\n========== interview-memory 全流程图验证 ==========\n")

# 1. 题库导入
print("[1] 题库导入流程")
r1 = client.post("/api/questions/import", json={"platform": "test", "category": "Java",
    "question_text": "Q1 什么是 HashMap?", "reference_answer": "HashMap 是基于哈希表的 Map 实现，支持 O(1) 查询。", "difficulty": 2})
r2 = client.post("/api/questions/import", json={"platform": "test", "category": "并发",
    "question_text": "Q2 volatile 的作用?", "reference_answer": "volatile 保证可见性与禁止指令重排，但不保证原子性。", "difficulty": 3})
r3 = client.post("/api/questions/import", json={"platform": "test", "category": "并发",
    "question_text": "Q3 synchronized 与 Lock 区别?", "reference_answer": "Lock 更灵活，可中断、可超时、可公平。", "difficulty": 3})
q1, q2, q3 = r1.json()["id"], r2.json()["id"], r3.json()["id"]
check("导入 3 题成功(返回 id)", all(x > 0 for x in (q1, q2, q3)), f"ids={q1},{q2},{q3}")
rl = client.get("/api/questions?limit=10").json()
check("列表接口可见导入题目", rl["total"] >= 3 and any(x["id"] == q1 for x in rl["items"]))

# 2. 随机抽题
print("\n[2] 随机抽题流程")
rr = client.get("/api/questions/random").json()
check("随机抽题返回题目", "id" in rr, f"got id={rr.get('id')}")

# 3. 提交作答（正确，启发式）
print("\n[3] 提交作答 + 判题(启发式)流程")
ra_c = client.post("/api/answer", json={"question_id": q1, "user_answer": "HashMap 是基于哈希表的 Map 实现，支持 O(1) 查询。"}).json()
check("精确匹配判为正确", ra_c["is_correct"] is True, f"source={ra_c['source']}")
check("无 Agent 时走 heuristic 降级", ra_c["source"] == "heuristic")

# 4. 提交作答（错误，启发式）→ 错题本 + 复习计划 + 热力图
print("\n[4] 答错副作用：错题本/复习计划/热力图")
ra_w = client.post("/api/answer", json={"question_id": q2, "user_answer": "我完全不会这个随便写写写写写。"}).json()
check("不相关答案判为错误", ra_w["is_correct"] is False)
ra_w3 = client.post("/api/answer", json={"question_id": q3, "user_answer": "乱答乱答乱答乱答乱答乱答乱答。"}).json()
check("第三题也判错", ra_w3["is_correct"] is False)

act = client.get("/api/activity").json()
from datetime import date as _date
today_row = next((a for a in act if a["day"] == _date.today().isoformat()), None)
check("热力图聚合 answered=3", today_row and today_row["answered"] == 3, str(today_row))
check("热力图聚合 correct=1/wrong=2", today_row and today_row["correct"] == 1 and today_row["wrong"] == 2)

wb = client.get("/api/wrong-book").json()
check("错题本含 Q2/Q3 两条", len(wb) == 2 and {x["question_id"] for x in wb} == {q2, q3})
wb_q2 = next(x for x in wb if x["question_id"] == q2)
check("错题本 mastery=learning, wrong_count=1", wb_q2["mastery"] == "learning" and wb_q2["wrong_count"] == 1)

db = SessionLocal()
try:
    rs_q2 = db.query(M.ReviewSchedule).filter(M.ReviewSchedule.question_id == q2).first()
    check("答错自动建复习计划 stage=1", rs_q2 is not None and rs_q2.stage == 1)
    check("复习计划 next_review=now+1d(未到期)", rs_q2 and rs_q2.next_review_at > datetime.utcnow())
finally:
    db.close()

# 5. 待复习查询（未到期应为空；手动置过去后应有）
print("\n[5] 待复习查询流程")
due_empty = client.get("/api/review/due").json()
check("未到期时 /review/due 为空", due_empty == [])
db = SessionLocal()
try:
    rs_q2 = db.query(M.ReviewSchedule).filter(M.ReviewSchedule.question_id == q2).first()
    rs_q2.next_review_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
finally:
    db.close()
due_q2 = client.get("/api/review/due").json()
check("置为过去后 /review/due 命中 Q2", len(due_q2) == 1 and due_q2[0]["question_id"] == q2)

# 6. 复习反馈 + 艾宾浩斯推进
print("\n[6] 复习反馈 + 艾宾浩斯推进流程")
rf1 = client.post(f"/api/review/{q2}", json={"remembered": True}).json()
check("记住→stage 1→2", rf1["stage"] == 2 and rf1["status"] == "pending")
rf2 = client.post(f"/api/review/{q2}", json={"remembered": False}).json()
check("没记住→stage 回退到 1", rf2["stage"] == 1 and rf2["status"] == "pending")
# 连续记住直到 mastered
stage = 1
for _ in range(10):
    rr = client.post(f"/api/review/{q2}", json={"remembered": True}).json()
    stage = rr["stage"]
    if rr["status"] == "done":
        break
check("连续记住后到达 mastered(status=done)", rr["status"] == "done" and stage > len(get_steps("1,2,4,7,15,30,60")))
db = SessionLocal()
try:
    wb2 = db.query(M.WrongBook).filter(M.WrongBook.question_id == q2).first()
    check("mastery 翻为 mastered", wb2.mastery == "mastered")
finally:
    db.close()

# 7. 标记已掌握
print("\n[7] 标记已掌握流程")
client.post(f"/api/review/{q3}", json={"remembered": True})  # 先推一步
rm = client.post(f"/api/wrong-book/{q3}/master").json()
check("master 接口返回 mastered", rm["status"] == "mastered")
wb_only = client.get("/api/wrong-book?only_reviewing=true").json()
check("only_reviewing 过滤掉已掌握项", all(x["question_id"] != q3 for x in wb_only))

# 8. 设置读写 + 调度重排
print("\n[8] 设置读写 + 调度重排流程")
gs = client.get("/api/settings").json()
check("读取默认设置", gs["push_time"] == "09:00" and gs["ebbinghaus_steps"] == "1,2,4,7,15,30,60")
ps = client.post("/api/settings", json={"email": "me@test.com", "push_time": "08:30",
    "ebbinghaus_steps": "1,3,7", "app_base_url": "http://localhost:8000"}).json()
check("更新设置成功", ps["status"] == "updated")
gs2 = client.get("/api/settings").json()
check("设置已持久化(推送时间/间隔)", gs2["push_time"] == "08:30" and gs2["ebbinghaus_steps"] == "1,3,7")
check("ebbinghaus 解析 1,3,7=[1,3,7]", get_steps("1,3,7") == [1, 3, 7])

# 9. 每日邮件推送（模板渲染 + 缺失跳过）
print("\n[9] 每日邮件推送流程")
sample = [{"category": "并发", "question_text": "volatile 的作用?", "last_user_answer": "不会",
           "reference_answer": "保证可见性与禁止指令重排", "first_wrong_at": "2026-07-20", "wrong_count": 1}]
body = E.render_review_email(sample, heatmap_link="http://localhost:8000/")
check("邮件模板渲染含题目与参考答案", "volatile" in body and "保证可见性" in body)
# 未配置 SMTP → send 返回 False 且不崩溃
sent = E.send_review_email("", sample)
check("SMTP 缺失时 send 安全返回 False", sent is False)
# run_daily_review 在未配置邮箱时返回 0 不崩溃
pushed = S.run_daily_review()
check("run_daily_review 无邮箱时返回 0(不崩溃)", pushed == 0)

# 10. 判题三分支
print("\n[10] 判题三分支")
# (a) heuristic 已通过(answer 流程)。这里单独验证 overlap 阈值
loop = asyncio.new_event_loop()
async def j_heur():
    return await J.judge("q", "HashMap 是基于哈希表的 Map 实现，支持 O(1) 查询。",
                         "HashMap 是基于哈希表的 Map 实现，支持 O(1) 查询。")
hc = loop.run_until_complete(j_heur())
check("heuristic 精确匹配=True", hc[0] is True and hc[3] == "heuristic")

# (b) agent 成功分支（mock httpx.AsyncClient）
class FakeResp:
    def raise_for_status(self): pass
    def json(self): return {"is_correct": True, "explanation": "mock agent ok"}
class FakeClient:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, *a, **k): return FakeResp()
import httpx
orig_url = os.environ.get("AGENT_JUDGE_URL", "")
orig_client = httpx.AsyncClient
os.environ["AGENT_JUDGE_URL"] = "http://mock-agent"
httpx.AsyncClient = FakeClient
async def j_agent():
    return await J.judge("q", "r", "u")
ac = loop.run_until_complete(j_agent())
check("agent 成功分支解析 is_correct/explanation", ac[0] is True and ac[1] == "mock agent ok" and ac[3] == "agent")
httpx.AsyncClient = orig_client  # 恢复真实 AsyncClient，否则(c)会误用 mock

# (c) agent 不可用 → pending（连向关闭端口，连接必失败）
os.environ["AGENT_JUDGE_URL"] = "http://127.0.0.1:1/nope"
async def j_down():
    return await J.judge("q", "r", "u")
dc = loop.run_until_complete(j_down())
check("agent 不可用→降级 (None,'pending')", dc[0] is None and dc[3] == "pending")
loop.close()
os.environ["AGENT_JUDGE_URL"] = orig_url

# ---- 汇总 ----
print("\n========== 验证汇总 ==========")
print(f"通过 {len(PASS)} / 失败 {len(FAIL)}")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  - " + f)
else:
    print("🎉 全部流程通过！")

# 清理
try:
    appmod.scheduler.shutdown(wait=False)
    from backend.db import engine
    engine.dispose()
except Exception:
    pass
try:
    if os.path.exists(TMP_DB):
        os.remove(TMP_DB)
except Exception:
    pass
sys.exit(1 if FAIL else 0)
