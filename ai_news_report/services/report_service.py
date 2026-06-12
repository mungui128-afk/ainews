"""뉴스 보고서 생성"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from .news_service import NewsArticle, fetch_news

KST = timezone(timedelta(hours=9))
TOP_N = 5


def _format_kst(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    kst = dt.astimezone(KST)
    return f"{kst.year}년 {kst.month:02d}월 {kst.day:02d}일 {kst.hour:02d}:{kst.minute:02d}"


def _format_date_kst(dt: datetime) -> str:
    return f"{dt.year}년 {dt.month:02d}월 {dt.day:02d}일"


def _format_time_kst(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def _analyze_with_gemini(keyword: str, articles: list[NewsArticle]) -> dict[str, Any] | None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or not articles:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    news_text = "\n".join(
        f"{i}. [{a.source}] {a.title}\n   요약: {(a.summary or a.title)[:250]}\n   URL: {a.link}"
        for i, a in enumerate(articles[:12], 1)
    )

    prompt = f"""당신은 뉴스 분석 전문가입니다. JSON만 출력하세요.

키워드: {keyword}
뉴스 목록:
{news_text}

형식:
{{"executive_summary":"핵심요약 3~4문장","top_issues":[{{"rank":1,"title":"","key_content":"","why_important":"","source":"","link":""}}]}}
top_issues 5개."""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
        }
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
        issues = data.get("top_issues", [])[:TOP_N]
        for i, issue in enumerate(issues, 1):
            issue["rank"] = i
        return {
            "executive_summary": data.get("executive_summary", ""),
            "top_issues": issues,
        }
    except Exception:
        return None


def _build_fallback_report(keyword: str, articles: list[NewsArticle]) -> dict[str, Any]:
    top5 = articles[:TOP_N]
    titles = [a.title.split(" - ")[0] for a in top5[:3]]
    title_preview = ", ".join(f"「{t[:25]}」" for t in titles)

    executive_summary = (
        f"최근 7일간 '{keyword}' 관련 뉴스 {len(articles)}건을 분석한 결과, "
        f"{title_preview} 등이 핵심 이슈로 부상했습니다. "
        f"아래 TOP {len(top5)} 이슈는 보도 빈도·관련성 기준으로 선정했으며, "
        f"'{keyword}' 분야의 최신 동향 파악에 참고하시기 바랍니다."
    )

    top_issues = []
    for i, article in enumerate(top5, 1):
        key_content = (article.summary or article.title)[:300]
        if not key_content.endswith("."):
            key_content = key_content.rstrip() + "."

        why_important = (
            f"'{keyword}' 분야의 최근 흐름을 이해하는 데 핵심적인 이슈입니다. "
            f"{article.source} 등 주요 매체에서 보도되어 "
            f"업무·의사결정 시 참고 가치가 높습니다."
        )

        top_issues.append({
            "rank": i,
            "title": article.title,
            "key_content": key_content,
            "why_important": why_important,
            "source": article.source,
            "link": article.link,
            "published": _format_kst(article.published),
        })

    return {
        "executive_summary": executive_summary,
        "top_issues": top_issues,
    }


def _issues_to_html(issues: list[dict[str, Any]]) -> str:
    cards = []
    for issue in issues:
        link = issue.get("link", "#")
        cards.append(f"""
        <div class="issue-card">
          <div class="issue-rank">TOP {issue.get("rank", "")}</div>
          <h3 class="issue-title">{issue.get("title", "")}</h3>
          <dl class="issue-detail">
            <dt>핵심내용</dt>
            <dd>{issue.get("key_content", "")}</dd>
            <dt>왜 중요한지</dt>
            <dd>{issue.get("why_important", "")}</dd>
            <dt>출처</dt>
            <dd><a href="{link}" target="_blank" rel="noopener">[{issue.get("source", "")}] {issue.get("title", "")[:60]}</a></dd>
          </dl>
        </div>""")
    return "\n".join(cards)


def _issues_to_plain(issues: list[dict[str, Any]]) -> str:
    lines = ["=== 주요이슈 TOP 5 ===", ""]
    for issue in issues:
        lines.extend([
            f"TOP {issue.get('rank', '')}. {issue.get('title', '')}",
            f"  · 핵심내용: {issue.get('key_content', '')}",
            f"  · 왜 중요한지: {issue.get('why_important', '')}",
            f"  · 출처: [{issue.get('source', '')}] {issue.get('link', '')}",
            "",
        ])
    return "\n".join(lines)


def _build_email_html(
    keyword: str,
    created_at: datetime,
    article_count: int,
    report_data: dict[str, Any],
    all_articles: list[NewsArticle],
) -> str:
    issues_html = _issues_to_html(report_data["top_issues"])
    sources_html = "".join(
        f'<li><a href="{a.link}" target="_blank" rel="noopener">'
        f'[{a.source}] {a.title}</a> '
        f'<span class="source-date">({_format_kst(a.published)})</span></li>'
        for a in all_articles
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.7; color: #222; max-width: 720px; margin: 0 auto; padding: 24px; }}
    h1 {{ color: #1a365d; border-bottom: 3px solid #3182ce; padding-bottom: 8px; }}
    h2 {{ color: #2c5282; margin-top: 28px; font-size: 1.1rem; }}
    .meta {{ background: #ebf8ff; padding: 12px 16px; border-radius: 8px; margin: 16px 0; }}
    .meta p {{ margin: 4px 0; }}
    .summary-box {{ background: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px 20px; border-radius: 8px; margin: 20px 0; }}
    .summary-box h2 {{ margin-top: 0; color: #b45309; }}
    .summary-box p {{ margin: 0; color: #78350f; }}
    .issue-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; }}
    .issue-rank {{ display: inline-block; background: #2563eb; color: white; font-size: 0.75rem; font-weight: 700; padding: 2px 10px; border-radius: 12px; margin-bottom: 8px; }}
    .issue-title {{ font-size: 1rem; font-weight: 700; color: #1e293b; margin: 4px 0 12px; }}
    .issue-detail {{ margin: 0; }}
    .issue-detail dt {{ font-size: 0.8rem; font-weight: 700; color: #64748b; margin-top: 8px; }}
    .issue-detail dd {{ margin: 4px 0 0 0; font-size: 0.9rem; color: #334155; }}
    .issue-detail a {{ color: #2563eb; text-decoration: none; }}
    .sources {{ background: #f7fafc; padding: 16px 20px; border-radius: 8px; border-left: 4px solid #3182ce; }}
    .sources ul {{ padding-left: 20px; }}
    .sources li {{ margin-bottom: 10px; word-break: break-all; }}
    .sources a {{ color: #2b6cb0; text-decoration: none; }}
    .source-date {{ color: #718096; font-size: 0.9em; }}
    .footer {{ margin-top: 32px; font-size: 0.85em; color: #718096; text-align: center; }}
  </style>
</head>
<body>
  <h1>📰 AI 뉴스 레포트</h1>
  <div class="meta">
    <p><strong>검색 키워드:</strong> {keyword}</p>
    <p><strong>수집 기간:</strong> 최근 7일</p>
    <p><strong>생성일:</strong> {_format_date_kst(created_at)}</p>
    <p><strong>생성시간:</strong> {_format_time_kst(created_at)} (KST)</p>
    <p><strong>수집 건수:</strong> {article_count}건</p>
  </div>

  <div class="summary-box">
    <h2>💡 핵심요약</h2>
    <p>{report_data["executive_summary"]}</p>
  </div>

  <h2>🔥 주요이슈 TOP 5</h2>
  {issues_html}

  <h2>📚 참고출처</h2>
  <div class="sources">
    <ul>{sources_html}</ul>
  </div>

  <div class="footer">본 보고서는 AI 뉴스 레포트 시스템에 의해 자동 생성되었습니다.</div>
</body>
</html>"""


def generate_report(keyword: str) -> dict:
    """보고서 HTML과 메타데이터를 생성합니다."""
    created_at = datetime.now(KST)
    articles = fetch_news(keyword, days=7)

    if not articles:
        raise ValueError(f"'{keyword}' 관련 최근 7일 이내 뉴스를 찾지 못했습니다.")

    report_data = _analyze_with_gemini(keyword, articles) or _build_fallback_report(keyword, articles)

    html = _build_email_html(keyword, created_at, len(articles), report_data, articles)

    plain_lines = [
        f"AI 뉴스 레포트 - {keyword}",
        f"생성일: {_format_date_kst(created_at)}",
        f"생성시간: {_format_time_kst(created_at)} (KST)",
        "",
        "=== 핵심요약 ===",
        report_data["executive_summary"],
        "",
        _issues_to_plain(report_data["top_issues"]),
        "=== 참고출처 ===",
    ]
    for i, a in enumerate(articles, 1):
        plain_lines.append(f"{i}. [{a.source}] {a.title}")
        plain_lines.append(f"   {a.link}")

    return {
        "keyword": keyword,
        "created_at": created_at,
        "article_count": len(articles),
        "html": html,
        "plain": "\n".join(plain_lines),
        "report_data": report_data,
        "articles": articles,
    }
