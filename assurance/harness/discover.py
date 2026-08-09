#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""失敗仮説の創出と独立批判（DISCOVER → CHALLENGE。venv の python で動かす）。

独立性は構造で守る（ADR-115）:
- DISCOVER と CHALLENGE は**別々の**一回限りセッション。会話・計画・弁明を共有しない。
- CHALLENGE が受け取るのは DISCOVER の構造化 JSON だけで、その口しか無い
  （`prompts.build_challenge_prompt` の署名が引数を一つしか持たない）。
- 実装者はどちらの判定も書き換えない。批判の結果は結果として残す。

出発点の事実は**手で選ばない**。台帳から決定論で組む —— 未修正の事象・網羅台帳の
「対応計画あり」と判定不能・故障注入の残余リスク。選り好みで seed を作ると、
評価者は選んだ側の話しかしない。

usage: discover.py [--max-scenarios 8] [--dry-run]

終了コード: 0=創出と批判が済んだ / 2=批判で受理ゼロ / 3=UNASSESSED / 4=途中停止。
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

from harness import (books, control_structure, ledger_io,  # noqa: E402
                     model_policy,
                     prompts, schemas, sdk_lane)

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")
CATALOG_DIR = os.path.join(LEDGER_DIR, "catalogs")
SCENARIO_DIR = os.path.join(LEDGER_DIR, "scenarios")
INCIDENTS_PATH = os.path.join(LEDGER_DIR, "incidents.json")


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def principle_index():
    """三冊の鍵をまとめて返す。創出は観点を跨いでよい（批判が絞る）。"""
    out, seen = [], set()
    for book_id in ("stpa", "jerg", "cast"):
        path = os.path.join(CATALOG_DIR, "%s-principles.json" % book_id)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                cat = json.load(f)
        except (OSError, ValueError):
            continue
        for p in cat.get("principles", []):
            key = (p.get("dedupe_key") or "").strip()
            if key and key not in seen:
                seen.add(key)
                out.append((key, p.get("title") or "", p.get("statement") or ""))
    return out


def seed_facts(limit_per_kind=8):
    """出発点の事実を台帳から決定論で組む（手で選ばない）。

    - 未修正の事象（fixed が真でないもの）
    - 網羅台帳の「対応計画あり」と判定不能（体系が持っていないと自ら言った箇所）
    - 故障注入の残余リスク（攻撃で測れていないと自ら言った箇所）
    """
    facts = []
    try:
        with open(INCIDENTS_PATH, encoding="utf-8") as f:
            for inc in json.load(f).get("incidents", [])[:limit_per_kind * 2]:
                if inc.get("fixed") is True:
                    continue
                # 受容済み（cost_accepted）の事象は種にしない（ADR-144）。
                # 所有者が費用として受け入れた形を新しい仮説の種へ流すと、
                # 裁定済みの選択肢を毎反復問い直す「消えない行動」になる。
                if inc.get("cost_accepted"):
                    continue
                facts.append("未修正の事象 %s: %s"
                             % (inc.get("id"), (inc.get("summary") or "")[:180]))
    except (OSError, ValueError):
        pass

    for book_id in sorted(books.BOOKS):
        path = os.path.join(CATALOG_DIR, "%s-coverage.json" % book_id)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f).get("entries", [])
        except (OSError, ValueError):
            continue
        gaps = [e for e in entries
                if e.get("disposition") in ("対応計画あり", "UNKNOWN", "UNASSESSED")
                and e.get("gap")]
        for e in gaps[:limit_per_kind]:
            facts.append("網羅の穴（%s / %s）: %s ｜ 足りないもの: %s"
                         % (book_id, e.get("disposition"),
                            (e.get("title") or "")[:80], (e.get("gap") or "")[:160]))

    for name in sorted(os.listdir(LEDGER_DIR)) if os.path.isdir(LEDGER_DIR) else []:
        if not (name.startswith("mutations-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(LEDGER_DIR, name), encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        for risk in (doc.get("residual_risks") or [])[:limit_per_kind]:
            facts.append("攻撃で測れていない残余リスク: %s" % str(risk)[:200])
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-scenarios", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--today", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    facts = seed_facts()
    keys = principle_index()
    if not facts or not keys:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "台帳から出発点か規範の鍵を組めない"},
                         ensure_ascii=False))
        return 3

    boundary = ("doctrine（Markdown の統治木を Hook・リンタ・監査・技能・CI で統治する"
                "プラグイン）と、その保証レーン。統制構造の要素は %s"
                % ", ".join(control_structure.ELEMENT_IDS))
    discover_prompt = prompts.build_discover_prompt(facts, boundary, keys)

    if args.dry_run:
        print(json.dumps({"seed_facts": len(facts), "principle_keys": len(keys),
                          "prompt_chars": len(discover_prompt),
                          "prompt_sha256": schemas.sha256_of(discover_prompt)},
                         ensure_ascii=False, indent=2))
        return 0

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    # --- DISCOVER（一つ目のセッション）---
    d_rec = sdk_lane.run_one_shot(
        discover_prompt, schema=schemas.SCENARIOS_SCHEMA,
        model=run_opts["model"], effort=run_opts["effort"],
        max_budget_usd=args.budget_per_call,
        cwd=tempfile.mkdtemp(prefix="assurance-discover-"),
        allowed_tools=(), max_turns=8, timeout_s=args.timeout)
    if d_rec["status"] != "PASS":
        print(json.dumps({"status": d_rec["status"], "phase": "DISCOVER",
                          "errors": d_rec["errors"]}, ensure_ascii=False))
        return 3 if d_rec["status"] == "UNASSESSED" else 4

    scenarios = (d_rec["structured_output"] or {}).get("scenarios", [])
    scenarios = scenarios[: args.max_scenarios]
    accepted, rejected = prompts.verify_scenarios(scenarios,
                                                  [k for k, _t, _s in keys])
    if not accepted:
        print(json.dumps({"status": "FAIL", "phase": "DISCOVER",
                          "reason": "出典の照合を通った候補がゼロ",
                          "rejected": len(rejected)}, ensure_ascii=False))
        return 2

    # --- CHALLENGE（別セッション。渡すのは構造化 JSON だけ）---
    c_rec = sdk_lane.run_one_shot(
        prompts.build_challenge_prompt(accepted),
        schema=schemas.CHALLENGE_SCHEMA,
        model=run_opts["model"], effort=run_opts["effort"],
        max_budget_usd=args.budget_per_call,
        cwd=tempfile.mkdtemp(prefix="assurance-challenge-"),
        allowed_tools=(), max_turns=8, timeout_s=args.timeout)

    verdicts, unrequested, missing = [], [], [s["scenario_id"] for s in accepted]
    if c_rec["status"] == "PASS":
        verdicts, unrequested, missing = prompts.verify_verdicts(
            (c_rec["structured_output"] or {}).get("verdicts", []),
            [s["scenario_id"] for s in accepted])

    by_id = {v["scenario_id"]: v for v in verdicts}
    survivors = [s for s in accepted
                 if by_id.get(s["scenario_id"], {}).get("verdict") == "ACCEPT"]

    today = args.today or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%d")
    os.makedirs(SCENARIO_DIR, exist_ok=True)
    doc = {
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "discover-challenge",
        "date": today,
        "git_sha": _git(["rev-parse", "HEAD"]),
        "seed_facts": facts,
        "boundary": boundary,
        "discover": {
            "status": d_rec["status"],
            "prompt_sha256": d_rec["prompt_sha256"],
            "model": d_rec["options"]["model"],
            "effort": d_rec["options"]["effort"],
            "cost_usd": (d_rec.get("result_meta") or {}).get("total_cost_usd"),
            "produced": len(scenarios),
            "accepted": len(accepted),
            "rejected": rejected,
        },
        "challenge": {
            "status": c_rec["status"],
            "prompt_sha256": c_rec["prompt_sha256"],
            "cost_usd": (c_rec.get("result_meta") or {}).get("total_cost_usd"),
            "verdicts": verdicts,
            "unrequested": unrequested,
            "missing": missing,   # 沈黙は ACCEPT と読まない
            "errors": c_rec["errors"],
        },
        "scenarios": accepted,
        "survivors": [s["scenario_id"] for s in survivors],
    }
    path = os.path.join(SCENARIO_DIR, "%s.json" % today)
    ledger_io.write_json(path, doc)

    print(json.dumps({
        "written": os.path.relpath(path, REPO_DIR),
        "produced": len(scenarios), "accepted": len(accepted),
        "challenge_status": c_rec["status"],
        "survivors": len(survivors), "missing_verdicts": len(missing),
        "cost_usd": round(
            float((d_rec.get("result_meta") or {}).get("total_cost_usd") or 0)
            + float((c_rec.get("result_meta") or {}).get("total_cost_usd") or 0), 4),
    }, ensure_ascii=False, indent=2))
    if c_rec["status"] != "PASS":
        return 4
    return 0 if survivors else 2


if __name__ == "__main__":
    sys.exit(main())
