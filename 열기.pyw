"""AI 뉴스 레포트 — 로컬 서버 (Gemini API)"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from urllib.parse import parse_qs, unquote, urlparse

DIR = os.path.dirname(os.path.abspath(__file__))
if DIR not in sys.path:
    sys.path.insert(0, DIR)

try:
    import feedparser
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "feedparser", "requests", "-q"])
    import feedparser
    import requests

from gemini_report import build_full_report, fetch_news

PORT_START = 8777
PORT_END = 8785
HTML_NAME = "index.html"
PORT_FILE = "server_port.txt"


def load_env() -> None:
    env_path = os.path.join(DIR, ".env")
    if not os.path.isfile(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


class NewsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"

        if path == "/api/ping":
            self._json_response(200, {"ok": True})
            return

        if path == "/api/port":
            port = int(os.environ.get("SERVER_PORT", PORT_START))
            self._json_response(200, {"port": port})
            return

        if path == "/api/news":
            keyword = parse_qs(parsed.query).get("keyword", [""])[0].strip()
            try:
                if not keyword:
                    raise ValueError("키워드를 입력해 주세요.")
                articles = fetch_news(keyword)
                if not articles:
                    raise ValueError(f"'{keyword}' 관련 뉴스를 찾지 못했습니다.")
                self._json_response(200, {"success": True, "articles": articles})
            except Exception as e:
                self._json_response(400, {"success": False, "error": str(e)})
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
            self._serve_file(target)
            return

        self._json_response(404, {"success": False, "error": f"경로를 찾을 수 없습니다: {path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/") or "/"

        if path != "/api/generate":
            self._json_response(404, {"success": False, "error": "POST /api/generate 만 지원합니다."})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._json_response(400, {"success": False, "error": "잘못된 JSON 요청입니다."})
            return

        keyword = (body.get("keyword") or "").strip()
        try:
            if not keyword:
                raise ValueError("키워드를 입력해 주세요.")
            result = build_full_report(keyword)
            self._json_response(200, result)
        except Exception as e:
            self._json_response(400, {"success": False, "error": str(e)})

    def _serve_file(self, path: str):
        if not os.path.isfile(path):
            self._json_response(404, {"success": False, "error": "HTML 파일 없음"})
            return
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


class ReusableServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    load_env()
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
        raise SystemExit("사용 가능한 포트를 찾지 못했습니다.")

    os.environ["SERVER_PORT"] = str(port)
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
