# 09. 権限設計 — 管理会社・購入者・運営

対応事項: **13. 管理会社・購入者・運営側それぞれの権限設計**

## ロール定義

| ロール | 所属 | 説明 |
|-------|------|------|
| `guest` | — | 未ログイン閲覧者 |
| `member` | 購入者 | 無料会員（お気に入り・詳細分析閲覧） |
| `entrant` | 購入者 | SMS認証済み（エントリー可能）※memberの属性フラグでも可 |
| `partner_staff` | 管理会社 | 自社物件の掲載・管理 |
| `partner_admin` | 管理会社 | 上記 + 自社メンバー管理・会社情報編集 |
| `ops` | 運営 | 審査・エントリー管理・商談管理 |
| `ops_admin` | 運営 | 上記 + スタッフ管理・評価エンジン設定・管理会社アカウント承認 |

実装: `users.role` は運営系のみ。管理会社の所属・役割は `org_members(user_id, organization_id, role)` で表現（1ユーザーが複数社に所属するケースに対応）。

## 権限マトリクス（主要リソース）

| リソース / 操作 | guest | member | partner | ops | ops_admin |
|---|---|---|---|---|---|
| 公開物件の閲覧 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 詳細分析（会員限定コンテンツ） | ─ | ✅ | ─ | ✅ | ✅ |
| **評価スコア内訳（score_breakdown）** | ─ | ─ | **─** | ✅ | ✅ |
| お気に入り | ─ | ✅ 自分のみ | ─ | 集計のみ | 集計のみ |
| エントリー作成/撤回 | ─ | ✅ 自分のみ | ─ | ─ | ─ |
| エントリー一覧（個人情報含む） | ─ | ─ | **件数のみ** | ✅ | ✅ |
| 優先権の確定・繰り上げ | ─ | ─ | ─ | ✅ | ✅ |
| 物件の下書き作成・編集 | ─ | ─ | ✅ 自社のみ | ✅ | ✅ |
| 掲載承認・保留・却下 | ─ | ─ | ─ | ✅ | ✅ |
| 価格変更の反映 | ─ | ─ | 申請のみ | ✅ | ✅ |
| 会員個人情報の閲覧 | ─ | 自分のみ | ─ | 担当物件のみ推奨 | ✅ |
| 管理会社アカウント承認 | ─ | ─ | ─ | ─ | ✅ |
| 評価エンジン設定・監査ログ | ─ | ─ | ─ | 閲覧のみ | ✅ |

### 設計上とくに重要な3点

1. **管理会社にはエントリー者の個人情報を渡さない。**
   渡すのは件数と進捗ステータスのみ。購入者の個人情報の管理主体をLife Shiftに一元化することで、
   個情法上の責任範囲が明確になり、管理会社経由の直接取引（中抜き）も構造的に防げる。
2. **score_breakdownは運営ロール以外に一切露出しない。**
   APIレスポンス・管理会社画面・会員画面のどこにも出さない（ブラックボックスの技術的担保）。
3. **partnerは「申請」、opsが「反映」。** 公開情報（価格・掲載状態）を変える操作は
   必ず運営の確認を挟む2段階にする（おとり広告・誤掲載の防止）。

## 実装方式: Supabase RLS + アプリ層ガード

```sql
-- 例1: 物件は公開済みなら誰でも、下書きは自社と運営のみ
create policy listings_read on listings for select using (
  status = 'published'
  or exists (select 1 from properties p join org_members m
             on m.organization_id = p.organization_id
             where p.id = listings.property_id and m.user_id = auth.uid())
  or is_ops(auth.uid())
);

-- 例2: エントリーは本人と運営のみ（管理会社は不可）
create policy entries_read on entries for select using (
  user_id = auth.uid() or is_ops(auth.uid())
);

-- 例3: 評価内訳は運営のみ（テーブルごと遮断し、公開情報はビューで提供）
create policy evaluations_read on evaluations for select using (is_ops(auth.uid()));
create view public_certifications as
  select listing_id, certification_rank, public_comment from listings
  where status = 'published';
```

- **RLSを一次防衛線**とし、アプリ層（Next.js Route Handler）でも同じチェックを行う二重防御。
  SQLインジェクションや実装ミスがあってもDB層で情報が漏れない。
- 管理会社向けの集計値（エントリー件数等）は専用ビュー/RPCで提供し、行データは見せない。

## 監査ログ

権限をまたぐ操作（承認・優先権確定・個人情報閲覧・価格変更）はすべて `audit_logs` に記録:

```sql
create table audit_logs (
  id bigserial primary key,
  actor_id uuid, actor_role text,
  action text not null,          -- listing.approve / priority.grant / member.view …
  target_type text, target_id uuid,
  before jsonb, after jsonb, reason text,
  created_at timestamptz default now()
);
```

- 個情法の安全管理措置・宅建業法トラブル時の説明・社内不正防止の3役を兼ねる。
- ops_adminのみ閲覧可・削除は誰も不可（append-only）。
