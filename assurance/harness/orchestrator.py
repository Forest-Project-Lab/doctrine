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
import glob
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, ledger_io, model_policy, prompts  # noqa: E402

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
    problems.extend(_validate_verify_refs())
    problems.extend(_validate_incident_evidence())
    problems.extend(_validate_closure_vocabulary())
    problems.extend(_validate_coverage_merges())
    problems.extend(_validate_ledger_readability())
    problems.extend(_validate_nameable_states())
    problems.extend(_validate_shipped_conditions())
    problems.extend(_validate_owner_overrides())
    problems.extend(_validate_no_swallowed_corruption())
    return problems


def _validate_no_swallowed_corruption():
    """読み手が黙って飲み込んだ破損を名指す（INC-027 推奨#0）。

    読み手は黙って劣化してよい —— 帳簿が読めない日でもレーンは走れた方が
    よい。しかし「読めなかった」という事実まで消すと、切り詰めと不在が
    区別できない（INC-006 の沈黙）。読み手は None を返しつつ場所を積み、
    ここが声を上げる。`_validate_ledger_readability` は台帳を**総なめ**に
    するが、こちらは**この実行で実際に読もうとして失敗した**ものを指す。
    """
    return ["読み手が破損を飲み込んだ（空として読み替えていない）: %s" % e
            for e in corrupt_seen()]


def _validate_nameable_states():
    """名指しできる状態は優先順の表に載り、名指ししない状態は載らない。

    ADR-120（を置換した ADR-148）の二分と ADR-131 の表が、別々に
    書き換えられて食い違うのを防ぐ。試験の側だけで持っていたので、
    運転手順 §0 が毎回走らせる validate へ移す。
    """
    problems = []
    nameable = set(NAMEABLE_STATES)
    within = set(WITHIN_CYCLE_STATES)
    priority = set(ACTION_PRIORITY)
    for st in sorted(nameable - priority):
        problems.append("名指しできる状態 %s が優先順の表に無い" % st)
    for st in sorted(priority - nameable):
        problems.append("優先順の表の %s が名指しできる状態でない" % st)
    for st in sorted(nameable & within):
        problems.append("状態 %s が名指しの二分の両側に在る" % st)
    missing = set(STATES) - nameable - within
    for st in sorted(missing):
        problems.append("状態 %s がどちらにも属さない" % st)
    return problems


#: 各行動の駆動源と、待ち行列が有界かどうかの宣言（INC-051 推奨#1）。
#:
#: INC-051 は「無界の在庫駆動の下に鮮度駆動を置くと、下は決して着手されない」
#: という形だった。APPLY_FINDINGS の待ち行列は空にならず、ATTACK_EVALUATOR は
#: 鮮度で毎反復挙がるので、毎反復 2 番目に置かれ続けた。
#:
#: **ここは順序を決めない。**閾値も昇格も優先順の表の書き換えであり所有者判断
#: である（INC-051 推奨#0・ADR-131 が表を凍結している）。ここが持つのは
#: 「その行動が何で駆動され、待ち行列が有界か」という**事実の宣言**だけで、
#: 表の形が飢餓の形になっていないかを `starvation_shaped_pairs` が見る。
#:
#: 行動を足す者は駆動源を言うこと。言えない行動は、飢えるかどうかも言えない。
ACTION_DRIVE = {
    "INGEST_NORMS": {
        "drive": "在庫", "bounded": True,
        "why": "規範3冊の原則は有限で、抽出しきれば空になる"},
    "CAST_ANALYSIS": {
        "drive": "在庫", "bounded": True,
        "why": "未分析の事象の数だけであり、分析すれば減って空になる"},
    "REVIEW_ASSUMPTION": {
        "drive": "在庫", "bounded": True,
        "why": "登記された想定の数だけであり、再検討すれば減る"},
    "MAP_COVERAGE": {
        "drive": "鮮度", "bounded": True,
        "why": "索引の指紋が動けば古びる。ただし冊子は3つで、割当は有限"},
    "APPLY_FINDINGS": {
        "drive": "在庫", "bounded": False,
        "why": "推奨は事故分析のたびに増える。**空にならない** —— "
               "本日時点で調査済み未着手 271 件（INC-051 の実測）"},
    "ATTACK_EVALUATOR": {
        "drive": "鮮度", "bounded": True,
        "why": "評価器の成果物が故障注入の証拠より新しければ挙がる（ADR-120）。"
               "走らせれば必ず消えるので有界"},
    "REPRODUCE_RED": {
        "drive": "在庫", "bounded": True,
        "why": "承認済みで赤の証拠が無い計画の数だけ。再現すれば減る"},
    "FORMALIZE": {
        "drive": "在庫", "bounded": True,
        "why": "独立批判を生き延びた候補の数だけ。仕様化すれば減る"},
    "DISCOVER": {
        "drive": "在庫", "bounded": True,
        "why": "未批判の候補の数だけ。批判すれば減る"},
}


#: 飢餓の形のまま在り、**所有者判断を待っている**対（INC-051）。
#:
#: 直せないから外す、ではない。**直すこと自体が優先順の表の書き換え**であり、
#: ADR-131 が表を凍結し、INC-051 推奨#0 が owner_decision_required=true を
#: 立てている。ここに置くのは「見えていて、裁定待ちである」という記録であり、
#: 見えなくするための免除ではない。
#:
#: 免除の根拠は機械で確かめる（`_owner_pending_is_real`）—— 対応する処遇が
#: 台帳に `owner` として在ることを要する。裁定が下りて処遇が動けば、この
#: 免除は根拠を失って赤になる。**免除が自分の期限を持つ形にしてある。**
STARVATION_SHAPED_OWNER_PENDING = {
    ("APPLY_FINDINGS", "ATTACK_EVALUATOR"):
        "INC-051-unbounded-queue-starves-the-freshness-driven-action#0",
}


def _owner_pending_is_real(ref, rows=None):
    """免除が指す処遇が、実際に『所有者判断』として台帳に在るか。"""
    incident_id, _, index = ref.rpartition("#")
    if rows is None:
        rows = load_recommendation_status()
    row = rows.get((incident_id, int(index)))
    return bool(row) and row.get("state") == "owner"


def starvation_shaped_pairs(priority=None, drive=None):
    """飢餓の形になっている対を返す（INC-051 推奨#1）。

    形とは「**無界**と宣言された在庫駆動の**下位**に、鮮度駆動が在る」こと。
    上が空にならない以上、下は先頭を飛ばさない限り着手されない。

    宣言が無い行動はここでは判じない（その欠落は別の試験が咎める）。
    返すのは (上に在る無界の在庫駆動, 下に在る鮮度駆動) の対の一覧。
    """
    priority = ACTION_PRIORITY if priority is None else priority
    drive = ACTION_DRIVE if drive is None else drive
    unbounded = [a for a in priority
                 if drive.get(a, {}).get("drive") == "在庫"
                 and drive.get(a, {}).get("bounded") is False]
    pairs = []
    for upper in sorted(unbounded, key=lambda a: priority[a]):
        for lower in sorted(priority, key=lambda a: priority[a]):
            if priority[lower] <= priority[upper]:
                continue
            if drive.get(lower, {}).get("drive") == "鮮度":
                pairs.append((upper, lower))
    return pairs


# 条件(2)の検算を要さない出荷（祖父条項。ADR-139 の VERIFY_GRANDFATHERED と同じ形）。
#
# v0.11.0 の出荷 8 件は fix_commit を記録せずに積まれた。散文の fix_note から
# commit を推すことはできるが、**推した値を検算の根拠にするのは検算ではない**。
# 事実として、修正はいずれも tag の木に在ることを人が確かめている。
# この列は増やさない —— 増やすことは検証の門を後ろへ動かすことであり、
# 保証範囲の変更として所有者判断に当たる（運転手順 §7）。
SHIPPED_GRANDFATHERED = frozenset({
    "INC-010-evaluated-unknown-relisted",
    "INC-015-discover-output-invisible-to-canon",
    "INC-016-cast-analysis-content-unread-by-canon",
    "INC-020-evaluator-blindness-read-as-owner-authority",
    "INC-021-lane-fires-on-declared-without-a-runner",
    "INC-022-ci-that-cannot-run-is-read-as-red",
    "INC-023-attack-freshness-truncated-to-the-day",
    "INC-025-adr-130-implemented-the-option-it-rejected",
})


def _validate_shipped_conditions(incidents=None):
    """出荷（shipped）の三条件を機械で検める（ADR-144。INC-036）。

    ADR-144 は三条件を定めたが、機械が検めていたのは「記録の形」だけで、
    条件そのものは書き手の手順に委ねられていた。独立再監査が、台帳唯一の
    fix_commit がどの ref からも到達できない dangling commit であること
    （squash merge の前の枝の commit）を実測した —— 条件(2)が実際に作用する
    唯一のフィールドが、その検算に落ちる。

    検めるのは三つ。fix_commit が書かれていること・その commit が実在して
    到達できること・ship_ref の tag の祖先であること。git が使えない環境では
    何も言わない（前提の欠如を所見にしない）。
    """
    problems = []
    incidents = load_incidents() if incidents is None else incidents
    if not _git_available():
        return problems
    for inc in incidents:
        if not inc.get("shipped"):
            continue
        if inc.get("id") in SHIPPED_GRANDFATHERED:
            continue
        ident = inc.get("id")
        tag = (inc.get("ship_ref") or "").strip()
        commit = (inc.get("fix_commit") or "").strip()
        if not tag:
            problems.append("出荷 %s に ship_ref が無い" % ident)
            continue
        tag_name = tag.split()[0] if tag else ""
        if not commit:
            problems.append(
                "出荷 %s に fix_commit が無い（ADR-144 の条件2 を検算できない）"
                % ident)
            continue
        if not _git_has_commit(commit):
            problems.append(
                "出荷 %s の fix_commit %s がどの ref からも到達できない"
                % (ident, commit))
            continue
        if not _git_is_ancestor(commit, tag_name):
            problems.append(
                "出荷 %s の fix_commit %s が %s の祖先でない"
                % (ident, commit, tag_name))
    return problems


def _git(args):
    try:
        return subprocess.run(["git"] + args, cwd=os.path.dirname(LANE_DIR),
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def _git_available():
    """git が使えて、履歴が揃っていること。

    浅い複製（CI の `actions/checkout` の既定は深さ 1）では、実在する commit
    でも到達できないと出る。前提の欠如を所見にすると、門が偽の赤を出す ——
    「門が正しいものを咎める型は、見逃しより害が大きい」（WATCH-001 第10項）。
    浅いときは検算そのものを見送る。
    """
    r = _git(["rev-parse", "--git-dir"])
    if not (r and r.returncode == 0):
        return False
    shallow = _git(["rev-parse", "--is-shallow-repository"])
    if shallow and shallow.stdout.strip() == "true":
        return False
    return True


def _git_has_commit(rev):
    r = _git(["merge-base", "--is-ancestor", rev, "HEAD"])
    if r is not None and r.returncode == 0:
        return True
    r = _git(["branch", "-a", "--contains", rev])
    return bool(r and r.returncode == 0 and r.stdout.strip())


def _git_is_ancestor(rev, ref):
    r = _git(["merge-base", "--is-ancestor", rev, ref])
    return bool(r and r.returncode == 0)


def _validate_owner_overrides(rows=None):
    """評価者の「所有者判断が要る」の印を覆すなら、理由を書く（INC-036）。

    評価者が owner を印した推奨 67 件のうち 55 件が owner 以外の状態へ
    置かれていた。覆すこと自体は正しい —— 分析には統治木が渡らないので、
    評価者には全部が未決に見える（正本自身がそう書いている）。しかし
    **覆した理由を機械が要求していなかった**。今は規律だけが支えている。
    """
    problems = []
    if rows is None:
        # 鍵つきの写像で返るので、行だけを取る。
        rows = list(load_recommendation_status().values())
    for r in rows:
        if not isinstance(r, dict) or not r.get("evaluator_owner_required"):
            continue
        if r.get("state") == "owner":
            continue
        if (r.get("owner_override_reason") or "").strip():
            continue
        problems.append(
            "推奨 %s#%s は評価者が所有者判断を要すると印したのに、"
            "%s へ置いた理由（owner_override_reason）が無い"
            % (r.get("incident_id"), r.get("index"), r.get("state")))
    return problems


def _validate_ledger_readability(ledger_dir=None):
    """台帳が全件 JSON として読めること（切り詰めを「空」と読み替えない）。

    次の行動を導く読み手（`latest_formalize`・`latest_scenarios`・
    `load_verify_records`・`load_recommendation_status`）は `ValueError` を
    握り潰す —— 帳簿が読めない日でもレーンは走れた方がよいからである。
    その寛容さの代償として、**切り詰められた台帳と、そもそも無い台帳が
    区別できない**（事象 INC-027）。区別する場所をここに一つだけ置く。
    行動の導出は黙って劣化させ、`validate` が声を上げる —— 想定の台帳が
    既に採っている三分（読み手は投げ、行動は飲み、validate が名指す）と同じ形。

    `ledger_files()` が数える成果物を一つずつ読むので、新しい種類の台帳も
    宣言を足した時点で自動的に覆われる。
    """
    problems = []
    root = ledger_dir or _ledger_dir()
    for rel in ledger_files(root):
        if not rel.endswith(".json"):
            continue
        path = os.path.join(root, rel)
        try:
            ledger_io.read_json(path, required=True)
        except ledger_io.LedgerCorrupt as exc:
            problems.append("台帳が読めない（空ではない。破損の疑い）: %s" % exc)
    return problems


def _validate_coverage_merges(ledger_dir=None):
    """重複統合（merged_into。CURATE）の書き方の検査。

    統合欄は (1) 同じ冊子に実在する key を指し、(2) 指す先が自身も統合済み
    ではなく（連鎖の禁止 —— 出自が二段で辿れなくなる）、(3) merge_note
    （日付と理由）を持つ。判定は消さない（生き残りの項が正本）。
    """
    problems = []
    root = ledger_dir or _ledger_dir()
    for path in sorted(glob.glob(os.path.join(root, "catalogs",
                                              "*-coverage.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f).get("entries", [])
        except (OSError, ValueError):
            continue  # 読めない台帳は台帳種別の検査が指す
        by_key = {e.get("key"): e for e in entries}
        book = os.path.basename(path)
        for e in entries:
            target = e.get("merged_into")
            if not target:
                continue
            where = "%s の %s" % (book, e.get("key"))
            if target not in by_key:
                problems.append("統合 %s が実在しない key %s を指す" % (where, target))
            elif by_key[target].get("merged_into"):
                problems.append("統合 %s の指す先 %s も統合済み（連鎖の禁止）"
                                % (where, target))
            if not (e.get("merge_note") or "").strip():
                problems.append("統合 %s に merge_note（日付と理由）が無い" % where)
            if target in by_key:
                src_rank = _DISPOSITION_RANK.get(e.get("disposition"))
                dst_rank = _DISPOSITION_RANK.get(
                    by_key[target].get("disposition"))
                if (src_rank is not None and dst_rank is not None
                        and dst_rank > src_rank):
                    problems.append(
                        "統合 %s が判定を緑へ寄せている（%s → %s）。"
                        "重複の統合は数の付け替えであって判定の変更ではない"
                        % (where, e.get("disposition"),
                           by_key[target].get("disposition")))
    return problems


# 判定の「緑さ」の順。統合で判定が緑へ動くことを禁ずるためだけに使う
# （評価の優劣を表す表ではない。数の付け替えで判定不能が消えるのを防ぐ）。
_DISPOSITION_RANK = {
    "UNASSESSED": 0,
    "UNKNOWN": 1,
    "対応計画あり": 2,
    "非該当で理由あり": 3,
    "実装・試験・証拠あり": 4,
}


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
        problems.extend(_validate_observation(where, row))
    return problems


#: 所見（investigated）が持つ欄。観測は「いつ・誰が・どう見て・何を言ったか」で
#: 初めて後から古びを問える（INC-050 推奨#0）。
OBSERVATION_FIELDS = ("observed_at", "observed_by", "method", "claim")


def _validate_observation(where, row):
    """処遇の所見は『観測』の形で書く（INC-050 推奨#0）。

    自由型（文字列・真偽値）の所見は、いつ見たかを機械が読めない。
    `investigated: true` に至っては「調べた」と主張しながら中身を持たない ——
    古びを問うことすらできず、後の反復がそれを**現状**として読む。

    **欄が無いこと自体は咎めない。**所見を持たない処遇は「観測していない」
    のであって、偽の観測ではない。咎めるのは観測を騙る非構造である。

    **欠測は欠測として残す。**観測日が無いなら method がその理由を言うこと。
    真偽値だった所見を日付へ推測変換すれば、古びの計算が嘘の値を返す。
    """
    if "investigated" not in row:
        return []
    obs = row["investigated"]
    if not isinstance(obs, dict):
        return ["推奨 %s の所見が自由型（%s）である。観測は %s を持つ構造で書く"
                % (where, type(obs).__name__, "・".join(OBSERVATION_FIELDS))]
    missing = [k for k in OBSERVATION_FIELDS if k not in obs]
    if missing:
        return ["推奨 %s の所見に欄が無い: %s" % (where, "・".join(missing))]
    if obs.get("observed_at") is None and not (obs.get("method") or "").strip():
        return ["推奨 %s の所見に観測日が無く、無い理由も無い（沈黙は理由ではない）"
                % where]
    return []


def _validate_assumptions(path=None, incident_ids=None):
    """想定の登記簿の書き方の検査（ADR-126）。

    想定は「何も検証していない前提」を名指しする物なので、検証者の欄が
    空であること自体は欠陥ではない。欠陥なのは、欄が**無い**ことである
    （沈黙は理由ではない）。先行指標の二条件は ADR-117 と同じ形にし、
    観測を書くなら日付と状態語彙を必ず添えさせる。

    機械の観測（observe_assumptions.py。ADR-144）は `observation_history` へ
    追記だけを行う。履歴の各項は日付・状態語彙・観測者を持つこと。
    `verified_by` は null か文字列のどちらか —— 埋めるのは独立の評価セッション
    の実施であって、機械の観測ではない。
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
        elif not (row["verified_by"] is None
                  or isinstance(row["verified_by"], str)):
            problems.append(
                "想定 %s の verified_by は null か文字列であること"
                "（検証の主体と方式を文で名指しする欄。ADR-144）" % aid)
        for n, entry in enumerate(row.get("observation_history") or []):
            if not isinstance(entry, dict):
                problems.append(
                    "想定 %s の観測履歴#%d が構造を持たない" % (aid, n))
                continue
            if not (entry.get("date") or "").strip():
                problems.append(
                    "想定 %s の観測履歴#%d に日付が無い" % (aid, n))
            state = entry.get("state")
            if state not in ASSUMPTION_STATES:
                problems.append(
                    "想定 %s の観測履歴#%d の状態 %r が語彙に無い（%s）"
                    % (aid, n, state, "/".join(ASSUMPTION_STATES)))
            if not (entry.get("observed_by") or "").strip():
                problems.append(
                    "想定 %s の観測履歴#%d に観測者が無い" % (aid, n))
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
    # ADR-148 が ADR-120 を置換して移した。承認された検証計画は「買った義務」で
    # あり、帳簿（formalize と red）だけから指せる。名指しできないままだと、
    # FORMALIZE が計画を承認した瞬間にその計画は正本の視野から消える —— 実測で
    # 30 件が消えていた（INC-033）。
    "REPRODUCE_RED",
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
#   REPRODUCE_RED     承認済みの検証計画。**既に買った義務**であり、
#                     新しい計画や新しい仮説を買うより先に果たす
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
    "REPRODUCE_RED": 65,
    "FORMALIZE": 70,
    "DISCOVER": 80,
}

# 反復の中の遷移。直前の成果物が在って初めて意味を持つので、帳簿だけからは
# 名指しできない（DISCOVER が scenario を出して初めて CHALLENGE が立つ）。
# ここに置くことは「名指ししない」ことの明示であって、やらなくてよいという
# 意味ではない。反復の中で順に踏む。
WITHIN_CYCLE_STATES = frozenset({
    "CHALLENGE", "FIX", "VERIFY", "RECORD", "CURATE",
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
     "read_by": ("evaluator_outputs_latest", "cast_recommendations",
                 "cast_scenario_candidates"),
     "why_not_read": None},
    {"kind": "scenarios/<日付>.json",
     "match": "scenarios/*.json",
     "read_by": ("latest_scenarios", "triaged_candidate_keys"),
     "why_not_read": None},
    {"kind": "formalize/<日付>.json",
     "match": "formalize/*.json",
     "read_by": ("latest_formalize", "unformalized_survivors"),
     "why_not_read": None},
    {"kind": "verify/<対象 id>.json",
     "match": "verify/*.json",
     "read_by": ("load_verify_records",),
     "why_not_read": None},
    {"kind": "mutations-<日付>.json",
     "match": "mutations-*.json",
     "read_by": ("attack_evidence_latest", "unknown_aging"),
     "why_not_read": None},
    {"kind": "recommendation-status.json",
     "match": "recommendation-status.json",
     "read_by": ("load_recommendation_status",),
     "why_not_read": None},
    {"kind": "assumptions.json",
     "match": "assumptions.json",
     "read_by": ("load_assumptions", "assumption_backlog"),
     "why_not_read": None},
    {"kind": "red/<対象 id>.json",
     "match": "red/*.json",
     "read_by": ("load_red_records", "unreproduced_plans"),
     "why_not_read": None},
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
    {"kind": "rulings/<日付>-<件名>.json",
     "match": "rulings/*.json",
     "read_by": (),
     "why_not_read":
         "所有者裁定の監査証跡。行動は ADR-145 と SKILL §7.2 が運ぶ。"
         "正本の行動導出には使わない"},
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
        # 第二の入口は候補の取り込み（triage_candidates.py。ADR-140）。同じ状態・
        # 同じ成果物種別を共有し、独立批判も同じ口（CHALLENGE）を通る。
        "runner": "discover.py",
        "prompt_builders": ("build_discover_prompt",
                            "build_candidate_formulation_prompt"),
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
        # 検証計画の審査（jerg）。INC-021 推奨#3 の所有者裁定（2026-08-07）で
        # 実装した（ADR-138）。ADR-128 の不変条件そのものは維持したまま、
        # 「未実装の明記」から走らせ手の三点へ倒した。
        "runner": "formalize.py",
        "prompt_builders": ("build_formalize_prompt",),
        "ledger_kind": "formalize/<日付>.json"},
    "VERIFY": {
        # 修正の独立検証（jerg）。同じ所有者裁定で実装した（ADR-139）。
        # 得られるのはセッションの独立までで、独立した組織による検証（IV&V）
        # にはならない（NONGOAL-001 第17項。同系 model の共通原因故障は残余
        # リスク）。新規の fixed:true は PASS の verify 記録を要す
        # （_validate_verify_refs が検める）。
        "runner": "verify_fix.py",
        "prompt_builders": ("build_verify_prompt",),
        "ledger_kind": "verify/<対象 id>.json"},
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

    対象は評価の成果物だけ（カタログ・事故分析・網羅の割当・計画審査・
    独立検証）。決定論試験や煙試験は評価ではないので数えない。
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
    # 計画審査（ADR-138）と独立検証（ADR-139）も評価の成果物である。数えないと
    # これらの評価器だけが攻撃の鮮度の外に立つ（INC-012 と同じ穴の作り直し）。
    fm = latest_formalize()
    if fm:
        seen.append(fm.get("generated_at") or fm.get("date"))
    for doc in load_verify_records().values():
        seen.append(doc.get("generated_at"))
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
    path = os.path.join(scn_dir, names[-1])
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        return note_corrupt(path, exc)


def latest_formalize():
    """直近の検証計画審査の記録。無ければ None（ADR-138）。"""
    fm_dir = os.path.join(LANE_DIR, "ledger", "formalize")
    if not os.path.isdir(fm_dir):
        return None
    names = sorted(n for n in os.listdir(fm_dir) if n.endswith(".json"))
    if not names:
        return None
    path = os.path.join(fm_dir, names[-1])
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        return note_corrupt(path, exc)


def unformalized_survivors():
    """批判を生き残ったのに、まだ計画審査の判定を持たない scenario の id。

    APPROVE も REJECT も UNKNOWN も消化と数える —— 判定は評価の結論であり、
    割当済みである（評価済み UNKNOWN を引き直さないのと同じ規則。INC-006）。
    挙がり続けるのは、計画が返らなかった沈黙だけ（沈黙を APPROVE と読まない。
    ADR-138）。
    """
    scn = latest_scenarios()
    survivors = (scn or {}).get("survivors") or []
    if not survivors:
        return []
    planned = set()
    fm_dir = os.path.join(LANE_DIR, "ledger", "formalize")
    if os.path.isdir(fm_dir):
        for name in sorted(os.listdir(fm_dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(fm_dir, name), encoding="utf-8") as f:
                    doc = json.load(f)
            except (OSError, ValueError):
                continue
            for plan in doc.get("plans") or []:
                if isinstance(plan, dict) and plan.get("scenario_id"):
                    planned.add(plan["scenario_id"])
    return [sid for sid in survivors if sid not in planned]


# 読み手が握り潰した破損を、名指しできる形で残す（INC-027 推奨#0）。
#
# 読み手は黙って劣化してよい —— 帳簿が読めない日でもレーンは走れた方がよい。
# しかし「読めなかった」という事実まで消すと、切り詰めと不在が区別できない。
# 読み手は None を返しつつ、ここへ場所を積む。validate がそれを名指す。
_CORRUPT_SEEN = []


def note_corrupt(path, exc):
    """破損を記録して、呼び手には黙って None を返させる。"""
    entry = "%s (%s)" % (path, exc)
    if entry not in _CORRUPT_SEEN:
        _CORRUPT_SEEN.append(entry)
    return None


def corrupt_seen():
    """このプロセスで読み手が飲み込んだ破損の一覧。"""
    return list(_CORRUPT_SEEN)


def load_red_records(ledger_dir=None):
    """修正前 FAIL の証拠。鍵は対象 id（scenario か incident）。無ければ空。

    鍵はファイル名を第一とする —— `verify_fix.py` が
    `ledger/red/<対象 id>.json` で引くので、引き方を二重定義しない。
    """
    out = {}
    root = ledger_dir or _ledger_dir()
    d = os.path.join(root, "red")
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(d, name)
        try:
            doc = ledger_io.read_json(path, default=None)
        except ledger_io.LedgerCorrupt as exc:
            # 読み手は黙って劣化する。破損は note_corrupt が覚え、
            # validate が名指す（INC-027 推奨#11。三分を保つ）。
            note_corrupt(path, exc)
            continue
        if isinstance(doc, dict):
            out[name[:-5]] = doc
    return out


def red_closed(record):
    """REPRODUCE_RED が消化されたか（ADR-148）。

    消化と認めるのは二つだけ。
    - 赤が赤だった（`phase: before-fix` で、0 でない返り値と観測された失敗）。
      **最初から緑は再現と認めない**（運転手順 §2）。
    - 再現不能と記録された（`phase: impossible`）。理由つきで RECORD へ抜ける。

    どちらでもない記録（沈黙・空の観測）は消化ではない。
    """
    if not isinstance(record, dict):
        return False
    phase = record.get("phase")
    if phase == "impossible":
        return bool(record.get("reason") or record.get("note"))
    if phase != "before-fix":
        return False
    if record.get("returncode") in (0, None) and not record.get("reds"):
        return False        # 最初から緑（または返り値が無い）は再現ではない
    observed = record.get("observed_failures") or record.get("reds") or []
    return bool(observed)


def unreproduced_plans(ledger_dir=None):
    """承認された検証計画のうち、赤の証拠も再現不能の記録も無いもの。

    返すのは [(scenario_id, formalize のファイル名)] を id 順で。
    数えるのは APPROVE だけ —— REJECT と UNKNOWN は義務を生まない。
    """
    root = ledger_dir or _ledger_dir()
    fm_dir = os.path.join(root, "formalize")
    if not os.path.isdir(fm_dir):
        return []
    reds = load_red_records(root)
    out = []
    for name in sorted(os.listdir(fm_dir)):
        if not name.endswith(".json"):
            continue
        fpath = os.path.join(fm_dir, name)
        try:
            doc = ledger_io.read_json(fpath, default=None)
        except ledger_io.LedgerCorrupt as exc:
            note_corrupt(fpath, exc)
            continue
        if not isinstance(doc, dict):
            continue
        for plan in doc.get("plans") or []:
            if not isinstance(plan, dict):
                continue
            if plan.get("verdict") != "APPROVE":
                continue
            sid = plan.get("scenario_id")
            if not sid:
                continue
            if red_closed(reds.get(sid)):
                continue
            out.append((sid, name))
    return sorted(set(out))


def reproduce_red_summary(ledger_dir=None):
    """承認・消化・未消化の数。挙げないときも必ず数えて出す。"""
    root = ledger_dir or _ledger_dir()
    fm_dir = os.path.join(root, "formalize")
    approved = set()
    if os.path.isdir(fm_dir):
        for name in sorted(os.listdir(fm_dir)):
            if not name.endswith(".json"):
                continue
            fpath = os.path.join(fm_dir, name)
            try:
                doc = ledger_io.read_json(fpath, default=None)
            except ledger_io.LedgerCorrupt as exc:
                note_corrupt(fpath, exc)
                continue
            for plan in (doc or {}).get("plans") or []:
                if isinstance(plan, dict) and plan.get("verdict") == "APPROVE" \
                        and plan.get("scenario_id"):
                    approved.add(plan["scenario_id"])
    outstanding = [sid for sid, _f in unreproduced_plans(root)]
    return {"approved": len(approved),
            "reproduced": len(approved) - len(outstanding),
            "outstanding": len(outstanding)}


def load_verify_records():
    """修正の独立検証の記録。鍵は対象 id。無ければ空（ADR-139）。

    新規の fixed:true の事象は、ここに PASS の記録を持たなければならない
    （_validate_verify_refs が検める。祖父条項は VERIFY_GRANDFATHERED）。
    """
    out = {}
    v_dir = os.path.join(LANE_DIR, "ledger", "verify")
    if not os.path.isdir(v_dir):
        return out
    for name in sorted(os.listdir(v_dir)):
        if not name.endswith(".json"):
            continue
        vpath = os.path.join(v_dir, name)
        try:
            with open(vpath, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as exc:
            note_corrupt(vpath, exc)
            continue
        if isinstance(doc, dict):
            out[doc.get("target_id") or name[:-len(".json")]] = doc
    return out


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


def cast_scenario_candidates():
    """事故分析が出した新規仮説候補の全件。事象 id と番号で一意に指す（ADR-140）。

    cast_recommendations と同じ読み方 —— 分析の記録のうち推奨は ADR-125 で
    正本へ届いたが、new_scenario_candidates の欄は一度も読まれていなかった
    （INC-016 の残余）。候補は仮説であり、判定済みの scenario ではない。
    取り込みは既存の DISCOVER→CHALLENGE の独立構造を通す。
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
        for index, cand in enumerate(
                analysis.get("new_scenario_candidates") or []):
            if not isinstance(cand, dict):
                continue
            out.append({
                "incident_id": incident_id,
                "index": index,
                "hypothesis": cand.get("hypothesis") or "",
                "oracle": cand.get("oracle") or "",
                "falsification_signal": cand.get("falsification_signal") or "",
                "severity": cand.get("severity") or "",
            })
    return out


def triaged_candidate_keys():
    """既に批判の口を通った候補の鍵 (事象 id, 番号) の集合（ADR-140）。

    消化の記帳は scenarios 台帳の出自欄 `candidates_considered` が持つ。
    第二の処遇の台帳は作らない —— 定式化されたか・重複か・定式化不能かに
    かかわらず、口を通った候補はここに載り、二度と数え直されない
    （評価済み UNKNOWN を引き直さないのと同じ規則。INC-006）。
    """
    out = set()
    scn_dir = os.path.join(LANE_DIR, "ledger", "scenarios")
    if not os.path.isdir(scn_dir):
        return out
    for name in sorted(os.listdir(scn_dir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(scn_dir, name), encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for entry in doc.get("candidates_considered") or []:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                out.add((entry[0], entry[1]))
    return out


def _candidate_summary():
    """新規仮説候補の集計（ADR-140）。

    次の行動に挙がらないときも必ず数えて出す —— 挙げないことと隠すことは
    違う（INC-006）。閾値は ADR-134 の一束をそのまま使う。
    """
    cands = cast_scenario_candidates()
    triaged = triaged_candidate_keys()
    untriaged = [c for c in cands
                 if (c["incident_id"], c["index"]) not in triaged]

    def _by_severity(rows):
        counts = {}
        for c in rows:
            sev = c["severity"] or "(無し)"
            counts[sev] = counts.get(sev, 0) + 1
        return {k: counts[k] for k in sorted(counts)}

    return {
        "total": len(cands),
        "triaged": len(cands) - len(untriaged),
        "untriaged": len(untriaged),
        "by_severity": _by_severity(cands),
        "untriaged_by_severity": _by_severity(untriaged),
        "raise_threshold": STALE_RAISE_THRESHOLD,
    }


def load_recommendation_status():
    """推奨の処遇の台帳。鍵は (事象 id, 番号)。無ければ空。"""
    path = os.path.join(LANE_DIR, "ledger", "recommendation-status.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f).get("dispositions", [])
    except (OSError, ValueError) as exc:
        note_corrupt(path, exc)
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


def unknown_aging():
    """UNKNOWN（判定不能）に分類された失敗の滞留の集計（INC-003 推奨#3）。

    数える範囲（経験則であって意味の判定ではない。過大に主張しない）:

    - mutations-*.json の注入行のうち、observed_status か sdk_status が
      UNKNOWN のもの。日付は記録の date を使う。
    - incidents.json の行のうち、status_at_detection か next_step の文面に
      UNKNOWN を含むもの。日付は行の date を使う。文面の含有で数えるのは、
      事象の側に分類の構造化された欄が無いためである（欄が入ったらこの
      経験則は置き換える）。

    数え出すのは件数と最古の日付だけで、経過日数へは換算しない —— 実時計を
    読まない（ADR-094 と同じ規律）ので、滞留の長さの解釈は読み手が今日の
    日付と突き合わせて行う。UNKNOWN の件数ゼロを健全さと読まないこと
    （ASM-004 の rejected_indicators に理由がある）。
    """
    dates = []
    mut_count = 0
    ledger = _ledger_dir()
    if os.path.isdir(ledger):
        for name in sorted(os.listdir(ledger)):
            if not (name.startswith("mutations-") and name.endswith(".json")):
                continue
            try:
                with open(os.path.join(ledger, name), encoding="utf-8") as f:
                    doc = json.load(f)
            except (OSError, ValueError):
                continue
            for run in doc.get("injections") or []:
                if not isinstance(run, dict):
                    continue
                if "UNKNOWN" in (run.get("observed_status"),
                                 run.get("sdk_status")):
                    mut_count += 1
                    if doc.get("date"):
                        dates.append(doc["date"])
    inc_count = 0
    try:
        incidents = load_incidents()
    except (OSError, ValueError):
        incidents = []
    for inc in incidents:
        if not isinstance(inc, dict):
            continue
        text = " ".join(str(inc.get(k) or "")
                        for k in ("status_at_detection", "next_step"))
        if "UNKNOWN" in text:
            inc_count += 1
            if inc.get("date"):
                dates.append(inc["date"])
    days = sorted(v[:10] for v in dates
                  if isinstance(v, str) and len(v) >= 10)
    return {"count": mut_count + inc_count,
            "mutations": mut_count,
            "incidents": inc_count,
            "oldest": days[0] if days else None}


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
               if not e.get("merged_into")
               and not e.get("assigned_at") and e.get("disposition") == "UNKNOWN")


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
        # 統合済み（merged_into。CURATE の重複統合）は作業として数えない。
        # 判定は消さず残る —— 生き残りの項が正本で、統合欄は出自の記録である。
        merged = sum(1 for e in entries if e.get("merged_into"))
        unassessed = sum(1 for e in entries
                         if not e.get("merged_into")
                         and e.get("disposition") == "UNASSESSED")
        unknown = sum(1 for e in entries
                      if not e.get("merged_into")
                      and e.get("disposition") == "UNKNOWN")
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
                if e.get("merged_into"):
                    continue
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
            # 五値のうち UNASSESSED（前提が欠けて評価できない）は、unknown
            # にも unmapped にも入らないので、どの数にも現れていなかった。
            # 一値が見えないと「五値で覆っている」という主張が保てない。
            "unassessed": unassessed,
            "stale_open": stale_open,
            "stale_settled": stale_settled,
            "merged": merged,
            "total": len(entries),
        }
    return out


def load_incidents():
    if not os.path.isfile(INCIDENTS_PATH):
        return []
    with open(INCIDENTS_PATH, encoding="utf-8") as f:
        return json.load(f).get("incidents", [])


# 修正の独立検証を要さない事象（祖父条項。ADR-139）。
#
# 凍結は 2026-08-07 時点の全事象。以後の fixed:true は PASS の verify 記録を要す。
# この列は増やさない —— 増やすことは検証の門を後ろへ動かすことであり、
# 保証範囲の変更として所有者判断に当たる（運転手順 §7）。
VERIFY_GRANDFATHERED = (
    "INC-001-sessionend-audit-gap",
    "INC-005-installed-plugin-version-lag",
    "INC-002-termcheck-ascii-substring",
    "INC-003-sdk-error-opacity",
    "INC-004-hyphen-token-undefined-term",
    "INC-006-next-actions-silently-empty",
    "INC-007-linter-nameerror-field-report",
    "INC-008-ledger-write-back-clobber",
    "INC-009-sessionend-audit-unobservable",
    "INC-010-evaluated-unknown-relisted",
    "INC-011-dot-joined-token-undefined-term",
    "INC-012-states-unnameable-by-canon",
    "INC-013-cast-analysis-accepts-fabricated-incident",
    "INC-014-evaluation-max-turns-marginal",
    "INC-015-discover-output-invisible-to-canon",
    "INC-016-cast-analysis-content-unread-by-canon",
    "INC-017-accepted-adr-born-red-is-unfixable",
    "INC-018-audit-degrades-into-a-tree-finding",
    "INC-019-version-string-does-not-identify-the-copy",
    "INC-020-evaluator-blindness-read-as-owner-authority",
    "INC-021-lane-fires-on-declared-without-a-runner",
    "INC-022-ci-that-cannot-run-is-read-as-red",
    "INC-023-attack-freshness-truncated-to-the-day",
    "INC-024-coverage-rubric-undecided-at-its-busiest-boundary",
    "INC-025-adr-130-implemented-the-option-it-rejected",
    "INC-026-accepted-adr-has-no-sanctioned-repair-path",
)


def _validate_verify_refs(incidents=None, verify_records=None):
    """fixed:true と独立検証の突合（ADR-139）。

    祖父条項（VERIFY_GRANDFATHERED。凍結済み）の外で fixed:true と書かれた
    事象は、verify_ref を持ち、それが PASS の verify 記録
    （ledger/verify/<事象 id>.json の record.verdict == "PASS"）へ解決しなければ
    ならない。修正したという申告は検証ではない —— 申告をそのまま信じる形は、
    この体系が三度「やらない」と決めている（ADR-127 と同じ向き）。
    """
    problems = []
    if incidents is None:
        try:
            incidents = load_incidents()
        except (OSError, ValueError) as exc:
            return ["事象の台帳が読めない: %s" % exc]
    if verify_records is None:
        verify_records = load_verify_records()
    for inc in incidents:
        if not isinstance(inc, dict) or inc.get("fixed") is not True:
            continue
        iid = inc.get("id")
        if iid in VERIFY_GRANDFATHERED:
            continue
        if not (inc.get("verify_ref") or "").strip():
            problems.append(
                "事象 %s は fixed:true だが verify_ref が無い（新規の修正は "
                "PASS の verify 記録を要す。ADR-139）" % iid)
            continue
        doc = verify_records.get(iid)
        if doc is None:
            problems.append(
                "事象 %s の verify_ref が指す記録 ledger/verify/%s.json が無い"
                % (iid, iid))
            continue
        verdict = (doc.get("record") or {}).get("verdict")
        if verdict != "PASS":
            problems.append(
                "事象 %s の verify 記録の verdict が PASS でない（%r）。"
                "検証を通らない fixed:true は申告であって修正ではない"
                % (iid, verdict))
    return problems


# 体系の外に在る証拠の種別（ADR-141）。解決しない理由を宣言で受ける ——
# 黙って通さず、何であるかを名指しさせる。定義はここ一箇所だけに持ち、
# cast_analysis はこれを import する（語彙の二重定義は、片方だけが変わった
# ときに門と分析で判定が割れる）。
EXTERNAL_EVIDENCE_KINDS = ("external", "conversational", "measurement")


def _validate_incident_evidence(incidents=None, resolve=None):
    """事象の証拠の宣言を、台帳へ積まれた時点で検める（ADR-141）。

    運転手順 §5 は「新しい事象には evidence_refs か evidence_kind を必ず
    持たせる」と定めるが、機械はどこも検めていなかった —— 捏造事象は分析が
    走るまで台帳に座る（INC-013 の構造の穴）。各行は次のどちらかを要す:

    - evidence_refs の少なくとも一つが、網羅の証拠と同じ解決経路
      （ADR-118/123。索引と実ファイル系）で解決する
    - evidence_kind が体系の外の証拠として宣言されている
      （EXTERNAL_EVIDENCE_KINDS の語彙そのまま。語彙の外の語は赤）

    **書いた参照は宣言の有無に関わらず全件が解決することを要す**（ADR-166）。
    免除の単位は体系外の実体であって行ではない —— 宣言して refs を一つも
    書かない行は緑のままだが、書いた refs が解決しないときは赤にし、どれが
    解決しないかを名指しする。宣言が在れば refs を見ずに通す形は、実在しない
    ADR の名を 4 日間座らせた（INC-040 → INC-041）。「一つでも解決すれば緑」も
    独立に通していたので、両方を閉じないと当の 1 件が検出されない。

    索引が組めない環境では refs の解決を判じられない。そのときは
    evidence_kind を持たない行だけを「確かめられない（UNKNOWN）」として
    報せる —— 前提の欠如で全件を赤に倒さない（緑へも倒さない）。

    保証限界: 解決は実証ではない。実在するファイルを引く捏造事象はこの門を
    通り得る（意味の判断であり機械では閉じない。NONGOAL-001 第1項）。
    その残余は評価器攻撃（A2）が監視する。
    """
    problems = []
    if incidents is None:
        try:
            incidents = load_incidents()
        except (OSError, ValueError) as exc:
            return ["事象の台帳が読めない: %s" % exc]
    index_ok = True
    if resolve is None:
        now = _index_now()
        if now is None or now.get("_idx") is None:
            index_ok = False
            resolve = lambda ptr: None  # noqa: E731
        else:
            resolve = _pointer_resolver()
    for inc in incidents:
        if not isinstance(inc, dict):
            continue
        iid = inc.get("id") or "(id 無し)"
        kind = inc.get("evidence_kind")
        refs = [r for r in (inc.get("evidence_refs") or [])
                if isinstance(r, str) and r.strip()]
        if kind is not None and kind not in EXTERNAL_EVIDENCE_KINDS:
            problems.append(
                "事象 %s の evidence_kind %r が語彙に無い（%s のいずれか）"
                % (iid, kind, " / ".join(EXTERNAL_EVIDENCE_KINDS)))
            continue
        declared = kind in EXTERNAL_EVIDENCE_KINDS
        if not refs:
            if not declared:
                problems.append(
                    "事象 %s に証拠の宣言が無い（evidence_refs も evidence_kind も"
                    "無い。事象は台帳へ積む時点で証拠の宣言を要す。ADR-141）" % iid)
            continue
        if not index_ok:
            if not declared:
                problems.append(
                    "事象 %s の evidence_refs を確かめられない（索引が組めない環境。"
                    "UNKNOWN。evidence_kind の宣言も無い）" % iid)
            continue
        unresolved = [r for r in refs if not resolve(r)]
        if unresolved and len(unresolved) == len(refs) and not declared:
            problems.append(
                "事象 %s の evidence_refs がどれも解決しない（%s）。実在しない"
                "機構を指す事象は台帳に積めない（ADR-141）" % (iid, refs[:3]))
        elif unresolved:
            problems.append(
                "事象 %s の evidence_refs に解決しない参照が %d 件ある（%s）。"
                "書いた参照は宣言の有無に関わらず全件が解決することを要す"
                "（ADR-166）" % (iid, len(unresolved), unresolved[:3]))
    return problems


def _validate_closure_vocabulary(incidents=None):
    """事象のクローズの語彙の検査（ADR-144）。

    受容（cost_accepted:true）は `cost_accepted_by` を必ず持つ —— 費用の
    受け入れは裁定であり、裁定者の無い受容は根拠なき PASS と同じ形である。
    fixed:true との両立は赤 —— 直ったなら受容は要らない（cost_accepted が
    在って fixed の欄が無い形は、判らないものとして通す。赤にするのは明示の
    矛盾だけ）。出荷（shipped:true）は `ship_ref` を必ず持つ —— 版番号は
    複製の同一性を判定しない（INC-019）ので、shipped はリリース tag の存在・
    `git merge-base --is-ancestor <修正 commit> <tag>`・ship_ref の三条件で
    立てる（判定の手順は ADR-144 が持ち、ここで検めるのは記録の形だけ）。
    """
    problems = []
    if incidents is None:
        try:
            incidents = load_incidents()
        except (OSError, ValueError) as exc:
            return ["事象の台帳が読めない: %s" % exc]
    for inc in incidents:
        if not isinstance(inc, dict):
            continue
        iid = inc.get("id") or "(id 無し)"
        if inc.get("cost_accepted") is True:
            if not (inc.get("cost_accepted_by") or "").strip():
                problems.append(
                    "事象 %s は cost_accepted:true だが cost_accepted_by が"
                    "無い（誰の裁定で費用を受け入れたかを名指しすること。"
                    "ADR-144）" % iid)
            if inc.get("fixed") is True:
                problems.append(
                    "事象 %s が fixed:true と cost_accepted:true を両方持つ"
                    "（直ったなら受容は要らない。どちらかへ倒すこと。ADR-144）"
                    % iid)
        if inc.get("shipped") is True and not (inc.get("ship_ref") or "").strip():
            problems.append(
                "事象 %s は shipped:true だが ship_ref が無い（shipped は"
                "リリース tag の存在・ancestor 照合・ship_ref の三条件で"
                "立てる。ADR-144）" % iid)
    return problems


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

    # 承認された検証計画のうち、赤の証拠が無いもの（ADR-148）。
    # FORMALIZE が「消化」と数えるのは判定が付いたことであって、計画が
    # 果たされたことではない。ここを読まないと、承認した瞬間に義務が
    # 正本の視野から消える（実測 30 件。INC-033）。
    unreproduced = unreproduced_plans()
    if unreproduced:
        head = ", ".join(sid for sid, _f in unreproduced[:3])
        add("REPRODUCE_RED: 承認済みで赤の証拠が無い計画 %d 件（%s%s）"
            % (len(unreproduced), head,
               " ほか" if len(unreproduced) > 3 else ""))

    # 批判を生き残ったのに計画審査の判定を持たない scenario（ADR-138）。
    # 挙げるのは判定の無い生き残りだけ —— 判定済み（APPROVE も REJECT も
    # UNKNOWN も）を挙げ続けると、消化した審査を毎回買い直す「消えない行動」に
    # なる（INC-006・INC-015 と同型）。挙がり続けるのは沈黙だけ。
    unplanned = unformalized_survivors()
    if unplanned:
        scn = latest_scenarios()
        add(
            "FORMALIZE: 計画審査の判定が無い生き残り %d 件（%s の創出。%s）"
            % (len(unplanned), (scn or {}).get("date"),
               ", ".join(unplanned[:3])
               + (" ほか" if len(unplanned) > 3 else "")))

    # 事故分析の新規仮説候補は DISCOVER の口から取り込む（ADR-140）。挙げるのは
    # 未批判の P0・P1 が一束（ADR-134 の閾値の再利用）に達したときだけ。
    # **数えるのは常に行う** —— 挙げないことと隠すことは違う（INC-006）。
    # 件数は status の scenario_candidates に出続ける。
    cand = _candidate_summary()
    cand_p0 = cand["untriaged_by_severity"].get("P0", 0)
    cand_p1 = cand["untriaged_by_severity"].get("P1", 0)
    if should_raise_stale(cand_p0 + cand_p1):
        add(
            "DISCOVER: 事故分析の新規仮説 %d 件（P0 %d・P1 %d）が未批判"
            "（triage_candidates.py）" % (cand_p0 + cand_p1, cand_p0, cand_p1))

    if not actions:
        # 空は「やることが無い」と読める。反復の既定の入口を必ず示す
        # （CAST_DONE・CURATED の遷移先。INC-006）。
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
            # 新規仮説候補も、次の行動に挙がらないときは必ず数えて出す
            # （ADR-140。閾値未満の沈黙を「候補が無い」と読ませない）。
            "scenario_candidates": _candidate_summary(),
            # UNKNOWN 分類の滞留も必ず数えて出す（INC-003 推奨#3）。件数と
            # 最古の日付だけで、健全さの判定はしない —— 件数ゼロを健全さと
            # 読む形は指標として成り立たない（ASM-004 の rejected_indicators）。
            "unknown_aging": unknown_aging(),
            "reproduce_red": reproduce_red_summary(),
        }, ensure_ascii=False, indent=2))
        return 0
    print("usage: orchestrator.py [status|validate]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
