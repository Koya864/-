#!/usr/bin/env python3
"""LaunchGuard P1 — 公開URLの外形診断(受動的チェックのみ).

使い方:
    python3 urlscan.py <URL> [--json out.json] [--md report.md]

やること: 通常のブラウザアクセスと同じ範囲(トップページの取得と、そこから
参照されている同一サイトのJSの取得)だけで診断する。
やらないこと: パスの総当たり・攻撃的リクエスト等の能動的チェック
(それらは所有者確認を通過したサイトに対してのみ行う設計)。
"""

import argparse
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan import ScanResult, check_html, check_js, check_secrets, render_markdown  # noqa: E402

USER_AGENT = "LaunchGuard/0.1 (+security self-check tool)"
TIMEOUT = 15
MAX_BYTES = 2 * 1024 * 1024   # 1レスポンスあたりの読み込み上限
MAX_SCRIPTS = 5               # 追加取得する同一サイトJSの上限

# 確認するセキュリティヘッダー: (ヘッダー名, 重さ, 見出し, 何が起きうるか, 直し方)
HEADER_RULES = [
    ("strict-transport-security", "warning",
     "HSTS(常時暗号化の宣言)が設定されていません",
     "訪問者が一度でも http:// で接続すると、カフェのWi-Fi等で通信を横取り・改ざんされる余地が残ります。",
     "レスポンスヘッダーに Strict-Transport-Security: max-age=31536000 を追加してください。"),
    ("x-content-type-options", "warning",
     "X-Content-Type-Options が設定されていません",
     "ブラウザがファイルの種類を勝手に推測し、画像のふりをした攻撃プログラムが実行される余地が生まれます。",
     "レスポンスヘッダーに X-Content-Type-Options: nosniff を追加してください。"),
    ("content-security-policy", "info",
     "Content-Security-Policy(CSP)が設定されていません",
     "スクリプト注入(XSS)が成立した場合の被害を抑える最後の防波堤がない状態です。",
     "まずは Content-Security-Policy-Report-Only で影響を確認しながら導入するのが安全です。"),
    ("referrer-policy", "info",
     "Referrer-Policy が設定されていません",
     "訪問者がリンクを踏んだ際、あなたのサイトのURL(パラメータ含む)が遷移先に筒抜けになります。",
     "レスポンスヘッダーに Referrer-Policy: strict-origin-when-cross-origin を追加してください。"),
    ("permissions-policy", "info",
     "Permissions-Policy が設定されていません",
     "カメラ・マイク・位置情報など、サイトが本来使わない機能の入口が開いたままになります。",
     "レスポンスヘッダーに Permissions-Policy: camera=(), microphone=(), geolocation=() 等を追加してください。"),
]


def _ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile)


def _is_private_target(hostname: str) -> bool:
    """SSRF対策: 内部ネットワーク宛の診断を拒否する(ホスト版でも同じ守りを使う)。"""
    if os.environ.get("LAUNCHGUARD_ALLOW_PRIVATE") == "1":  # ローカル開発・テスト用
        return False
    if hostname in ("localhost",):
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False  # プロキシ環境では手元で解決できないことがある。出口はプロキシ側の方針に従う
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            return True
    return False


def fetch(url: str):
    """URLを取得して (最終URL, ステータス, ヘッダーdict(小文字), 本文テキスト) を返す。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
        body = resp.read(MAX_BYTES)
        headers = {k.lower(): v for k, v in resp.headers.items()}
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.geturl(), resp.status, headers, body.decode(charset, errors="replace")


def check_headers(headers: dict, result: ScanResult):
    for name, sev, title, scenario, fix in HEADER_RULES:
        if name not in headers:
            result.add(severity=sev, check_id=f"header-{name}", title=title,
                       file="(レスポンスヘッダー)", line=0, scenario=scenario, fix=fix)
    if "x-frame-options" not in headers and "frame-ancestors" not in headers.get("content-security-policy", ""):
        result.add(severity="warning", check_id="header-x-frame-options",
                   title="クリックジャッキング対策(X-Frame-Options)がありません",
                   file="(レスポンスヘッダー)", line=0,
                   scenario="あなたのサイトを透明な膜のように偽サイトへ重ねられ、訪問者に意図しないボタンを押させる手口が可能になります。",
                   fix="レスポンスヘッダーに X-Frame-Options: DENY(または CSP の frame-ancestors)を追加してください。")
    for h in ("server", "x-powered-by"):
        value = headers.get(h, "")
        if re.search(r"\d+\.\d+", value):
            result.add(severity="info", check_id="header-version-disclosure",
                       title=f"サーバーの種類とバージョンが公開されています({h})",
                       file="(レスポンスヘッダー)", line=0,
                       scenario="攻撃者に「このバージョンの既知の穴が使える」というヒントを与えます。",
                       fix=f"{h} ヘッダーを削除するか、バージョン番号を含めない設定にしてください。")


def check_https(url: str, final_url: str, result: ScanResult):
    parsed = urllib.parse.urlparse(final_url)
    if parsed.scheme != "https":
        result.add(severity="critical", check_id="no-https",
                   title="サイトが暗号化(HTTPS)されていません",
                   file="(サイト全体)", line=0,
                   scenario="通信内容の盗み見・改ざんが可能な状態で、ブラウザにも「保護されていません」と表示されます。",
                   fix="ホスティングサービスのHTTPS設定(ほとんどのサービスで無料)を有効にしてください。")
        return
    # https で見られる場合、http アクセスが https に転送されるかを確認
    http_url = urllib.parse.urlunparse(("http",) + parsed[1:])
    try:
        redirected_url, _, _, _ = fetch(http_url)
        if urllib.parse.urlparse(redirected_url).scheme != "https":
            result.add(severity="warning", check_id="no-https-redirect",
                       title="http:// でアクセスすると暗号化されないまま表示されます",
                       file="(サイト全体)", line=0,
                       scenario="古いリンクやブックマークから来た訪問者が、保護されない通信のままサイトを使ってしまいます。",
                       fix="http から https への自動転送(リダイレクト)を設定してください。")
    except (urllib.error.URLError, OSError, ValueError):
        pass  # httpが閉じているのはむしろ健全


def collect_same_origin_scripts(base_url: str, html: str):
    base = urllib.parse.urlparse(base_url)
    urls = []
    for m in re.finditer(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", html, re.I):
        u = urllib.parse.urljoin(base_url, m.group(1))
        p = urllib.parse.urlparse(u)
        if p.netloc == base.netloc and u not in urls:
            urls.append(u)
    return urls[:MAX_SCRIPTS]


def scan_url(url: str) -> ScanResult:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise ValueError("URLの形式が正しくありません")
    if _is_private_target(parsed.hostname):
        raise ValueError("内部ネットワークのアドレスは診断できません")

    result = ScanResult(target=url)
    final_url, status, headers, html = fetch(url)
    result.files_scanned = 1

    check_https(url, final_url, result)
    check_headers(headers, result)

    lines = html.splitlines()
    page = urllib.parse.urlparse(final_url).path or "/"
    check_secrets(None, page, lines, result)
    check_html(None, page, html, lines, result)

    for script_url in collect_same_origin_scripts(final_url, html):
        try:
            _, _, _, js = fetch(script_url)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        result.files_scanned += 1
        rel = urllib.parse.urlparse(script_url).path
        js_lines = js.splitlines()
        check_secrets(None, rel, js_lines, result)
        check_js(None, rel, js, js_lines, result)

    return result


def main():
    ap = argparse.ArgumentParser(description="LaunchGuard 外形診断(公開URL版・受動的チェックのみ)")
    ap.add_argument("url", help="診断するサイトのURL(自分が所有するサイトに限る)")
    ap.add_argument("--json", help="JSON出力先")
    ap.add_argument("--md", help="Markdownレポート出力先")
    args = ap.parse_args()

    try:
        result = scan_url(args.url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        sys.exit(f"エラー: サイトを取得できませんでした: {e}")

    md = render_markdown(result)
    if args.json:
        payload = {"target": result.target, "files_scanned": result.files_scanned,
                   "findings": [asdict(f) for f in result.sorted_findings()]}
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    print(md)
    sys.exit(2 if any(f.severity == "critical" for f in result.findings) else 0)


if __name__ == "__main__":
    main()
