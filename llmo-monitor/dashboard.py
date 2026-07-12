#!/usr/bin/env python3
"""
dashboard.py — DBから顧客向けダッシュボードHTMLを生成する(フェーズ2の入口)

最新スナップショットのKPI・優先ギャップ・引用元ターゲット・改善バックログを
1枚のHTMLにまとめる。前回スナップショットがあれば言及率の変化も表示。

  python3 dashboard.py --db demo/llmo.db --name "みらい会計事務所" \
      --out demo/dashboard.html
"""
import argparse
import html
import os
import sys

from db import connect, DB_PATH
from analyze import classify_domain_rule

TEAL = "#0e7c86"


def snapshots(conn):
    rows = conn.execute(
        "SELECT DISTINCT timestamp FROM runs ORDER BY timestamp DESC"
    ).fetchall()
    return [r["timestamp"] for r in rows]


def mention_rate(conn, ts):
    r = conn.execute(
        "SELECT AVG(mentioned) m FROM runs WHERE timestamp=?", (ts,)
    ).fetchone()
    return r["m"] or 0.0


def avg_rank(conn, ts):
    r = conn.execute(
        "SELECT AVG(rank) a FROM runs WHERE timestamp=? AND mentioned=1", (ts,)
    ).fetchone()
    return r["a"]


def domains(conn, ts):
    rows = conn.execute(
        "SELECT s.domain d, COUNT(*) c FROM sources s JOIN runs r ON s.run_id=r.id "
        "WHERE r.timestamp=? AND s.domain!='' GROUP BY s.domain ORDER BY c DESC",
        (ts,),
    ).fetchall()
    return [{"domain": x["d"], "count": x["c"],
             "type": classify_domain_rule(x["d"])} for x in rows]


def gaps(conn, ts):
    rows = conn.execute("SELECT * FROM runs WHERE timestamp=?", (ts,)).fetchall()
    stats = {}
    for r in rows:
        s = stats.setdefault(r["query"], {"n": 0, "m": 0, "c": 0})
        s["n"] += 1
        s["m"] += r["mentioned"]
        if (r["competitors_seen"] or "").strip():
            s["c"] += 1
    out = []
    for q, s in stats.items():
        mr = s["m"] / s["n"]
        cr = s["c"] / s["n"]
        out.append({"query": q, "mention_rate": mr,
                    "opportunity": round((1 - mr) * cr, 3)})
    out.sort(key=lambda x: x["opportunity"], reverse=True)
    return out


def actions_for(query, top_domain):
    a = [("content",
          f"『{query}』に結論先出し(冒頭200語で回答)のFAQ型記事を作成し、"
          "表・箇条書きで構造化。独自の統計・出典を入れる。")]
    if top_domain:
        a.append(("third_party",
                  f"AIが引用している {top_domain['domain']}"
                  f"({top_domain['type']})への掲載・レビュー獲得を狙う。"))
    a.append(("freshness", "関連記事は約3ヶ月ごとに更新し鮮度を保つ。"))
    return a


TYPE_JA = {"comparison": "比較", "review": "レビュー", "media": "メディア",
           "official": "公式", "encyclopedia": "百科", "forum": "掲示板",
           "other": "その他"}


def esc(s):
    return html.escape(str(s))


def build_html(name, cur, prev, mr_cur, mr_prev, arank, doms, gp, conn):
    date = cur[:10]
    delta = ""
    if prev is not None:
        d = (mr_cur - mr_prev) * 100
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "—")
        cls = "up" if d > 0 else ("down" if d < 0 else "flat")
        delta = (f'<span class="delta {cls}">{arrow} {abs(d):.0f}pt '
                 f'<span class="muted">前月比</span></span>')

    # KPIタイル
    tracked = conn.execute(
        "SELECT COUNT(DISTINCT query) c FROM runs WHERE timestamp=?", (cur,)
    ).fetchone()["c"]
    kpis = [
        ("AI言及率", f"{mr_cur*100:.0f}%", delta),
        ("平均掲載順位", f"{arank:.1f}位" if arank else "—", ""),
        ("引用元サイト数", str(len(doms)), ""),
        ("監視クエリ数", str(tracked), ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-label">{esc(l)}</div>'
        f'<div class="kpi-val">{esc(v)}</div>{d}</div>'
        for l, v, d in kpis
    )

    # 優先ギャップ
    gap_rows = ""
    priority = [g for g in gp if g["opportunity"] > 0]
    for g in gp:
        bar = int(g["opportunity"] * 100)
        tag = ('<span class="pill hot">要対応</span>' if g["opportunity"] > 0
               else '<span class="pill ok">良好</span>')
        gap_rows += (
            f'<tr><td>{esc(g["query"])}</td>'
            f'<td class="num">{g["mention_rate"]*100:.0f}%</td>'
            f'<td><div class="bar"><span style="width:{bar}%"></span></div></td>'
            f'<td>{tag}</td></tr>'
        )

    # 引用元ターゲット
    dom_rows = ""
    for d in doms[:8]:
        dom_rows += (
            f'<tr><td><span class="badge t-{d["type"]}">'
            f'{esc(TYPE_JA.get(d["type"], d["type"]))}</span></td>'
            f'<td>{esc(d["domain"])}</td>'
            f'<td class="num">{d["count"]}</td></tr>'
        )

    # 改善バックログ
    top_domain = doms[0] if doms else None
    backlog = ""
    for i, g in enumerate(priority[:5], 1):
        items = "".join(
            f'<li><span class="atype a-{t}">{esc(t)}</span>{esc(rec)}</li>'
            for t, rec in actions_for(g["query"], top_domain)
        )
        backlog += (
            f'<div class="task"><div class="task-h">'
            f'<span class="rank-badge">{i}</span>{esc(g["query"])}</div>'
            f'<ul>{items}</ul></div>'
        )
    if not backlog:
        backlog = '<p class="muted">優先度の高いギャップはありません。</p>'

    return TEMPLATE.format(
        name=esc(name), date=esc(date), kpis=kpi_html,
        gap_rows=gap_rows, dom_rows=dom_rows, backlog=backlog,
    )


TEMPLATE = """<title>{name} — AI検索(LLMO)ダッシュボード</title>
<style>
  :root {{
    --bg:#f5f8f8; --surface:#fff; --surface2:#eef2f1; --ink:#16201f;
    --soft:#3e4b49; --faint:#6b7a77; --line:#dde4e2; --accent:#0e7c86;
    --accent-soft:#d6ecec; --good:#2f7d54; --warn:#b5730f; --crit:#b23b3b;
  }}
  @media (prefers-color-scheme:dark){{:root{{
    --bg:#0d1413; --surface:#141d1c; --surface2:#1b2625; --ink:#e7edeb;
    --soft:#b6c2bf; --faint:#7f8f8c; --line:#26332f; --accent:#45b7bd;
    --accent-soft:#123536; --good:#5fbf87; --warn:#d9a24a; --crit:#e07a7a;
  }}}}
  :root[data-theme="dark"]{{
    --bg:#0d1413; --surface:#141d1c; --surface2:#1b2625; --ink:#e7edeb;
    --soft:#b6c2bf; --faint:#7f8f8c; --line:#26332f; --accent:#45b7bd;
    --accent-soft:#123536; --good:#5fbf87; --warn:#d9a24a; --crit:#e07a7a;
  }}
  :root[data-theme="light"]{{
    --bg:#f5f8f8; --surface:#fff; --surface2:#eef2f1; --ink:#16201f;
    --soft:#3e4b49; --faint:#6b7a77; --line:#dde4e2; --accent:#0e7c86;
    --accent-soft:#d6ecec; --good:#2f7d54; --warn:#b5730f; --crit:#b23b3b;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);line-height:1.6;
    font-family:-apple-system,"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,
    "Segoe UI",system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
  .wrap{{max-width:1000px;margin:0 auto;padding:0 20px 80px}}
  header{{padding:40px 0 24px;border-bottom:1px solid var(--line);margin-bottom:28px}}
  .eyebrow{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;
    color:var(--accent);font-weight:700;margin:0 0 8px}}
  h1{{font-size:clamp(22px,4vw,30px);margin:0;font-weight:800;letter-spacing:-.01em}}
  .sub{{color:var(--faint);font-size:13px;margin-top:8px;display:flex;gap:10px;
    flex-wrap:wrap;align-items:center}}
  .demo-badge{{background:var(--accent-soft);color:var(--accent);font-weight:700;
    font-size:11px;padding:3px 9px;border-radius:999px;letter-spacing:.04em}}
  h2{{font-size:16px;margin:32px 0 14px;font-weight:800;display:flex;
    align-items:center;gap:8px}}
  h2::before{{content:"";width:4px;height:16px;background:var(--accent);
    border-radius:2px;display:inline-block}}
  .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
  @media(max-width:640px){{.kpis{{grid-template-columns:repeat(2,1fr)}}}}
  .kpi{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:16px}}
  .kpi-label{{font-size:12px;color:var(--faint)}}
  .kpi-val{{font-size:28px;font-weight:800;color:var(--accent);
    font-variant-numeric:tabular-nums;line-height:1.2;margin-top:4px}}
  .delta{{font-size:12px;font-weight:700;margin-top:4px;display:inline-block}}
  .delta.up{{color:var(--good)}} .delta.down{{color:var(--crit)}}
  .delta.flat{{color:var(--faint)}} .muted{{color:var(--faint);font-weight:400}}
  .card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    overflow:hidden}}
  table{{border-collapse:collapse;width:100%;font-size:14px}}
  th,td{{text-align:left;padding:11px 16px;border-bottom:1px solid var(--line)}}
  th{{background:var(--surface2);font-size:12px;font-weight:700;color:var(--soft)}}
  tr:last-child td{{border-bottom:none}}
  td.num{{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}}
  .bar{{background:var(--surface2);border-radius:5px;height:8px;width:120px;
    overflow:hidden}}
  .bar span{{display:block;height:100%;background:var(--accent)}}
  .pill{{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px}}
  .pill.hot{{background:#fbe6e0;color:var(--crit)}}
  .pill.ok{{background:var(--accent-soft);color:var(--accent)}}
  @media(prefers-color-scheme:dark){{.pill.hot{{background:#3a2320}}}}
  .badge{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;
    background:var(--surface2);color:var(--soft)}}
  .badge.t-comparison{{background:var(--accent-soft);color:var(--accent)}}
  .badge.t-review{{background:#f6ead2;color:var(--warn)}}
  .task{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:16px 18px;margin-bottom:12px}}
  .task-h{{font-weight:700;display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .rank-badge{{background:var(--accent);color:#fff;width:22px;height:22px;
    border-radius:6px;display:grid;place-items:center;font-size:12px;flex:none}}
  .task ul{{list-style:none;margin:0;padding:0;display:grid;gap:7px}}
  .task li{{font-size:13.5px;color:var(--soft);padding-left:2px}}
  .atype{{font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:4px;
    margin-right:8px;text-transform:uppercase}}
  .a-content{{background:var(--accent-soft);color:var(--accent)}}
  .a-third_party{{background:#f6ead2;color:var(--warn)}}
  .a-freshness{{background:var(--surface2);color:var(--faint)}}
  footer{{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
    font-size:12px;color:var(--faint)}}
</style>
<div class="wrap">
  <header>
    <p class="eyebrow">AI検索 可視化レポート</p>
    <h1>{name}</h1>
    <div class="sub"><span class="demo-badge">DEMO ACCOUNT</span>
      <span>計測日 {date}</span>
      <span>ChatGPT / Gemini / Perplexity / Claude を横断計測</span></div>
  </header>

  <div class="kpis">{kpis}</div>

  <h2>優先ギャップ(競合は出るが自社が出ない質問)</h2>
  <div class="card"><table>
    <thead><tr><th>質問</th><th class="num">言及率</th>
      <th>機会スコア</th><th>状態</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table></div>

  <h2>引用元ターゲット(AIが引用=載るべき場所)</h2>
  <div class="card"><table>
    <thead><tr><th>種別</th><th>ドメイン</th><th class="num">引用回数</th></tr></thead>
    <tbody>{dom_rows}</tbody>
  </table></div>

  <h2>改善バックログ(優先質問ごとの推奨アクション)</h2>
  {backlog}

  <footer>本ダッシュボードはデモ用の作り込みデータです。実データでは各AIへの
  実計測結果が入ります。改善アクションはたたき台であり、最終判断は担当者が行います。</footer>
</div>
"""


def main():
    ap = argparse.ArgumentParser(description="LLMOダッシュボード生成")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--name", default="デモ社")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"DBが見つかりません: {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = connect(args.db)
    snaps = snapshots(conn)
    if not snaps:
        print("データがありません。", file=sys.stderr)
        sys.exit(1)
    cur = snaps[0]
    prev = snaps[1] if len(snaps) > 1 else None
    html_out = build_html(
        args.name, cur, prev,
        mention_rate(conn, cur),
        mention_rate(conn, prev) if prev else None,
        avg_rank(conn, cur), domains(conn, cur), gaps(conn, cur), conn,
    )
    conn.close()

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"ダッシュボードを生成: {args.out}")


if __name__ == "__main__":
    main()
