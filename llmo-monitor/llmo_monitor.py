#!/usr/bin/env python3
"""
llmo_monitor.py — AI検索(LLMO)での自社言及モニタリング 最小ツール

やること(フェーズ1のエンジン部分):
  1. config.json に登録した「監視したい質問」を読み込む
  2. その質問を各AI(OpenAI / Gemini / Perplexity / Anthropic)に投げる
  3. 返ってきた回答に自社(や競合)が登場するかを判定する
  4. 順位・シェア・引用ソースを解析して CSV に追記する

設計方針:
  - 依存ライブラリなし(Python標準ライブラリだけ)。pip install 不要。
  - APIキーが無いエンジンは自動でスキップ。1つも無ければ --mock で動作確認できる。
  - 回答は毎回ゆらぐので runs_per_query 回まわして「傾向」で見る。

使い方:
  python3 llmo_monitor.py --mock            # キー不要。仕組みの体験用
  python3 llmo_monitor.py                    # config.json のキーがあるエンジンで実行
  python3 llmo_monitor.py --config my.json   # 別の設定ファイルを使う

APIキーは環境変数で渡す(コードには絶対に書かない):
  export OPENAI_API_KEY=...
  export GEMINI_API_KEY=...
  export PERPLEXITY_API_KEY=...
  export ANTHROPIC_API_KEY=...
"""

import argparse
import csv
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# HTTP ヘルパー(標準ライブラリだけで POST する)
# ---------------------------------------------------------------------------

def _post_json(url, headers, payload, timeout=90):
    """JSON を POST してレスポンスを dict で返す。失敗時は例外を投げる。"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _walk_strings(obj):
    """ネストした dict/list から文字列を全部拾う(URL抽出などの保険用)。"""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


# ---------------------------------------------------------------------------
# エンジンアダプタ
#   各関数は (answer_text, sources) を返す。
#   answer_text: AIの回答本文(str)
#   sources:     回答が引用した URL のリスト(list[str])
#   キーが無い/失敗した場合は None を返す(呼び出し側でスキップ)。
# ---------------------------------------------------------------------------

def engine_openai(prompt, cfg):
    """OpenAI Responses API + Web検索。LLMOでは"検索する"版が本命。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    model = cfg.get("openai_model", "gpt-4o")
    body = {
        "model": model,
        "input": prompt,
        "tools": [{"type": "web_search"}],
    }
    try:
        r = _post_json(
            "https://api.openai.com/v1/responses",
            {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            body,
        )
    except Exception as e:
        print(f"  [openai] error: {e}", file=sys.stderr)
        return None

    # Responses API: output[] の中の message.content[].text を集める
    text_parts, sources = [], []
    for item in r.get("output", []):
        for block in item.get("content", []) or []:
            if block.get("type") in ("output_text", "text"):
                text_parts.append(block.get("text", ""))
                for ann in block.get("annotations", []) or []:
                    if ann.get("url"):
                        sources.append(ann["url"])
    text = "\n".join(text_parts) or r.get("output_text", "")
    return text, sources


def engine_perplexity(prompt, cfg):
    """Perplexity(検索ネイティブ)。LLMOと相性が良い。"""
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None
    model = cfg.get("perplexity_model", "sonar")
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        r = _post_json(
            "https://api.perplexity.ai/chat/completions",
            {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            body,
        )
    except Exception as e:
        print(f"  [perplexity] error: {e}", file=sys.stderr)
        return None

    text = r.get("choices", [{}])[0].get("message", {}).get("content", "")
    sources = list(r.get("citations", []) or [])
    if not sources:  # 新形式 search_results への保険
        for sr in r.get("search_results", []) or []:
            if sr.get("url"):
                sources.append(sr["url"])
    return text, sources


def engine_gemini(prompt, cfg):
    """Google Gemini + Google検索グラウンディング。"""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    model = cfg.get("gemini_model", "gemini-2.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }
    try:
        r = _post_json(url, {"Content-Type": "application/json"}, body)
    except Exception as e:
        print(f"  [gemini] error: {e}", file=sys.stderr)
        return None

    cand = (r.get("candidates") or [{}])[0]
    text = "".join(
        p.get("text", "") for p in cand.get("content", {}).get("parts", []) or []
    )
    sources = []
    for chunk in cand.get("groundingMetadata", {}).get("groundingChunks", []) or []:
        uri = chunk.get("web", {}).get("uri")
        if uri:
            sources.append(uri)
    return text, sources


def engine_anthropic(prompt, cfg):
    """Anthropic Claude + Web検索ツール。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = cfg.get("anthropic_model", "claude-opus-4-8")
    body = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search_20260209", "name": "web_search"}],
    }
    try:
        r = _post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            body,
        )
    except Exception as e:
        print(f"  [anthropic] error: {e}", file=sys.stderr)
        return None

    text_parts, sources = [], []
    for block in r.get("content", []) or []:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        # 検索結果ブロックから引用元URLを拾う
        if block.get("type") == "web_search_tool_result":
            for item in block.get("content", []) or []:
                if isinstance(item, dict) and item.get("url"):
                    sources.append(item["url"])
    return "\n".join(text_parts), sources


def engine_mock(prompt, cfg):
    """キー不要のダミー。仕組みの体験・動作確認用。"""
    target = cfg["target"]["name"]
    competitors = cfg.get("competitors", [])
    # プロンプトに応じてそれっぽい回答を組み立てる(半分の質問で自社に言及)
    mentions_target = (len(prompt) % 2 == 0)
    parts = ["この分野でよく名前が挙がるのは次のとおりです。"]
    listed = list(competitors[:2])
    if mentions_target:
        listed.insert(1, target)
    for i, name in enumerate(listed, 1):
        parts.append(f"{i}. {name} — 実績があり評判も良い。")
    text = "\n".join(parts)
    sources = ["https://example.com/review", "https://example.com/compare"]
    return text, sources


ENGINES = {
    "openai": engine_openai,
    "perplexity": engine_perplexity,
    "gemini": engine_gemini,
    "anthropic": engine_anthropic,
    "mock": engine_mock,
}

# ---------------------------------------------------------------------------
# 解析ロジック(このツールの価値の中心)
# ---------------------------------------------------------------------------

def analyze(text, target, competitors):
    """
    回答テキストを解析する。
      mentioned    : 自社が登場したか(True/False)
      rank         : 自社が何番目に登場したか(1が最上位、0=登場せず)
      share        : 登場した「自社+競合」のうち自社が占める言及回数の割合
      competitors_seen: 登場した競合名のリスト
    """
    low = text.lower()

    def first_pos(names):
        """別名(エイリアス)を含めて、最初に出現した文字位置を返す。無ければ -1。"""
        best = -1
        for n in names:
            i = low.find(n.lower())
            if i != -1 and (best == -1 or i < best):
                best = i
        return best

    target_names = [target["name"]] + target.get("aliases", [])
    target_pos = first_pos(target_names)
    mentioned = target_pos != -1

    # 自社と各競合の出現位置を集めて順位を決める
    positions = []
    if mentioned:
        positions.append((target_pos, "__target__"))
    competitors_seen = []
    for comp in competitors:
        p = low.find(comp.lower())
        if p != -1:
            positions.append((p, comp))
            competitors_seen.append(comp)
    positions.sort()
    rank = 0
    for idx, (_, who) in enumerate(positions, 1):
        if who == "__target__":
            rank = idx
            break

    # シェア(言及回数ベース)。自社言及数 /(自社+競合の言及数合計)
    def count(names):
        return sum(low.count(n.lower()) for n in names)

    target_count = count(target_names)
    comp_count = sum(low.count(c.lower()) for c in competitors)
    denom = target_count + comp_count
    share = round(target_count / denom, 3) if denom else 0.0

    return {
        "mentioned": mentioned,
        "rank": rank,
        "share": share,
        "competitors_seen": competitors_seen,
    }


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def run(config_path, force_mock, out_path):
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)

    target = cfg["target"]
    competitors = cfg.get("competitors", [])
    queries = cfg["queries"]
    runs = int(cfg.get("runs_per_query", 1))

    # 使うエンジンを決める
    if force_mock:
        engines = ["mock"]
    else:
        engines = [e for e in cfg.get("engines", []) if e in ENGINES]
        # キーが1つも無ければ mock にフォールバック
        available = [e for e in engines if ENGINES[e](queries[0], cfg) is not None]
        if not available:
            print("APIキーが見つからないため mock モードで実行します "
                  "(--mock 相当)。", file=sys.stderr)
            engines = ["mock"]
        else:
            engines = available

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    print(f"監視対象: {target['name']} / 競合: {', '.join(competitors) or '(なし)'}")
    print(f"エンジン: {', '.join(engines)} / 質問数: {len(queries)} "
          f"/ 各{runs}回\n")

    for q in queries:
        for engine in engines:
            for run_no in range(1, runs + 1):
                result = ENGINES[engine](q, cfg)
                if result is None:
                    continue
                text, sources = result
                a = analyze(text, target, competitors)
                rows.append({
                    "timestamp": ts,
                    "engine": engine,
                    "query": q,
                    "run": run_no,
                    "mentioned": a["mentioned"],
                    "rank": a["rank"],
                    "share_of_voice": a["share"],
                    "competitors_seen": "|".join(a["competitors_seen"]),
                    "sources": "|".join(sources[:5]),
                })
                mark = "○" if a["mentioned"] else "×"
                rank = f"{a['rank']}位" if a["rank"] else "圏外"
                print(f"[{engine:10}] {mark} {rank}  「{q}」")

    # CSV へ追記(初回のみヘッダを書く)
    fields = ["timestamp", "engine", "query", "run", "mentioned",
              "rank", "share_of_voice", "competitors_seen", "sources"]
    write_header = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerows(rows)

    # サマリ
    total = len(rows)
    mentioned = sum(1 for r in rows if r["mentioned"])
    print(f"\n--- サマリ ---")
    print(f"計測数: {total} / 自社言及: {mentioned} "
          f"({round(100*mentioned/total) if total else 0}%)")
    print(f"結果を追記しました: {out_path}")


def main():
    ap = argparse.ArgumentParser(description="AI検索(LLMO)言及モニタリング")
    ap.add_argument("--config", default="config.json", help="設定ファイル")
    ap.add_argument("--mock", action="store_true",
                    help="APIキー不要のダミーモードで動かす")
    ap.add_argument("--out", default="results.csv", help="出力CSV")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print(f"設定ファイルが見つかりません: {args.config}\n"
              f"config.example.json をコピーして使ってください。", file=sys.stderr)
        sys.exit(1)
    run(args.config, args.mock, args.out)


if __name__ == "__main__":
    main()
