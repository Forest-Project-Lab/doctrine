#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""批判を生き残った scenario の検証計画審査（FORMALIZE。venv の python で動かす）。

- 役割は model_policy の evaluation（最低線 opus / effort high。ADR-116）。
- 入力は直近の創出記録の生き残り scenario と jerg カタログだけ。実装者の会話・
  弁明は渡さない（CHALLENGE と同じ独立性。ADR-115）。
- 計画の出典（jerg の dedupe_key）は機械照合する。解決する鍵を一つでも保つ計画は
  残して欠陥を刻み、ゼロの計画は受け取らない（ADR-121 の主張単位の規則）。
- APPROVE も REJECT も UNKNOWN も消化と数える。挙がり続けるのは計画が返らなかった
  沈黙だけ（orchestrator.unformalized_survivors が読む段。ADR-138）。
- 承認（REPRODUCE_RED へ進んでよい）は prompts.oracle_observable が決定論で検める。
  実装の前に観測できない oracle を持つ計画は、承認とは読まれない。

usage: formalize.py [--budget-per-call 4.0] [--timeout 900] [--today 日付]
                    [--dry-run]

一回の実行で扱うのは、未審査の生き残り最大 6 件（一つの一回限りセッション）。
終了コード: 0=計画が台帳へ入った / 2=照合を通った計画がゼロ / 3=UNASSESSED
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

from harness import ledger_io, model_policy, prompts, schemas, sdk_lane  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")
CATALOG_DIR = os.path.join(LEDGER_DIR, "catalogs")
SCENARIO_DIR = os.path.join(LEDGER_DIR, "scenarios")
FORMALIZE_DIR = os.path.join(LEDGER_DIR, "formalize")

# 一つの一回限りセッションへ渡す scenario の上限。多く渡すほど一件あたりの
# 審査が薄まる（INC-014 で見た尺度の問題と同じ向き）。残りは次の実行が拾う
# —— 台帳が再開を持つので進捗は失われない。
BATCH_LIMIT = 6


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def load_jerg_index():
    """jerg カタログを (dedupe_key, title, statement) の列にする。

    絞らずに全件を渡す（選り好みで規範を絞ると「都合のよい出典だけを見た」
    審査になる。cast_analysis と同じ流儀）。
    """
    path = os.path.join(CATALOG_DIR, "jerg-principles.json")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        cat = json.load(f)
    index, seen = [], set()
    for p in cat.get("principles", []):
        key = (p.get("dedupe_key") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        index.append((key, p.get("title") or "", p.get("statement") or ""))
    return index


def latest_scenarios_doc():
    """直近の創出記録（ファイル名の辞書順の最後）。無ければ (None, None)。"""
    if not os.path.isdir(SCENARIO_DIR):
        return None, None
    names = sorted(n for n in os.listdir(SCENARIO_DIR) if n.endswith(".json"))
    if not names:
        return None, None
    path = os.path.join(SCENARIO_DIR, names[-1])
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), path
    except (OSError, ValueError):
        return None, path


def planned_scenario_ids():
    """既に計画（どの verdict でも）を持つ scenario の id 集合。

    APPROVE も REJECT も UNKNOWN も消化である。残るのは沈黙だけ（ADR-138）。
    """
    out = set()
    if not os.path.isdir(FORMALIZE_DIR):
        return out
    for name in sorted(os.listdir(FORMALIZE_DIR)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(FORMALIZE_DIR, name), encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for plan in doc.get("plans") or []:
            if isinstance(plan, dict) and plan.get("scenario_id"):
                out.add(plan["scenario_id"])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--today", default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="SDK を呼ばずプロンプトの組み立てだけを検める")
    args = parser.parse_args(argv)

    scn_doc, scn_path = latest_scenarios_doc()
    if not scn_doc:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "創出の記録が無い（DISCOVER が先）"},
                         ensure_ascii=False))
        return 3
    survivors = scn_doc.get("survivors") or []
    by_id = {s.get("scenario_id"): s for s in scn_doc.get("scenarios") or []
             if isinstance(s, dict)}
    pending = [sid for sid in survivors
               if sid not in planned_scenario_ids() and sid in by_id]
    if not pending:
        print(json.dumps({"status": "PASS",
                          "note": "未審査の生き残りは無い"}, ensure_ascii=False))
        return 0
    targets = pending[:BATCH_LIMIT]

    principle_index = load_jerg_index()
    if not principle_index:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "jerg カタログが無い（INGEST_NORMS が先）"},
                         ensure_ascii=False))
        return 3

    prompt = prompts.build_formalize_prompt(
        [by_id[sid] for sid in targets], principle_index)

    if args.dry_run:
        print(json.dumps({
            "scenarios_source": os.path.relpath(scn_path, REPO_DIR),
            "survivors": len(survivors),
            "pending": len(pending),
            "targets": targets,
            "principle_keys": len(principle_index),
            "prompt_chars": len(prompt),
            "prompt_sha256": schemas.sha256_of(prompt),
        }, ensure_ascii=False, indent=2))
        return 0

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    record = sdk_lane.run_one_shot(
        prompt, schema=schemas.FORMALIZE_PLAN_SCHEMA,
        model=run_opts["model"], effort=run_opts["effort"],
        max_budget_usd=args.budget_per_call,
        cwd=tempfile.mkdtemp(prefix="assurance-formalize-"),
        allowed_tools=(), max_turns=8, timeout_s=args.timeout)
    if record["status"] != "PASS":
        print(json.dumps({"status": record["status"], "phase": "FORMALIZE",
                          "errors": record["errors"]}, ensure_ascii=False))
        return 3 if record["status"] == "UNASSESSED" else 4

    plans = (record["structured_output"] or {}).get("plans", [])
    matched, unrequested, missing = prompts.verify_formalize_plans(
        plans, [k for k, _t, _s in principle_index], targets)

    today = args.today or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%d")
    now = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(FORMALIZE_DIR, exist_ok=True)
    path = os.path.join(FORMALIZE_DIR, "%s.json" % today)

    # 同じ日の既存の計画は消さない（分割審査の後半が前半を潰す形を作らない。
    # INC-008 の書き戻しと同じ注意）。同じ id の計画は新しい方が勝つ。
    prior_plans, prior_requested = [], []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                prior = json.load(f)
            prior_plans = [p for p in prior.get("plans") or []
                           if isinstance(p, dict)]
            prior_requested = list(prior.get("requested") or [])
        except (OSError, ValueError):
            pass
    new_ids = {p["scenario_id"] for p in matched}
    plans_out = [p for p in prior_plans
                 if p.get("scenario_id") not in new_ids] + matched
    requested_out = sorted(set(prior_requested) | set(targets))
    planned_ids = {p.get("scenario_id") for p in plans_out}
    missing_out = [sid for sid in requested_out if sid not in planned_ids]

    cost = float((record.get("result_meta") or {}).get("total_cost_usd") or 0)
    approved = sorted(p["scenario_id"] for p in plans_out
                      if prompts.oracle_observable(p))
    doc = {
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "formalize-plans",
        "date": today,
        "generated_at": now,
        "git_sha": _git(["rev-parse", "HEAD"]),
        "scenarios_source": os.path.relpath(scn_path, REPO_DIR),
        "requested": requested_out,
        "plans": plans_out,
        "missing": missing_out,   # 沈黙は APPROVE と読まない
        "unrequested": unrequested,
        "citation_defects": sorted(p["scenario_id"] for p in plans_out
                                   if p.get("citation_defect")),
        "prompt_sha256": record["prompt_sha256"],
        "model": record["options"]["model"],
        "effort": record["options"]["effort"],
        "cost_usd": round(cost, 4),
        "approved": approved,
    }
    ledger_io.write_json(path, doc)

    print(json.dumps({
        "written": os.path.relpath(path, REPO_DIR),
        "requested": len(targets),
        "planned": len(matched),
        "approved": approved,
        "rejected_or_unknown": sorted(
            p["scenario_id"] for p in matched
            if p.get("verdict") != "APPROVE"),
        "missing": missing_out,
        "unrequested": len(unrequested),
        "still_pending": len(pending) - len(targets),
        "cost_usd": round(cost, 4),
    }, ensure_ascii=False, indent=2))
    return 0 if matched else 2


if __name__ == "__main__":
    sys.exit(main())
