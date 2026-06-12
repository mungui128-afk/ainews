"""최근 7일 이내 뉴스 수집 (Google News RSS)"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests


@dataclass
class NewsArticle:
    title: str
    summary: str
    link: str
    source: str
    published: datetime


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


def fetch_news(keyword: str, days: int = 7, max_articles: int = 15) -> list[NewsArticle]:
    """키워드로 최근 N일 이내 뉴스를 수집합니다."""
    encoded = quote_plus(keyword)
    url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded}+when:{days}d&hl=ko&gl=KR&ceid=KR:ko"
    )

    feed = feedparser.parse(url)
    if feed.bozo and not feed.entries:
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        feed = feedparser.parse(response.content)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles: list[NewsArticle] = []

    for entry in feed.entries:
        published = _parse_published(entry)
        if published and published < cutoff:
            continue

        title = (entry.get("title") or "").strip()
        if not title:
            continue

        link = entry.get("link", "")
        summary = _clean_summary(entry.get("summary") or entry.get("description") or "")

        articles.append(
            NewsArticle(
                title=title,
                summary=summary,
                link=link,
                source=_extract_source(entry),
                published=published or datetime.now(timezone.utc),
            )
        )

        if len(articles) >= max_articles:
            break

    articles.sort(key=lambda a: a.published, reverse=True)
    return articles
