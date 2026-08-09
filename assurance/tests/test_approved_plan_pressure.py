#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""承認済みの検証計画に正本の圧が掛かること（INC-033。ADR-148）。

FORMALIZE は「判定が付いたこと」を消化と数える。それは計画審査の圧としては
正しいが、**計画が果たされたこと**ではない。REPRODUCE_RED は ADR-120 で
「名指しされない状態」に置かれていたので、承認された瞬間に義務が正本の
視野から消えていた —— 実測では 30 件が消えていた。

凍結したいこと:
- 承認された計画で赤の証拠が無いものを、正本が名指しすること。
- 赤の証拠（または再現不能の記録）が在れば圧が消えること（消えない行動に
  しない。INC-006）。
- **最初から緑は再現と認めない**（運転手順 §2）。
- REJECT と UNKNOWN の計画は義務を生まないこと。
- 名指しの二分と優先順の表が食い違わないこと（validate が見る）。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import ledger_io, orchestrator  # noqa: E402


def _plan(sid, verdict="APPROVE"):
    return {"scenario_id": sid, "verdict": verdict, "oracle": "o",
            "injection_point": "p"}


def _red(sid, phase="before-fix", rc=1, observed=("FAIL: x",), reason=None):
    rec = {"kind": "reproduce-red", "phase": phase, "returncode": rc,
           "observed_failures": list(observed)}
    if reason:
        rec["reason"] = reason
    return rec


class ApprovedPlanPressureTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pressure-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.ledger = os.path.join(self.dir, "ledger")
        os.makedirs(os.path.join(self.ledger, "formalize"))
        os.makedirs(os.path.join(self.ledger, "red"))

    def _formalize(self, *plans, name="2026-08-09.json"):
        ledger_io.write_json(
            os.path.join(self.ledger, "formalize", name),
            {"kind": "formalize", "generated_at": "2026-08-09T00:00:00Z",
             "plans": list(plans)})

    def _put_red(self, sid, record):
        ledger_io.write_json(os.path.join(self.ledger, "red", "%s.json" % sid),
                             record)

    def _outstanding(self):
        return [s for s, _f in orchestrator.unreproduced_plans(self.ledger)]

    def test_an_approved_plan_without_red_evidence_is_named(self):
        self._formalize(_plan("SCN-A"))
        self.assertEqual(self._outstanding(), ["SCN-A"])

    def test_red_evidence_clears_the_pressure(self):
        self._formalize(_plan("SCN-A"))
        self._put_red("SCN-A", _red("SCN-A"))
        self.assertEqual(self._outstanding(), [],
                         "消えない行動にしない（INC-006）")

    def test_red_impossible_also_clears_it(self):
        self._formalize(_plan("SCN-A"))
        self._put_red("SCN-A", {"kind": "reproduce-red", "phase": "impossible",
                                "reason": "外部の停止を再現できない"})
        self.assertEqual(self._outstanding(), [])

    def test_green_from_the_start_is_not_a_reproduction(self):
        """運転手順 §2 を機械にする —— 最初から緑は再現と認めない。"""
        self._formalize(_plan("SCN-A"))
        self._put_red("SCN-A", _red("SCN-A", rc=0, observed=()))
        self.assertEqual(self._outstanding(), ["SCN-A"])

    def test_silence_in_the_red_record_is_not_a_reproduction(self):
        self._formalize(_plan("SCN-A"))
        self._put_red("SCN-A", {"kind": "reproduce-red", "phase": "before-fix"})
        self.assertEqual(self._outstanding(), ["SCN-A"])

    def test_rejected_and_unknown_plans_carry_no_pressure(self):
        self._formalize(_plan("SCN-R", "REJECT"), _plan("SCN-U", "UNKNOWN"))
        self.assertEqual(self._outstanding(), [])

    def test_plans_from_every_formalize_file_are_counted(self):
        self._formalize(_plan("SCN-A"), name="2026-08-08.json")
        self._formalize(_plan("SCN-B"), name="2026-08-09.json")
        self.assertEqual(self._outstanding(), ["SCN-A", "SCN-B"])

    def test_the_summary_counts_even_when_nothing_is_raised(self):
        self._formalize(_plan("SCN-A"))
        self._put_red("SCN-A", _red("SCN-A"))
        self.assertEqual(
            orchestrator.reproduce_red_summary(self.ledger),
            {"approved": 1, "reproduced": 1, "outstanding": 0},
            "挙げないときも数えて出す")


class TheRealLedgerIsNamedTest(unittest.TestCase):
    def test_the_real_ledger_has_approved_plans_and_they_are_counted(self):
        """実台帳に対して。件数は凍らせない（自壊する門にしない）。"""
        summary = orchestrator.reproduce_red_summary()
        self.assertGreater(summary["approved"], 0,
                           "承認済みの計画が一件も見えていない")
        self.assertEqual(summary["approved"],
                         summary["reproduced"] + summary["outstanding"])


class StateTablesAgreeTest(unittest.TestCase):
    def test_reproduce_red_is_nameable_and_has_a_priority(self):
        self.assertIn("REPRODUCE_RED", orchestrator.NAMEABLE_STATES)
        self.assertIn("REPRODUCE_RED", orchestrator.ACTION_PRIORITY)
        self.assertNotIn("REPRODUCE_RED", orchestrator.WITHIN_CYCLE_STATES)

    def test_it_outranks_formalize_and_discover(self):
        """既に買った義務が、新しい計画や新しい仮説より先に来ること。"""
        pr = orchestrator.ACTION_PRIORITY
        self.assertLess(pr["REPRODUCE_RED"], pr["FORMALIZE"])
        self.assertLess(pr["REPRODUCE_RED"], pr["DISCOVER"])
        self.assertGreater(pr["REPRODUCE_RED"], pr["MAP_COVERAGE"],
                           "本丸の欠落より後（測る対象が先。ADR-131）")

    def test_validate_catches_a_table_that_disagrees(self):
        """検出器そのものが働くこと。"""
        problems = orchestrator._validate_nameable_states()
        self.assertEqual(problems, [])
        keep = orchestrator.ACTION_PRIORITY.pop("REPRODUCE_RED")
        try:
            self.assertTrue(orchestrator._validate_nameable_states())
        finally:
            orchestrator.ACTION_PRIORITY["REPRODUCE_RED"] = keep

    def test_reproduce_red_is_not_a_firing_point(self):
        """凍結する —— どのレーンも発火しないので表に足さない（ADR-128）。

        実装者の仕事であって LLM の評価点ではない。足すと
        `_validate_firing_points` が「どのレーンも宣言していない」で赤くなる。
        """
        self.assertNotIn("REPRODUCE_RED", orchestrator.FIRING_POINTS)

    def test_the_red_ledger_declares_its_reader(self):
        entry = [e for e in orchestrator.LEDGER_KINDS
                 if e["match"] == "red/*.json"][0]
        self.assertTrue(entry["read_by"])
        self.assertIsNone(entry["why_not_read"])
        for fn in entry["read_by"]:
            self.assertTrue(hasattr(orchestrator, fn), fn)


if __name__ == "__main__":
    unittest.main()
