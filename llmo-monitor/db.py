#!/usr/bin/env python3
"""
db.py — 診断結果(results.csv)を蓄積型SQLite DBに取り込む

4つのテーブル:
  runs    : 計測1回ぶん(質問・エンジン・順位・言及)      … ツールが自動で埋める
  sources : 引用URL・ドメイン・種別・誰を引用したか        … ツール＋AIが分類
  queries : 質問・意図・価値/優先度                        … AIが下書き→人が確定
  actions : 改善タスク・推奨内容・状態                      … AIが草案→人が取捨

依存なし(sqlite3 は Python 標準)。

使い方:
  python3 db.py init                       # DBを初期化(llmo.db を作成)
  python3 db.py ingest results.csv         # CSVをDBに取り込む
"""

import argparse
import csv
import sqlite3
import sys
from urllib.parse import urlparse

DB_PATH = "llmo.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    engine TEXT,
    query TEXT,
    run INTEGER,
    mentioned INTEGER,
    rank INTEGER,
    share_of_voice REAL,
    competitors_seen TEXT,
    UNIQUE(timestamp, engine, query, run)
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id),
    url TEXT,
    domain TEXT,
    source_type TEXT DEFAULT 'unclassified'
);

CREATE TABLE IF NOT EXISTS queries (
    query TEXT PRIMARY KEY,
    intent TEXT,
    priority INTEGER,
    value_note TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    query TEXT,
    action_type TEXT,
    recommendation TEXT,
    target_source TEXT,
    status TEXT DEFAULT 'todo',
    created_at TEXT
);
"""


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init(path=DB_PATH):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"初期化しました: {path}")


def _domain(url):
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def ingest(csv_path, path=DB_PATH):
    conn = connect(path)
    conn.executescript(SCHEMA)  # 未初期化でも安全なように
    new_runs = 0
    new_sources = 0
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cur = conn.execute(
                """INSERT OR IGNORE INTO runs
                   (timestamp, engine, query, run, mentioned, rank,
                    share_of_voice, competitors_seen)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    row["timestamp"], row["engine"], row["query"],
                    int(row["run"]),
                    1 if row["mentioned"] == "True" else 0,
                    int(row["rank"]), float(row["share_of_voice"]),
                    row.get("competitors_seen", ""),
                ),
            )
            if cur.rowcount == 0:
                continue  # 既に取り込み済み
            new_runs += 1
            run_id = cur.lastrowid
            for url in filter(None, (row.get("sources") or "").split("|")):
                conn.execute(
                    "INSERT INTO sources (run_id, url, domain) VALUES (?,?,?)",
                    (run_id, url, _domain(url)),
                )
                new_sources += 1
    conn.commit()
    conn.close()
    print(f"取り込み: 新規runs {new_runs} 件 / 引用ソース {new_sources} 件")


def main():
    ap = argparse.ArgumentParser(description="LLMO診断結果のDB取り込み")
    ap.add_argument("cmd", choices=["init", "ingest"])
    ap.add_argument("csv", nargs="?", help="ingest 時のCSVパス")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    if args.cmd == "init":
        init(args.db)
    elif args.cmd == "ingest":
        if not args.csv:
            print("使い方: python3 db.py ingest results.csv", file=sys.stderr)
            sys.exit(1)
        ingest(args.csv, args.db)


if __name__ == "__main__":
    main()
