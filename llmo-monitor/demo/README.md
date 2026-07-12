# デモアカウント(みらい会計事務所)

営業でそのまま見せられる、作り込みデータ入りのデモ一式です。

- `results.csv` … 架空クライアントの2時点(先月・今月)の診断データ(demo_seed.pyで生成)
- `dashboard.html` … 顧客向けダッシュボード(dashboard.pyで生成)
- `llmo.db` は生成物なのでコミットしません(.gitignore済み)

## 再生成の手順

```bash
cd llmo-monitor
python3 demo_seed.py --out demo/results.csv          # デモデータ生成
python3 db.py init   --db demo/llmo.db
python3 db.py ingest demo/results.csv --db demo/llmo.db
python3 analyze.py   --db demo/llmo.db               # 改善案をDBに書き戻し
python3 dashboard.py --db demo/llmo.db --name "みらい会計事務所" --out demo/dashboard.html
```

`dashboard.html` をブラウザで開けばそのままデモになります。
