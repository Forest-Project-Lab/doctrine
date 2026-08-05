#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""事象 → 統制欠陥と先行指標（CAST_ANALYSIS。venv の python で動かす）。

- 役割は model_policy の evaluation（最低線 opus / effort high。ADR-116）。
- 入力は事象の構造化記録・統制構造・CAST カタログだけ。実装者の会話・弁明は
  渡さない（CHALLENGE と同じ独立性。ADR-115）。
- 統制欠陥の参照先（統制要素 id・規範の dedupe_key）はカタログと機械照合し、
  実在しない参照を持つ欠陥は却下する。全部却下されたら分析は成立していない。
- 事象を閉じてよいのは、先行指標が定義された分析が揃ったときだけ
  （orchestrator の CAST_DONE の guard と同じ判定を prompts が持つ）。
  修正済みであることは閉じる理由にならない。

usage: cast_analysis.py [--incident ID | --all] [--dry-run]

終了コード: 0=分析成立 / 2=分析が成立しない(FAIL) / 3=UNASSESSED(前提欠如)
            / 4=途中停止(UNKNOWN・予算)
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

from harness import (control_structure, model_policy, prompts,  # noqa: E402
                     schemas, sdk_lane)

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")
CATALOG_DIR = os.path.join(LEDGER_DIR, "catalogs")
CAST_DIR = os.path.join(LEDGER_DIR, "cast")
INCIDENTS_PATH = os.path.join(LEDGER_DIR, "incidents.json")


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def load_principle_index():
    """CAST カタログを (dedupe_key, title, statement) の列にする。

    選り好みで規範を絞ると「都合のよい出典だけを見た」分析になるので、
    絞らずに全件を渡す（重複鍵は最初の一件に寄せる）。
    """
    path = os.path.join(CATALOG_DIR, "cast-principles.json")
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


def load_incidents():
    with open(INCIDENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def update_incident(incident_id, fields):
    """台帳の一件だけを書き換える（他の列を巻き込まない）。

    分析は分単位で走るので、その間に台帳へ別の事象が積まれ得る。全体を
    読んだときの写しで上書きすると、後から積まれた事象が消える（実際に
    INC-007 の追記が消えかけた）。書く直前に読み直し、対象の id の項だけを
    更新する。対象が消えていれば書かずに False を返す。
    """
    doc = load_incidents()
    for inc in doc.get("incidents", []):
        if inc.get("id") == incident_id:
            inc.update(fields)
            break
    else:
        return False
    with open(INCIDENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return True


def analysis_path(incident_id):
    return os.path.join(CAST_DIR, "%s.json" % incident_id)


def analyze_one(incident, principle_index, *, timeout_s, budget_usd):
    """一件の事象を分析し、(記録, 分析成立か) を返す。

    分析成立の条件（すべて満たすときだけ True）:
    1. SDK 実行が PASS（schema にレーン側再検証でも適合）
    2. 参照照合を通った統制欠陥が一つ以上残る
    3. 先行指標が定義されている（CAST_DONE の guard）
    """
    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    prompt = prompts.build_cast_analysis_prompt(
        incident, control_structure.as_prompt_text(), principle_index)
    isolated_cwd = tempfile.mkdtemp(prefix="assurance-cast-")
    record = sdk_lane.run_one_shot(
        prompt,
        schema=schemas.CAST_ANALYSIS_SCHEMA,
        model=run_opts["model"],
        effort=run_opts["effort"],
        max_budget_usd=budget_usd,
        cwd=isolated_cwd,
        allowed_tools=(),
        max_turns=1,
        timeout_s=timeout_s,
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    known_keys = [k for k, _t, _s in principle_index]
    accepted, rejected, guard_ok = [], [], False
    analysis = record.get("structured_output") if record["status"] == "PASS" else None
    if analysis:
        accepted, rejected = prompts.verify_cast_analysis(
            analysis, control_structure.ELEMENT_IDS, known_keys)
        guard_ok = prompts.leading_indicators_defined(analysis)

    settled = bool(analysis) and bool(accepted) and guard_ok
    if analysis and not settled:
        # 走ったが分析の要件を満たさない。緑へ倒さず FAIL のまま残す。
        record["status"] = "FAIL"
        record["oracle"] = "分析要件の不足: %s" % ", ".join(
            filter(None, [
                None if accepted else "参照照合を通った統制欠陥がゼロ",
                None if guard_ok else "先行指標が未定義（CAST_DONE の guard）"]))

    record.update({
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "cast-analysis",
        "incident_id": incident["id"],
        "incident_sha256": schemas.sha256_of(incident),
        "control_structure_ids": list(control_structure.ELEMENT_IDS),
        "principles_offered": len(principle_index),
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "analysis": analysis,
        "accepted_flaws": accepted,
        "rejected_flaws": rejected,
        "leading_indicators_defined": guard_ok,
        "settled": settled,
    })
    # 生の応答本文は分析本体と重複するので台帳へは残さない。
    record.pop("result_text_head", None)
    return record, settled


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident", default=None,
                        help="対象の事象 id（既定: 未分析の先頭一件）")
    parser.add_argument("--all", action="store_true",
                        help="未分析の事象をすべて扱う")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--dry-run", action="store_true",
                        help="SDK を呼ばずプロンプトの組み立てだけを検める")
    args = parser.parse_args(argv)

    if not os.path.isfile(INCIDENTS_PATH):
        print(json.dumps({"status": "UNASSESSED", "reason": "事象台帳が無い"},
                         ensure_ascii=False))
        return 3

    missing = control_structure.missing_implementations()
    if missing:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "統制構造が実体を失っている: %s" % missing},
                         ensure_ascii=False))
        return 3

    principle_index = load_principle_index()
    if not principle_index:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "CAST カタログが無い（INGEST_NORMS が先）"},
                         ensure_ascii=False))
        return 3

    doc = load_incidents()
    pending = [i for i in doc["incidents"]
               if i.get("cast_analysis") in (None, "pending")]
    if args.incident:
        targets = [i for i in doc["incidents"] if i["id"] == args.incident]
        if not targets:
            print(json.dumps({"status": "UNASSESSED",
                              "reason": "未知の事象 id: %s" % args.incident},
                             ensure_ascii=False))
            return 3
    elif args.all:
        targets = pending
    else:
        targets = pending[:1]

    if not targets:
        print(json.dumps({"status": "PASS", "note": "未分析の事象は無い"},
                         ensure_ascii=False))
        return 0

    if args.dry_run:
        for inc in targets:
            prompt = prompts.build_cast_analysis_prompt(
                inc, control_structure.as_prompt_text(), principle_index)
            print(json.dumps({
                "incident": inc["id"], "prompt_chars": len(prompt),
                "prompt_sha256": schemas.sha256_of(prompt),
                "principles_offered": len(principle_index),
                "elements": len(control_structure.ELEMENT_IDS),
            }, ensure_ascii=False))
        return 0

    os.makedirs(CAST_DIR, exist_ok=True)
    summary, worst = [], 0
    for inc in targets:
        record, settled = analyze_one(
            inc, principle_index,
            timeout_s=args.timeout, budget_usd=args.budget_per_call)
        with open(analysis_path(inc["id"]), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

        if settled:
            fields = {
                "cast_analysis": "done",
                "cast_analysis_ref": os.path.relpath(
                    analysis_path(inc["id"]), REPO_DIR),
                "cast_analyzed_at": record["generated_at"],
            }
        else:
            # 閉じない。次の実行が同じ事象をもう一度引く。
            fields = {"cast_analysis": "pending",
                      "cast_analysis_last_status": record["status"]}
        inc.update(fields)
        update_incident(inc["id"], fields)

        cost = ((record.get("result_meta") or {}).get("total_cost_usd")) or 0.0
        summary.append({
            "incident": inc["id"], "status": record["status"],
            "settled": settled,
            "accepted_flaws": len(record["accepted_flaws"]),
            "rejected_flaws": len(record["rejected_flaws"]),
            "leading_indicators": len(
                (record.get("analysis") or {}).get("leading_indicators") or []),
            "cost_usd": round(float(cost), 4),
            "oracle": record.get("oracle"),
            "errors": record.get("errors"),
        })
        worst = max(worst, {"PASS": 0, "FAIL": 2,
                            "UNASSESSED": 3, "UNKNOWN": 4}.get(record["status"], 1))
        print(json.dumps(summary[-1], ensure_ascii=False), flush=True)

    print(json.dumps({"analyzed": summary}, ensure_ascii=False, indent=2))
    return worst


if __name__ == "__main__":
    sys.exit(main())
