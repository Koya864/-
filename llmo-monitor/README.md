# llmo-monitor

AI検索(LLMO)で、自社や顧客企業が **ChatGPT / Gemini / Perplexity / Claude の回答に登場するか** を計測する最小ツール。事業計画でいう「フェーズ1(自動化スクリプト)」の心臓部です。

- 依存ライブラリなし(Python 3 標準ライブラリだけ)。`pip install` 不要。
- APIキーが1つも無くても `--mock` で動いて仕組みを体験できる。
- 質問を各AIに投げ → 回答に自社が出たか・何番目か・引用ソースは何か を解析 → CSV に追記。

## 使い方

```bash
# 1. 設定ファイルを作る
cp config.example.json config.json
#    → config.json を編集(会社名・競合・監視したい質問を記入)

# 2a. まず動きを見る(APIキー不要)
python3 llmo_monitor.py --mock

# 2b. 本番(キーがあるエンジンだけ自動で実行)
export OPENAI_API_KEY=...        # 使うものだけでOK
export PERPLEXITY_API_KEY=...
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
python3 llmo_monitor.py
```

結果は `results.csv` に追記されます(定期実行して時系列で見るのが前提)。

## config.json の項目

| キー | 意味 |
|---|---|
| `target.name` / `target.aliases` | 自社名と表記ゆれ(英語名・略称など) |
| `competitors` | 比較したい競合名 |
| `queries` | 見込み客がAIに聞きそうな質問 ← **ここの設計が成果を左右する** |
| `engines` | 使うAI。キーが無いものは自動スキップ |
| `runs_per_query` | 各質問を何回まわすか(回答はゆらぐので複数回の傾向で見る) |

## 出力CSVの列

`timestamp, engine, query, run, mentioned(登場したか), rank(何番目か), share_of_voice(言及シェア), competitors_seen(登場した競合), sources(引用URL)`

## 注意

- APIは従量課金。`質問数 × エンジン数 × runs_per_query` で呼び出し回数が増えます。まず数件で試すこと。
- 各AIのAPI仕様(モデル名・Web検索ツール)は変わることがあるので、動かないエンジンは `*_model` を最新値に更新してください。
- `config.json` と `results.csv` は顧客データ/出力のため `.gitignore` 済み(コミットされません)。
