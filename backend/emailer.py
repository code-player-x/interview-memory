"""每日复习邮件的固定模板与 SMTP 发送。

模板只接受题目数据和链接，不依赖模型生成，保证通知内容稳定可控。
"""
import os
import smtplib
from datetime import date, datetime
from email.mime.text import MIMEText
from typing import Iterable, Mapping, Optional


def _format_date(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value or "未知")


def render_review_email(items: Iterable[Mapping], heatmap_link: str) -> str:
    """用固定纯文本模板渲染当天的待复习题目。"""
    rows = list(items)
    today = date.today().isoformat()
    lines = [
        f"早上好 👋 根据艾宾浩斯遗忘曲线，今天有 {len(rows)} 道题到了复习时间（{today}）：",
        "",
    ]
    for number, item in enumerate(rows, 1):
        category = item.get("category") or "未分类"
        question = item.get("question_text") or "（题目内容缺失）"
        answer = item.get("reference_answer") or "（暂无参考答案）"
        last_answer = item.get("last_user_answer") or "（未记录）"
        lines.extend([
            f"{number}. [{category}] {question}",
            f"   · 你曾答错：{last_answer}",
            f"   · 参考答案：{answer}",
            f"   · 上次错误：{_format_date(item.get('first_wrong_at'))} · 已错 {item.get('wrong_count') or 1} 次",
            "",
        ])
    lines.extend([
        "────────────────────────",
        "💡 先凭记忆作答，再打开应用对照参考答案。",
        f"📊 查看你的热力图：{heatmap_link}",
    ])
    return "\n".join(lines)


def send_review_email(
    to_email: str,
    items: Iterable[Mapping],
    heatmap_link: Optional[str] = None,
) -> bool:
    """发送固定复习邮件；缺少 SMTP 配置或发送失败时安全返回 False。"""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    # SMTP_PASS 是历史配置名，保留兼容；文档统一使用 SMTP_PASSWORD。
    password = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")
    if not (to_email and host and user and password):
        return False

    try:
        port = int(os.getenv("SMTP_PORT", "465"))
    except ValueError:
        return False
    use_ssl = os.getenv("SMTP_USE_SSL", "1").strip().lower() not in {"0", "false", "no"}
    rows = list(items)
    base_url = (heatmap_link or os.getenv("APP_BASE_URL", "http://localhost:8000")).rstrip("/")
    message = MIMEText(render_review_email(rows, base_url), "plain", "utf-8")
    message["Subject"] = f"【八股文复习】今天有 {len(rows)} 道错题待巩固（{date.today().isoformat()}）"
    message["From"] = user
    message["To"] = to_email

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as client:
                client.login(user, password)
                client.sendmail(user, [to_email], message.as_string())
        else:
            with smtplib.SMTP(host, port) as client:
                client.starttls()
                client.login(user, password)
                client.sendmail(user, [to_email], message.as_string())
    except (OSError, smtplib.SMTPException):
        return False
    return True
