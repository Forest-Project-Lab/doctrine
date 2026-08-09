#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""修正の独立検証（VERIFY。venv の python で動かす）。

- 役割は model_policy の evaluation（最低線 opus / effort high。ADR-116）。
- 入力は構造化された一つの対象（対象 id・主張・赤の証拠・diff・修正後の観測）
  だけ。実装者の会話・弁明は渡さない（CHALLENGE と同じ独立性。ADR-115）。
- 赤の証拠（ledger/red/<対象 id>.json）が無ければ検証は始まらない ——
  修正前に FAIL した観測が無い修正は、効いたかどうかを原理的に測れない。
  UNASSESSED の記録を書いて止まる。
- diff は本スクリプトが git から取る。上限（30000 字）を超えたら黙って切り詰めず、
  UNASSESSED の記録を書いて止まる（--allow-large で全文のまま通せる。閉じる側へ
  倒す）。
- 記録が PASS で三つの checks が全て PASS のときだけ before_fail_after_pass
  （orchestrator の TRANSITIONS の VERIFIED の guard と同名）が真になる。
  新規の fixed:true はこの記録を要す（正本の validate が検める。ADR-139）。
- 得られるのはセッションの独立まで。独立した組織による検証（IV&V）ではなく、
  同系 model の共通原因故障は残余リスクとして残る（NONGOAL-001 第17項）。

usage: verify_fix.py (--incident ID | --scenario ID) --diff-range a..b
                     --claim text|@file [--red PATH] [--post-fix-json PATH]
                     [--budget-per-call 4.0] [--timeout 900] [--allow-large]
                     [--dry-run]

終了コード: 0=PASS（三 checks も PASS） / 2=FAIL / 3=UNASSESSED(前提欠如)
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
RED_DIR = os.path.join(LEDGER_DIR, "red")
VERIFY_DIR = os.path.join(LEDGER_DIR, "verify")

# diff の上限（字数）。超えたら黙って切り詰めず UNASSESSED へ倒す。
# 一部だけ見た検証を全体の検証として記録しない（閉じる側へ倒す）。
DIFF_CHAR_LIMIT = 30000


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=60)
        return proc.stdout if proc.returncode == 0 else None
    except OSError:
        return None


def before_fail_after_pass(record):
    """VERIFIED の guard（orchestrator の TRANSITIONS と同名）。

    verdict が PASS で、三つの checks（red_was_red / green_is_green /
    single_change）がすべて PASS のときだけ真。UNKNOWN は満たさない ——
    判定できなかったことを、通ったことと読まない。
    """
    if not isinstance(record, dict) or record.get("verdict") != "PASS":
        return False
    checks = record.get("checks") or {}
    return all(checks.get(key) == "PASS"
               for key in ("red_was_red", "green_is_green", "single_change"))


def build_record(target_id, *, diff_range=None, diff_sha256=None,
                 red_sha256=None, prompt_sha256=None, model=None, effort=None,
                 cost_usd=None, record=None, sdk_status=None, reason=None,
                 git_sha=None, generated_at=None):
    """台帳へ書く記録を組む（純関数。書き込みは main が行う）。

    record が None の記録（UNASSESSED など）は before_fail_after_pass を満たさず、
    正本の fixed:true の門も通らない（前提欠如は閉じる側へ倒す。ADR-139）。
    """
    return {
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "verify-record",
        "target_id": target_id,
        "generated_at": generated_at or datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "diff_range": diff_range,
        "diff_sha256": diff_sha256,
        "red_sha256": red_sha256,
        "prompt_sha256": prompt_sha256,
        "model": model,
        "effort": effort,
        "cost_usd": cost_usd,
        "record": record,
        "sdk_status": sdk_status,
        "reason": reason,
    }


def _write(doc):
    os.makedirs(VERIFY_DIR, exist_ok=True)
    path = os.path.join(VERIFY_DIR, "%s.json" % doc["target_id"])
    ledger_io.write_json(path, doc)
    return path


def _read_claim(raw):
    if raw.startswith("@"):
        with open(raw[1:], encoding="utf-8") as f:
            return f.read()
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--incident", default=None, help="対象の事象 id")
    who.add_argument("--scenario", default=None, help="対象の scenario id")
    parser.add_argument("--diff-range", required=True,
                        help="git の範囲（a..b）。diff は本スクリプトが取る")
    parser.add_argument("--claim", required=True,
                        help="修正の主張（文字列か @ファイル）")
    parser.add_argument("--red", default=None,
                        help="赤の証拠（既定: ledger/red/<対象 id>.json）")
    parser.add_argument("--post-fix-json", default=None,
                        help="修正後の観測（構造化 JSON のファイル）")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--budget-per-call", type=float, default=4.0)
    parser.add_argument("--allow-large", action="store_true",
                        help="上限超過の diff を全文のまま渡す（切り詰めはしない）")
    parser.add_argument("--dry-run", action="store_true",
                        help="SDK を呼ばずプロンプトの組み立てだけを検める")
    args = parser.parse_args(argv)

    target_id = args.incident or args.scenario
    git_sha = (_git(["rev-parse", "HEAD"]) or "").strip() or None

    def bail_unassessed(reason, **fields):
        doc = build_record(target_id, diff_range=args.diff_range,
                           sdk_status="UNASSESSED", reason=reason,
                           git_sha=git_sha, **fields)
        written = None
        if not args.dry_run:   # dry-run は台帳に触れない（検めるだけ）
            written = os.path.relpath(_write(doc), REPO_DIR)
        print(json.dumps({"status": "UNASSESSED", "reason": reason,
                          "written": written}, ensure_ascii=False))
        return 3

    # 赤の証拠が無ければ検証は始まらない（修正前 FAIL の観測が無い修正は
    # 効いたかどうかを測れない）。
    red_path = args.red or os.path.join(RED_DIR, "%s.json" % target_id)
    if not os.path.isfile(red_path):
        return bail_unassessed(
            "赤の証拠が無い: %s（修正前 FAIL の記録なしに検証は始まらない）"
            % os.path.relpath(red_path, REPO_DIR))
    try:
        with open(red_path, encoding="utf-8") as f:
            red_doc = json.load(f)
    except (OSError, ValueError) as exc:
        return bail_unassessed("赤の証拠が読めない: %s" % exc)
    red_sha256 = schemas.sha256_of(red_doc)

    # 検証の記録そのものを、検証対象の diff から外す(INC-028)。
    #
    # 記録は commit 前の diff に対して作られるのに、その記録自体が次の commit で
    # 同じ枝へ入る。すると独立検証は毎回「この diff は、別の変更集合に対する
    # 検証記録を同梱している」と正しく指摘する —— 記録と、それが検証した変更
    # 集合が、原理的に一致しないからである。実測では二度とも single_change の
    # 減点材料になった。
    #
    # 記録は評価の成果であって、評価される変更ではない。除外して循環を切る。
    diff_text = _git(["diff", args.diff_range, "--",
                      ".", ":(exclude)assurance/ledger/verify/"])
    if diff_text is None:
        return bail_unassessed(
            "git diff %s が取れない（範囲が不正か repo の外）" % args.diff_range,
            red_sha256=red_sha256)
    if len(diff_text) > DIFF_CHAR_LIMIT and not args.allow_large:
        # 黙って切り詰めない。一部だけ見た検証を全体の検証として記録しない。
        return bail_unassessed(
            "diff が %d 字で上限 %d を超える（--allow-large で全文のまま通すか、"
            "範囲を絞ること。切り詰めはしない）"
            % (len(diff_text), DIFF_CHAR_LIMIT),
            red_sha256=red_sha256,
            diff_sha256=schemas.sha256_of(diff_text))

    try:
        claim = _read_claim(args.claim)
    except OSError as exc:
        return bail_unassessed("主張のファイルが読めない: %s" % exc,
                               red_sha256=red_sha256)
    post_fix = None
    if args.post_fix_json:
        try:
            with open(args.post_fix_json, encoding="utf-8") as f:
                post_fix = json.load(f)
        except (OSError, ValueError) as exc:
            return bail_unassessed("修正後の観測が読めない: %s" % exc,
                                   red_sha256=red_sha256)

    verify_input = {
        "target_id": target_id,
        "claim": claim,
        "red_evidence": red_doc,
        "diff": diff_text,
        "post_fix_observation": post_fix,
    }
    prompt = prompts.build_verify_prompt(verify_input)

    if args.dry_run:
        print(json.dumps({
            "target_id": target_id,
            "diff_range": args.diff_range,
            "diff_chars": len(diff_text),
            "red": os.path.relpath(red_path, REPO_DIR),
            "prompt_chars": len(prompt),
            "prompt_sha256": schemas.sha256_of(prompt),
        }, ensure_ascii=False, indent=2))
        return 0

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    sdk_rec = sdk_lane.run_one_shot(
        prompt, schema=schemas.VERIFY_RECORD_SCHEMA,
        model=run_opts["model"], effort=run_opts["effort"],
        max_budget_usd=args.budget_per_call,
        cwd=tempfile.mkdtemp(prefix="assurance-verify-"),
        allowed_tools=(), max_turns=8, timeout_s=args.timeout)

    record = None
    reason = None
    sdk_status = sdk_rec["status"]
    if sdk_status == "PASS":
        record = sdk_rec.get("structured_output")
        if (record or {}).get("target_id") != target_id:
            # 依頼していない対象への判定は受け取らない（verify_verdicts と
            # 同じ機械照合。取り違えた記録で門を通さない）。
            reason = ("返された記録の target_id %r が対象 %s と一致しない"
                      % ((record or {}).get("target_id"), target_id))
            record = None
            sdk_status = "FAIL"

    cost = float((sdk_rec.get("result_meta") or {}).get("total_cost_usd") or 0)
    doc = build_record(
        target_id,
        diff_range=args.diff_range,
        diff_sha256=schemas.sha256_of(diff_text),
        red_sha256=red_sha256,
        prompt_sha256=sdk_rec["prompt_sha256"],
        model=sdk_rec["options"]["model"],
        effort=sdk_rec["options"]["effort"],
        cost_usd=round(cost, 4),
        record=record,
        sdk_status=sdk_status,
        reason=reason,
        git_sha=git_sha)
    path = _write(doc)

    ok = before_fail_after_pass(record)
    print(json.dumps({
        "written": os.path.relpath(path, REPO_DIR),
        "sdk_status": sdk_status,
        "verdict": (record or {}).get("verdict"),
        "checks": (record or {}).get("checks"),
        "before_fail_after_pass": ok,
        "errors": sdk_rec.get("errors"),
        "cost_usd": round(cost, 4),
    }, ensure_ascii=False, indent=2))
    if sdk_status == "UNASSESSED":
        return 3
    if sdk_status in ("UNKNOWN",):
        return 4
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
