#!/usr/bin/env python3
"""
analyze.py — 蓄積したDBから「次にやるべき改善策」を導き出す

層A(データだけ・常に動く):
  - 優先度つきギャップ:競合は出るのに自社が出ない質問を影響度順に
  - 引用元ターゲット:AIが引用しているドメインを集計(=載るべき場所)
  - 自社 vs 第三者:自社サイトが引用されているか

層B(--ai かつ ANTHROPIC_API_KEY がある時):
  - 引用元ドメインの種別をClaudeが分類(比較/レビュー/メディア/公式/百科/その他)
  - 優先ギャップ質問ごとに改善アクションの草案をClaudeが生成
  ※ キーが無ければルールベースで代替(必ず何か出る)

結果は queries / actions テーブルに書き戻し、レポートを表示する。

使い方:
  python3 analyze.py                       # 層Aのみ(ルールベース)
  python3 analyze.py --ai                  # Claudeで分類・草案生成
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from db import connect, DB_PATH

# ---------------------------------------------------------------------------
# 引用元ドメインの種別分類(ルールベース。--ai でAIに置き換え可能)
# ---------------------------------------------------------------------------

_RULES = [
    ("encyclopedia", ["wikipedia.", "wikiwand."]),
    ("review", ["review", "kuchikomi", "口コミ", "minhyo", "trustpilot", "g2."]),
    ("comparison", ["hikaku", "比較", "compare", "ranking", "osusume",
                    "boxil", "itreview", "capterra"]),
    ("official", []),  # 後で「自社/競合の公式らしさ」用に予約
    ("media", ["news", "prtimes", "itmedia", "note.com", "blog", "media",
               "diamond", "toyokeizai"]),
    ("forum", ["reddit", "yahoo", "chiebukuro", "quora", "5ch", "teratail"]),
]


def classify_domain_rule(domain):
    d = domain.lower()
    for label, keys in _RULES:
        if any(k in d for k in keys):
            return label
    return "other"


# ---------------------------------------------------------------------------
# Claude 呼び出し(層B)。失敗時は None を返して層Aにフォールバック。
# ---------------------------------------------------------------------------

def call_claude(prompt, max_tokens=1500):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        return "".join(
            b.get("text", "") for b in r.get("content", []) if b.get("type") == "text"
        )
    except Exception as e:
        print(f"  [claude] error: {e}", file=sys.stderr)
        return None


def _parse_json(text):
    """テキストからJSON部分を取り出してパース。失敗時 None。"""
    if not text:
        return None
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        s, e = text.find("["), text.rfind("]")
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 層A:データからの集計
# ---------------------------------------------------------------------------

def query_gaps(conn):
    """質問ごとに 言及率・競合出現率・機会スコア を計算し、優先度順に返す。"""
    rows = conn.execute("SELECT * FROM runs").fetchall()
    stats = {}
    for r in rows:
        s = stats.setdefault(r["query"], {"n": 0, "mentioned": 0, "comp": 0})
        s["n"] += 1
        s["mentioned"] += r["mentioned"]
        if (r["competitors_seen"] or "").strip():
            s["comp"] += 1
    out = []
    for q, s in stats.items():
        mention_rate = s["mentioned"] / s["n"]
        comp_rate = s["comp"] / s["n"]
        opportunity = round((1 - mention_rate) * comp_rate, 3)
        out.append({
            "query": q, "runs": s["n"],
            "mention_rate": round(mention_rate, 3),
            "competitor_presence": round(comp_rate, 3),
            "opportunity": opportunity,
        })
    out.sort(key=lambda x: x["opportunity"], reverse=True)
    return out


def cited_domains(conn):
    """引用元ドメインを集計(頻度順)。"""
    rows = conn.execute(
        "SELECT domain, COUNT(*) c FROM sources WHERE domain != '' "
        "GROUP BY domain ORDER BY c DESC"
    ).fetchall()
    return [{"domain": r["domain"], "count": r["c"]} for r in rows]


def self_vs_third_party(conn, site_domain):
    """
    自社サイトが引用されているかを見る。
      own_total     : 自社ドメインが引用された回数
      third_party_queries: 自社は登場するのに自社サイトは引用されていない質問
                           (=AIは第三者経由で認識 → その第三者を強化すべき)
    site_domain が未設定なら None。
    """
    if not site_domain:
        return None
    site_domain = site_domain.lower().replace("www.", "")
    own_total = conn.execute(
        "SELECT COUNT(*) c FROM sources WHERE domain LIKE ?",
        (f"%{site_domain}%",),
    ).fetchone()["c"]

    third_party_queries = []
    q_rows = conn.execute(
        "SELECT DISTINCT query FROM runs WHERE mentioned=1"
    ).fetchall()
    for qr in q_rows:
        q = qr["query"]
        hit = conn.execute(
            "SELECT COUNT(*) c FROM sources s JOIN runs r ON s.run_id=r.id "
            "WHERE r.query=? AND s.domain LIKE ?",
            (q, f"%{site_domain}%"),
        ).fetchone()["c"]
        if hit == 0:
            third_party_queries.append(q)
    return {"site": site_domain, "own_total": own_total,
            "third_party_queries": third_party_queries}


# ---------------------------------------------------------------------------
# 種別分類(層B優先、ダメなら層A)
# ---------------------------------------------------------------------------

def classify_domains(conn, domains, use_ai):
    labels = {}
    if use_ai and domains:
        prompt = (
            "次のドメイン一覧を、AI検索(LLMO)の引用元としての種別に分類してください。"
            "種別は comparison(比較・ランキング)/ review(レビュー・口コミ)/ "
            "media(ニュース・専門メディア)/ official(企業公式)/ "
            "encyclopedia(Wikipedia等)/ forum(掲示板・Q&A)/ other のいずれか。"
            "JSONで {\"ドメイン\": \"種別\"} だけを返してください。\n\n"
            + "\n".join(d["domain"] for d in domains)
        )
        parsed = _parse_json(call_claude(prompt))
        if isinstance(parsed, dict):
            labels = parsed
    for d in domains:
        dom = d["domain"]
        d["type"] = labels.get(dom) or classify_domain_rule(dom)
        conn.execute(
            "UPDATE sources SET source_type=? WHERE domain=?", (d["type"], dom)
        )
    conn.commit()
    return domains


# ---------------------------------------------------------------------------
# アクション草案の生成
# ---------------------------------------------------------------------------

def build_actions(conn, gaps, domains, use_ai, top_n=5):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    top_domains = domains[:5]
    priority_gaps = [g for g in gaps if g["opportunity"] > 0][:top_n]

    conn.execute("DELETE FROM actions")  # 毎回作り直す(冪等)
    all_actions = []

    ai_recs = {}
    if use_ai and priority_gaps:
        prompt = (
            "あなたはLLMO(AI検索最適化)コンサルタントです。"
            "以下の『AIに引用されていない質問』それぞれに対し、具体的な改善アクションを"
            "1〜2文で提案してください。効果の強い要因(結論先出し・構造化・第三者からの"
            "言及・鮮度)に基づくこと。JSONで {\"質問\": \"提案\"} を返してください。\n\n"
            "参考:AIがよく引用しているサイト = "
            + ", ".join(f"{d['domain']}({d['type']})" for d in top_domains) + "\n\n"
            "質問一覧:\n" + "\n".join(g["query"] for g in priority_gaps)
        )
        parsed = _parse_json(call_claude(prompt))
        if isinstance(parsed, dict):
            ai_recs = parsed

    for g in priority_gaps:
        q = g["query"]
        # 1) コンテンツ改善(AI草案があれば優先)
        rec = ai_recs.get(q) or (
            f"『{q}』に結論先出し(冒頭200語で回答)のFAQ型記事を作成し、"
            "表・箇条書きで構造化。独自の統計や出典を入れて引用されやすくする。"
        )
        all_actions.append((q, "content", rec, ""))
        # 2) 第三者掲載(最大の要因)
        if top_domains:
            td = top_domains[0]
            all_actions.append((
                q, "third_party",
                f"AIが引用している {td['domain']}({td['type']})への掲載・"
                "レビュー獲得を狙う。第三者からの言及はAI引用に最も効く。",
                td["domain"],
            ))
        # 3) 鮮度
        all_actions.append((
            q, "freshness",
            "関連記事は約3ヶ月ごとに更新し鮮度を保つ(放置すると引用が落ちる)。", ""
        ))

    for q, atype, rec, tgt in all_actions:
        conn.execute(
            "INSERT INTO actions (query, action_type, recommendation, "
            "target_source, created_at) VALUES (?,?,?,?,?)",
            (q, atype, rec, tgt, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO queries (query, priority) VALUES (?,?)", (q, 0)
        )
    # 優先度を機会スコア順に採番
    for i, g in enumerate(priority_gaps, 1):
        conn.execute("UPDATE queries SET priority=? WHERE query=?", (i, g["query"]))
    conn.commit()
    return priority_gaps, all_actions


# ---------------------------------------------------------------------------
# レポート表示
# ---------------------------------------------------------------------------

def report(gaps, domains, priority_gaps, actions, selfp):
    print("\n================ LLMO 改善レポート ================\n")

    print("■ 優先ギャップ(競合は出るが自社が出ない質問 / 機会スコア順)")
    if not any(g["opportunity"] > 0 for g in gaps):
        print("  該当なし(データが少ないか、既に十分言及されています)")
    for g in gaps[:8]:
        print(f"  機会 {g['opportunity']:.2f} | 言及率 {g['mention_rate']:.0%} "
              f"| 競合出現 {g['competitor_presence']:.0%} | {g['query']}")

    print("\n■ 引用元ターゲット(AIが引用しているサイト = 載るべき場所)")
    if not domains:
        print("  引用元データがありません")
    for d in domains[:8]:
        print(f"  {d['count']:>3}回 | {d.get('type','?'):12} | {d['domain']}")

    print("\n■ 改善アクション草案(優先質問ごと)")
    by_q = {}
    for q, atype, rec, tgt in actions:
        by_q.setdefault(q, []).append((atype, rec))
    for i, g in enumerate(priority_gaps, 1):
        print(f"\n  [{i}] {g['query']}")
        for atype, rec in by_q.get(g["query"], []):
            print(f"      - ({atype}) {rec}")

    if selfp:
        print("\n■ 自社サイト vs 第三者")
        print(f"  自社サイト({selfp['site']})の引用回数: {selfp['own_total']}")
        tpq = selfp["third_party_queries"]
        if tpq:
            print("  自社は登場するが自社サイトは引用されていない質問"
                  "(=第三者経由で認識。その第三者を強化):")
            for q in tpq[:6]:
                print(f"    - {q}")
        elif selfp["own_total"]:
            print("  自社サイトが引用されています(良好)。")

    print("\n===================================================")
    print("※ 草案です。実際にどの掲載先を取りに行くか等の最終判断は人(あなた)が。")


def main():
    ap = argparse.ArgumentParser(description="LLMO改善レコメンド生成")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--ai", action="store_true",
                    help="Claudeで種別分類・アクション草案を生成")
    ap.add_argument("--config", default="config.json",
                    help="自社サイトドメイン判定などに使用(任意)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"DBが見つかりません: {args.db}\n"
              f"先に  python3 db.py init && python3 db.py ingest results.csv  を実行。",
              file=sys.stderr)
        sys.exit(1)

    use_ai = args.ai and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if args.ai and not use_ai:
        print("ANTHROPIC_API_KEY が無いためルールベースで実行します。",
              file=sys.stderr)

    # 自社サイトのドメイン(任意)を config から読む
    site_domain = None
    if os.path.exists(args.config):
        try:
            with open(args.config, encoding="utf-8") as f:
                site_domain = json.load(f).get("target", {}).get("site")
        except Exception:
            pass

    conn = connect(args.db)
    gaps = query_gaps(conn)
    domains = classify_domains(conn, cited_domains(conn), use_ai)
    priority_gaps, actions = build_actions(conn, gaps, domains, use_ai)
    selfp = self_vs_third_party(conn, site_domain)
    report(gaps, domains, priority_gaps, actions, selfp)
    conn.close()


if __name__ == "__main__":
    main()
