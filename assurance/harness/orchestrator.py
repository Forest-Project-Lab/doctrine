#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""観点別レーンのオーケストレーション（決定論・標準ライブラリのみ）。

「どういう時に・どの観点の評価が・何を見るか」の正本。遷移は外側の
決定論コードが判じ、LLM の気分で状態を変えない（ADR-115）。

三観点は冊子と一対一:
- stpa  … 事故候補と相互作用の創出。DISCOVER で発火。
- jerg  … 検証計画と客観的証拠。FORMALIZE（計画の審査）と VERIFY（証拠の審査）で発火。
- cast  … 失敗後の保証体系更新。FAIL・事象の記録を受けて CAST_ANALYSIS で発火。
横断の challenge は規範共通の独立批判で、DISCOVER の直後に必ず挟む。

このモジュールは帳簿と門番だけを持つ。SDK 呼び出しは各 CLI（抽出・煙試験・
今後の discover/challenge 実行器）が行う。
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, model_policy  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(LANE_DIR, "ledger", "catalogs")
INCIDENTS_PATH = os.path.join(LANE_DIR, "ledger", "incidents.json")

STATES = (
    "INGEST_NORMS",      # 冊子 → 検証原則カタログ（観点の弾込め）
    "MAP_COVERAGE",      # カタログ × doctrine 現状 → 網羅台帳（五値の割当）
    "DISCOVER",          # 失敗仮説の創出
    "CHALLENGE",         # 独立批判（構造化 JSON だけを受け取る）
    "FORMALIZE",         # scenario 化 + jerg レーンによる検証計画の審査
    "REPRODUCE_RED",     # 修正前 FAIL の再現
    "FIX",               # 最小修正（一度に一つ）
    "VERIFY",            # 独立検証 + jerg レーンによる証拠の審査
    "ATTACK_EVALUATOR",  # 保証機構自身への故障注入
    "CAST_ANALYSIS",     # 失敗・事象からの統制分析（cast レーン）
    "RECORD",            # 恒久化（限定列挙）
    "CURATE",            # 重複統合・archive・平時コンテキスト最小化
)

# 観点レーン。model 役割は model_policy が正本（ここでは役割名だけを持つ）。
LANES = {
    "stpa": {
        "book": "stpa", "role": "evaluation", "fires_on": ("DISCOVER",),
        "reads": "システム境界・seed 事実・STPA カタログ",
        "writes": "SCENARIO_SCHEMA の配列（UCA・相互作用・注入点）",
    },
    "jerg": {
        "book": "jerg", "role": "evaluation",
        "fires_on": ("MAP_COVERAGE", "FORMALIZE", "VERIFY"),
        "reads": "scenario/claim・検証計画・証拠の台帳・JERG カタログ",
        "writes": "検証計画の判定・証拠適合の判定（VERDICT_SCHEMA）",
    },
    "cast": {
        "book": "cast", "role": "evaluation", "fires_on": ("CAST_ANALYSIS",),
        "reads": "事象の記録・統制構造・CAST カタログ",
        "writes": "統制欠陥・先行指標・新 scenario 候補",
    },
    "challenge": {
        "book": None, "role": "evaluation", "fires_on": ("CHALLENGE",),
        "reads": "DISCOVER の構造化 JSON だけ（会話・弁明は構造上渡せない）",
        "writes": "VERDICT_SCHEMA（ACCEPT/REJECT/UNKNOWN）",
    },
    "degradation-probe": {
        "book": None, "role": "degradation-probe",
        "fires_on": ("ATTACK_EVALUATOR",),
        "reads": "evaluation と同一の入力",
        "writes": "弱い model での判定（意味の保持の差分測定にだけ使う）",
    },
}

# 遷移の正本。event が起きたら from_state から to_state へ。guard は前提条件。
TRANSITIONS = (
    {"event": "CATALOG_READY",    "from": "INGEST_NORMS",  "to": "MAP_COVERAGE",
     "guard": "catalog_exists"},
    {"event": "COVERAGE_MAPPED",  "from": "MAP_COVERAGE",  "to": "DISCOVER",
     "guard": None},
    {"event": "SCENARIOS_READY",  "from": "DISCOVER",      "to": "CHALLENGE",
     "guard": "schema_valid"},
    {"event": "CHALLENGE_DONE",   "from": "CHALLENGE",     "to": "FORMALIZE",
     "guard": "has_accepted_candidates"},
    {"event": "PLAN_APPROVED",    "from": "FORMALIZE",     "to": "REPRODUCE_RED",
     "guard": "oracle_observable"},
    {"event": "RED_CONFIRMED",    "from": "REPRODUCE_RED", "to": "FIX",
     "guard": "red_evidence_saved"},
    {"event": "RED_IMPOSSIBLE",   "from": "REPRODUCE_RED", "to": "RECORD",
     "guard": None},   # UNKNOWN として台帳へ（実装へ進まない）
    {"event": "FIX_APPLIED",      "from": "FIX",           "to": "VERIFY",
     "guard": "single_change"},
    {"event": "VERIFIED",         "from": "VERIFY",        "to": "ATTACK_EVALUATOR",
     "guard": "before_fail_after_pass"},
    {"event": "EVALUATOR_ATTACKED", "from": "ATTACK_EVALUATOR", "to": "RECORD",
     "guard": "attack_evidence_saved"},
    {"event": "INCIDENT",         "from": "*",             "to": "CAST_ANALYSIS",
     "guard": "incident_recorded"},   # 失敗はどの状態からでも CAST へ
    {"event": "CAST_DONE",        "from": "CAST_ANALYSIS", "to": "DISCOVER",
     "guard": "leading_indicators_defined"},
    {"event": "RECORDED",         "from": "RECORD",        "to": "CURATE",
     "guard": None},
    {"event": "CURATED",          "from": "CURATE",        "to": "DISCOVER",
     "guard": None},
)


def validate():
    """正本の自己検査。矛盾があれば文字列のリスト（試験が凍結する）。"""
    problems = []
    for name, lane in LANES.items():
        if lane["book"] is not None and lane["book"] not in books.BOOKS:
            problems.append("レーン %s が未知の冊子 %r を指す" % (name, lane["book"]))
        try:
            opts = model_policy.options_for(lane["role"])
            if lane["role"] == "evaluation":
                model_policy.assert_evaluation_floor(opts["model"], opts["effort"])
        except ValueError as exc:
            problems.append("レーン %s: %s" % (name, exc))
        for st in lane["fires_on"]:
            if st not in STATES:
                problems.append("レーン %s が未知の状態 %r で発火する" % (name, st))
    for tr in TRANSITIONS:
        if tr["from"] != "*" and tr["from"] not in STATES:
            problems.append("遷移 %s の from が未知: %s" % (tr["event"], tr["from"]))
        if tr["to"] not in STATES:
            problems.append("遷移 %s の to が未知: %s" % (tr["event"], tr["to"]))
    return problems


def catalog_status():
    """冊子ごとのカタログ状態（存在・原則数・費用・残チャンク推定は持たない）。"""
    out = {}
    for book_id in sorted(books.BOOKS):
        path = os.path.join(CATALOG_DIR, "%s-principles.json" % book_id)
        if not os.path.isfile(path):
            out[book_id] = {"status": "UNASSESSED", "reason": "カタログ未抽出"}
            continue
        try:
            with open(path, encoding="utf-8") as f:
                cat = json.load(f)
            out[book_id] = {
                "status": "PARTIAL" if cat.get("stopped") else "PRESENT",
                "principles": cat["totals"]["principles"],
                "rejected": cat["totals"]["rejected"],
                "cost_usd": cat["totals"]["cost_usd"],
                "chunks_done": len(cat["chunks"]),
            }
        except (OSError, ValueError, KeyError) as exc:
            out[book_id] = {"status": "UNKNOWN", "reason": str(exc)}
    return out


def coverage_status():
    """冊子ごとの網羅台帳の状態。骨組みの存在と割当の完了を区別する。

    骨組みだけが在る台帳は「MAP_COVERAGE 未実施」であって済みではない
    （事象 INC-006: 骨組みの存在を済みと読み、606 件が UNKNOWN のまま
    next_actions が空になった）。
    """
    out = {}
    for book_id in sorted(books.BOOKS):
        path = os.path.join(CATALOG_DIR, "%s-coverage.json" % book_id)
        if not os.path.isfile(path):
            out[book_id] = {"status": "UNASSESSED", "unknown": None, "total": 0}
            continue
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f).get("entries", [])
        except (OSError, ValueError) as exc:
            out[book_id] = {"status": "UNKNOWN", "reason": str(exc),
                            "unknown": None, "total": 0}
            continue
        unknown = sum(1 for e in entries if e.get("disposition") == "UNKNOWN")
        out[book_id] = {
            "status": "PARTIAL" if unknown else "MAPPED",
            "unknown": unknown,
            "total": len(entries),
        }
    return out


def load_incidents():
    if not os.path.isfile(INCIDENTS_PATH):
        return []
    with open(INCIDENTS_PATH, encoding="utf-8") as f:
        return json.load(f).get("incidents", [])


def next_actions():
    """決定論の「次にやること」。judgement を挟まない導出。"""
    actions = []
    cats = catalog_status()
    for book_id in ("jerg", "stpa", "cast"):   # 抽出の順序の正本(ADR-115)
        st = cats[book_id]["status"]
        if st == "UNASSESSED":
            actions.append("INGEST_NORMS: %s のカタログ抽出" % book_id)
        elif st == "PARTIAL":
            actions.append("INGEST_NORMS: %s の抽出再開" % book_id)
    for inc in load_incidents():
        if inc.get("cast_analysis") in (None, "pending"):
            actions.append("CAST_ANALYSIS: %s" % inc["id"])
    covs = coverage_status()
    for book_id in ("jerg", "stpa", "cast"):
        if cats[book_id]["status"] != "PRESENT":
            continue          # 抽出が済むまで台帳は立たない（上の行動が先）
        cov = covs[book_id]
        if cov["status"] == "UNASSESSED":
            actions.append("MAP_COVERAGE: %s の台帳骨組みの生成" % book_id)
        elif cov["status"] == "PARTIAL":
            actions.append("MAP_COVERAGE: %s の未割当 %d/%d 件"
                           % (book_id, cov["unknown"], cov["total"]))
        elif cov["status"] == "UNKNOWN":
            actions.append("MAP_COVERAGE: %s の台帳が読めない（%s）"
                           % (book_id, cov.get("reason")))
    if not actions:
        # 空は「やることが無い」と読める。反復の既定の入口を必ず示す
        # （CAST_DONE・CURATED の遷移先。INC-006）。
        actions.append("DISCOVER: 新しい失敗仮説の創出（前提はすべて充足）")
    return actions


def main(argv=None):
    cmd = (argv or sys.argv[1:] or ["status"])[0]
    if cmd == "validate":
        problems = validate()
        print(json.dumps({"problems": problems}, ensure_ascii=False, indent=2))
        return 0 if not problems else 2
    if cmd == "status":
        # 行動列だけでなく、それが導かれた根拠（未割当の件数）も必ず出す。
        # 短い行動列を「済んだ」と読ませない（INC-006 の統制欠陥）。
        print(json.dumps({
            "catalogs": catalog_status(),
            "coverage": coverage_status(),
            "incidents": [
                {"id": i["id"], "cast_analysis": i.get("cast_analysis")}
                for i in load_incidents()],
            "next_actions": next_actions(),
        }, ensure_ascii=False, indent=2))
        return 0
    print("usage: orchestrator.py [status|validate]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
