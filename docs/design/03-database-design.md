# 03. データベース設計 — 全国展開を見据えて

対応事項: **9. 将来的な全国展開を見据えたDB設計**

## 設計方針

1. **エリアはマスタテーブル駆動**にする。愛知県→東海3県→全国の拡大は「マスタに行を足す」だけで完了させる。コードに県名をハードコードしない。
2. **物件・評価・掲載を分離**する。同じ物件が再掲載されるケース、評価基準が改定されるケースに耐える。
3. **スコアの内訳は非公開前提のスキーマ**にする（公開ビューに内訳を含めない）。
4. 監査可能性: 価格変更・審査判断・優先権付与は履歴テーブルに残す（宅建業法・トラブル対応）。

## ER図（主要部分）

```
prefectures ─< cities ─< towns
     │            │
stations >── station_lines        （駅×路線は多対多）

organizations（管理会社）─< org_members ─ users ─ profiles
     │
     └─< listing_requests（掲載依頼）
              │
              └─ properties（物件）─< property_photos
                    │                └< property_stations
                    ├─< evaluations（AI評価・バージョン付き）
                    ├─< reviews（社内審査）
                    ├─< listings（掲載。公開状態・期間）
                    │      ├─< favorites
                    │      └─< entries（購入エントリー）
                    │             └─< entry_priorities（優先購入権）
                    └─< price_histories
categories（SEOカテゴリ）>─< listing_categories
```

## 主要テーブル定義

### エリアマスタ（全国展開の要）

```sql
create table prefectures (
  id smallint primary key,          -- JIS X 0401 都道府県コード（23=愛知）
  name text not null, slug text unique not null,
  is_active boolean default false   -- Phase制御: 愛知のみtrue → 東海3県 → 全国
);

create table cities (
  id integer primary key,           -- JIS X 0402 市区町村コード（5桁）
  prefecture_id smallint references prefectures,
  name text not null, slug text not null,
  is_active boolean default false,
  unique (prefecture_id, slug)
);

create table stations (
  id serial primary key,
  name text not null, slug text not null,
  city_id integer references cities,
  lat double precision, lng double precision
);
-- 出典: 国土数値情報 or 駅データ.jp。路線は station_lines で多対多
```

- **JIS標準コードを主キーに採用**することで、公的統計・地価データ・不動産情報ライブラリAPIとの結合が自明になる。
- `is_active` フラグで対象エリアのPhase拡大を制御（検索対象・カテゴリ生成対象の判定に使用）。

### 物件・掲載

```sql
create table properties (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references organizations,
  property_type text not null,      -- used_mansion / new_mansion / used_house / new_house / land
  name text not null,
  slug text unique not null,        -- SEO用。公開後不変
  prefecture_id smallint references prefectures,
  city_id integer references cities,
  address_detail text,              -- 町名以下（公開粒度は別カラムで制御）
  lat double precision, lng double precision,
  price bigint not null,            -- 円。将来の海外展開は考えず円整数
  floor_area_sqm numeric(7,2),
  land_area_sqm numeric(9,2),
  layout text,                      -- 3LDK等
  built_year_month date,
  management_fee integer, repair_reserve integer,
  land_rights text,
  transaction_type text not null,   -- 宅建業法: 取引態様（媒介/代理/売主）必須
  attributes jsonb default '{}',    -- 種別ごとの可変属性（拡張はここに逃がす）
  data_source text not null,        -- document_upload / own_url / manual
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table listings (
  id uuid primary key default gen_random_uuid(),
  property_id uuid references properties,
  status text not null default 'draft',
  -- draft → in_review → approved → published → entry_closed → negotiating → sold / withdrawn / on_hold(保留)
  published_at timestamptz, closed_at timestamptz,
  entry_deadline timestamptz,             -- エントリー期間終了日時
  certification_rank text,                -- S / A / B（公開情報）
  public_comment text,                    -- おすすめコメント（公開）
  highlight_metric text,                  -- カードに1つだけ出す補助情報の種類
  -- favorites_count / considering_count / ranking のいずれか（企画書「複数表示しない」）
  plan text default 'standard'            -- standard / premium（収益モデル）
);
```

- `properties`（物件そのもの）と `listings`（掲載）を分けることで、
  再掲載・掲載保留（85点未満）・価格改定後の再審査が自然に表現できる。
- 種別ごとに異なる属性（マンションの階数・戸建ての接道等）は `attributes` JSONBへ。
  **検索軸になる項目だけ正規カラムに昇格**させる方針で、全国展開時のスキーマ変更を最小化。

### 評価・審査（ブラックボックス保持）

```sql
create table evaluations (
  id uuid primary key default gen_random_uuid(),
  property_id uuid references properties,
  engine_version text not null,     -- 評価エンジンのバージョン（07参照）
  total_score numeric(5,2) not null,
  rank text not null,               -- S/A/B（公開可能な形）
  score_breakdown jsonb not null,   -- 内訳（非公開。RLSで運営のみ）
  ai_summary text,                  -- AI生成の評価サマリ（社内向け）
  improvement_suggestions jsonb,    -- 保留物件への改善提案（価格調整/写真改善/リフォーム）
  created_at timestamptz default now()
);

create table reviews (                -- 社内審査（人間の最終判断）
  id uuid primary key default gen_random_uuid(),
  listing_id uuid references listings,
  evaluation_id uuid references evaluations,
  reviewer_id uuid references users,
  decision text not null,           -- approve / hold / reject
  reason text,                      -- 判断理由（監査証跡）
  created_at timestamptz default now()
);
```

- **公開用ビュー `public_listings` には rank・public_comment のみ含め、score_breakdown は絶対に載せない。**
  RLS + ビュー分離の二重防御でブラックボックス方針をスキーマレベルで保証する。

### エントリー・優先購入権

```sql
create table entries (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid references listings,
  user_id uuid references users,
  status text not null default 'active',
  -- active / withdrawn / prioritized / declined / contracted
  pre_approved boolean default false,      -- 住宅ローン事前審査済み
  intended_payment text,                   -- cash / loan
  note text,
  created_at timestamptz default now(),
  unique (listing_id, user_id)
);

create table entry_priorities (            -- 優先購入権の付与履歴（監査可能）
  id uuid primary key default gen_random_uuid(),
  listing_id uuid references listings,
  entry_id uuid references entries,
  priority_order integer not null,         -- 1位, 2位（繰り上げ用）...
  granted_by uuid references users,        -- 付与した運営担当者
  rule_snapshot jsonb not null,            -- 付与時の順位決定ルールのスナップショット
  status text default 'offered',           -- offered / accepted / expired / passed
  offered_at timestamptz, expires_at timestamptz,
  unique (listing_id, priority_order)
);
```

### SEOカテゴリ

```sql
create table categories (
  id serial primary key,
  kind text not null,               -- area / station / feature / price_range / layout
  slug text not null, title text not null,
  intro_md text,                    -- カテゴリページ冒頭の解説文（コンテンツSEO）
  meta jsonb default '{}',
  unique (kind, slug)
);
create table listing_categories (
  listing_id uuid references listings,
  category_id integer references categories,
  primary key (listing_id, category_id)
);
```

- カテゴリページは `categories × 掲載中listing 1件以上` の条件でISR生成（01参照）。

## 全国展開時のスケール見通し

- 全国の年間中古流通は約60万件規模だが、**認定制のため掲載数は多くても数千件/年**。
  PostgreSQL単一インスタンスで長期間十分。シャーディング等は不要。
- 負荷が先に来るのは**閲覧側（SEO流入）**であり、これはISR/CDNで吸収する設計（DBに閲覧負荷を落とさない）。
- 地理検索（「この駅から徒歩10分圏」等）が必要になった時点でPostGIS拡張を有効化（lat/lngは最初から保持）。
- お気に入り数・検討中人数などの表示用カウントは、リアルタイム集計ではなく
  マテリアライズドビュー or 定期バッチで `listings` に非正規化して持つ（表示は「約」で足りる）。
