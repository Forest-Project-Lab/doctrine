#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""検証原則 × doctrine の現状 → 網羅台帳の五値（MAP_COVERAGE。venv の python で動かす）。

- 役割は model_policy の evaluation（最低線 opus / effort high。ADR-116）。
- 入力は原則の束と `system_index` の索引だけ。評価者にツールも設定も渡さない
  （`setting_sources=[]`・空の一時 cwd・`allowed_tools=()`）。
- 返ってきた証拠ポインタは索引と機械照合する。解決しないポインタを根拠にした
  「実装・試験・証拠あり」は UNKNOWN へ落とす（ADR-115 の「証拠ポインタの無い
  『実装・試験・証拠あり』は書かない」をコードで守る）。
- 再開可能: すでに UNKNOWN 以外が入っている項は飛ばす。束ごとに台帳へ保存する。

usage: map_coverage.py --book jerg [--batch-size 25] [--max-batches 3] [--dry-run]

終了コード: 0=全件割当済み / 2=一部FAIL / 3=UNASSESSED(前提欠如) / 4=途中停止。
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

from harness import (books, model_policy, prompts, schemas,  # noqa: E402
                     sdk_lane, system_index)

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
CATALOG_DIR = os.path.join(LANE_DIR, "ledger", "catalogs")


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def _paths(book_id):
    return (os.path.join(CATALOG_DIR, "%s-principles.json" % book_id),
            os.path.join(CATALOG_DIR, "%s-coverage.json" % book_id))


def load_pair(book_id):
    cat_path, cov_path = _paths(book_id)
    for path in (cat_path, cov_path):
        if not os.path.isfile(path):
            return None, None
    with open(cat_path, encoding="utf-8") as f:
        cat = json.load(f)
    with open(cov_path, encoding="utf-8") as f:
        cov = json.load(f)
    return cat, cov


def save_coverage(book_id, cov):
    _cat_path, cov_path = _paths(book_id)
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(cov, f, ensure_ascii=False, indent=2)
        f.write("\n")


def principle_details(cat, cov_entries):
    """台帳の key → カタログの原則本体。台帳と同じ並びで返す。

    台帳の key はカタログの並びから決定論で作られている（coverage.principle_key）。
    ここでは題と行範囲の一致で引き当て、引けないものは飛ばす（作らない）。
    """
    by_title = {}
    for p in cat.get("principles", []):
        by_title.setdefault((p.get("title"), p.get("source_lines")), p)
    out = []
    for e in cov_entries:
        p = by_title.get((e.get("title"), e.get("source_lines")))
        if p is None:
            continue
        out.append({
            "key": e["key"],
            "title": p.get("title"),
            "statement": p.get("statement"),
            "category": p.get("category"),
            "applicability": p.get("applicability"),
            "suggested_oracle": p.get("suggested_oracle"),
        })
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=sorted(books.BOOKS))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cat, cov = load_pair(args.book)
    if cov is None:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "カタログか台帳が無い（先に抽出と init）"},
                         ensure_ascii=False))
        return 3

    idx = system_index.build()
    if not idx["documents"] or not idx["scripts"]:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "現状の索引が組めない（統治木・配布物が読めない）"},
                         ensure_ascii=False))
        return 3
    index_text = system_index.as_prompt_text(idx)

    # 未評価だけを引く。評価の結果としての UNKNOWN（assigned_at つき）は割当済みで
    # あり、引き直すと同じ判定不能を永久に買い直すことになる。
    todo_entries = [e for e in cov["entries"]
                    if e.get("disposition") == "UNKNOWN" and not e.get("assigned_at")]
    todo = principle_details(cat, todo_entries)
    batches = [todo[i:i + args.batch_size]
               for i in range(0, len(todo), args.batch_size)]
    if args.max_batches is not None:
        batches = batches[: args.max_batches]

    print("book=%s 未割当=%d 束=%d 索引=%d 文字 sha=%s"
          % (args.book, len(todo), len(batches), len(index_text),
             idx["sha256"][:12]), flush=True)

    if args.dry_run:
        for i, batch in enumerate(batches[:2]):
            prompt = prompts.build_map_coverage_prompt(batch, index_text)
            print(json.dumps({"batch": i, "items": len(batch),
                              "prompt_chars": len(prompt),
                              "prompt_sha256": schemas.sha256_of(prompt)},
                             ensure_ascii=False))
        return 0

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])
    by_key = {e["key"]: e for e in cov["entries"]}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_sha = _git(["rev-parse", "HEAD"])

    had_fail = False
    stopped = None
    totals = {"assigned": 0, "downgraded": 0, "rejected": 0, "cost_usd": 0.0}
    for i, batch in enumerate(batches):
        prompt = prompts.build_map_coverage_prompt(batch, index_text)
        record = sdk_lane.run_one_shot(
            prompt,
            schema=schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            model=run_opts["model"],
            effort=run_opts["effort"],
            max_budget_usd=args.budget_per_call,
            cwd=tempfile.mkdtemp(prefix="assurance-mapcov-"),
            allowed_tools=(),
            max_turns=1,
            timeout_s=args.timeout,
        )
        cost = ((record.get("result_meta") or {}).get("total_cost_usd")) or 0.0
        totals["cost_usd"] = round(totals["cost_usd"] + float(cost), 4)

        if record["status"] == "UNASSESSED":
            stopped = "レーン前提の欠如: %s" % record["errors"]
            break
        if record["status"] == "UNKNOWN":
            stopped = "観測不能(束 %d): %s" % (i, record["errors"])
            break
        if record["status"] != "PASS":
            had_fail = True
            continue

        out = record["structured_output"] or {}
        accepted, downgraded, rejected = prompts.verify_coverage_assignments(
            out.get("assignments", []),
            lambda p: system_index.resolve_pointer(idx, p),
            [b["key"] for b in batch])
        for a in accepted + downgraded:
            entry = by_key.get(a["key"])
            if entry is None:
                continue
            entry.update({
                "disposition": a["disposition"],
                "reason": a.get("reason"),
                "evidence": a.get("evidence") or None,
                "gap": a.get("gap"),
                "recheck_trigger": a.get("recheck_trigger"),
                "confidence": a.get("confidence"),
                "assigned_at": now,
                "assigned_by": {
                    "model": record["options"]["model"],
                    "effort": record["options"]["effort"],
                    "prompt_sha256": record["prompt_sha256"],
                    "index_sha256": idx["sha256"],
                    "git_sha": git_sha,
                },
            })
            if a.get("unresolved_evidence"):
                entry["unresolved_evidence"] = a["unresolved_evidence"]
            if a.get("original_disposition"):
                entry["original_disposition"] = a["original_disposition"]
        totals["assigned"] += len(accepted)
        totals["downgraded"] += len(downgraded)
        totals["rejected"] += len(rejected)
        cov["index_sha256"] = idx["sha256"]
        save_coverage(args.book, cov)   # 束ごとに保存（途中終了しても失わない）
        print("束 %d/%d 件=%d 受理=%d 降格=%d 却下=%d 費用=%.3f"
              % (i + 1, len(batches), len(batch), len(accepted),
                 len(downgraded), len(rejected), cost), flush=True)

    remaining = sum(1 for e in cov["entries"]
                    if e.get("disposition") == "UNKNOWN" and not e.get("assigned_at"))
    judged_unknown = sum(1 for e in cov["entries"]
                         if e.get("disposition") == "UNKNOWN" and e.get("assigned_at"))
    # 鍵の名は unmapped 側で揃える（五値の UNASSESSED と数を混ぜない。orchestrator
    # の coverage_status と同じ語で呼ぶ）。
    summary = dict(totals, book=args.book, remaining_unmapped=remaining,
                   judged_unknown=judged_unknown, stopped=stopped)
    print(json.dumps(summary, ensure_ascii=False))
    if stopped:
        return 4
    if had_fail:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
