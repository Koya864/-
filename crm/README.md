# ご縁CRM — 保険営業向け顧客管理ツール

「顧客リストの管理」ではなく「関係性を育てる」ための営業支援ツール。
契約更新・契約記念日・誕生日・疎遠アラートを自動算出し、面談メモをタイムラインで蓄積します。

企画・設計の背景は [`docs/insurance-crm-design.md`](../docs/insurance-crm-design.md) を参照。

## 技術構成

- Next.js 15 (App Router) + TypeScript + Tailwind CSS
- Prisma + PostgreSQL
- ホスティング: Vercel（+ Neon Postgres）を想定

---

## 公開手順（Vercel — ボタン操作だけで完了します）

### 1. Vercelにログイン
https://vercel.com を開き「Continue with GitHub」でログイン（無料）。

### 2. プロジェクトをインポート
「Add New… → Project」→ リポジトリ `Koya864/-` の「Import」を押す。

- **Root Directory** の「Edit」を押して **`crm`** を指定（重要）
- そのまま「Deploy」を押す
- ※ 1回目のデプロイはDB未設定のため**失敗しますが正常**です。次へ進んでください

### 3. データベース（Neon）を接続
プロジェクト画面の「Storage」タブ →「Create Database」→ **Neon**（Postgres）を選択
→ 無料プランで作成 →「Connect Project」でこのプロジェクトに接続。

これで環境変数 `DATABASE_URL` が自動設定されます。
（変数名が `DATABASE_URL` になっていることを Settings → Environment Variables で確認）

### 4. 本番ブランチを設定
Settings → Git → **Production Branch** を
`claude/insurance-crm-design-c6xf1s` に変更（コードがこのブランチにあるため）。

### 5. 再デプロイ
「Deployments」タブ → 最新のデプロイの「…」→「Redeploy」。

ビルド時にテーブル作成とサンプル顧客3名の投入まで自動で行われます
（既にデータがある場合、サンプル投入は自動でスキップされ実データは消えません）。

完了すると `https://〇〇.vercel.app` が発行され、スマホからでも触れます。

---

## ローカルで動かす場合

Node.js 18以上が必要です。

```bash
cd crm
npm install
cp .env.example .env
# .env の DATABASE_URL に接続URLを記入
#（Vercel → Storage → Neon → 「.env.local」タブのURLをコピーするのが簡単）
npx prisma db push      # テーブル作成
npx prisma db seed      # サンプルデータ投入（既存データがあればスキップ）
npm run dev             # http://localhost:3001 で起動
```

ポートは3001を使うので、3000番で動いている他のプロジェクトと共存できます。

## セキュリティメモ

顧客の家族構成・健康に関する記録は機微情報です。

- `.env`（DB接続情報）は絶対にコミットしない（.gitignore済み）
- 現状は認証なしのMVPです。**URLを知っていれば誰でも閲覧できる**ため、
  本格利用の前に認証（Phase 2でログイン機能）を入れること
- それまでは営業マン本人への共有にとどめてください
