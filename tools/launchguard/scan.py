#!/usr/bin/env python3
"""LaunchGuard P1 — AI生成サイトの外形診断エンジン(ローカル静的サイト版).

使い方:
    python3 scan.py <サイトのディレクトリ> [--json out.json] [--md report.md]

依存パッケージなし(Python 3.9+ 標準ライブラリのみ)。
発見(検出)は決定的なルールで行い、AIは使わない。
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SEVERITY_JA = {"critical": "重大", "warning": "警告", "info": "推奨"}

TEXT_EXTS = {".html", ".htm", ".js", ".mjs", ".css", ".json", ".txt", ".md",
             ".yml", ".yaml", ".toml", ".xml", ".env", ".ts", ".jsx", ".tsx"}

# 公開フォルダに存在してはいけない/残すべきでないファイル
SENSITIVE_FILE_RULES = [
    (re.compile(r"^\.env(\..*)?$"), "critical",
     "環境変数ファイル(.env)が公開フォルダに含まれています",
     "このファイルにはAPIキーやパスワードが入っているのが普通です。公開されると、誰でもあなたの有料サービスの鍵を入手できます。",
     "サイトの公開フォルダから .env を取り除き、中に書かれていた鍵はすべて無効化・再発行してください。"),
    (re.compile(r"^\.git$"), "critical",
     ".git ディレクトリが公開フォルダに含まれています",
     "コードの全履歴(消したはずの鍵や個人情報を含む)を丸ごとダウンロードされる可能性があります。",
     "公開対象から .git を除外してください(デプロイ設定で除外するか、ビルド成果物だけを公開する)。"),
    (re.compile(r".*\.(bak|old|orig|swp)$"), "warning",
     "バックアップファイルが公開フォルダに残っています",
     "編集前の古いファイルには、削除したはずの情報(鍵・コメント・未公開情報)が残っていることがあります。",
     "公開フォルダからバックアップファイルを削除してください。"),
    (re.compile(r".*\.(zip|tar|tar\.gz|tgz|rar|7z)$"), "warning",
     "アーカイブファイルが公開フォルダに含まれています",
     "サイト一式やソースコードの圧縮ファイルは、URLを推測されるとそのままダウンロードされます。",
     "公開フォルダからアーカイブを削除してください。配布目的でなければ置く理由はありません。"),
    (re.compile(r".*\.(sql|sqlite|db)$"), "critical",
     "データベースファイルが公開フォルダに含まれています",
     "顧客情報などのデータを丸ごと抜かれる可能性があります。",
     "公開フォルダから即座に削除し、中身に個人情報が含まれていた場合は漏洩として扱ってください。"),
    (re.compile(r"^\.DS_Store$"), "info",
     "macOSのシステムファイル(.DS_Store)が含まれています",
     "フォルダ構成(非公開ファイル名など)が外部から推測される手がかりになります。",
     ".gitignore に .DS_Store を追加し、公開フォルダから削除してください。"),
]

# シークレット(鍵)の直書きパターン
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "OpenAI APIキー"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic APIキー"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "Google APIキー"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWSアクセスキー"),
    (re.compile(r"(sk|rk)_(live|test)_[0-9a-zA-Z]{20,}"), "Stripe シークレットキー"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHubトークン"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "Slackトークン"),
    (re.compile(r"eyJhbGciOi[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"), "JWT/サービストークン"),
    (re.compile(
        r"""(?i)\b(api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd)\b\s*[:=]\s*["'][^"'\s]{8,}["']"""),
     "認証情報らしき直書き"),
]

# 誤検知を除外(プレースホルダー等)
SECRET_FALSE_POSITIVE = re.compile(
    r"(?i)(example|sample|placeholder|your[_-]?|xxxx|\*\*\*\*|dummy|test1234|changeme|<[^>]+>)")


@dataclass
class Finding:
    severity: str          # critical / warning / info
    check_id: str
    title: str             # 何が見つかったか(平易な日本語)
    file: str
    line: int
    scenario: str          # 何が起きうるか
    fix: str               # どう直すか
    evidence: str = ""     # 該当箇所(マスク済み)


@dataclass
class ScanResult:
    target: str
    files_scanned: int = 0
    findings: list = field(default_factory=list)

    def add(self, **kw):
        self.findings.append(Finding(**kw))

    def sorted_findings(self):
        return sorted(self.findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.file))


def mask(text: str) -> str:
    """検出した値そのものはレポートに載せない(レポート自体が漏洩源になるため)。"""
    text = text.strip()
    if len(text) <= 12:
        return text[:4] + "…"
    return text[:8] + "…" + text[-4:]


def iter_text_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and (p.suffix.lower() in TEXT_EXTS or p.name.startswith(".env")):
            yield p


def check_sensitive_files(root: Path, result: ScanResult):
    for p in sorted(root.rglob("*")):
        name = p.name
        rel = str(p.relative_to(root))
        for pattern, sev, title, scenario, fix in SENSITIVE_FILE_RULES:
            if pattern.match(name):
                result.add(severity=sev, check_id="exposed-file", title=title,
                           file=rel, line=0, scenario=scenario, fix=fix)
                break


def check_secrets(path: Path, rel: str, lines: list, result: ScanResult):
    for i, line in enumerate(lines, 1):
        for pattern, label in SECRET_PATTERNS:
            m = pattern.search(line)
            if m and not SECRET_FALSE_POSITIVE.search(m.group(0)):
                result.add(
                    severity="critical", check_id="hardcoded-secret",
                    title=f"{label}がコードに直接書かれています",
                    file=rel, line=i,
                    scenario="公開した瞬間からボットが自動収集します。他人があなたの契約でサービスを使い放題になり、高額請求や成りすましにつながります。",
                    fix="鍵をコードから削除して環境変数に移し、漏れた鍵は必ず無効化・再発行してください(削除だけでは履歴に残ります)。",
                    evidence=mask(m.group(0)))
                break


def check_html(path: Path, rel: str, text: str, lines: list, result: ScanResult):
    # フォーム関連
    for m in re.finditer(r"<form\b[^>]*>", text, re.I):
        tag = m.group(0)
        line_no = text[:m.start()].count("\n") + 1
        action = re.search(r"""action\s*=\s*["']([^"']*)["']""", tag, re.I)
        if action and action.group(1).lower().startswith("http://"):
            result.add(severity="critical", check_id="form-insecure-action",
                       title="フォームの送信先が暗号化されていません(http://)",
                       file=rel, line=line_no,
                       scenario="訪問者が入力した名前・連絡先が、通信途中で第三者に盗み見られる可能性があります。",
                       fix="送信先URLを https:// に変更してください。")
        if action and action.group(1).lower().startswith("mailto:"):
            result.add(severity="warning", check_id="form-mailto",
                       title="フォームの送信先がメールアドレス直指定(mailto:)になっています",
                       file=rel, line=line_no,
                       scenario="送信が訪問者のメール環境頼みになり届かないことが多いうえ、アドレスがスパム業者に収集されます。",
                       fix="フォーム送信サービス(Formspree等)やサーバー側の処理に切り替えてください。")
        if not action or not action.group(1):
            # JSで処理するフォーム: 送信先の実装確認を促す
            result.add(severity="info", check_id="form-js-handled",
                       title="フォームの送信先が指定されていません(JavaScript処理と推測)",
                       file=rel, line=line_no,
                       scenario="AI生成サイトでは「送信したふりをして実際はどこにも届かない」フォームがよくあります。問い合わせの機会損失に直結します。",
                       fix="送信処理が実在するか(どこに届くのか)を確認してください。届いていない場合はフォーム送信サービスの導入を。")

    # 混在コンテンツ(http:// の読み込み)
    for m in re.finditer(r"""(?:src|href)\s*=\s*["'](http://[^"']+)["']""", text, re.I):
        line_no = text[:m.start()].count("\n") + 1
        result.add(severity="warning", check_id="mixed-content",
                   title="暗号化されていない資源(http://)を読み込んでいます",
                   file=rel, line=line_no,
                   scenario="ブラウザに「保護されていない通信」と警告され、読み込みがブロックされたり訪問者の信頼を失ったりします。",
                   fix="URLを https:// に変更するか、その資源を自サイトに置いてください。",
                   evidence=mask(m.group(1)))

    # 外部スクリプトのSRI(改ざん検知)なし
    for m in re.finditer(r"<script\b[^>]*\bsrc\s*=\s*[\"'](https://[^\"']+)[\"'][^>]*>", text, re.I):
        tag = m.group(0)
        if "integrity=" not in tag.lower():
            line_no = text[:m.start()].count("\n") + 1
            result.add(severity="info", check_id="script-no-sri",
                       title="外部スクリプトに改ざん検知(integrity属性)がありません",
                       file=rel, line=line_no,
                       scenario="読み込み先のCDNが攻撃されると、あなたのサイトの訪問者にも悪意あるプログラムが配られます。",
                       fix="scriptタグに integrity と crossorigin 属性を追加してください(SRI Hash Generatorで生成できます)。",
                       evidence=mask(m.group(1)))

    # target="_blank" で rel="noopener" なし
    for m in re.finditer(r"<a\b[^>]*target\s*=\s*[\"']_blank[\"'][^>]*>", text, re.I):
        tag = m.group(0)
        if "noopener" not in tag.lower() and "noreferrer" not in tag.lower():
            line_no = text[:m.start()].count("\n") + 1
            result.add(severity="info", check_id="blank-noopener",
                       title='target="_blank" のリンクに rel="noopener" がありません',
                       file=rel, line=line_no,
                       scenario="リンク先のページから、元のページ(あなたのサイト)を偽ページに差し替えられる古典的な手口があります。",
                       fix='該当リンクに rel="noopener" を追加してください。')

    # メールアドレスの生掲載
    for m in re.finditer(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text):
        if m.group(0).endswith((".png", ".jpg", ".svg")):
            continue
        line_no = text[:m.start()].count("\n") + 1
        result.add(severity="info", check_id="email-exposed",
                   title="メールアドレスがページにそのまま掲載されています",
                   file=rel, line=line_no,
                   scenario="スパム業者の収集ボットに拾われ、迷惑メールが増えます。",
                   fix="フォーム経由の連絡に統一するか、画像化・難読化を検討してください。",
                   evidence=mask(m.group(0)))
        break  # 同一ファイルでは1件に集約


def check_js(path: Path, rel: str, text: str, lines: list, result: ScanResult):
    risky = [
        (re.compile(r"\beval\s*\("), "eval() の使用",
         "外部から与えられた文字列がそのままプログラムとして実行される危険があります。"),
        (re.compile(r"\bdocument\.write\s*\("), "document.write() の使用",
         "改ざん・スクリプト注入の温床になりやすい古い書き方です。"),
    ]
    for i, line in enumerate(lines, 1):
        for pattern, title, scenario in risky:
            if pattern.search(line):
                result.add(severity="warning", check_id="risky-js",
                           title=title, file=rel, line=i, scenario=scenario,
                           fix="該当処理を安全なDOM操作(textContent等)に書き換えてください。")
    # innerHTML への変数埋め込み(XSSの典型)
    for i, line in enumerate(lines, 1):
        m = re.search(r"\.innerHTML\s*[+]?=\s*(.+)$", line)
        if not m:
            continue
        rhs = m.group(1).strip().rstrip(";")
        # 固定の文字列リテラルのみ(変数の混入なし)は安全とみなす
        if re.fullmatch(r"(['\"])(?:(?!\1).)*\1", rhs):
            continue
        if rhs.startswith("`"):
            # テンプレートリテラル: 閉じバッククォートまでに ${ が無ければ固定文字列
            tail = "\n".join(lines[i - 1:i + 60])
            body = tail.split("`", 2)
            if len(body) >= 2 and "${" not in body[1]:
                continue
        result.add(severity="warning", check_id="innerhtml-injection",
                   title="innerHTML に変数を直接埋め込んでいます(XSSの典型パターン)",
                   file=rel, line=i,
                   scenario="埋め込まれる値に利用者の入力が混ざると、訪問者のブラウザで攻撃者のプログラムが動きます(サイトの改ざん・情報窃取)。",
                   fix="textContent を使うか、埋め込む値をエスケープしてください。現状データが固定値でも、後で入力値に差し替えた瞬間に穴になります。")


def check_headers_config(root: Path, result: ScanResult):
    configs = ["vercel.json", "netlify.toml", "_headers", "firebase.json"]
    if not any((root / c).exists() for c in configs):
        result.add(severity="warning", check_id="no-security-headers",
                   title="セキュリティヘッダーの設定ファイルが見つかりません",
                   file="(サイト全体)", line=0,
                   scenario="ブラウザへの「守り方の指示書」がない状態です。クリックジャッキング等、数行の設定で防げる攻撃に無防備になります。",
                   fix="ホスティング先に合わせて設定ファイル(vercel.json / netlify.toml / _headers)を追加し、X-Frame-Options、X-Content-Type-Options、Content-Security-Policy 等を設定してください。")


def scan(target: Path) -> ScanResult:
    result = ScanResult(target=str(target))
    check_sensitive_files(target, result)
    check_headers_config(target, result)
    for p in iter_text_files(target):
        rel = str(p.relative_to(target))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        result.files_scanned += 1
        check_secrets(p, rel, lines, result)
        if p.suffix.lower() in {".html", ".htm"}:
            check_html(p, rel, text, lines, result)
        if p.suffix.lower() in {".js", ".mjs", ".ts", ".jsx", ".tsx"}:
            check_js(p, rel, text, lines, result)
    return result


def render_markdown(result: ScanResult) -> str:
    findings = result.sorted_findings()
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}
    out = []
    out.append("# LaunchGuard 診断レポート\n")
    out.append(f"対象: `{result.target}`(検査ファイル数: {result.files_scanned})\n")
    out.append(f"## 診断結果: 重大 {counts['critical']}件 / 警告 {counts['warning']}件 / 推奨 {counts['info']}件\n")
    if counts["critical"]:
        out.append("> **今すぐ対応してください。** 重大な項目は、放置すると実害(金銭・情報漏洩)につながります。\n")
    elif counts["warning"]:
        out.append("> 公開は可能ですが、警告の項目は早めの対応をおすすめします。\n")
    else:
        out.append("> 大きな問題は見つかりませんでした。\n")
    for f in findings:
        loc = f.file + (f":{f.line}" if f.line else "")
        out.append(f"### [{SEVERITY_JA[f.severity]}] {f.title}")
        out.append(f"- 場所: `{loc}`" + (f"(検出値: `{f.evidence}`)" if f.evidence else ""))
        out.append(f"- **何が起きうるか**: {f.scenario}")
        out.append(f"- **直し方**: {f.fix}\n")
    out.append("---")
    out.append("このレポートはあなたのサイトの弱点情報です。取り扱いに注意してください。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="LaunchGuard 外形診断(ローカル静的サイト版)")
    ap.add_argument("target", help="診断するサイトのディレクトリ")
    ap.add_argument("--json", help="JSON出力先")
    ap.add_argument("--md", help="Markdownレポート出力先")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        sys.exit(f"エラー: ディレクトリが見つかりません: {target}")

    result = scan(target)
    md = render_markdown(result)

    if args.json:
        payload = {"target": result.target, "files_scanned": result.files_scanned,
                   "findings": [asdict(f) for f in result.sorted_findings()]}
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    print(md)

    has_critical = any(f.severity == "critical" for f in result.findings)
    sys.exit(2 if has_critical else 0)


if __name__ == "__main__":
    main()
