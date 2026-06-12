"""이메일 발송"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


DEFAULT_RECIPIENT = "mungui128@gmail.com"


def send_report(
    subject: str,
    html_body: str,
    plain_body: str,
    recipient: str | None = None,
) -> str:
    """보고서를 이메일로 발송합니다."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    to_addr = recipient or os.getenv("REPORT_RECIPIENT", DEFAULT_RECIPIENT)

    if not smtp_user or not smtp_password:
        raise ValueError(
            "이메일 발송을 위해 .env 파일에 SMTP_USER, SMTP_PASSWORD를 설정해 주세요. "
            "(Gmail 사용 시 앱 비밀번호 필요)"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_addr], msg.as_string())

    return to_addr
