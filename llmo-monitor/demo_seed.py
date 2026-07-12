#!/usr/bin/env python3
"""
demo_seed.py — デモアカウント用のリアルな診断データを生成する

営業でそのまま見せられるよう、架空クライアント「みらい会計事務所」の
2時点(先月・今月)の計測結果を results.csv 形式で書き出す。
実APIは叩かない(デモ用の作り込みデータ)。列は本番の results.csv と同一なので
そのまま db.py ingest できる。

  python3 demo_seed.py --out demo/results.csv
"""
import argparse
import csv
import os

TARGET = "みらい会計事務所"
COMPETITORS = ["税理士法人ABC", "スマート会計", "さくら税務"]
ENGINES = ["openai", "perplexity", "gemini", "anthropic"]

# 質問ごとに「引用されやすいドメイン群」を作り込む(現実に近い構成)
QUERY_SOURCES = {
    "東京 税理士 おすすめ": [
        "zeiri4.com", "zeirishi-hikaku.jp", "google.com", "note.com"],
    "クラウド会計 導入支援 税理士": [
        "boxil.jp", "zeiri4.com", "freee.co.jp", "note.com"],
    "創業融資 サポート 税理士 東京": [
        "zeiri4.com", "j-net21.smrj.go.jp", "prtimes.jp"],
    "確定申告 丸投げ 費用 相場": [
        "zeirishi-hikaku.jp", "kuchikomi-zeirishi.jp", "zeiri4.com"],
    "インボイス 対応 税理士 相談": [
        "zeiri4.com", "note.com", "nta.go.jp"],
}

# (先月, 今月) の状態: rank=0 は圏外。今月は施策で少し改善している設定。
# query -> engine -> (rank_jun, rank_jul)
SCENARIO = {
    "東京 税理士 おすすめ": {
        "openai": (0, 0), "perplexity": (0, 4),
        "gemini": (0, 0), "anthropic": (0, 3)},
    "クラウド会計 導入支援 税理士": {
        "openai": (3, 2), "perplexity": (2, 2),
        "gemini": (0, 3), "anthropic": (3, 2)},
    "創業融資 サポート 税理士 東京": {
        "openai": (0, 0), "perplexity": (0, 0),
        "gemini": (0, 0), "anthropic": (0, 0)},
    "確定申告 丸投げ 費用 相場": {
        "openai": (0, 5), "perplexity": (4, 3),
        "gemini": (0, 0), "anthropic": (0, 4)},
    "インボイス 対応 税理士 相談": {
        "openai": (2, 1), "perplexity": (1, 1),
        "gemini": (2, 2), "anthropic": (1, 1)},
}

DATES = {"jun": "2026-06-10T09:00:00+00:00", "jul": "2026-07-10T09:00:00+00:00"}


def rows_for(month_key, month_idx):
    ts = DATES[month_key]
    rows = []
    for query, per_engine in SCENARIO.items():
        srcs = QUERY_SOURCES[query]
        for engine, ranks in per_engine.items():
            rank = ranks[month_idx]
            mentioned = rank > 0
            # 掲載順位からシェアを近似(上位ほど高い)
            share = round(max(0.0, (5 - rank) / 10), 3) if mentioned else 0.0
            # 自社が上位のときだけ自社サイトも引用されることがある設定
            sources = list(srcs)
            if mentioned and rank <= 2:
                sources = ["mirai-kaikei.jp"] + sources
            rows.append({
                "timestamp": ts,
                "engine": engine,
                "query": query,
                "run": 1,
                "mentioned": mentioned,
                "rank": rank,
                "share_of_voice": share,
                "competitors_seen": "|".join(COMPETITORS[:2]),
                "sources": "|".join(sources[:5]),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo/results.csv")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    all_rows = rows_for("jun", 0) + rows_for("jul", 1)
    fields = ["timestamp", "engine", "query", "run", "mentioned",
              "rank", "share_of_voice", "competitors_seen", "sources"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)
    print(f"デモデータを生成: {args.out}({len(all_rows)} 行 / 2時点)")


if __name__ == "__main__":
    main()
