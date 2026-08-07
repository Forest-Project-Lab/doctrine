#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""事故分析の新規仮説候補の取り込み（定式化 → 独立批判。venv の python で動かす）。

- 候補は仮説であり、判定済みの scenario ではない（ADR-140。INC-016 の残余）。
  取り込みは既存の DISCOVER→CHALLENGE の独立構造をそのまま通し、第二の処遇の
  台帳は作らない —— 消化の記帳は scenarios 台帳の出自欄 candidates_considered
  が持つ（considered = 定式化済み + dropped が常に成り立つ）。
- session 1（定式化）は model_policy の evaluation（最低線 opus / effort high。
  ADR-116）。憲章は、渡していない仮説の発明を禁じ、既存 scenario と実質同一の
  候補には duplicate_of を要す。出自（source_candidate）と出典（規範の鍵）は
  機械照合し、通らない scenario は外す（憲章だけの禁止は INC-013 で破られた形。
  機械の床を併せて持つ）。
- duplicate_of を持つ scenario は記録するが CHALLENGE へは渡さない。
- session 2（独立批判）は既存の build_challenge_prompt。構造化 JSON だけが渡る
  （ADR-115）。生き残りは既存の読む段（unformalized_survivors）が FORMALIZE へ
  渡す。

usage: triage_candidates.py [--severities P0,P1] [--batch-size 12]
                            [--max-batches 1] [--today 日付] [--dry-run]
                            [--budget-per-call 4.0] [--timeout 900]

終了コード: 0=記帳まで済んだ / 2=批判を生き残った候補がゼロ / 3=UNASSESSED
            / 4=途中停止(UNKNOWN・予算)。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import (control_structure, discover, model_policy,  # noqa: E402
                     orchestrator, prompts, schemas)

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")
SCENARIO_DIR = os.path.join(LEDGER_DIR, "scenarios")

# 重大度の順。既定で口へ入れるのは P0・P1 だけ（--severities で変えられる）。
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def candidate_key(cand):
    return "%s#%s" % (cand["incident_id"], cand["index"])


def select_untriaged(candidates, triaged_keys, severities):
    """未批判の候補を決定論で選ぶ（手で選ばない。ADR-115）。

    並びは (重大度, 事象 id, 番号)。同じ入力からは常に同じ一括が組まれる。
    """
    picked = [c for c in candidates
              if (c["incident_id"], c["index"]) not in triaged_keys
              and c.get("severity") in severities]
    return sorted(picked, key=lambda c: (
        SEVERITY_ORDER.get(c.get("severity"), 9), c["incident_id"], c["index"]))


def existing_scenario_ids():
    """既存の scenario id の全件（重複の照合先）。"""
    out = set()
    if not os.path.isdir(SCENARIO_DIR):
        return sorted(out)
    for name in sorted(os.listdir(SCENARIO_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(SCENARIO_DIR, name), encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for field in ("scenarios", "duplicates"):
            for scn in doc.get(field) or []:
                if isinstance(scn, dict) and scn.get("scenario_id"):
                    out.add(scn["scenario_id"])
    return sorted(out)


def partition_formulated(batch, accepted_scenarios):
    """定式化の結果を候補ごとに帳合いする（決定論）。

    返り値: (to_challenge, duplicates, dropped, invented)
    - to_challenge … 出自の鍵が一括の中に在り、duplicate_of の無い scenario。
    - duplicates   … duplicate_of を持つ scenario。記録するが批判へ渡さない。
    - dropped      … scenario を持たない候補と重複の候補（{key, reason} の列）。
    - invented     … 出自の鍵が一括に無い scenario の id。捨てる —— 渡して
                     いない仮説の発明は憲章が禁じ、ここが機械の側の床である。

    considered（一括の全候補）= 定式化済みの候補 + dropped が常に成り立つ。
    """
    keys = {candidate_key(c) for c in batch}
    to_challenge, duplicates, invented = [], [], []
    formulated_keys, duplicate_keys = set(), {}
    for scn in accepted_scenarios:
        src = str(scn.get("source_candidate") or "")
        if src not in keys:
            invented.append(scn.get("scenario_id"))
            continue
        if str(scn.get("duplicate_of") or "").strip():
            duplicates.append(scn)
            duplicate_keys.setdefault(src, scn["duplicate_of"])
            continue
        to_challenge.append(scn)
        formulated_keys.add(src)
    dropped = []
    for cand in batch:
        key = candidate_key(cand)
        if key in formulated_keys:
            continue
        if key in duplicate_keys:
            dropped.append({
                "key": key,
                "reason": "既存 scenario %s と実質同一（duplicate_of）"
                          % duplicate_keys[key]})
        else:
            dropped.append({
                "key": key,
                "reason": "定式化されなかった（観測可能な oracle に書き直せない"
                          "か、出自・出典の機械照合を通らない）"})
    return to_challenge, duplicates, dropped, invented


def load_today_doc(path):
    """同じ日付の既存記録。無ければ None。candidate-triage 以外なら例外。

    別種の創出記録を上書きしない（INC-008 の書き戻しと同じ注意）。
    """
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("kind") != "candidate-triage":
        raise ValueError(
            "同じ日付の創出記録が既に在る（kind=%r）。--today で別の日付を指す"
            "こと" % doc.get("kind"))
    return doc


def merge_batch(doc, batch, to_challenge, duplicates, dropped, verdicts,
                survivors, batch_meta):
    """一括の結果を記録へ足し込む（記帳は全候補。ADR-140）。"""
    considered = {tuple(entry) for entry in
                  map(tuple, doc.get("candidates_considered") or [])}
    for cand in batch:
        considered.add((cand["incident_id"], cand["index"]))
    doc["candidates_considered"] = [list(k) for k in sorted(
        considered, key=lambda k: (str(k[0]), str(k[1])))]

    by_id = {s.get("scenario_id"): s for s in doc.get("scenarios") or []}
    for scn in to_challenge:
        by_id[scn["scenario_id"]] = scn
    doc["scenarios"] = list(by_id.values())

    dup_by_id = {s.get("scenario_id"): s for s in doc.get("duplicates") or []}
    for scn in duplicates:
        dup_by_id[scn.get("scenario_id")] = scn
    doc["duplicates"] = list(dup_by_id.values())

    dropped_by_key = {d["key"]: d for d in doc.get("dropped") or []}
    for d in dropped:
        dropped_by_key[d["key"]] = d
    doc["dropped"] = [dropped_by_key[k] for k in sorted(dropped_by_key)]

    challenge = doc.get("challenge") or {"verdicts": [], "missing": [],
                                         "unrequested": []}
    challenge["verdicts"] = (challenge.get("verdicts") or []) + verdicts
    challenge["missing"] = sorted(
        set(challenge.get("missing") or [])
        | set(batch_meta.get("challenge_missing") or []))
    doc["challenge"] = challenge

    doc["survivors"] = sorted(set(doc.get("survivors") or []) | set(survivors))
    doc.setdefault("batches", []).append(batch_meta)
    return doc


def write_doc(path, doc):
    os.makedirs(SCENARIO_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--severities", default="P0,P1",
                        help="口へ入れる重大度（例: P0,P1）")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--today", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="SDK を呼ばずプロンプトの組み立てだけを検める")
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)

    severities = [s.strip() for s in args.severities.split(",") if s.strip()]
    candidates = orchestrator.cast_scenario_candidates()
    if not candidates:
        print(json.dumps({"status": "PASS", "note": "新規仮説候補が無い"},
                         ensure_ascii=False))
        return 0
    pending = select_untriaged(
        candidates, orchestrator.triaged_candidate_keys(), severities)
    if not pending:
        print(json.dumps({"status": "PASS",
                          "note": "未批判の候補は無い（対象重大度: %s）"
                                  % ",".join(severities)}, ensure_ascii=False))
        return 0

    principle_index = discover.principle_index()
    if not principle_index:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "規範の鍵を組めない（INGEST_NORMS が先）"},
                         ensure_ascii=False))
        return 3

    boundary = ("doctrine（Markdown の統治木を Hook・リンタ・監査・技能・CI で"
                "統治するプラグイン）と、その保証レーン。統制構造の要素は %s"
                % ", ".join(control_structure.ELEMENT_IDS))
    known_ids = existing_scenario_ids()
    batches = [pending[i:i + args.batch_size]
               for i in range(0, len(pending), args.batch_size)]
    batches = batches[:max(args.max_batches, 0)] or []

    if args.dry_run:
        out = []
        for batch in batches:
            prompt = prompts.build_candidate_formulation_prompt(
                batch, principle_index, boundary, known_ids)
            out.append({
                "batch": [candidate_key(c) for c in batch],
                "prompt_chars": len(prompt),
                "prompt_sha256": schemas.sha256_of(prompt),
            })
        print(json.dumps({
            "untriaged": len(pending), "severities": severities,
            "principle_keys": len(principle_index),
            "existing_scenario_ids": len(known_ids),
            "batches": out,
        }, ensure_ascii=False, indent=2))
        return 0

    from harness import sdk_lane  # SDK は実行時にだけ要る
    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    today = args.today or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(SCENARIO_DIR, "%s.json" % today)
    try:
        doc = load_today_doc(path)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "UNASSESSED", "reason": str(exc)},
                         ensure_ascii=False))
        return 3
    if doc is None:
        doc = {
            "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
            "kind": "candidate-triage",
            "date": today,
            "git_sha": _git(["rev-parse", "HEAD"]),
            "boundary": boundary,
            "scenarios": [],
            "duplicates": [],
            "survivors": [],
            "candidates_considered": [],
            "dropped": [],
        }

    worst = 0
    total_survivors = []
    for batch in batches:
        prompt = prompts.build_candidate_formulation_prompt(
            batch, principle_index, boundary, known_ids)
        f_rec = sdk_lane.run_one_shot(
            prompt, schema=schemas.SCENARIOS_SCHEMA,
            model=run_opts["model"], effort=run_opts["effort"],
            max_budget_usd=args.budget_per_call,
            cwd=tempfile.mkdtemp(prefix="assurance-triage-"),
            allowed_tools=(), max_turns=8, timeout_s=args.timeout)
        if f_rec["status"] != "PASS":
            print(json.dumps({"status": f_rec["status"], "phase": "FORMULATION",
                              "errors": f_rec["errors"]}, ensure_ascii=False))
            return 3 if f_rec["status"] == "UNASSESSED" else 4

        produced = (f_rec["structured_output"] or {}).get("scenarios", [])
        accepted, rejected = prompts.verify_scenarios(
            produced, [k for k, _t, _s in principle_index])
        to_challenge, duplicates, dropped, invented = partition_formulated(
            batch, accepted)

        verdicts, unrequested, missing = [], [], []
        c_status = "NOT-APPLICABLE"
        c_cost = 0.0
        survivors = []
        if to_challenge:
            c_rec = sdk_lane.run_one_shot(
                prompts.build_challenge_prompt(to_challenge),
                schema=schemas.CHALLENGE_SCHEMA,
                model=run_opts["model"], effort=run_opts["effort"],
                max_budget_usd=args.budget_per_call,
                cwd=tempfile.mkdtemp(prefix="assurance-triage-challenge-"),
                allowed_tools=(), max_turns=8, timeout_s=args.timeout)
            c_status = c_rec["status"]
            c_cost = float((c_rec.get("result_meta") or {})
                           .get("total_cost_usd") or 0)
            ids = [s["scenario_id"] for s in to_challenge]
            missing = list(ids)
            if c_rec["status"] == "PASS":
                verdicts, unrequested, missing = prompts.verify_verdicts(
                    (c_rec["structured_output"] or {}).get("verdicts", []), ids)
            by_id = {v["scenario_id"]: v for v in verdicts}
            survivors = [sid for sid in ids
                         if by_id.get(sid, {}).get("verdict") == "ACCEPT"]
            if c_rec["status"] != "PASS":
                worst = max(worst, 4)

        batch_meta = {
            "batch": [candidate_key(c) for c in batch],
            "formulation": {
                "status": f_rec["status"],
                "prompt_sha256": f_rec["prompt_sha256"],
                "model": f_rec["options"]["model"],
                "effort": f_rec["options"]["effort"],
                "cost_usd": (f_rec.get("result_meta") or {})
                .get("total_cost_usd"),
                "produced": len(produced),
                "accepted": len(accepted),
                "rejected": rejected,
                "invented_discarded": invented,
            },
            "challenge_status": c_status,
            "challenge_cost_usd": c_cost,
            "challenge_missing": missing,
            "unrequested": unrequested,
        }
        merge_batch(doc, batch, to_challenge, duplicates, dropped,
                    verdicts, survivors, batch_meta)
        # 一括ごとに書く —— 後の一括の停止で前の記帳を失わない。
        write_doc(path, doc)
        total_survivors.extend(survivors)

    print(json.dumps({
        "written": os.path.relpath(path, REPO_DIR),
        "considered": len(doc["candidates_considered"]),
        "to_challenge": len(doc["scenarios"]),
        "duplicates": len(doc["duplicates"]),
        "dropped": len(doc["dropped"]),
        "survivors": doc["survivors"],
        "still_untriaged": max(len(pending) - sum(len(b) for b in batches), 0),
    }, ensure_ascii=False, indent=2))
    if worst:
        return worst
    return 0 if total_survivors else 2


if __name__ == "__main__":
    sys.exit(main())
