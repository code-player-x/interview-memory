"""测试环境前置：必须在任何 backend.app import 之前准备好 ARTICLES_BOOK_DIR。

原因：ARTICLES_BOOK_DIR 在 backend/app.py 模块级求值，StaticFiles mount 也只发生一次。
如果让 test_api.py 先 import，会把默认路径（真实 lianglianglee 备份）锁定，后续
test_article_rewrite.py 设的临时目录就废了。
"""
import os
import tempfile

# 测试不可继承开发者的真实数据库、文章目录或远端服务凭据。
# 每次 pytest 运行独立建库，避免两个进程互删固定临时数据库。
TEST_DIR = tempfile.mkdtemp(prefix="im_tests_")
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["APP_AUTH_USER"] = os.environ["APP_AUTH_PASSWORD"] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(TEST_DIR, "test.db")
for key in (
    "AGENT_JUDGE_URL", "AGENT_JUDGE_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
    "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL", "SMTP_HOST", "SMTP_USER",
    "SMTP_PASSWORD", "SMTP_PASS",
):
    os.environ[key] = ""
os.environ["STORAGE_BACKEND"] = "local"

# 临时目录：装一些「lianglianglee 风格 .md 实际是 HTML」用于嗅探测试
FAKE_BOOK = tempfile.mkdtemp(prefix="im_book_")
os.makedirs(os.path.join(FAKE_BOOK, "MySQL"), exist_ok=True)
with open(
    os.path.join(FAKE_BOOK, "MySQL", "04 索引.md"),
    "w",
    encoding="utf-8",
) as f:
    f.write(
        "<!DOCTYPE html>\n"
        '<html><head><link rel="stylesheet" href="/static/index.css"></head>\n'
        '<body><a href="/">根</a><a href="/专栏/MySQL/00 开篇.md">开篇</a></body></html>\n'
    )
# 真·纯文本 .md（不是 HTML）—— 验证不会被误判
with open(os.path.join(FAKE_BOOK, "README.md"), "w", encoding="utf-8") as f:
    f.write("# 这是普通 markdown\n\n文本段落。\n")

os.environ["ARTICLES_BOOK_DIR"] = FAKE_BOOK
