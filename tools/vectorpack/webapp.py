#!/usr/bin/env python3
"""VectorPack — ローカル起動用サーバー(アップロード→変換→プレビュー→ダウンロード).

使い方:
    python3 tools/vectorpack/webapp.py
    → ブラウザで http://localhost:8788 を開く

フロー:
    1. 画像を送る(POST /api/vectorize、本文に画像バイト)
       → ベクター化して、適性判定 + プレビュー用SVG + ダウンロードID を返す(無料)
    2. ダウンロード(GET /api/download?id=…)で納品パック(ZIP)を受け取る(本番は課金の位置)

依存: pip install vtracer cairosvg pillow
"""

import io
import json
import sys
import tempfile
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vectorize import is_monochrome, make_pack  # noqa: E402
from PIL import Image  # noqa: E402

PORT = 8788
INDEX = Path(__file__).resolve().parents[2] / "public" / "vectorpack.html"
MAX_BYTES = 12 * 1024 * 1024  # アップロード上限 12MB

# ダウンロードID → (zipバイト, ファイル名)。プロセス内メモリのみ(保存しない)
_PACKS: dict[str, tuple[bytes, str]] = {}


def process_image(raw: bytes) -> dict:
    """画像バイトを受け取り、変換してプレビューSVG等を返す。"""
    img = Image.open(io.BytesIO(raw))
    img.load()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / "input.png"
        img.convert("RGBA").save(src)
        pack = make_pack(src, td / "out")
        out = td / "out"
        svg = (out / "input.svg").read_text(encoding="utf-8")
        zip_bytes = pack.read_bytes()

    mono = is_monochrome(img)
    dl_id = uuid.uuid4().hex
    _PACKS[dl_id] = (zip_bytes, "vectorpack.zip")
    # 直近の数件だけ保持(メモリ肥大を防ぐ)
    if len(_PACKS) > 50:
        for k in list(_PACKS)[:-50]:
            _PACKS.pop(k, None)

    from vectorize import analyze_suitability
    note, suitable = analyze_suitability(img)
    return {
        "ok": True,
        "note": note,
        "suitable": suitable,
        "monochrome": mono,
        "preview_svg": svg,
        "download_id": dl_id,
        "zip_kb": round(len(zip_bytes) / 1024),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "VectorPack/0.1"

    def _send(self, status, content_type, body: bytes, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, "application/json; charset=utf-8",
                   json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", INDEX.read_bytes())
            return
        if parsed.path == "/api/download":
            params = urllib.parse.parse_qs(parsed.query)
            dl_id = (params.get("id") or [""])[0]
            entry = _PACKS.get(dl_id)
            if not entry:
                self._json(404, {"error": "ダウンロードが見つかりません。もう一度変換してください。"})
                return
            data, fname = entry
            self._send(200, "application/zip", data,
                       {"Content-Disposition": f'attachment; filename="{fname}"'})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/vectorize":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BYTES:
            self._json(400, {"error": "画像サイズが不正です(12MBまで)"})
            return
        raw = self.rfile.read(length)
        try:
            result = process_image(raw)
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"変換できませんでした: {e}"})
            return
        self._json(200, result)

    def log_message(self, fmt, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"VectorPack を起動しました → http://localhost:{PORT}")
    print("終了するには Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
