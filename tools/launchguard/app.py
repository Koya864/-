#!/usr/bin/env python3
"""LaunchGuard — ローカル起動用サーバー.

使い方:
    python3 tools/launchguard/app.py
    → ブラウザで http://localhost:8787 を開く

Vercel版と同じ画面(public/index.html)と同じAPI(/api/scan)を配信する。
依存パッケージなし(Python 3.9+ 標準ライブラリのみ)。診断結果は保存しない。
"""

import json
import sys
import urllib.error
import urllib.parse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from urlscan import scan_url  # noqa: E402

PORT = 8787
INDEX = Path(__file__).resolve().parents[2] / "public" / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "LaunchGuard/0.1"

    def _send(self, status: int, content_type: str, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        self._send(status, "application/json; charset=utf-8",
                   json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", INDEX.read_bytes())
            return
        if parsed.path == "/api/scan":
            params = urllib.parse.parse_qs(parsed.query)
            url = (params.get("url") or [""])[0].strip()
            own = (params.get("own") or [""])[0]
            if not url:
                self._json(400, {"error": "URLを指定してください"})
                return
            if own != "1":
                self._json(400, {"error": "自分が管理するサイトであることの確認が必要です"})
                return
            try:
                result = scan_url(url)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            except (urllib.error.URLError, OSError) as e:
                self._json(502, {"error": f"サイトを取得できませんでした: {e}"})
                return
            self._json(200, {
                "target": result.target,
                "files_scanned": result.files_scanned,
                "findings": [asdict(f) for f in result.sorted_findings()],
            })
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"LaunchGuard を起動しました → http://localhost:{PORT}")
    print("終了するには Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
