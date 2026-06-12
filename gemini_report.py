"""뉴스 수집 + Gemini 보고서 생성"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import quote_plus

import feedparser
import requests

KST = timezone(timedelta(hours=9))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


def _parse_published(entry: dict) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                pass
    return None


def _extract_source(entry: dict) -> str:
    source = entry.get("source", {})
    if isinstance(source, dict) and source.get("title"):
        return source["title"]
    link = entry.get("link", "")
    match = re.search(r"https?://(?:www\.)?([^/]+)", link)
    return match.group(1) if match else "알 수 없음"


def _clean_summary(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _format_date(dt: datetime) -> str:
    kst = dt.astimezone(KST)
    return f"{kst.year}년 {kst.month:02d}월 {kst.day:02d}일"


def _format_time(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def fetch_news(keyword: str, days: int = 7, max_articles: int = 15) -> list[dict]:
    encoded = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}+when:{days}d&hl=ko&gl=KR&ceid=KR:ko"

    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        feed = feedparser.parse(response.content)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles: list[dict] = []

    for entry in feed.entries:
        published = _parse_published(entry)
        if published and published < cutoff:
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        link = entry.get("link", "")
        summary = _clean_summary(entry.get("summary") or entry.get("description") or "")
        pub = published or datetime.now(timezone.utc)
        articles.append({
            "title": title,
            "link": link,
            "desc": summary,
            "source": _extract_source(entry),
            "published": _format_date(pub),
        })
        if len(articles) >= max_articles:
            break

    return articles


def _get_gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    return key


def _call_gemini(prompt: str) -> str:
    api_key = _get_gemini_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    return parts[0]["text"]


def _fallback_report(keyword: str, articles: list[dict]) -> dict[str, Any]:
    top5 = articles[:5]
    preview = ", ".join(f"「{a['title'].split(' - ')[0][:25]}」" for a in top5[:3])
    executive_summary = (
        f"최근 7일간 '{keyword}' 관련 뉴스 {len(articles)}건 중 "
        f"{preview} 등이 핵심 이슈로 부상했습니다."
    )
    top_issues = []
    for i, a in enumerate(top5, 1):
        top_issues.append({
            "rank": i,
            "title": a["title"],
            "key_content": (a["desc"] or a["title"])[:300],
            "why_important": (
                f"'{keyword}' 분야 최근 흐름 파악에 중요하며 "
                f"{a['source']} 등에서 보도되었습니다."
            ),
            "source": a["source"],
            "link": a["link"],
        })
    return {"executive_summary": executive_summary, "top_issues": top_issues}


def generate_report_with_gemini(keyword: str, articles: list[dict]) -> dict[str, Any]:
    news_text = "\n".join(
        f"{i}. [{a['source']}] {a['title']}\n   요약: {a['desc'][:200]}\n   URL: {a['link']}"
        for i, a in enumerate(articles[:12], 1)
    )
    prompt = f"""당신은 뉴스 분석 전문가입니다. 아래 뉴스 목록을 분석하여 JSON만 출력하세요.

키워드: {keyword}

뉴스 목록:
{news_text}

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "executive_summary": "핵심요약 3~4문장 (한국어)",
  "top_issues": [
    {{
      "rank": 1,
      "title": "이슈 제목",
      "key_content": "핵심내용 2~3문장",
      "why_important": "왜 중요한지 1~2문장",
      "source": "언론사명",
      "link": "기사 URL"
    }}
  ]
}}

top_issues는 정확히 5개. executive_summary는 보고서 맨 앞 핵심요약."""

    try:
        raw = _call_gemini(prompt)
        data = json.loads(raw)
        issues = data.get("top_issues", [])[:5]
        for i, issue in enumerate(issues, 1):
            issue["rank"] = i
        return {
            "executive_summary": data.get("executive_summary", ""),
            "top_issues": issues,
        }
    except Exception:
        return _fallback_report(keyword, articles)


def build_full_report(keyword: str) -> dict[str, Any]:
    created_at = datetime.now(KST)
    articles = fetch_news(keyword)
    if not articles:
        raise ValueError(f"'{keyword}' 관련 최근 7일 이내 뉴스를 찾지 못했습니다.")

    report_data = generate_report_with_gemini(keyword, articles)

    return {
        "success": True,
        "keyword": keyword,
        "article_count": len(articles),
        "created_date": _format_date(created_at),
        "created_time": _format_time(created_at),
        "executive_summary": report_data["executive_summary"],
        "top_issues": report_data["top_issues"],
        "articles": articles,
    }
