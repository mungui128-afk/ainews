"""Gmail 앱 비밀번호 설정 및 발송 테스트"""

from __future__ import annotations

import getpass
import re
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
KST = timezone(timedelta(hours=9))


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def write_env(values: dict[str, str]) -> None:
    lines = [
        "# Gmail SMTP (발송 계정)",
        f"SMTP_HOST={values.get('SMTP_HOST', 'smtp.gmail.com')}",
        f"SMTP_PORT={values.get('SMTP_PORT', '587')}",
        f"SMTP_USER={values.get('SMTP_USER', 'mungui128@gmail.com')}",
        f"SMTP_PASSWORD={values.get('SMTP_PASSWORD', '')}",
        "",
        "# 보고서 수신 이메일",
        f"REPORT_RECIPIENT={values.get('REPORT_RECIPIENT', 'mungui128@gmail.com')}",
        "",
        "# OpenAI API (선택 - AI 요약 사용 시)",
    ]
    if values.get("OPENAI_API_KEY"):
        lines.append(f"OPENAI_API_KEY={values['OPENAI_API_KEY']}")
    else:
        lines.append("# OPENAI_API_KEY=")
    lines.append(f"OPENAI_MODEL={values.get('OPENAI_MODEL', 'gpt-4o-mini')}")
    lines.append("")
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")


def test_smtp(user: str, password: str, recipient: str) -> None:
    now = datetime.now(KST)
    msg = MIMEText(
        f"AI 뉴스 레포트 이메일 설정이 완료되었습니다.\n"
        f"테스트 발송 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)",
        "plain",
        "utf-8",
    )
    msg["Subject"] = "[AI 뉴스 레포트] 이메일 설정 테스트"
    msg["From"] = user
    msg["To"] = recipient

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [recipient], msg.as_string())


def main() -> None:
    print("=" * 50)
    print("  AI 뉴스 레포트 - Gmail 이메일 설정")
    print("=" * 50)
    print()
    print("앱 비밀번호가 없다면:")
    print("  1. https://myaccount.google.com/apppasswords 접속")
    print("  2. Google 2단계 인증 활성화")
    print("  3. '메일'용 앱 비밀번호 16자리 생성")
    print()

    env = read_env()
    user = env.get("SMTP_USER", "mungui128@gmail.com")
    recipient = env.get("REPORT_RECIPIENT", "mungui128@gmail.com")

    print(f"발송 계정: {user}")
    print(f"수신 계정: {recipient}")
    print()

    existing = env.get("SMTP_PASSWORD", "")
    if existing:
        use_existing = input("저장된 앱 비밀번호로 테스트할까요? (Y/n): ").strip().lower()
        if use_existing in ("", "y", "yes"):
            password = existing
        else:
            password = getpass.getpass("Gmail 앱 비밀번호 (16자리): ").strip()
    else:
        password = getpass.getpass("Gmail 앱 비밀번호 (16자리): ").strip()

    password = re.sub(r"\s+", "", password)
    if len(password) < 16:
        raise SystemExit("앱 비밀번호가 올바르지 않습니다. 16자리를 입력해 주세요.")

    env["SMTP_USER"] = user
    env["SMTP_PASSWORD"] = password
    env["REPORT_RECIPIENT"] = recipient
    env.setdefault("SMTP_HOST", "smtp.gmail.com")
    env.setdefault("SMTP_PORT", "587")

    print()
    print("SMTP 연결 및 테스트 메일 발송 중...")
    test_smtp(user, password, recipient)

    write_env(env)
    print()
    print("설정 완료!")
    print(f"  .env 파일 저장됨: {ENV_PATH}")
    print(f"  테스트 메일 발송됨: {recipient}")
    print()
    print("이제 python app.py 실행 후 웹에서 보고서를 생성하세요.")


if __name__ == "__main__":
    main()
