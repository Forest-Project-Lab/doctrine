#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""想定の独立検証（ADR-126・ADR-144）。

観測は observe_assumptions.py（決定論）が書く。ここは、その観測を独立の
評価セッションへ渡し、想定が観測に照らして成り立つかの判定を買い、
verified_by の欄を「誰が・何を・どう検めたか」で埋める駆動器である。

保証限界:
- 予防: 何も予防しない。判定は評価者のものであり、実装者は書き換えない
  （ADR-115。判定は observation_history へ追記のみ）。
- 検出: AI の一致は客観的証拠ではない（残余リスク。ADR-116 の床だけ守る）。
- 委ねる: 観測そのものの正しさは observe_assumptions.py と実ファイル系に委ねる。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import model_policy, observe_assumptions, prompts, schemas, sdk_lane  # noqa: E402

ASSUMPTIONS_PATH = observe_assumptions.ASSUMPTIONS_PATH


def build_input(row):
    """評価者へ渡す構造化入力。会話・弁明の口を持たない。"""
    return {
        "asm_id": row.get("id"),
        "assumption": row.get("assumption"),
        "leading_indicators": row.get("leading_indicators", []),
        "observations": row.get("observations", []),
        "observation_history": row.get("observation_history", []),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="想定の独立検証")
    parser.add_argument("--today", required=True)
    parser.add_argument("--asm", help="対象の想定 id（省略時は全件）")
    parser.add_argument("--ledger", default=ASSUMPTIONS_PATH)
    parser.add_argument("--budget-per-call", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    opts = parser.parse_args(argv)

    with open(opts.ledger, encoding="utf-8") as f:
        ledger = json.load(f)
    rows = [r for r in ledger.get("assumptions", [])
            if not opts.asm or r.get("id") == opts.asm]
    if not rows:
        print("対象の想定が無い", file=sys.stderr)
        return 2

    role = model_policy.options_for("evaluation")
    model, effort = role["model"], role["effort"]
    model_policy.assert_evaluation_floor(model, effort)
    results = []
    for row in rows:
        payload = build_input(row)
        prompt = prompts.build_assumption_verification_prompt(payload)
        if opts.dry_run:
            results.append({"asm_id": row.get("id"), "dry_run": True,
                            "prompt_chars": len(prompt)})
            continue
        rec = sdk_lane.run_one_shot(
            prompt, schema=schemas.ASSUMPTION_VERDICT_SCHEMA,
            model=model, effort=effort,
            timeout_s=opts.timeout, max_budget_usd=opts.budget_per_call)
        out = rec.get("structured_output") or {}
        verdict = out.get("holds")
        if rec.get("status") != "PASS" or out.get("asm_id") != row.get("id") \
                or verdict not in ("PASS", "FAIL", "UNKNOWN"):
            results.append({"asm_id": row.get("id"), "status": "UNASSESSED",
                            "reason": "評価が成立しない（応答不備か対象違い）"})
            continue
        entry = {
            "date": opts.today,
            "state": verdict,
            "observed": ["独立検証の判定: %s" % verdict] +
                        [r[:200] for r in (out.get("reasons") or [])],
            "observed_by": "verify_assumptions.py 経由の独立評価セッション"
                           "（%s×%s）" % (model, effort),
        }
        row.setdefault("observation_history", []).append(entry)
        observe_assumptions.set_verified_by(
            ledger, row.get("id"),
            "独立の評価セッション %s×%s（%s。verify_assumptions.py が観測を渡し、"
            "判定 %s を observation_history へ追記）"
            % (model, effort, opts.today, verdict))
        results.append({"asm_id": row.get("id"), "holds": verdict,
                        "cost_usd": rec.get("cost_usd")})
    if not opts.dry_run:
        with open(opts.ledger, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
