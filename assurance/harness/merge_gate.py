#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""門の判定を三値で出す（ADR-129。判定は純関数・収集だけが外へ出る）。

体系は状態語彙に UNASSESSED（前提欠如で未評価）を持ち「前提が欠けたら PASS では
なく UNASSESSED へ倒す」と決めている。だが常設許可の条件3 は『PR の CI が pass』
という二値でしか書かれておらず、その決定が門の経路へ継承されていなかった
（事象 INC-022）。2026-08-06 の GitHub Actions 障害で実際に踏み、走らなかった検査を
赤と読むか実質緑と読むかが運転者の裁量へ落ちた。

ここが機械化するのは、事故分析が出した五つの先行指標のうち三つである:

1. ジョブ取得不成立の注記を含む run の出現 → PASS/FAIL のどちらにも数えない
2. 同一 run に対する状態語の不一致 → 一致を PASS 採用の必要条件とする
3. 検査対象 SHA と適用対象 SHA の乖離 → 不一致なら止める

残る二つ（イベントから run 生成までの遅延・二値語彙で書かれた条項の残存数）は
ここでは見ない。前者は時刻の観測が要り、後者は散文の走査であって別の経路が持つ。

判定は純関数 judge() に閉じる。gh の呼び出しは collect() だけが行い、決定論試験は
judge() を fixture で凍結する（通信に依存する試験を作らない）。
"""
import argparse
import json
import subprocess
import sys

sys.dont_write_bytecode = True

# 運転手順 §5 の状態語彙のうち、門が出しうる三つ。
# DEGRADED と NOT-APPLICABLE は門の判定には現れない（縮退運転で merge しない・
# 非該当という門は無い）。語をここで増やさない。
VERDICTS = ("PASS", "FAIL", "UNASSESSED")

# 実行されたうえでの不適合。これだけが FAIL であり、他は前提欠如へ倒す。
_FAILED_CONCLUSIONS = frozenset({
    "failure", "timed_out", "cancelled", "action_required", "startup_failure",
})

# ジョブが取得されなかったことを示す注記の断片（2026-08-06 の実測）。
# 文言の完全一致に寄りかからない —— 部分一致で拾い、拾いすぎる側へ倒す
# （拾いすぎれば UNASSESSED になるだけで、誤って PASS にはならない）。
_NOT_ACQUIRED_MARKERS = ("was not acquired", "not acquired by runner")

_EXIT = {"PASS": 0, "FAIL": 2, "UNASSESSED": 3}


def exit_code(verdict):
    """判定 → 終了コード（0=PASS / 2=FAIL / 3=UNASSESSED）。

    レーンの他の実行器（cast_analysis・smoke）と同じ割り当てにする。
    """
    return _EXIT[verdict]


def judge(pr_head_sha, run):
    """門の判定。返り値は (判定, 理由の列)。

    理由は**全部**返す。一つ直せば通ると読ませないため（欠けている前提が
    複数あるとき、先頭だけを見て引き直すと同じ場所で二度止まる）。

    run は収集済みの辞書か None:
      {"status", "conclusion", "head_sha", "annotations", "status_words"}
    """
    reasons = []

    if not run:
        return "UNASSESSED", ["対応する run が無い（検査が生成されていない。"
                              "走っていないことは不適合ではない）"]

    for note in run.get("annotations") or []:
        low = (note or "").lower()
        if any(m in low for m in _NOT_ACQUIRED_MARKERS):
            reasons.append(
                "ジョブが取得されていない（注記: %s）。実行が成立していないので "
                "PASS にも FAIL にも数えない" % (note or "")[:80])
            break

    words = {k: v for k, v in (run.get("status_words") or {}).items() if v}
    if len(set(words.values())) > 1:
        reasons.append(
            "同一 run について状態語が割れている（%s）。どれも信じない"
            % ", ".join("%s=%s" % kv for kv in sorted(words.items())))

    head = (run.get("head_sha") or "").strip()
    want = (pr_head_sha or "").strip()
    if not head or not want:
        reasons.append("検査対象 SHA か適用対象 SHA が取れない")
    elif not (head.startswith(want) or want.startswith(head)):
        reasons.append(
            "検査対象 SHA (%s) と適用対象 SHA (%s) が違う。検査していない木は "
            "通さない" % (head[:12], want[:12]))

    if run.get("status") != "completed":
        reasons.append("run が走り終わっていない（status=%s）"
                       % run.get("status"))

    if reasons:
        return "UNASSESSED", reasons

    conclusion = run.get("conclusion")
    if conclusion == "success":
        return "PASS", []
    if conclusion in _FAILED_CONCLUSIONS:
        return "FAIL", ["検査が不適合（conclusion=%s）" % conclusion]
    # 知らない語を PASS と読まない（根拠なき PASS を書かない）。
    return "UNASSESSED", ["conclusion が既知の語彙に無い（%s）" % conclusion]


def collect(pr_number, repo=None):
    """gh から判定の材料を集める。通信するのはここだけ。

    状態語は list と view の二経路から取る。障害中はこの二つが割れた（実測）。
    取れない経路は落とし、残った物どうしで一致を見る。
    """
    def _gh(args):
        try:
            out = subprocess.run(["gh"] + args, capture_output=True,
                                 text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, str(exc)
        if out.returncode != 0:
            return None, (out.stderr or "").strip()[:200]
        try:
            return json.loads(out.stdout), None
        except ValueError:
            return out.stdout.strip(), None

    prefix = ["-R", repo] if repo else []
    pr, err = _gh(["pr", "view", str(pr_number), "--json",
                   "headRefOid,headRefName"] + prefix)
    if not pr:
        return None, None, "PR を引けない: %s" % err
    head = pr["headRefOid"]

    runs, err = _gh(["run", "list", "--branch", pr["headRefName"], "--limit",
                     "20", "--json",
                     "databaseId,status,conclusion,headSha"] + prefix)
    if runs is None:
        return head, None, "run を引けない: %s" % err
    mine = [r for r in runs if r.get("headSha") == head]
    if not mine:
        return head, None, None
    latest = mine[0]

    detail, _ = _gh(["api", "repos/{owner}/{repo}/actions/runs/%d"
                     % latest["databaseId"], "--jq",
                     "{status,conclusion,head_sha}"] + prefix)
    annotations = []
    checks, _ = _gh(["api", "repos/{owner}/{repo}/commits/%s/check-runs" % head,
                     "--jq", "[.check_runs[].output.title]"] + prefix)
    for title in checks or []:
        if title:
            annotations.append(title)

    run = {
        "status": latest.get("status"),
        "conclusion": latest.get("conclusion"),
        "head_sha": latest.get("headSha"),
        "annotations": annotations,
        "status_words": {
            "list": latest.get("status"),
            "view": (detail or {}).get("status") if isinstance(detail, dict)
            else None,
        },
    }
    return head, run, None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="門の判定を三値で出す（0=PASS / 2=FAIL / 3=UNASSESSED）")
    ap.add_argument("--pr", required=True, help="PR 番号")
    ap.add_argument("--repo", default=None, help="owner/name（省略時は現在地）")
    args = ap.parse_args(argv)

    head, run, err = collect(args.pr, args.repo)
    if err:
        verdict, reasons = "UNASSESSED", [err]
    else:
        verdict, reasons = judge(head, run)
    print(json.dumps({"pr": args.pr, "head": head, "verdict": verdict,
                      "reasons": reasons, "run": run},
                     ensure_ascii=False, indent=2))
    return exit_code(verdict)


if __name__ == "__main__":
    sys.exit(main())
