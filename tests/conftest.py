"""测试环境前置：必须在任何 backend.app import 之前准备好 ARTICLES_BOOK_DIR。

原因：ARTICLES_BOOK_DIR 在 backend/app.py 模块级求值，StaticFiles mount 也只发生一次。
如果让 test_api.py 先 import，会把默认路径（真实 lianglianglee 备份）锁定，后续
test_article_rewrite.py 设的临时目录就废了。
"""
import os
import tempfile

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

os.environ.setdefault("ARTICLES_BOOK_DIR", FAKE_BOOK)
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.gettempdir(), "im_test_conftest.db"))
os.environ.setdefault("AGENT_JUDGE_URL", "")
os.environ.setdefault("LLM_BASE_URL", "")