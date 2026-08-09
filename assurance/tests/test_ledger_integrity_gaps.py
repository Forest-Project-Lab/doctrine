#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""台帳が黙って通していた四つの穴（INC-036）。

独立再監査 2026-08-09 が実測した。いずれも `validate` が緑のまま通る。

- 重複統合が、判定の緑さを問わない。UNKNOWN を緑の項へ吸わせると、
  数の上から判定不能が消える（実台帳の 1 件は正当だが、機械の番人が無い）。
- 五値のうち UNASSESSED が、status のどの数にも現れない。
- `shipped: true` の三条件（ADR-144）を機械が一つも検めていない。
  台帳唯一の fix_commit はどの ref からも到達できない dangling commit で、
  条件(2)の検算がそこで落ちる。
- 評価者が「所有者判断が要る」と印した推奨を覆すとき、理由を求めていない。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import ledger_io, orchestrator  # noqa: E402


def _entry(key, disposition, **over):
    e = {"key": key, "title": key, "category": "c",
         "disposition": disposition, "reason": "r", "evidence": [],
         "assigned_at": "2026-08-01T00:00:00Z",
         "assigned_by": {"model": "m"}}
    e.update(over)
    return e


class MergeMustNotWhitenAVerdictTest(unittest.TestCase):
    """重複統合で判定不能を緑へ吸わせない（INC-036）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lig-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.ledger = os.path.join(self.dir, "ledger")
        os.makedirs(os.path.join(self.ledger, "catalogs"))

    def _write(self, *entries):
        ledger_io.write_json(
            os.path.join(self.ledger, "catalogs", "jerg-coverage.json"),
            {"kind": "coverage-ledger", "book_id": "jerg",
             "entries": list(entries)})

    def test_merging_unknown_into_green_is_a_problem(self):
        self._write(
            _entry("A", "UNKNOWN", merged_into="B", merge_note="2026-08-09 重複"),
            _entry("B", "実装・試験・証拠あり"))
        problems = orchestrator._validate_coverage_merges(self.ledger)
        self.assertTrue(problems, "UNKNOWN を緑へ統合しても咎めない")
        self.assertTrue(any("UNKNOWN" in p for p in problems), problems)

    def test_merging_like_into_like_is_fine(self):
        self._write(
            _entry("A", "UNKNOWN", merged_into="B", merge_note="2026-08-09 重複"),
            _entry("B", "UNKNOWN"))
        self.assertEqual(orchestrator._validate_coverage_merges(self.ledger), [])

    def test_merging_green_into_unknown_is_fine(self):
        """安全側（緑を判定不能へ寄せる）は咎めない。"""
        self._write(
            _entry("A", "実装・試験・証拠あり", merged_into="B",
                   merge_note="2026-08-09 重複"),
            _entry("B", "UNKNOWN"))
        self.assertEqual(orchestrator._validate_coverage_merges(self.ledger), [])

    def test_the_existing_guards_still_work(self):
        self._write(_entry("A", "UNKNOWN", merged_into="居ない",
                           merge_note="x"))
        self.assertTrue(orchestrator._validate_coverage_merges(self.ledger))


class UnassessedIsCountedTest(unittest.TestCase):
    """五値の一つが数のどこにも出ない形をやめる（INC-036）。"""

    def test_coverage_status_reports_unassessed(self):
        summary = orchestrator.coverage_status()
        for book, v in summary.items():
            self.assertIn("unassessed", v,
                          "%s の要約に unassessed が無い（五値のうち一値が"
                          "どの数にも現れない）" % book)

    def test_the_real_ledger_has_the_two_unassessed_visible(self):
        summary = orchestrator.coverage_status()
        total = sum(v.get("unassessed") or 0 for v in summary.values())
        self.assertGreater(total, 0, "実台帳の UNASSESSED が見えていない")


class ShippedConditionsAreCheckedTest(unittest.TestCase):
    """ADR-144 の三条件を機械が検める（INC-036）。"""

    def test_a_shipped_incident_without_a_fix_commit_is_a_problem(self):
        incidents = [{"id": "INC-900-x", "date": "2026-08-09", "summary": "s",
                      "fixed": True, "shipped": True, "ship_ref": "v0.11.0",
                      "cast_analysis": "done", "evidence_kind": "measurement"}]
        problems = orchestrator._validate_shipped_conditions(incidents)
        self.assertTrue(problems, "fix_commit の無い shipped を咎めない")

    def test_a_shipped_incident_with_an_unreachable_commit_is_a_problem(self):
        incidents = [{"id": "INC-901-x", "date": "2026-08-09", "summary": "s",
                      "fixed": True, "shipped": True, "ship_ref": "v0.11.0",
                      "fix_commit": "0123456789abcdef0123456789abcdef01234567",
                      "cast_analysis": "done", "evidence_kind": "measurement"}]
        problems = orchestrator._validate_shipped_conditions(incidents)
        self.assertTrue(problems, "到達できない commit を咎めない")

    def test_the_real_ledger_is_checked(self):
        """実台帳に対して走ること（空の緑にしない）。"""
        if not orchestrator._git_available():
            self.skipTest("git の履歴が揃っていない（浅い複製）")
        problems = orchestrator._validate_shipped_conditions()
        self.assertEqual(problems, [])

    def test_the_grandfather_list_is_frozen_and_justified(self):
        """祖父条項は増やさない（増やすのは保証範囲の変更＝所有者判断）。"""
        self.assertEqual(len(orchestrator.SHIPPED_GRANDFATHERED), 8)
        shipped = {i["id"] for i in orchestrator.load_incidents()
                   if i.get("shipped")}
        stale = orchestrator.SHIPPED_GRANDFATHERED - shipped
        self.assertEqual(stale, set(),
                         "出荷でない id が祖父条項に残っている: %r" % (stale,))

    def test_a_new_shipped_incident_is_not_grandfathered(self):
        incidents = [{"id": "INC-999-new", "shipped": True,
                      "ship_ref": "v0.11.0"}]
        self.assertTrue(orchestrator._validate_shipped_conditions(incidents),
                        "新しい出荷は祖父条項に入らない")

    def test_the_dangling_fix_commit_is_gone(self):
        """INC-002 の fix_commit が到達できる commit であること。

        浅い複製（CI の既定）では履歴が無いので判じられない。前提が欠けた
        ときは飛ばす —— 偽の赤を出さない。
        """
        if not orchestrator._git_available():
            self.skipTest("git の履歴が揃っていない（浅い複製）")
        for inc in orchestrator.load_incidents():
            commit = (inc.get("fix_commit") or "").strip()
            if not commit:
                continue
            self.assertTrue(
                orchestrator._git_has_commit(commit),
                "%s の fix_commit %s がどの ref からも到達できない"
                % (inc["id"], commit))


class OwnerOverrideNeedsAReasonTest(unittest.TestCase):
    """評価者の所有者判断の印を覆すなら、理由を書く（INC-036）。"""

    def test_overriding_without_a_reason_is_a_problem(self):
        rows = [{"incident_id": "INC-902-x", "index": 0, "state": "landed",
                 "evidence_ref": "x", "evaluator_owner_required": True}]
        problems = orchestrator._validate_owner_overrides(rows)
        self.assertTrue(problems, "理由なしの覆しを咎めない")

    def test_overriding_with_a_reason_is_fine(self):
        rows = [{"incident_id": "INC-903-x", "index": 0, "state": "landed",
                 "evidence_ref": "x", "evaluator_owner_required": True,
                 "owner_override_reason": "統治木が既に決めている（DECIDED-001 事実7）"}]
        self.assertEqual(orchestrator._validate_owner_overrides(rows), [])

    def test_rows_the_evaluator_did_not_flag_are_untouched(self):
        rows = [{"incident_id": "INC-904-x", "index": 0, "state": "landed",
                 "evidence_ref": "x"}]
        self.assertEqual(orchestrator._validate_owner_overrides(rows), [])

    def test_owner_state_needs_no_override_reason(self):
        rows = [{"incident_id": "INC-905-x", "index": 0, "state": "owner",
                 "owner_decision_kind": "互換性を壊す変更",
                 "evaluator_owner_required": True}]
        self.assertEqual(orchestrator._validate_owner_overrides(rows), [])


class ValidateWiresThemAllTest(unittest.TestCase):
    def test_validate_calls_the_new_checks(self):
        import inspect
        src = inspect.getsource(orchestrator.validate)
        for name in ("_validate_shipped_conditions", "_validate_owner_overrides"):
            self.assertIn(name, src, "%s が validate に配線されていない" % name)

    def test_the_real_ledger_validates_clean(self):
        self.assertEqual(orchestrator.validate(), [])


if __name__ == "__main__":
    unittest.main()
