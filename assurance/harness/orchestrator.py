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
    "APPLY_FINDINGS",    # 事故分析の推奨の処遇決め（ADR-125）
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
    {"event": "CAST_DONE",        "from": "CAST_ANALYSIS", "to": "APPLY_FINDINGS",
     "guard": "leading_indicators_defined"},
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
    problems.extend(_validate_ledger_kinds())
    problems.extend(_validate_recommendation_status())
    return problems


def _validate_recommendation_status():
    """推奨の処遇の書き方の検査（ADR-125）。

    却下は理由を、機構化済みは証拠のポインタを必ず持つ。持たない処遇は
    「片づいた」と読めてしまうので、根拠なき PASS と同じ扱いで赤にする。
    """
    problems = []
    keys = {(r["incident_id"], r["index"]) for r in cast_recommendations()}
    for (incident_id, index), row in sorted(
            load_recommendation_status().items(), key=lambda kv: repr(kv[0])):
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
    "ATTACK_EVALUATOR", "FORMALIZE", "APPLY_FINDINGS",
})

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
    {"kind": "red/<事象 id>.json",
     "match": "red/*.json",
     "read_by": (),
     "why_not_read":
         "修正前 FAIL の証拠。これを読む段（REPRODUCE_RED・FIX・VERIFY）は"
         "WITHIN_CYCLE_STATES であり、帳簿だけからは指せないと ADR-120 で"
         "明記済み。証拠は反復の中で作られ、その反復の中で読まれる。"},
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
    """ISO の日付・時刻文字列の最大。先頭10文字（YYYY-MM-DD）で比べる。"""
    days = sorted(v[:10] for v in values if isinstance(v, str) and len(v) >= 10)
    return days[-1] if days else None


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
                seen.append(_max_date([e.get("assigned_at") for e in entries]))
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
    return _max_date([v for v in seen if v])


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

    書かれた処遇が無い推奨は、所有者判断が要ると分析が印した物なら owner、
    それ以外は pending（未着手）として扱う。既存の 146 件に移行の行を書かせない
    ための既定であって、「状態欄が無い」ことを黙認するのではない —— 既定の側も
    ここで明示している。
    """
    known = load_recommendation_status()
    buckets = {state: [] for state in RECOMMENDATION_STATES}
    for rec in cast_recommendations():
        row = known.get((rec["incident_id"], rec["index"]))
        state = (row or {}).get("state")
        if state not in RECOMMENDATION_STATES:
            state = "owner" if rec["owner_decision_required"] else "pending"
        item = dict(rec)
        item["state"] = state
        item["note"] = (row or {}).get("note")
        item["evidence_ref"] = (row or {}).get("evidence_ref")
        buckets[state].append(item)
    return buckets


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
                seen.append(json.load(f).get("date"))
        except (OSError, ValueError):
            continue
    return _max_date([v for v in seen if v])


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
        # 評価の結果としての UNKNOWN（割当済み）と、まだ評価していない項を分ける。
        # 混ぜると、判定不能と結論した項目を永久に引き直す「消えない行動」になる
        # （INC-006 と同型を、その修正の直後に持ち込みかけた）。
        #
        # 鍵の名は unmapped であって unassessed ではない。五値の UNASSESSED は
        # 「前提が欠けて評価できない」という**評価の結論**であり、割当済みである。
        # 同じ語で二つを数えると、一語に二つの意味を持たせる取り違え（INC-006・
        # INC-010 で二度起きた形）をこの帳簿自身が持つことになる。
        unmapped = sum(1 for e in entries if not e.get("assigned_at")
                       and e.get("disposition") == "UNKNOWN")
        out[book_id] = {
            "status": "PARTIAL" if unmapped else "MAPPED",
            "unmapped": unmapped,
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
    # 事故分析の推奨は、terminal な処遇に至るまで次の行動に挙がり続ける（ADR-125）。
    # 先頭の一件だけを名指しし、残りの件数も必ず添える —— 短い行動列を「済んだ」と
    # 読ませない（INC-006 の統制欠陥）。
    backlog = recommendation_backlog()
    pending = backlog["pending"]
    if pending:
        head = pending[0]
        actions.append(
            "APPLY_FINDINGS: %s の推奨#%d（%s）「%s」／未着手 %d 件・"
            "所有者判断待ち %d 件・処遇済み %d 件"
            % (head["incident_id"], head["index"], head["kind"],
               head["action"][:70], len(pending), len(backlog["owner"]),
               len(backlog["landed"]) + len(backlog["rejected"])))
    covs = coverage_status()
    for book_id in ("jerg", "stpa", "cast"):
        if cats[book_id]["status"] != "PRESENT":
            continue          # 抽出が済むまで台帳は立たない（上の行動が先）
        cov = covs[book_id]
        if cov["status"] == "UNASSESSED":
            actions.append("MAP_COVERAGE: %s の台帳骨組みの生成" % book_id)
        elif cov["status"] == "PARTIAL":
            actions.append("MAP_COVERAGE: %s の未評価 %d/%d 件（判定不能 %d 件は割当済み）"
                           % (book_id, cov["unmapped"], cov["total"],
                              cov["unknown"] - cov["unmapped"]))
        elif cov["status"] == "UNKNOWN":
            actions.append("MAP_COVERAGE: %s の台帳が読めない（%s）"
                           % (book_id, cov.get("reason")))
    # 評価機構自身への故障注入。評価器の成果物が証拠より新しければ、その評価器は
    # まだ攻撃されていない。AI の判定が「実際に欠陥を捕まえる」ことは、攻撃の証拠
    # でしか言えない（INC-012）。
    latest_output = evaluator_outputs_latest()
    latest_attack = attack_evidence_latest()
    if latest_output and (latest_attack is None or latest_attack < latest_output):
        actions.append(
            "ATTACK_EVALUATOR: 評価器の成果物(%s)が故障注入の証拠(%s)より新しい"
            % (latest_output, latest_attack or "無し"))

    if not actions:
        # 空は「やることが無い」と読める。反復の既定の入口を必ず示す
        # （CAST_DONE・CURATED の遷移先。INC-006）。
        scn = latest_scenarios()
        survivors = (scn or {}).get("survivors") or []
        if survivors:
            actions.append(
                "FORMALIZE: 批判を生き残った候補 %d 件の定式化（%s の創出。%s）"
                % (len(survivors), (scn or {}).get("date"),
                   ", ".join(survivors[:3])
                   + (" ほか" if len(survivors) > 3 else "")))
        else:
            actions.append("DISCOVER: 新しい失敗仮説の創出（前提はすべて充足）")
    return actions


def _recommendation_summary():
    """推奨の処遇の集計と、所有者へ渡す一覧。"""
    backlog = recommendation_backlog()
    return {
        "counts": {state: len(backlog[state]) for state in RECOMMENDATION_STATES},
        "owner_decisions": [
            {"incident_id": r["incident_id"], "index": r["index"],
             "kind": r["kind"], "action": r["action"]}
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
            # 所有者判断は報告のたびに思い出す物ではない。分析が印した物を
            # 正本が数えて出す（INC-016: 分析の中身が正本へ届いていなかった）。
            "recommendations": _recommendation_summary(),
        }, ensure_ascii=False, indent=2))
        return 0
    print("usage: orchestrator.py [status|validate]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
