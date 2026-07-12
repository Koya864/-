# LaunchGuard — AI生成サイトの診断エンジン(フェーズ1)

AIで作ったサイトを公開する前に、セキュリティ・品質の「開いている窓」を見つけて、
平易な日本語(何が起きうるか/どう直すか)で報告するツール。

全体構想は [docs/ROADMAP.md](../../docs/ROADMAP.md) を参照。

## 使い方

```bash
python3 tools/launchguard/scan.py <サイトのフォルダ> [--md report.md] [--json result.json]
```

依存パッケージなし(Python 3.9+ のみ)。重大な検出があると終了コード 2 を返す(CI組み込み用)。

## 現在の診断項目

| ID | 重さ | 内容 |
|---|---|---|
| hardcoded-secret | 重大 | APIキー等のコード直書き(OpenAI/Anthropic/Google/AWS/Stripe/GitHub/Slack/JWT/汎用) |
| exposed-file | 重大〜推奨 | .env / .git / DB / バックアップ / アーカイブの公開フォルダ混入 |
| no-security-headers | 警告 | セキュリティヘッダー設定ファイルの欠如 |
| innerhtml-injection | 警告 | innerHTML への変数埋め込み(XSSの典型) |
| risky-js | 警告 | eval / document.write の使用 |
| form-insecure-action / form-mailto / form-js-handled | 重大〜推奨 | フォーム送信先の問題 |
| mixed-content | 警告 | http:// 資源の読み込み |
| script-no-sri | 推奨 | 外部スクリプトの改ざん検知なし |
| blank-noopener | 推奨 | target="_blank" の noopener 欠如 |
| email-exposed | 推奨 | メールアドレスの生掲載 |

## 設計原則

- **発見と検証は決定的なルールで行う。AIは説明と修正の生成のみ**(合否判定をLLMにさせない)
- レポートに検出値そのものを載せない(マスクする)— レポート自体を漏洩源にしない
- 1検出 = 「何が」「何が起きうるか」「どう直すか」の3点セットを必ず出す

## 次のステップ

- [ ] URL(公開サイト)モード: HTTPS / セキュリティヘッダー / 公開ファイル露出の実地チェック
- [ ] JS内の http:// 通信(fetch/XHR)の検出
- [ ] リポジトリモード: コミット履歴のシークレット走査(gitleaks連携)
- [ ] LLMによるサイト文脈込みレポート生成
- [ ] 修正提案の自動生成(修正PR)

## サンプル

`docs/samples/real-estate-site-report.md` — 本リポジトリ同梱のAI生成サイトを診断した実レポート。
