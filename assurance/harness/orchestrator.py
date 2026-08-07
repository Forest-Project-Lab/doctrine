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
import fnmatch
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, model_policy, prompts  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(LANE_DIR, "ledger", "catalogs")
INCIDENTS_PATH = os.path.join(LANE_DIR, "ledger", "incidents.json")
ASSUMPTIONS_PATH = os.path.join(LANE_DIR, "ledger", "assumptions.json")

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
    "REVIEW_ASSUMPTION",  # 保証が寄りかかる想定の観測（ADR-126）
    "APPLY_FINDINGS",    # 事故分析の推奨の処遇決め（ADR-125）
    "RECORD",            # 恒久化（限定列挙）
    "CURATE",            # 重複統合・archive・平時コンテキスト最小化
)

# 観点レーン。model 役割は model_policy が正本（ここでは役割名だけを持つ）。
LANES = {
    "stpa": {
        "book": "stpa", "role": "evaluation",
        "fires_on": ("INGEST_NORMS", "DISCOVER"),
        "reads": "システム境界・seed 事実・STPA カタログ",
        "writes": "SCENARIO_SCHEMA の配列（UCA・相互作用・注入点）",
    },
    "jerg": {
        "book": "jerg", "role": "evaluation",
        "fires_on": ("INGEST_NORMS", "MAP_COVERAGE", "FORMALIZE", "VERIFY"),
        "reads": "scenario/claim・検証計画・証拠の台帳・JERG カタログ",
        "writes": "検証計画の判定・証拠適合の判定（VERDICT_SCHEMA）",
    },
    "cast": {
        "book": "cast", "role": "evaluation",
        "fires_on": ("INGEST_NORMS", "CAST_ANALYSIS"),
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
    {"event": "CAST_DONE",        "from": "CAST_ANALYSIS", "to": "APPLY_FINDINGS",
     "guard": "leading_indicators_defined"},
    {"event": "ASSUMPTION_BROKEN", "from": "REVIEW_ASSUMPTION",
     "to": "CAST_ANALYSIS", "guard": "incident_recorded"},
    {"event": "ASSUMPTION_HOLDS",  "from": "REVIEW_ASSUMPTION",
     "to": "APPLY_FINDINGS", "guard": None},
    {"event": "FINDINGS_TRIAGED", "from": "APPLY_FINDINGS", "to": "DISCOVER",
     "guard": "no_pending_recommendation"},
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
    problems.extend(_validate_firing_points())
    problems.extend(_validate_ledger_kinds())
    problems.extend(_validate_recommendation_status())
    problems.extend(_validate_assumptions())
    return problems


def _validate_recommendation_status(rows=None):
    """推奨の処遇の書き方の検査（ADR-125・ADR-127）。

    却下は理由を、機構化済みは証拠のポインタを、所有者判断は**類型**を必ず持つ。
    持たない処遇は「片づいた」と読めてしまうので、根拠なき PASS と同じ扱いで
    赤にする。類型を書けない所有者判断は所有者判断ではない。
    """
    problems = []
    keys = {(r["incident_id"], r["index"]) for r in cast_recommendations()}
    if rows is None:
        rows = load_recommendation_status()
    for (incident_id, index), row in sorted(
            rows.items(), key=lambda kv: repr(kv[0])):
        state = row.get("state")
        where = "%s#%s" % (incident_id, index)
        if state not in RECOMMENDATION_STATES:
            problems.append("推奨 %s の処遇 %r が語彙に無い（%s）"
                            % (where, state, "/".join(RECOMMENDATION_STATES)))
            continue
        if (incident_id, index) not in keys:
            problems.append("推奨 %s の処遇が、存在しない推奨を指している" % where)
        if state == "rejected" and not (row.get("note") or "").strip():
            problems.append("推奨 %s の却下に理由が無い" % where)
        if state == "landed" and not (row.get("evidence_ref") or "").strip():
            problems.append("推奨 %s の『機構化済み』に証拠のポインタが無い" % where)
        if state == "owner":
            kind = (row.get("owner_decision_kind") or "").strip()
            if kind not in OWNER_DECISION_KINDS:
                problems.append(
                    "推奨 %s の『所有者判断』が類型を名指していない（%s のいずれか"
                    "を書くこと。当たらないなら所有者判断ではない）"
                    % (where, " / ".join(OWNER_DECISION_KINDS)))
    return problems


def _validate_assumptions(path=None, incident_ids=None):
    """想定の登記簿の書き方の検査（ADR-126）。

    想定は「何も検証していない前提」を名指しする物なので、検証者の欄が
    空であること自体は欠陥ではない。欠陥なのは、欄が**無い**ことである
    （沈黙は理由ではない）。先行指標の二条件は ADR-117 と同じ形にし、
    観測を書くなら日付と状態語彙を必ず添えさせる。
    """
    problems = []
    try:
        rows = load_assumptions(path)
    except (OSError, ValueError) as exc:
        return ["想定の登記簿が読めない: %s" % exc]
    if incident_ids is None:
        incident_ids = {i.get("id") for i in load_incidents()}
    seen = set()
    for row in rows:
        aid = row.get("id") or "(id 無し)"
        if aid in seen:
            problems.append("想定 %s の宣言が重複している" % aid)
        seen.add(aid)
        if "verified_by" not in row:
            problems.append(
                "想定 %s に verified_by の欄が無い（検証者が居ないなら null と"
                "明記すること。欄の不在は理由にならない）" % aid)
        indicators = row.get("leading_indicators") or []
        if not indicators:
            problems.append("想定 %s に先行指標が無い" % aid)
        for n, ind in enumerate(indicators):
            for key in ("observe_where", "abnormal_when"):
                if not (ind.get(key) or "").strip():
                    problems.append("想定 %s の先行指標#%d に %s が無い"
                                    % (aid, n, key))
            observed = _indicator_observation(ind)
            if observed is None:
                continue
            if not (ind.get("observed_at") or "").strip():
                problems.append("想定 %s の先行指標#%d の観測に日付が無い" % (aid, n))
            if observed not in ASSUMPTION_STATES:
                problems.append(
                    "想定 %s の先行指標#%d の状態 %r が語彙に無い（%s）"
                    % (aid, n, observed, "/".join(ASSUMPTION_STATES)))
        linked = row.get("incident_id")
        if linked and linked not in incident_ids:
            problems.append(
                "想定 %s が指す事象 %s が事象の列に無い" % (aid, linked))
    return problems


def _validate_ledger_kinds():
    """台帳の成果物種別の宣言と、実際に在る物との突合（ADR-124）。

    宣言の側（読む経路か読まない理由か・名が実在するか）と、台帳の側
    （宣言に当たらない物が在るか）の両方を見る。片側だけでは、宣言が
    実装から離れても、台帳に新種が増えても、どちらも赤にならない。
    """
    problems = []
    seen_kinds = set()
    for entry in LEDGER_KINDS:
        kind = entry["kind"]
        if kind in seen_kinds:
            problems.append("台帳種別 %s の宣言が重複している" % kind)
        seen_kinds.add(kind)
        read_by = entry.get("read_by") or ()
        why = entry.get("why_not_read")
        if bool(read_by) == bool(why):
            problems.append(
                "台帳種別 %s は、読取経路か読まない理由のちょうど一方を持つこと"
                "（今: 読取 %d 件・理由 %s）"
                % (kind, len(read_by), "有り" if why else "無し"))
        for fn_name in read_by:
            if not callable(globals().get(fn_name)):
                problems.append(
                    "台帳種別 %s の読取経路 %r が本モジュールに無い" % (kind, fn_name))
    for rel in undeclared_ledger_files():
        problems.append(
            "台帳に在るが種別が未宣言: %s（LEDGER_KINDS へ、読む経路か"
            "読まない理由のどちらかを明記すること）" % rel)
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


# next_actions が名指しできる状態と、できない状態。
#
# 「できない」を暗黙にしない。状態機械に在るのに一度も名指しされない状態は、
# 手で選ばない規律（ADR-115）の下では決して起きない —— ATTACK_EVALUATOR は
# 実際に5反復手つかずだった（事象 INC-012）。増やすときはどちらかへ明記する。
NAMEABLE_STATES = frozenset({
    "INGEST_NORMS", "MAP_COVERAGE", "CAST_ANALYSIS", "DISCOVER",
    "ATTACK_EVALUATOR", "FORMALIZE", "APPLY_FINDINGS", "REVIEW_ASSUMPTION",
})

# 名指しできる状態の優先順（ADR-131。所有者判断）。
#
# 正本は「手で選ばない・先頭から着手する・飛ばさない」を定める（ADR-115、
# 運転手順 §1）。**だから並びそのものが規範である** —— 並びが誤っていると、
# 規律を守る者ほど本丸へ着かない。かつては next_actions の append の順序が
# 事実上の優先順だった。それは表に書かれておらず、試験も無く、段を足すたびに
# 黙って変わる。実際 APPLY_FINDINGS（検証基盤の推奨 177 件）が MAP_COVERAGE
# （本丸の欠落 299 件）の前に立ち、推奨を消化しきるまで本丸へ着かない形に
# なっていた。
#
# 順の意味は「前提 → 前提の破れ → 測る対象 → 測る道具」である:
#   INGEST_NORMS      カタログが無ければ網羅台帳が立たない（他のすべての前提）
#   CAST_ANALYSIS     「なぜ見逃したか」を残す装置。動かさない
#   REVIEW_ASSUMPTION 想定が破れれば、そこに寄りかかる下流の PASS が根拠を失う
#   MAP_COVERAGE      本丸（Doctrine 本体）の欠落。**測る対象**
#   APPLY_FINDINGS    検証基盤の改善の推奨。**測る道具**の完成度
#   ATTACK_EVALUATOR  評価器自身への攻撃
#   FORMALIZE/DISCOVER 上のどれも鳴らないときの既定の入口（INC-006）
#
# 検証基盤は本丸を測るための道具であって、道具の完成度が目的ではない。
# 数の多い道具の推奨が、数の少ない本丸の欠落を永久に押しのける形を禁ずる。
ACTION_PRIORITY = {
    "INGEST_NORMS": 10,
    "CAST_ANALYSIS": 20,
    "REVIEW_ASSUMPTION": 30,
    "MAP_COVERAGE": 40,
    "APPLY_FINDINGS": 50,
    "ATTACK_EVALUATOR": 60,
    "FORMALIZE": 70,
    "DISCOVER": 80,
}

# 反復の中の遷移。直前の成果物が在って初めて意味を持つので、帳簿だけからは
# 名指しできない（DISCOVER が scenario を出して初めて CHALLENGE が立つ）。
# ここに置くことは「名指ししない」ことの明示であって、やらなくてよいという
# 意味ではない。反復の中で順に踏む。
WITHIN_CYCLE_STATES = frozenset({
    "CHALLENGE", "REPRODUCE_RED", "FIX", "VERIFY", "RECORD", "CURATE",
})

# 台帳に在る成果物の種別と、正本がそれを読む経路。
#
# 走らせ手（成果物を生む段）を足したのに、その成果を正本が読む段を足さないと、
# 同じ行動を毎回買い直す「消えない行動」になる。この形は INC-012・INC-015 で
# 同型が三度通った。一段ごとの受入試験は、その一段しか守らない。ここでは種別
# ごとに「読む関数の名」か「読まない理由」のどちらかを必ず持たせ、どちらも
# 持たない種別と、台帳に現れて match のどれにも当たらない物を禁ずる。
# 差集合が空でなければ赤（INC-015 の事故分析が定めた先行指標）。
#
# read_by は関数名の列。名は本モジュールの呼べる属性へ解決できなければならない
# （宣言が嘘をつけないようにする。ADR-124）。
LEDGER_KINDS = (
    {"kind": "catalogs/<book>-principles.json",
     "match": "catalogs/*-principles.json",
     "read_by": ("catalog_status", "evaluator_outputs_latest"),
     "why_not_read": None},
    {"kind": "catalogs/<book>-coverage.json",
     "match": "catalogs/*-coverage.json",
     "read_by": ("coverage_status", "evaluator_outputs_latest"),
     "why_not_read": None},
    {"kind": "incidents.json",
     "match": "incidents.json",
     "read_by": ("load_incidents",),
     "why_not_read": None},
    {"kind": "cast/<事象 id>.json",
     "match": "cast/*.json",
     "read_by": ("evaluator_outputs_latest",),
     "why_not_read": None},
    {"kind": "scenarios/<日付>.json",
     "match": "scenarios/*.json",
     "read_by": ("latest_scenarios",),
     "why_not_read": None},
    {"kind": "mutations-<日付>.json",
     "match": "mutations-*.json",
     "read_by": ("attack_evidence_latest",),
     "why_not_read": None},
    {"kind": "recommendation-status.json",
     "match": "recommendation-status.json",
     "read_by": ("load_recommendation_status",),
     "why_not_read": None},
    {"kind": "assumptions.json",
     "match": "assumptions.json",
     "read_by": ("load_assumptions", "assumption_backlog"),
     "why_not_read": None},
    {"kind": "red/<事象 id>.json",
     "match": "red/*.json",
     "read_by": (),
     "why_not_read":
         "修正前 FAIL の証拠。これを読む段（REPRODUCE_RED・FIX・VERIFY）は"
         "WITHIN_CYCLE_STATES であり、帳簿だけからは指せないと ADR-120 で"
         "明記済み。証拠は反復の中で作られ、その反復の中で読まれる。"},
    {"kind": "recheck-<日付>.json",
     "match": "recheck-*.json",
     "read_by": (),
     "why_not_read":
         "抜取りの独立再判定の記録。**行動に効く中身は既に台帳へ実体化して"
         "いる** —— 不一致の項は判定を取り下げて未割当の UNKNOWN へ戻すので、"
         "coverage_status が unmapped として数え、MAP_COVERAGE が拾い直す"
         "（_count_unmapped がその読む段である）。この記録自体は標本と判定の"
         "対の監査証跡であり、red/*.json と同じ位置にある。"
         "なお正本はまだ『前回の抜取りより後に評価器が動いたか』を見ていない"
         "—— ATTACK_EVALUATOR と同型の鮮度規則を置くかどうかは、優先順の表の"
         "書き換えに当たるので所有者判断とする（ADR-131）。"},
    {"kind": "runs/<実行 id>.json",
     "match": "runs/*.json",
     "read_by": (),
     "why_not_read":
         ".gitignore 対象の実行時生成物であり、選別を経ていない。正本が読むのは"
         "選別済みの証拠（台帳直下）だけとする。ここを読むと、コミットされない"
         "手元の残骸で次の行動が変わる。"},
    {"kind": "smoke-latest.json",
     "match": "smoke-latest.json",
     "read_by": (),
     "why_not_read":
         "配管確認（煙試験）の証拠。レーン前提の診断は doctor.py が毎反復持ち、"
         "次の行動を導く材料ではない。ただし『煙の証拠が harness の変更より"
         "古いことを正本が見るべきか』は未決の問いとして残る（ATTACK_EVALUATOR "
         "と同型になりうる）。決めるまでは読まない側に置く。"},
)


# 宣言された評価の発火点と、それを実際に走らせる手（ADR-128）。
#
# ADR-120 は状態の二分を、ADR-124 は台帳の成果物の二分を課した。どちらも
# 「在る物」を入力に走るので、走らせ手の無い段は成果物を生まず、台帳に欠落の
# 記録すら現れない。宣言された発火点と実行器の対応という**三面目**は、両者の
# 対象範囲の外にあった（INC-021）。
#
# 各発火点は「走らせ手の三点（実行器・prompt 組立関数・台帳の成果物種別）」を
# 持つか、「未実装である旨と理由」を持つかの、ちょうど一方に属する。表の鍵集合は
# すべてのレーンの fires_on の合併と一致しなければならない（両方向の差集合が空）
# —— 宣言だけの段も、宣言の無い実行器も許さない。逆向きの穴は実在した:
# INGEST_NORMS は実 opus セッションを走らせるのに、どの fires_on にも無かった。
FIRING_POINTS = {
    "INGEST_NORMS": {
        "runner": "extract_principles.py",
        "prompt_builders": ("build_extract_principles_prompt",),
        "ledger_kind": "catalogs/<book>-principles.json"},
    "MAP_COVERAGE": {
        "runner": "map_coverage.py",
        "prompt_builders": ("build_map_coverage_prompt",),
        "ledger_kind": "catalogs/<book>-coverage.json"},
    "DISCOVER": {
        "runner": "discover.py",
        "prompt_builders": ("build_discover_prompt",),
        "ledger_kind": "scenarios/<日付>.json"},
    "CHALLENGE": {
        "runner": "discover.py",
        "prompt_builders": ("build_challenge_prompt",),
        "ledger_kind": "scenarios/<日付>.json"},
    "CAST_ANALYSIS": {
        "runner": "cast_analysis.py",
        "prompt_builders": ("build_cast_analysis_prompt",),
        "ledger_kind": "cast/<事象 id>.json"},
    "ATTACK_EVALUATOR": {
        # 攻撃は既存の評価器へ故障を注入するので、自前の組み立て関数を持たない
        # （注入先の関数をそのまま使う。設計上の意図であって欠落ではない）。
        "runner": "attack_evaluator.py",
        "prompt_builders": ("build_map_coverage_prompt",
                            "build_cast_analysis_prompt"),
        "ledger_kind": "mutations-<日付>.json"},
    "FORMALIZE": {
        "unimplemented":
            "検証計画の審査（jerg）を走らせる実体が無い。schemas.py に成果物の"
            "スキーマだけが在り、prompt 組立関数も実行器も台帳の種別も無い。"
            "事象 INC-021 が持つ。実装するか、fires_on から外すかで消える。"},
    "VERIFY": {
        "unimplemented":
            "修正の正しさを別セッションが確かめる段の実体が無い。状態機械は"
            "FIX_APPLIED → VERIFY → ATTACK_EVALUATOR を持つが、踏む先が無いので"
            "実際には独立検証を経ずに抜けている。事象 INC-021 が持つ。"
            "なお実装しても得られるのはセッションの独立までで、独立した組織に"
            "よる検証（IV&V）にはならない（NONGOAL-001 第17項）。"},
}


def _validate_firing_points():
    """発火点の宣言と走らせ手の突合（ADR-128）。

    宣言の側（三点そろいか未実装の明記か・名が実在するか）と、レーンの側
    （fires_on との差集合）の両方を見る。片側だけでは、宣言が実装から離れても、
    実装だけが増えても、どちらも赤にならない（ADR-124 と同じ形）。
    """
    problems = []
    harness_dir = os.path.dirname(os.path.abspath(__file__))
    known_kinds = {e["kind"] for e in LEDGER_KINDS}
    for state, entry in sorted(FIRING_POINTS.items()):
        runner = entry.get("runner")
        why = entry.get("unimplemented")
        if bool(runner) == bool(why):
            problems.append(
                "発火点 %s は、走らせ手か未実装の明記のちょうど一方を持つこと"
                "（今: 走らせ手 %s・理由 %s）"
                % (state, "有り" if runner else "無し", "有り" if why else "無し"))
            continue
        if why:
            continue
        if not os.path.isfile(os.path.join(harness_dir, runner)):
            problems.append("発火点 %s の走らせ手 %r が harness/ に無い"
                            % (state, runner))
        for name in entry.get("prompt_builders") or ():
            if not callable(getattr(prompts, name, None)):
                problems.append("発火点 %s の組み立て関数 %r が prompts に無い"
                                % (state, name))
        kind = entry.get("ledger_kind")
        if kind not in known_kinds:
            problems.append("発火点 %s の成果物種別 %r が LEDGER_KINDS に無い"
                            % (state, kind))
    declared = set()
    for lane in LANES.values():
        declared.update(lane["fires_on"])
    for state in sorted(declared - set(FIRING_POINTS)):
        problems.append(
            "発火点 %s がレーンから宣言されているが FIRING_POINTS に無い" % state)
    for state in sorted(set(FIRING_POINTS) - declared):
        problems.append(
            "発火点 %s が FIRING_POINTS に在るが、どのレーンも宣言していない"
            % state)
    for state in sorted(set(FIRING_POINTS) - set(STATES)):
        problems.append("発火点 %s が状態機械に無い" % state)
    return problems


def _firing_point_summary():
    """発火点ごとの走らせ手の有無（ADR-128）。

    未実装の段は、次の行動には挙げない —— 是正は事象 INC-021 が持っており、
    二重に鳴らすとどちらを踏んでも消えない行動になる（ADR-126 と同じ判断）。
    その代わり status が必ず数えて出す。沈黙と区別が付かなければ、宣言だけが
    在って実体が無い形をもう一度繰り返す。
    """
    return {
        "total": len(FIRING_POINTS),
        "runnable": sorted(s for s, e in FIRING_POINTS.items() if e.get("runner")),
        "unimplemented": {
            s: e["unimplemented"]
            for s, e in sorted(FIRING_POINTS.items()) if e.get("unimplemented")},
        "tracked_by": "INC-021-lane-fires-on-declared-without-a-runner",
    }


def _ledger_dir():
    return os.path.join(LANE_DIR, "ledger")


def ledger_files(ledger_dir=None):
    """台帳に現在在る成果物の相対パス（POSIX 区切り・辞書順）。

    隠しファイルと隠しディレクトリは数えない（編集器の残骸は成果物ではない）。
    """
    root = ledger_dir or _ledger_dir()
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def ledger_kind_of(rel_path):
    """相対パスに当たる宣言。当たらなければ None。"""
    for entry in LEDGER_KINDS:
        if fnmatch.fnmatchcase(rel_path, entry["match"]):
            return entry
    return None


def undeclared_ledger_files(ledger_dir=None):
    """台帳に在るのに、どの種別の宣言にも当たらない成果物。

    「読む」でも「読まない理由」でもなく、そもそも宣言が無い状態を指す。
    これが空でない間は、正本の外に成果物が滞留しうる（INC-015）。
    """
    return [rel for rel in ledger_files(ledger_dir)
            if ledger_kind_of(rel) is None]


def _max_date(values):
    """ISO の日付・時刻文字列の最大。先頭10文字（YYYY-MM-DD）で比べる。

    日の粒度で足りるのは、人へ見せる表示だけである。**鮮度の判定には使わない**
    —— 同じ日の中の前後が消えるので、証拠より後に生まれた成果物を「済み」と
    読んでしまう（事象 INC-023）。判定は _max_instant を使う。
    """
    days = sorted(v[:10] for v in values if isinstance(v, str) and len(v) >= 10)
    return days[-1] if days else None


def _max_instant(values):
    """ISO の日付・時刻文字列の最大を、時刻を捨てずに返す。

    区切りの空白は T へ寄せてから比べる（"2026-08-06 23:00" と
    "2026-08-06T09:00" が文字の順序で逆転するため）。日付だけの値は
    その日の**始まり**として並ぶ —— これは安全側である。日付だけの証拠は
    その日の中で先か後かを示さないので、同じ日の成果物を覆ったと見なさない。
    """
    seen = sorted(v.replace(" ", "T", 1)
                  for v in values if isinstance(v, str) and len(v) >= 10)
    return seen[-1] if seen else None


def evaluator_outputs_latest():
    """評価器が最後に何かを出した日。無ければ None。

    対象は評価の成果物だけ（カタログ・事故分析・網羅の割当）。決定論試験や
    煙試験は評価ではないので数えない。
    """
    seen = []
    for book_id in sorted(books.BOOKS):
        for name, key in (("%s-principles.json" % book_id, "updated_at"),):
            path = os.path.join(CATALOG_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    seen.append(json.load(f).get(key))
            except (OSError, ValueError):
                continue
        cov_path = os.path.join(CATALOG_DIR, "%s-coverage.json" % book_id)
        if os.path.isfile(cov_path):
            try:
                with open(cov_path, encoding="utf-8") as f:
                    entries = json.load(f).get("entries", [])
                seen.append(_max_instant([e.get("assigned_at")
                                          for e in entries]))
            except (OSError, ValueError):
                pass
    cast_dir = os.path.join(LANE_DIR, "ledger", "cast")
    if os.path.isdir(cast_dir):
        for name in sorted(os.listdir(cast_dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(cast_dir, name), encoding="utf-8") as f:
                    seen.append(json.load(f).get("generated_at"))
            except (OSError, ValueError):
                continue
    return _max_instant([v for v in seen if v])


def latest_scenarios():
    """直近の創出と批判の記録。無ければ None。

    走らせ手を作っても、その成果を正本が見なければ同じ創出を毎回買い直す
    （INC-012 と同型。事象 INC-015）。生き残った候補が在るなら次は定式化であり、
    創出をもう一度挙げてはならない。
    """
    scn_dir = os.path.join(LANE_DIR, "ledger", "scenarios")
    if not os.path.isdir(scn_dir):
        return None
    names = sorted(n for n in os.listdir(scn_dir) if n.endswith(".json"))
    if not names:
        return None
    try:
        with open(os.path.join(scn_dir, names[-1]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# 推奨の処遇。terminal は landed / rejected / owner の三つ。
# owner が terminal なのは「レーンとしてはここで止まり、判断を仰ぐ」の意味であって、
# 片づいたという意味ではない（status は別項として所有者へ列挙する）。
RECOMMENDATION_STATES = ("pending", "landed", "rejected", "owner")
TERMINAL_RECOMMENDATION_STATES = frozenset({"landed", "rejected", "owner"})

# 所有者判断の類型（ADR-127）。所有者が運転手順 §7 に書いた六つをそのまま写す。
# レーンはこの表を増やさない —— 自分の自律の境界を自分で広げないため。
#
# 事故分析が付ける owner_decision_required は、所有者の権限についての判定ではなく
# **評価者の視野の申告**である。分析の入力は事象・統制構造・カタログだけで、統治木
# （確定事実・非目標・退行監視・ADR）は一つも渡っていない（`prompts.build_cast_
# analysis_prompt`）。何も決まっていない場所から見れば、すべてが未決に見える。
# 申告をそのまま権限の判定として読み替えるのは「検証できない申告を信じる」形であり、
# この体系が ADR-050・NONGOAL-001 第9・14・16項で三度「やらない」と決めている。
OWNER_DECISION_KINDS = (
    "互換性を壊す変更",
    "配布境界や保証範囲の変更",
    "復旧不能な削除",
    "外部費用や credential",
    "評価 model 最低線の引き下げ",
    "配布物の版番号の変更とリリース",
)


def cast_recommendations():
    """事故分析が出した推奨の全件。事象 id と番号で一意に指す。

    事故分析の記録は日付だけが読まれ、統制欠陥・先行指標・新規仮説・推奨は
    正本へ一度も入力されていなかった（INC-016。同型の四度目）。ADR-124 の
    不変条件は種別の粒度までしか見ず、この形を赤にできなかった。
    """
    out = []
    cast_dir = os.path.join(LANE_DIR, "ledger", "cast")
    if not os.path.isdir(cast_dir):
        return out
    for name in sorted(os.listdir(cast_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(cast_dir, name), encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        analysis = doc.get("analysis") or {}
        incident_id = analysis.get("incident_id") or doc.get("incident_id") or name
        for index, rec in enumerate(analysis.get("recommendations") or []):
            if not isinstance(rec, dict):
                continue
            out.append({
                "incident_id": incident_id,
                "index": index,
                "action": rec.get("action") or "",
                "kind": rec.get("kind") or "",
                "owner_decision_required": bool(rec.get("owner_decision_required")),
            })
    return out


def load_recommendation_status():
    """推奨の処遇の台帳。鍵は (事象 id, 番号)。無ければ空。"""
    path = os.path.join(LANE_DIR, "ledger", "recommendation-status.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f).get("dispositions", [])
    except (OSError, ValueError):
        return {}
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        out[(row.get("incident_id"), row.get("index"))] = row
    return out


def recommendation_backlog():
    """推奨を処遇ごとに分ける。

    書かれた処遇が無い推奨は、分析が何を印していようと pending（未着手）である
    （ADR-127）。かつては owner_decision_required の申告をそのまま owner の既定に
    していたが、その申告は所有者の権限についての判定ではなく評価者の視野の申告
    であり、45 件が誰にも読まれない棚へ既定で落ちていた。owner になるのは、処遇の
    行が明示的に state と**類型**を書いたときだけとする。
    """
    known = load_recommendation_status()
    buckets = {state: [] for state in RECOMMENDATION_STATES}
    for rec in cast_recommendations():
        row = known.get((rec["incident_id"], rec["index"]))
        state = (row or {}).get("state")
        if state not in RECOMMENDATION_STATES:
            state = "pending"
        item = dict(rec)
        item["state"] = state
        item["note"] = (row or {}).get("note")
        item["evidence_ref"] = (row or {}).get("evidence_ref")
        item["owner_decision_kind"] = (row or {}).get("owner_decision_kind")
        # 行が在れば「調べたうえで未着手」、無ければ「まだ調べていない」。
        # 一語で混ぜると、見ていない山を見た山と同じ顔で数えることになる
        # （INC-006・INC-010 で二度起きた、一語に二つの意味を持たせる取り違え）。
        item["examined"] = row is not None
        buckets[state].append(item)
    return buckets


def _split_pending(pending):
    """未着手を「調べた」と「まだ調べていない」に分ける。"""
    examined = [r for r in pending if r["examined"]]
    untouched = [r for r in pending if not r["examined"]]
    return examined, untouched


def attack_evidence_latest():
    """評価機構への故障注入の証拠の最新日。無ければ None。"""
    ledger = os.path.join(LANE_DIR, "ledger")
    if not os.path.isdir(ledger):
        return None
    seen = []
    for name in sorted(os.listdir(ledger)):
        if not (name.startswith("mutations-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(ledger, name), encoding="utf-8") as f:
                doc = json.load(f)
            # 時点が在ればそれを、無ければ日付を使う。日付だけの証拠はその日の
            # 始まりとして並び、同じ日の成果物を覆わない（安全側。INC-023）。
            seen.append(doc.get("generated_at") or doc.get("date"))
        except (OSError, ValueError):
            continue
    return _max_instant([v for v in seen if v])


_INDEX_SHA_CACHE = []


def current_index_sha():
    """現在の索引の指紋。走査は一度だけ行い、以後は使い回す。

    索引が覆うのは doctrine_docs と plugin/{scripts,tests,skills,hooks} で、
    assurance/ は含まれない。基盤だけを触る反復では指紋が動かないので、
    古びの判定が毎反復鳴る形にはならない（消えない行動を作らない）。
    """
    if not _INDEX_SHA_CACHE:
        try:
            from harness import system_index
            _INDEX_SHA_CACHE.append(system_index.build().get("sha256"))
        except Exception:            # 索引が組めない環境では古びを判じない
            _INDEX_SHA_CACHE.append(None)
    return _INDEX_SHA_CACHE[0]


# 判定が「済んだ」側の五値。ここに在る項は、索引が動いても評価を買い直さない
# —— 証拠ポインタの再照合は決定論でできるからである（ADR-118）。ただし数えて
# 出す。見ていないことにはしない。
_SETTLED_DISPOSITIONS = frozenset({"実装・試験・証拠あり", "非該当で理由あり"})


# 証拠ポインタの種別 → 索引の種別名。古びを「引いた範囲」に限るための対応表。
_POINTER_KIND_TO_CATEGORY = {
    "document": "documents",
    "audit_check": "audit_checks",
    "linter_code": "linter_codes",
    "hook_event": "hooks",
    "skill": "skills",
    "file": "scripts",
    "test": "test_files",
}

# 古びを次の行動に挙げる閾値（ADR-134。所有者判断 2026-08-07）。
#
# 一束（25 件）に満たない古びで評価を買い直すと、単価に対して割に合わない。
# 閾値未満でも**数えて出す** —— 挙げないことと隠すことは違う（INC-006）。
STALE_RAISE_THRESHOLD = 25


def should_raise_stale(count):
    """この件数の古びを next_actions に挙げるか（数えるのは常に行う）。"""
    return bool(count) and count >= STALE_RAISE_THRESHOLD


def is_stale(entry, index_now, resolve):
    """判定が古びているか。**引いた範囲**だけを見る（ADR-134）。

    index_now: {"category_sha256": {...}, "category_counts": {...}}
    resolve:   証拠ポインタ → 種別 or None（system_index.resolve_pointer の部分適用）

    規則は二つに分かれる:

    - **証拠を持つ判定**は、その証拠が属する種別が動いたときだけ古びる。
      文書を根拠にした判定は、試験が 1 件増えても古びない —— 主張の根拠は
      文書の側に在り、試験の側は主張に関わっていない（INC-025 の実害そのもの）。
    - **証拠を持たない非終端**（「その原則を果たす機構が索引に無い」という主張）は、
      種別が**増えた**ときだけ古びる。増えた物だけが「無い」を覆せるからである。
      並べ替えや削除で古びさせると、また全件が毎回古びる形へ戻る。

    種別の指紋を持たない古い記録は「どの索引に対する判定か判らない」として
    古い側へ倒す（ADR-130 第1項と同じ向き。判らないものは前提欠如の側へ）。
    """
    stamp = (entry.get("assigned_by") or {}).get("category_sha256")
    if not stamp:
        return True
    now = index_now.get("category_sha256") or {}
    moved = {name for name, sha in now.items() if stamp.get(name) != sha}
    if not moved:
        return False

    cited = set()
    for pointer in (entry.get("evidence") or []):
        kind = resolve(pointer)
        category = _POINTER_KIND_TO_CATEGORY.get(kind)
        if category:
            cited.add(category)
    if cited:
        return bool(cited & moved)

    # 証拠が無い（か、どれも解決しない）判定 —— 「無い」という主張である。
    before = (entry.get("assigned_by") or {}).get("category_counts") or {}
    after = index_now.get("category_counts") or {}
    if not before or not after:
        # 件数が判らなければ「増えたか」を判じられない。判らないものは
        # 古い側へ倒す（指紋を持たない記録と同じ向き。安全側）。
        return True
    return any(after.get(name, 0) > before.get(name, 0) for name in moved)


def _count_unmapped(cov):
    """まだ評価していない項の数。「未割当」の規則をここに一度だけ持つ。

    評価の結果としての UNKNOWN（割当済み）と、まだ評価していない項を分ける。
    混ぜると、判定不能と結論した項目を永久に引き直す「消えない行動」になる
    （INC-006 と同型）。

    鍵の名は unmapped であって unassessed ではない。五値の UNASSESSED は
    「前提が欠けて評価できない」という**評価の結論**であり、割当済みである。
    同じ語で二つを数えると、一語に二つの意味を持たせる取り違え（INC-006・
    INC-010 で二度起きた形）をこの帳簿自身が持つことになる。

    独立再判定が判定を取り下げた項（`independent_recheck.withdraw`）も、
    assigned_at を落とすのでここに数えられる —— それが「取り下げを正本が
    読む段」である（走らせ手だけを足さない。INC-012・INC-015）。
    """
    return sum(1 for e in cov.get("entries", [])
               if not e.get("assigned_at") and e.get("disposition") == "UNKNOWN")


_INDEX_NOW_CACHE = []


def _index_now(index_sha=None):
    """古びの判定に使う「いまの索引」の指紋一式。組めなければ None。

    index_sha を渡されたときは、その値を全種別の指紋として扱う（試験が
    古びを人為的に起こすための口。ADR-130 からの互換）。
    """
    if index_sha is not None:
        return {"category_sha256": {k: index_sha for k in
                                    _POINTER_KIND_TO_CATEGORY.values()},
                "category_counts": {}}
    if not _INDEX_NOW_CACHE:
        try:
            from harness import system_index
            idx = system_index.build()
            _INDEX_NOW_CACHE.append(
                {"category_sha256": idx["category_sha256"],
                 "category_counts": idx["category_counts"],
                 "_idx": idx})
        except Exception:            # 索引が組めない環境では古びを判じない
            _INDEX_NOW_CACHE.append(None)
    return _INDEX_NOW_CACHE[0]


def _pointer_resolver():
    """証拠ポインタ → 種別。索引が組めない環境では常に None を返す。"""
    now = _index_now()
    idx = (now or {}).get("_idx")
    if idx is None:
        return lambda p: None
    from harness import system_index
    return lambda p: system_index.resolve_pointer(idx, p)


def coverage_status(index_sha=None):
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
        # 評価の結果としての UNKNOWN（割当済み）と、まだ評価していない項を分ける。
        # 混ぜると、判定不能と結論した項目を永久に引き直す「消えない行動」になる
        # （INC-006 と同型を、その修正の直後に持ち込みかけた）。
        #
        # 鍵の名は unmapped であって unassessed ではない。五値の UNASSESSED は
        # 「前提が欠けて評価できない」という**評価の結論**であり、割当済みである。
        # 同じ語で二つを数えると、一語に二つの意味を持たせる取り違え（INC-006・
        # INC-010 で二度起きた形）をこの帳簿自身が持つことになる。
        unmapped = _count_unmapped({"entries": entries})
        # 古びは**引いた範囲**だけで見る（ADR-134。INC-025 の是正）。
        # 索引全体の指紋で見ると、関係の無い変更が全件を古びさせる ——
        # 実測で試験ファイル 1 件の追加が非終端 286 件を古びさせた。
        # 指紋を持たない項は「どの索引に対する判定か判らない」ので古い側へ倒す。
        now = _index_now(index_sha)
        stale_open = stale_settled = 0
        if now:
            resolve = _pointer_resolver()
            for e in entries:
                if not e.get("assigned_at"):
                    continue
                if not is_stale(e, now, resolve):
                    continue
                if e.get("disposition") in _SETTLED_DISPOSITIONS:
                    stale_settled += 1
                else:
                    stale_open += 1
        out[book_id] = {
            "status": "PARTIAL" if unmapped else "MAPPED",
            "unmapped": unmapped,
            "unknown": unknown,
            "stale_open": stale_open,
            "stale_settled": stale_settled,
            "total": len(entries),
        }
    return out


def load_incidents():
    if not os.path.isfile(INCIDENTS_PATH):
        return []
    with open(INCIDENTS_PATH, encoding="utf-8") as f:
        return json.load(f).get("incidents", [])


# 想定の観測に使える状態語彙。運転手順 §5 の六語をそのまま使う。
# 根拠なき PASS を書かせないための語彙であって、ここで語を増やさない。
ASSUMPTION_STATES = (
    "PASS", "FAIL", "UNKNOWN", "UNASSESSED", "DEGRADED", "NOT-APPLICABLE",
)


def load_assumptions(path=None):
    """保証が寄りかかる想定の登記簿（ADR-126）。無ければ空。

    読めない台帳は空ではない。ここでは例外を投げ、validate が UNKNOWN と
    して赤にする（読めないものを『在るが空』と読み替えない）。
    """
    path = path or ASSUMPTIONS_PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = json.load(f).get("assumptions", [])
    return [r for r in rows if isinstance(r, dict)]


def _indicator_observation(indicator):
    """先行指標に観測が書かれていれば状態を返す。無ければ None。

    観測の有無は state 欄の有無で判ずる。observation の自由文だけが在って
    state が無い物は「観測していない」ではなく「書き方が不備」なので、
    validate の側が拾う（ここでは None を返さず生の値を返す）。
    """
    if "state" not in indicator:
        return None
    return indicator.get("state")


def assumption_backlog(path=None):
    """手当てが要る想定。理由は「未観測」と「破れている」の二つだけ。

    破れた想定に対応する事象 id が在るなら、ここでは鳴らさない。是正は
    事象の側（CAST_ANALYSIS と推奨の処遇）が持っており、二重に鳴らすと
    どちらを踏んでも消えない行動になる。
    """
    out = []
    try:
        rows = load_assumptions(path)
    except (OSError, ValueError):
        return out
    for row in rows:
        aid = row.get("id") or "(id 無し)"
        indicators = row.get("leading_indicators") or []
        observed = [_indicator_observation(i) for i in indicators]
        observed = [s for s in observed if s is not None]
        if not observed:
            out.append({"id": aid, "reason": "未観測",
                        "detail": "先行指標 %d 件のどれも観測されていない"
                                  % len(indicators)})
            continue
        broken = [s for s in observed if s != "PASS"]
        if broken and not row.get("incident_id"):
            out.append({"id": aid, "reason": "破れている",
                        "detail": "PASS でない観測 %d 件（%s）に対応する事象が"
                                  "立っていない" % (len(broken),
                                                    "・".join(sorted(set(broken))))})
    return out


def next_actions(index_sha=None):
    """決定論の「次にやること」。judgement を挟まない導出。

    並びは append の順ではなく ACTION_PRIORITY が決める（ADR-131）。append の
    順を事実上の優先順にすると、段を足すたびに黙って変わり、どこにも書かれず、
    試験も効かない。ここでは (優先順, 発生順) の対で安定に並べ替える —— 同じ
    状態の中の順序（三冊の jerg→stpa→cast など）は発生順のまま保たれる。
    """
    actions = []

    def add(text):
        # 状態名は必ず ACTION_PRIORITY に載っていること。載らない状態は
        # 並びの中で自分の位置を主張できず、黙って末尾へ落ちる（INC-012 の形）。
        state = text.split(":", 1)[0]
        actions.append((ACTION_PRIORITY[state], len(actions), text))

    cats = catalog_status()
    for book_id in ("jerg", "stpa", "cast"):   # 抽出の順序の正本(ADR-115)
        st = cats[book_id]["status"]
        if st == "UNASSESSED":
            add("INGEST_NORMS: %s のカタログ抽出" % book_id)
        elif st == "PARTIAL":
            add("INGEST_NORMS: %s の抽出再開" % book_id)
    for inc in load_incidents():
        if inc.get("cast_analysis") in (None, "pending"):
            add("CAST_ANALYSIS: %s" % inc["id"])
    # 想定は保証の前提であって成果物ではない。前提が破れていれば、その前提に
    # 寄りかかる下流の PASS はすべて根拠を失う。だから推奨の山より前に置く
    # （後ろに置くと 100 件超の推奨の陰に隠れ、ATTACK_EVALUATOR が5反復飛ばされた
    # のと同じ形になる。INC-012）。一段で片づけられる —— 観測するか、事象を
    # 立てるかのどちらかで消える。
    for row in assumption_backlog():
        add("REVIEW_ASSUMPTION: %s が%s（%s）"
                       % (row["id"], row["reason"], row["detail"]))
    # 事故分析の推奨は、terminal な処遇に至るまで次の行動に挙がり続ける（ADR-125）。
    # 先頭の一件だけを名指しし、残りの件数も必ず添える —— 短い行動列を「済んだ」と
    # 読ませない（INC-006 の統制欠陥）。
    backlog = recommendation_backlog()
    pending = backlog["pending"]
    if pending:
        # まだ調べていない物を先に挙げる。見ていない山の中身は優先順を付けられない。
        examined, untouched = _split_pending(pending)
        head = (untouched or examined)[0]
        add(
            "APPLY_FINDINGS: %s の推奨#%d（%s）「%s」／未調査 %d 件・"
            "調査済み未着手 %d 件・所有者判断待ち %d 件・処遇済み %d 件"
            % (head["incident_id"], head["index"], head["kind"],
               head["action"][:70], len(untouched), len(examined),
               len(backlog["owner"]),
               len(backlog["landed"]) + len(backlog["rejected"])))
    covs = coverage_status(index_sha=index_sha)
    for book_id in ("jerg", "stpa", "cast"):
        if cats[book_id]["status"] != "PRESENT":
            continue          # 抽出が済むまで台帳は立たない（上の行動が先）
        cov = covs[book_id]
        if cov["status"] == "UNASSESSED":
            add("MAP_COVERAGE: %s の台帳骨組みの生成" % book_id)
        elif cov["status"] == "PARTIAL":
            add("MAP_COVERAGE: %s の未評価 %d/%d 件（判定不能 %d 件は割当済み）"
                           % (book_id, cov["unmapped"], cov["total"],
                              cov["unknown"] - cov["unmapped"]))
        elif cov["status"] == "UNKNOWN":
            add("MAP_COVERAGE: %s の台帳が読めない（%s）"
                           % (book_id, cov.get("reason")))
        # 索引が動いた後の非終端の項は、評価を買い直さないと解けない。
        # 終端の項の古びは数えるだけ（決定論の再照合で足りる。ADR-130）。
        # 閾値に達するまで挙げない（ADR-134）。**数えるのは常に行う** ——
        # 挙げないことと隠すことは違う（INC-006）。件数は status に出続ける。
        if should_raise_stale(cov.get("stale_open") or 0):
            add(
                "MAP_COVERAGE: %s の索引が動いた後で再判定していない %d 件"
                "（終端の再照合待ちは別に %d 件）"
                % (book_id, cov["stale_open"], cov.get("stale_settled") or 0))
    # 評価機構自身への故障注入。評価器の成果物が証拠より新しければ、その評価器は
    # まだ攻撃されていない。AI の判定が「実際に欠陥を捕まえる」ことは、攻撃の証拠
    # でしか言えない（INC-012）。
    latest_output = evaluator_outputs_latest()
    latest_attack = attack_evidence_latest()
    if latest_output and (latest_attack is None or latest_attack < latest_output):
        add(
            "ATTACK_EVALUATOR: 評価器の成果物(%s)が故障注入の証拠(%s)より新しい"
            % (latest_output, latest_attack or "無し"))

    if not actions:
        # 空は「やることが無い」と読める。反復の既定の入口を必ず示す
        # （CAST_DONE・CURATED の遷移先。INC-006）。
        scn = latest_scenarios()
        survivors = (scn or {}).get("survivors") or []
        if survivors:
            add(
                "FORMALIZE: 批判を生き残った候補 %d 件の定式化（%s の創出。%s）"
                % (len(survivors), (scn or {}).get("date"),
                   ", ".join(survivors[:3])
                   + (" ほか" if len(survivors) > 3 else "")))
        else:
            add("DISCOVER: 新しい失敗仮説の創出（前提はすべて充足）")
    # (優先順, 発生順) の対で安定に並べ替える。同じ状態の中の順序
    # （三冊の jerg→stpa→cast など）は発生順のまま保たれる。
    return [text for _, _, text in sorted(actions)]


def _assumption_summary():
    """想定ごとの最新の観測と、手当てが要る物の一覧（ADR-126）。"""
    try:
        rows = load_assumptions()
    except (OSError, ValueError) as exc:
        return {"status": "UNKNOWN", "reason": str(exc)}
    needs = {r["id"]: r for r in assumption_backlog()}
    out = []
    for row in rows:
        states = [_indicator_observation(i)
                  for i in row.get("leading_indicators") or []]
        aid = row.get("id")
        out.append({
            "id": aid,
            "assumption": row.get("assumption"),
            "states": [s for s in states if s is not None],
            "incident_id": row.get("incident_id"),
            "needs_action": needs.get(aid, {}).get("reason"),
        })
    return {"status": "READ", "total": len(out),
            "needs_action": len(needs), "entries": out}


def _recommendation_summary():
    """推奨の処遇の集計と、所有者へ渡す一覧。"""
    backlog = recommendation_backlog()
    examined, untouched = _split_pending(backlog["pending"])
    return {
        "counts": {state: len(backlog[state]) for state in RECOMMENDATION_STATES},
        "pending_examined": len(examined),
        "pending_untouched": len(untouched),
        # 評価者の**申告**と、類型の照合を通って**成立**した所有者判断を分けて
        # 数える。一語に二つの意味を持たせない（INC-006・INC-010・INC-018 と同型）。
        # 申告の側を消さないのは、視野の狭さ自体が観測対象だからである。
        "evaluator_claimed_owner": sum(
            1 for r in cast_recommendations() if r["owner_decision_required"]),
        "owner_decisions": [
            {"incident_id": r["incident_id"], "index": r["index"],
             "kind": r["kind"], "owner_decision_kind": r["owner_decision_kind"],
             "action": r["action"]}
            for r in backlog["owner"]],
    }


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
            # 想定は、次の行動に挙がらないときも必ず数えて出す。挙がらない
            # のは「事象として立っている」か「観測が PASS」のどちらかであり、
            # 沈黙と区別が付かなければ登記簿は在っても読まれていないのと同じ
            # （ADR-124 の粒度が種別までしか見なかった形。INC-016）。
            "assumptions": _assumption_summary(),
            # 走らせ手を持たない発火点も必ず数えて出す（ADR-128）。次の行動に
            # 挙げないのは事象 INC-021 が是正を持っているからで、沈黙して
            # よいからではない。
            "firing_points": _firing_point_summary(),
            # 所有者判断は報告のたびに思い出す物ではない。分析が印した物を
            # 正本が数えて出す（INC-016: 分析の中身が正本へ届いていなかった）。
            "recommendations": _recommendation_summary(),
        }, ensure_ascii=False, indent=2))
        return 0
    print("usage: orchestrator.py [status|validate]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
