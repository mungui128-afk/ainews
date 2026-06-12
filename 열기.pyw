"""AI 뉴스 레포트 — 로컬 서버 (뉴스 수집 API 포함)"""
from __future__ import annotations

import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

try:
    import feedparser
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "requests", "-q"])
    import feedparser
    import requests

PORT_START = 8777
PORT_END = 8785
DIR = os.path.dirname(os.path.abspath(__file__))
HTML_NAME = "index.html"
PORT_FILE = "server_port.txt"


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
    kst = dt.astimezone(timezone(timedelta(hours=9)))
    return f"{kst.year}년 {kst.month:02d}월 {kst.day:02d}일"


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

    articles.sort(key=lambda a: a.get("published", ""), reverse=True)
    return articles


class NewsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"

        if path == "/api/news":
            self._handle_news(parsed)
            return

        if path == "/api/ping":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        html_paths = {"/", "/index.html", "/AI뉴스레포트.html"}
        if path in html_paths or path.endswith(".html"):
            target = os.path.join(DIR, HTML_NAME)
            if not os.path.isfile(target):
                target = os.path.join(DIR, "AI뉴스레포트.html")
            self._serve_file(target, "text/html; charset=utf-8")
            return

        self._send_help_page(path)

    def _handle_news(self, parsed):
        keyword = parse_qs(parsed.query).get("keyword", [""])[0].strip()
        try:
            if not keyword:
                raise ValueError("키워드를 입력해 주세요.")
            articles = fetch_news(keyword)
            if not articles:
                raise ValueError(f"'{keyword}' 관련 최근 7일 뉴스를 찾지 못했습니다.")
            body = json.dumps({"success": True, "articles": articles}, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        except Exception as e:
            body = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

    def _serve_file(self, path: str, content_type: str):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _send_help_page(self, path: str):
        body = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
        <title>AI 뉴스 레포트</title></head><body style="font-family:Malgun Gothic;padding:40px">
        <h2>페이지를 찾을 수 없습니다 (404)</h2>
        <p>요청 경로: <code>{path}</code></p>
        <p><a href="/">← AI 뉴스 레포트 홈으로 이동</a></p>
        </body></html>"""
        data = body.encode("utf-8")
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ReusableServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    os.chdir(DIR)

    httpd = None
    port = None
    for p in range(PORT_START, PORT_END + 1):
        try:
            httpd = ReusableServer(("", p), NewsHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd or port is None:
        raise SystemExit("사용 가능한 포트를 찾지 못했습니다. 다른 프로그램을 종료 후 다시 시도하세요.")

    with open(os.path.join(DIR, PORT_FILE), "w", encoding="utf-8") as f:
        f.write(str(port))

    url = f"http://127.0.0.1:{port}/"

    def open_browser():
        time.sleep(1.0)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
