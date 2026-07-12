#!/usr/bin/env python3
"""LaunchGuard P1 — Web画面(お試し版).

使い方:
    python3 tools/launchguard/app.py
    → ブラウザで http://localhost:8787 を開く

依存パッケージなし(Python 3.9+ 標準ライブラリのみ)。
診断結果はどこにも保存されない(その場で表示するだけ)。
"""

import html
import sys
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan import SEVERITY_JA, ScanResult  # noqa: E402
from urlscan import scan_url  # noqa: E402

PORT = 8787

SEVERITY_STYLE = {
    "critical": ("重大", "#c0262e", "#fdf0f0"),
    "warning": ("警告", "#9a6700", "#fff8e6"),
    "info": ("推奨", "#0757ba", "#f0f6ff"),
}

BASE_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin:0; font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
       background:#f5f6f8; color:#1f2328; line-height:1.7; }
.wrap { max-width:760px; margin:0 auto; padding:32px 20px 64px; }
.brand { font-weight:800; font-size:22px; letter-spacing:.02em; }
.brand small { font-weight:600; color:#6a737d; margin-left:10px; font-size:12px; }
.card { background:#fff; border:1px solid #e4e7eb; border-radius:12px; padding:24px; margin-top:20px; }
h1 { font-size:26px; margin:24px 0 8px; }
p.lead { color:#57606a; margin-top:0; }
input[type=url] { width:100%; padding:14px 16px; font-size:16px; border:1.5px solid #d0d7de;
                  border-radius:10px; }
label.own { display:flex; gap:8px; align-items:flex-start; margin:14px 0; font-size:14px; color:#57606a; }
button.go { width:100%; padding:14px; font-size:16px; font-weight:700; color:#fff;
            background:#1a7f37; border:none; border-radius:10px; cursor:pointer; }
button.go:hover { background:#166f30; }
.note { font-size:12px; color:#8b949e; margin-top:12px; }
.scorebar { display:flex; gap:12px; margin:20px 0; }
.score { flex:1; text-align:center; border-radius:12px; padding:16px 8px; background:#fff;
         border:1px solid #e4e7eb; }
.score b { display:block; font-size:34px; }
.finding { border-radius:12px; padding:18px 20px; margin-top:14px; background:#fff;
           border:1px solid #e4e7eb; border-left-width:6px; }
.finding .sev { font-size:12px; font-weight:800; padding:2px 10px; border-radius:99px; }
.finding h3 { margin:8px 0 6px; font-size:16px; }
.finding .loc { font-size:12px; color:#8b949e; font-family:ui-monospace,monospace; }
.finding p { margin:8px 0 0; font-size:14px; }
details.fix { margin-top:10px; }
details.fix summary { cursor:pointer; font-weight:700; font-size:14px; color:#1a7f37; }
details.fix div { margin-top:8px; padding:12px 14px; background:#f2faf4; border-radius:8px; font-size:14px; }
.back { display:inline-block; margin-top:24px; color:#0757ba; }
.error { background:#fdf0f0; border:1px solid #f0c0c0; border-radius:12px; padding:20px; margin-top:20px; }
footer { margin-top:40px; font-size:12px; color:#8b949e; }
"""

PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LaunchGuard — AIで作ったサイトの健康診断</title>
<style>{css}</style></head><body><div class="wrap">
<div class="brand">🛡 LaunchGuard <small>AIで作ったサイトの健康診断(お試し版)</small></div>
{body}
<footer>診断は通常のブラウザアクセスと同じ範囲(受動的チェック)のみ行います。
診断結果はサーバーに保存されません。<br>
このツールは自分が管理するサイトの確認用です。他人のサイトの調査には使わないでください。</footer>
</div></body></html>"""

FORM = """
<h1>そのサイト、公開して大丈夫?</h1>
<p class="lead">URLを入れるだけで、セキュリティの「開いている窓」を30秒でチェックします。
専門用語は使わず、<b>何が起きうるか</b>と<b>直し方</b>を日本語で説明します。</p>
<div class="card">
<form method="get" action="/scan">
  <input type="url" name="url" placeholder="https://あなたのサイト.com" required>
  <label class="own"><input type="checkbox" name="own" value="1" required>
  このサイトは自分(自社)が管理するサイトです。自分のサイトの安全確認のために診断します。</label>
  <button class="go">無料で診断する</button>
  <p class="note">登録不要・結果は保存されません。</p>
</form>
</div>
"""


def render_findings(result: ScanResult) -> str:
    findings = result.sorted_findings()
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("critical", "warning", "info")}
    if counts["critical"]:
        verdict = "<b>今すぐ対応が必要です。</b>重大な項目は、放置すると実害(金銭・情報漏洩)につながります。"
    elif counts["warning"]:
        verdict = "公開は可能ですが、警告の項目は早めの対応をおすすめします。"
    else:
        verdict = "大きな問題は見つかりませんでした。よくできています!"

    parts = [f"<h1>診断結果</h1><p class='lead'>対象: {html.escape(result.target)}"
             f"(検査ファイル数: {result.files_scanned})</p>"]
    parts.append("<div class='scorebar'>")
    for sev in ("critical", "warning", "info"):
        ja, color, _ = SEVERITY_STYLE[sev]
        parts.append(f"<div class='score'><b style='color:{color}'>{counts[sev]}</b>{ja}</div>")
    parts.append("</div>")
    parts.append(f"<p>{verdict}</p>")

    for f in findings:
        ja, color, bg = SEVERITY_STYLE[f.severity]
        loc = f.file + (f":{f.line}" if f.line else "")
        evidence = f"(検出値: {html.escape(f.evidence)})" if f.evidence else ""
        parts.append(f"""
<div class="finding" style="border-left-color:{color}">
  <span class="sev" style="color:{color};background:{bg}">{ja}</span>
  <h3>{html.escape(f.title)}</h3>
  <div class="loc">{html.escape(loc)} {evidence}</div>
  <p><b>何が起きうるか:</b> {html.escape(f.scenario)}</p>
  <details class="fix"><summary>直し方を見る(製品版では有料機能)</summary>
  <div>{html.escape(f.fix)}</div></details>
</div>""")
    parts.append("<a class='back' href='/'>← 別のサイトを診断する</a>")
    return "".join(parts)


class Handler(BaseHTTPRequestHandler):
    server_version = "LaunchGuard/0.1"

    def _send(self, body_html: str, status: int = 200):
        page = PAGE.format(css=BASE_CSS, body=body_html).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # 自分自身にもセキュリティヘッダーを設定する(言行一致)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(FORM)
            return
        if parsed.path == "/scan":
            params = urllib.parse.parse_qs(parsed.query)
            url = (params.get("url") or [""])[0].strip()
            own = (params.get("own") or [""])[0]
            if not url or own != "1":
                self._send(FORM, 400)
                return
            try:
                result = scan_url(url)
            except (urllib.error.URLError, OSError, ValueError) as e:
                msg = html.escape(str(e))
                self._send(f"<div class='error'><b>診断できませんでした。</b><br>"
                           f"サイトにアクセスできるか、URLをもう一度確認してください。<br>"
                           f"<span style='font-size:12px;color:#8b949e'>詳細: {msg}</span></div>"
                           f"<a class='back' href='/'>← 戻る</a>", 502)
                return
            self._send(render_findings(result))
            return
        self._send("<div class='error'>ページが見つかりません。</div><a class='back' href='/'>← 戻る</a>", 404)

    def log_message(self, fmt, *args):  # 標準出力を静かに保つ
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"LaunchGuard お試し版を起動しました → http://localhost:{PORT}")
    print("終了するには Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
