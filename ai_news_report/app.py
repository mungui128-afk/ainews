"""AI 뉴스 레포트 - Flask 웹 애플리케이션"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.email_service import send_report
from services.report_service import generate_report

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)

EXAMPLE_KEYWORDS = [
    "인공지능",
    "반도체",
    "전기차",
    "금리",
    "K-뷰티",
    "원화환율",
]


@app.route("/")
def index():
    return render_template(
        "index.html",
        example_keywords=EXAMPLE_KEYWORDS,
        recipient=os.getenv("REPORT_RECIPIENT", "mungui128@gmail.com"),
    )


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    send_email = data.get("send_email", True)

    if not keyword:
        return jsonify({"success": False, "error": "키워드를 입력해 주세요."}), 400

    try:
        report = generate_report(keyword)
        created = report["created_at"]
        email_sent = False
        email_message = ""
        recipient = os.getenv("REPORT_RECIPIENT", "mungui128@gmail.com")

        if send_email:
            try:
                subject = (
                    f"[AI 뉴스 레포트] {keyword} - "
                    f"{created.year}.{created.month:02d}.{created.day:02d} "
                    f"{created.hour:02d}:{created.minute:02d}"
                )
                recipient = send_report(
                    subject=subject,
                    html_body=report["html"],
                    plain_body=report["plain"],
                )
                email_sent = True
                email_message = f"보고서가 {recipient}(으)로 발송되었습니다."
            except ValueError as e:
                email_message = str(e)

        articles = [
            {
                "title": a.title,
                "link": a.link,
                "source": a.source,
                "published": (
                    f"{a.published.year}년 {a.published.month:02d}월 "
                    f"{a.published.day:02d}일"
                ),
            }
            for a in report["articles"]
        ]

        return jsonify({
            "success": True,
            "email_sent": email_sent,
            "message": email_message or "보고서가 생성되었습니다.",
            "keyword": keyword,
            "article_count": report["article_count"],
            "created_date": f"{created.year}년 {created.month:02d}월 {created.day:02d}일",
            "created_time": f"{created.hour:02d}:{created.minute:02d}:{created.second:02d}",
            "executive_summary": report["report_data"]["executive_summary"],
            "top_issues": report["report_data"]["top_issues"],
            "articles": articles,
            "preview_html": report["html"],
            "recipient": recipient,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"오류가 발생했습니다: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
