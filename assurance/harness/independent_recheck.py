#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""束で回した網羅の判定を、抜取りで独立に判定し直す（venv の python で動かす）。

束で速く回すと質が落ちるのではないか —— この問いは、**同じ評価器にもう一度
訊いて一致を数えても答えられない**。AI の一致は客観的証拠ではなく、同系 model
の共通原因故障は残余リスクとして残る（運転手順 §4）。だからここは一致率を
成果として持たない。読むのは**不一致の中身**である。

やること:
- すでに判定の付いた項から、種を与えて決定論に標本を引く（実時計を読まない）。
- 標本を、前の判定を渡さない一回限りセッションで判定し直す。プロンプトは
  `prompts.build_map_coverage_prompt` だけを使い、証拠ポインタは同じ機械照合
  にかける（ADR-118）。
- 判定が割れた項は**判定を取り下げ、未割当の UNKNOWN へ戻す**。割当済みの
  UNKNOWN のままでは正本が拾わない（評価の結論と未評価は別物。INC-006）ので、
  `assigned_at` を落として初めて MAP_COVERAGE が拾い直す。
- 一致した項には触れない。実装者は評価者の判定を書き換えない（ADR-115）。

usage: independent_recheck.py --book stpa [--sample 25] [--seed 1] [--dry-run]

終了コード: 0=不一致なし / 1=不一致あり(台帳へ戻した) / 3=UNASSESSED(前提欠如)。
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import (books, map_coverage, model_policy, prompts,  # noqa: E402
                     schemas, sdk_lane, system_index)

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")


def sample(entries, n, seed):
    """判定済みの項から決定論に標本を引く。

    種を与えれば同じ標本になること。再現できない標本は「その標本で測った」と
    言えない —— 実時計を読む試験が日付だけで赤くなったのと同じ形である
    （WATCH-001 第11項）。並びは key で正規化してから引き、台帳の並び順の
    揺れが標本を変えないようにする。
    """
    judged = sorted([e for e in entries if e.get("assigned_at")],
                    key=lambda e: e.get("key") or "")
    if n >= len(judged):
        return judged
    return random.Random(seed).sample(judged, n)


def withdraw(entry, reason):
    """判定を取り下げ、未割当の UNKNOWN へ戻す。

    「UNKNOWN へ戻す」だけでは足りない。割当済みの UNKNOWN は評価の結論で
    あって未評価ではなく、正本は次の行動に挙げない（INC-006 で分けた区別）。
    `assigned_at` を落として初めて `_count_unmapped` が数え、MAP_COVERAGE が
    拾い直す。前の判定は消さず履歴へ積む（ADR-130）。
    """
    map_coverage.push_reassessment(entry)
    entry["disposition"] = "UNKNOWN"
    entry["reason"] = reason
    for key in ("assigned_at", "assigned_by", "evidence", "gap",
                "confidence", "unresolved_evidence", "original_disposition"):
        entry.pop(key, None)


def apply_verdict(entry, verdict, reason):
    """独立の判定を突き合わせる。一致なら触らない、割れたら取り下げる。

    返り値: 一致したか（bool）。
    """
    if verdict == entry.get("disposition"):
        return True
    withdraw(entry, "[独立の再判定と割れたため判定を取り下げた] " + reason)
    return False


def summarize(rows):
    """抜取りの結果の要約。

    **一致率を持たない。**AI の一致は客観的証拠ではないので、鍵に置くと次に
    読む者がそれを品質の指標として読む（運転手順 §4・§5）。数えて出すのは
    標本の大きさと、不一致の件数と、その**中身**である。
    """
    dis = [r for r in rows if not r.get("agreed")]
    return {
        "sampled": len(rows),
        "disagreements": len(dis),
        "disagreement_detail": [
            {"key": r["key"], "before": r["before"], "after": r["after"],
             "reason": r.get("reason")} for r in dis],
        "note": "一致率は持たない。AI の一致は客観的証拠でない（運転手順 §4）。"
                "読むのは不一致の中身であり、割れた項は判定を取り下げて"
                "未割当へ戻した。",
    }


def _git(args):
    try:
        return subprocess.check_output(["git"] + args, cwd=LANE_DIR,
                                       text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=sorted(books.BOOKS))
    parser.add_argument("--sample", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--today", required=True,
                        help="記録の日付(UTC)。実時計を読まない（WATCH-001 第11項）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cat, cov = map_coverage.load_pair(args.book)
    if cov is None:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "カタログか台帳が無い"}, ensure_ascii=False))
        return 3

    idx = system_index.build()
    if not idx["documents"] or not idx["scripts"]:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "現状の索引が組めない"}, ensure_ascii=False))
        return 3
    index_text = system_index.as_prompt_text(idx)

    picked = sample(cov["entries"], args.sample, args.seed)
    details = map_coverage.principle_details(cat, picked)
    if not details:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "標本の原則本体が引けない"}, ensure_ascii=False))
        return 3
    by_key = {e["key"]: e for e in cov["entries"]}
    before = {d["key"]: by_key[d["key"]].get("disposition") for d in details
              if d["key"] in by_key}

    print("book=%s 標本=%d 種=%d 索引 sha=%s"
          % (args.book, len(details), args.seed, idx["sha256"][:12]), flush=True)

    if args.dry_run:
        prompt = prompts.build_map_coverage_prompt(details, index_text)
        print(json.dumps({"prompt_chars": len(prompt),
                          "prompt_sha256": schemas.sha256_of(prompt),
                          "keys": [d["key"] for d in details]},
                         ensure_ascii=False))
        return 0

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    batches = [details[i:i + args.batch_size]
               for i in range(0, len(details), args.batch_size)]
    rows, cost_total = [], 0.0
    for i, batch in enumerate(batches):
        prompt = prompts.build_map_coverage_prompt(batch, index_text)
        record = sdk_lane.run_one_shot(
            prompt,
            schema=schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            model=run_opts["model"],
            effort=run_opts["effort"],
            max_budget_usd=args.budget_per_call,
            cwd=tempfile.mkdtemp(prefix="assurance-recheck-"),
            allowed_tools=(),
            max_turns=8,
            timeout_s=args.timeout,
        )
        cost_total += float(
            ((record.get("result_meta") or {}).get("total_cost_usd")) or 0.0)
        if record["status"] != "PASS":
            print(json.dumps({"status": "UNASSESSED",
                              "reason": "束 %d が %s: %s"
                                        % (i, record["status"], record["errors"])},
                             ensure_ascii=False))
            return 3
        out = record["structured_output"] or {}
        accepted, downgraded, _rejected = prompts.verify_coverage_assignments(
            out.get("assignments", []),
            lambda p: system_index.resolve_pointer(idx, p),
            [b["key"] for b in batch])
        for a in accepted + downgraded:
            entry = by_key.get(a["key"])
            if entry is None:
                continue
            agreed = apply_verdict(entry, a["disposition"],
                                   str(a.get("reason") or ""))
            rows.append({"key": a["key"], "before": before.get(a["key"]),
                         "after": a["disposition"], "agreed": agreed,
                         "reason": a.get("reason")})
        print("束 %d/%d 件=%d 費用=%.3f"
              % (i + 1, len(batches), len(batch), cost_total), flush=True)

    map_coverage.save_coverage(args.book, cov)
    summary = summarize(rows)
    summary.update({
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "independent-recheck",
        "book": args.book,
        "date": args.today,
        "generated_at": "%sT00:00:00Z" % args.today,
        "seed": args.seed,
        "cost_usd": round(cost_total, 4),
        "git_sha": _git(["rev-parse", "--short", "HEAD"]),
        "index_sha256": idx["sha256"],
        "model": run_opts["model"],
        "effort": run_opts["effort"],
        "rows": rows,
    })
    path = os.path.join(LEDGER_DIR, "recheck-%s-%s.json" % (args.book, args.today))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: summary[k] for k in
                      ("sampled", "disagreements", "cost_usd")},
                     ensure_ascii=False))
    return 1 if summary["disagreements"] else 0


if __name__ == "__main__":
    sys.exit(main())
