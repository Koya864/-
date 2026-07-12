"""LaunchGuard — /api/scan (Vercel Python Serverless Function).

GET /api/scan?url=<診断するURL>&own=1
→ 診断結果を JSON で返す。own=1(自分のサイト宣言)がないと 400。

診断ロジックは api/_lib/ にある(tools/launchguard/ のコピー。
編集は tools/launchguard/ 側で行い、scripts/sync-api-lib.sh で同期する)。
"""

import json
import os
import sys
import urllib.error
import urllib.parse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler

# サーバーレスの実行時間制限に収まるよう、取得回数と待ち時間を絞る
os.environ.setdefault("LAUNCHGUARD_TIMEOUT", "8")
os.environ.setdefault("LAUNCHGUARD_MAX_SCRIPTS", "3")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "_lib"))
from urlscan import scan_url  # noqa: E402

MAX_URL_LEN = 2048


class handler(BaseHTTPRequestHandler):  # noqa: N801  (Vercelの規約でこの名前)
    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        url = (params.get("url") or [""])[0].strip()
        own = (params.get("own") or [""])[0]

        if not url or len(url) > MAX_URL_LEN:
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

    def log_message(self, fmt, *args):
        pass
