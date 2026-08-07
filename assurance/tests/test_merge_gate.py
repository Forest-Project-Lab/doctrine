#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""門の判定は三値である（ADR-129）。

体系は状態語彙に UNASSESSED（前提欠如で未評価）を持ち「前提が欠けたら PASS では
なく UNASSESSED へ倒す」と決めている。だが常設許可の条件3 は『PR の CI が pass』
という二値でしか書かれておらず、その決定が門の経路へ継承されていなかった
（事象 INC-022。2026-08-06 の GitHub Actions 障害で実際に踏んだ）。

ここで凍結するのは、事故分析が出した先行指標のうち機械化できる三つである ——
ジョブ取得不成立の注記・状態語の不一致・検査対象 SHA と適用対象 SHA の乖離。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import merge_gate  # noqa: E402

HEAD = "b1ddc56715a242b21dc3b19428db4ff40f81a3d0"


def _run(**over):
    """走り終わって成功した run の骨。上書きして各欠陥を作る。"""
    base = {
        "status": "completed",
        "conclusion": "success",
        "head_sha": HEAD,
        "annotations": [],
        "status_words": {"list": "completed", "view": "completed"},
    }
    base.update(over)
    return base


class MergeGateTest(unittest.TestCase):

    def test_vocabulary_is_the_canonical_three(self):
        self.assertEqual(merge_gate.VERDICTS, ("PASS", "FAIL", "UNASSESSED"))

    def test_clean_success_passes(self):
        verdict, reasons = merge_gate.judge(HEAD, _run())
        self.assertEqual(verdict, "PASS", reasons)
        self.assertEqual(reasons, [])

    def test_missing_run_is_unassessed_not_fail(self):
        """期待される run が生成されていない。走っていないのは不適合ではない。"""
        verdict, reasons = merge_gate.judge(HEAD, None)
        self.assertEqual(verdict, "UNASSESSED", reasons)
        self.assertTrue(any("run が無い" in r for r in reasons), reasons)

    def test_job_not_acquired_is_unassessed_not_fail(self):
        """GitHub は fail を返すが、ジョブは一度も実行されていない（INC-022 の実測）。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(
            conclusion="failure",
            annotations=["The job was not acquired by Runner of type hosted "
                         "even after multiple attempts"]))
        self.assertEqual(verdict, "UNASSESSED", reasons)
        self.assertTrue(any("取得されていない" in r for r in reasons), reasons)

    def test_real_failure_is_fail(self):
        """実行されたうえでの不適合は FAIL。UNASSESSED へ逃がさない。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(conclusion="failure"))
        self.assertEqual(verdict, "FAIL", reasons)

    def test_disagreeing_status_words_are_unassessed(self):
        """同一 run について API の答えが割れたら、どれも信じない（INC-022 で四重に割れた）。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(
            status_words={"list": "queued", "view": "completed",
                          "cancel": "has not yet queued"}))
        self.assertEqual(verdict, "UNASSESSED", reasons)
        self.assertTrue(any("状態語" in r for r in reasons), reasons)

    def test_sha_mismatch_is_unassessed(self):
        """検査した木と適用する木が違う。#234 で実際に起きた形。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(head_sha="0" * 40))
        self.assertEqual(verdict, "UNASSESSED", reasons)
        self.assertTrue(any("SHA" in r for r in reasons), reasons)

    def test_unfinished_run_is_unassessed(self):
        for status in ("queued", "in_progress", "waiting"):
            verdict, _ = merge_gate.judge(HEAD, _run(status=status,
                                                     conclusion=None))
            self.assertEqual(verdict, "UNASSESSED", status)

    def test_unknown_conclusion_is_unassessed_not_pass(self):
        """知らない語を PASS と読まない（根拠なき PASS を書かない）。"""
        verdict, _ = merge_gate.judge(HEAD, _run(conclusion="neutral"))
        self.assertEqual(verdict, "UNASSESSED")

    def test_success_with_mismatched_sha_never_passes(self):
        """成功していても、対象が違えば通さない。二つの欠陥が重なる形。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(
            conclusion="success", head_sha="1" * 40))
        self.assertEqual(verdict, "UNASSESSED", reasons)

    def test_all_reasons_are_reported_together(self):
        """一つ直せば通る、と読ませない。欠けている前提を全部並べる。"""
        verdict, reasons = merge_gate.judge(HEAD, _run(
            head_sha="2" * 40,
            annotations=["The job was not acquired by Runner of type hosted"],
            status_words={"list": "queued", "view": "completed"}))
        self.assertEqual(verdict, "UNASSESSED")
        self.assertGreaterEqual(len(reasons), 3, reasons)

    def test_exit_codes_follow_the_lane_convention(self):
        """0=PASS / 2=FAIL / 3=UNASSESSED（レーンの他の実行器と揃える）。"""
        self.assertEqual(merge_gate.exit_code("PASS"), 0)
        self.assertEqual(merge_gate.exit_code("FAIL"), 2)
        self.assertEqual(merge_gate.exit_code("UNASSESSED"), 3)


if __name__ == "__main__":
    unittest.main()
