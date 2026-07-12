# LLMO(AI検索対策)改善プロンプト — LSエージェント サイト向け

> **使い方**: SEO強化の作業指示に、この内容を丸ごと追加してください。
> 制作会社・サーバ担当者への依頼書としても、サイトのコードを触るAIアシスタントへの
> 指示プロンプトとしても、そのまま使えます。
> **目的**: Google検索(SEO)だけでなく、ChatGPT・Gemini・Perplexity・Claude などの
> **AI検索の回答に引用・推薦される(LLMO)**状態を作ること。SEOとLLMOは競合せず、
> 土台を共有します。

---

## あなたへの依頼(コピペしてそのまま渡せます)

以下のサイト( https://ls-agent.jp/ )を、SEOに加えて **AI検索(LLMO/GEO)で
引用・推薦される** ように改善してください。実装は下の優先順で進め、各項目は
「なぜやるか」も理解した上で対応してください。

### 【最優先 P0】AIクローラのアクセスを許可する
現状、サイトがブラウザ以外のアクセスに **403 Forbidden** を返しており、AI検索の
クローラが読めない状態です。これが直らない限り他の施策は無効です。

1. **WAF / サーバのボット遮断を見直す**
   - Cloudflare の「Bot Fight Mode」やファイアウォールルール、または
     nginx/Apache/レンタルサーバのUser-Agent制限が、ブラウザ以外を一律ブロック
     していないか確認し、下記クローラを通す。
2. **`robots.txt` で主要AIクローラを明示的に許可する**
   ```
   User-agent: OAI-SearchBot
   Allow: /
   User-agent: GPTBot
   Allow: /
   User-agent: PerplexityBot
   Allow: /
   User-agent: ClaudeBot
   Allow: /
   User-agent: Google-Extended
   Allow: /

   Sitemap: https://ls-agent.jp/sitemap.xml
   ```
3. **確認**: 各クローラのUser-Agentで `curl` して 200 が返ること。例:
   ```
   curl -A "OAI-SearchBot" -I https://ls-agent.jp/
   curl -A "PerplexityBot" -I https://ls-agent.jp/
   ```

### 【P1】AIが"抜き取れる"コンテンツ設計にする
AIは回答を作るとき、ページから部品として情報を抜き取ります。以下の型を守る。

1. **結論先出し(Answer-first)**: 各ページ・各見出しの**冒頭で問いに答え切る**。
   前置きや自己紹介から入らない。AIは記事冒頭で関連性を判断する。
2. **構造化**: 見出し(h2/h3)・箇条書き・**表**・Q&A形式を積極的に使う。
   「この質問には何か」が一目で分かる形に。引用されるページの約8割がこの形。
3. **FAQを設置し、FAQPage構造化データ(JSON-LD)を付ける**。例:
   ```html
   <script type="application/ld+json">
   {
     "@context": "https://schema.org",
     "@type": "FAQPage",
     "mainEntity": [{
       "@type": "Question",
       "name": "(見込み客が実際に聞く質問)",
       "acceptedAnswer": { "@type": "Answer", "text": "(結論を先に、簡潔に)" }
     }]
   }
   </script>
   ```
4. **独自の数値・出典を入れる**: 実績値・料金の相場・事例の数字など、
   自社にしか出せない具体データ。統計や引用があるページは引用されやすい。

### 【P1】構造化データ(schema.org)を整備する
- 会社情報に `Organization`(name / url / logo / sameAs でSNS・登録先を列挙)
- サービスページに `Service` / `Product`、事例に `Article`、拠点があれば
  `LocalBusiness`(住所・電話・対応エリア)。
- AIと検索エンジンが「これは何の会社か」を機械的に理解できるようにする。

### 【P1】`llms.txt` を設置する(任意だが推奨)
サイト直下に `https://ls-agent.jp/llms.txt` を置き、会社概要・主要サービス・
重要ページへのリンクを**プレーンな箇条書き**でまとめる。AIが要点を把握しやすくなる。

### 【P2】鮮度を保つ運用にする
- 主要ページ・記事は**約3ヶ月ごとに更新**(情報の追記・日付更新)。
  AIは新しい情報を優先し、放置した記事は引用が落ちる傾向。
- 各ページに更新日を明示(`dateModified` を構造化データにも反映)。

### 【P2 / サイト外だが重要】第三者からの言及を増やす
AI引用に最も効くのは「他者が御社を語っている」状態(自社サイト磨きより効く)。
サイト改修と並行して、以下を担当部門で進める:
- 業界の比較サイト・ポータルへの掲載/レビュー獲得
- プレスリリース(PR TIMES等)・業界メディアへの寄稿
- Google ビジネス プロフィール等の整備

---

## 実装後にやること(効果測定)
改修後、AI各社(ChatGPT/Gemini/Perplexity/Claude)に見込み客の質問を投げ、
「自社が登場するか・何番目か・どのサイトが引用されているか」を計測して改善を回す。
※ この計測は本リポジトリの `llmo-monitor` ツールで自動化できる。

## 共通チェックリスト(各ページ)
- [ ] 冒頭で問いに答えているか(結論先出し)
- [ ] 見出し・箇条書き・表で構造化されているか
- [ ] FAQ + FAQPage 構造化データがあるか
- [ ] 独自の数値・出典が入っているか
- [ ] 更新日が新しいか(3ヶ月以内目安)
- [ ] そのページがAIクローラから200で読めるか
