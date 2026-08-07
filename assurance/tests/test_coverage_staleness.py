#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""網羅の判定は、判定した索引の指紋を持ち、索引が動いたら古びる（ADR-130）。

606 件の割当はすべて 2026-08-05 の一日で付いた。以後、統治木には ADR-114〜129 と
多数の試験が入り、索引は育っている。判定の基盤が動いたのに、判定は 2026-08-05 の
索引に対する主張のまま置かれていた —— しかも `assigned_by.index_sha256` として
指紋は**記録されていた**（読む口が無かっただけ）。INC-015 と同じ族の六度目。

ここで凍結するのは二つ。(A) 再判定は古い判定を消さず積み増す。(B) 索引の指紋が
現在と違う非終端の項を、正本が数えて次の行動に挙げる。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import map_coverage, orchestrator  # noqa: E402

OLD = "9e8b50a886f33305" + "0" * 48
NEW = "65ccd77b8063dd54" + "0" * 48


def _entry(disposition, sha, key="JERG:x"):
    return {
        "key": key, "title": "t", "category": "c", "disposition": disposition,
        "reason": "r", "evidence": ["ADR-001"], "assigned_at": "2026-08-05",
        "assigned_by": {"model": "claude-opus-5", "effort": "high",
                        "index_sha256": sha},
    }


class CoverageStalenessTest(unittest.TestCase):
    """(B) 索引が動いたら古びる。"""

    def test_status_reports_stale_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [_entry("対応計画あり", OLD),
                             _entry("実装・試験・証拠あり", OLD, "JERG:y"),
                             _entry("対応計画あり", NEW, "JERG:z")])
            st = orchestrator.coverage_status(index_sha=NEW)["jerg"]
            self.assertEqual(st["stale_open"], 1)      # 再判定が要る（評価が要る）
            self.assertEqual(st["stale_settled"], 1)   # 証拠の再照合が要る（決定論）

    def test_stale_open_entries_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [_entry("対応計画あり", OLD)])
            actions = orchestrator.next_actions(index_sha=NEW)
            hit = [a for a in actions if a.startswith("MAP_COVERAGE")]
            self.assertTrue(hit, actions)
            self.assertIn("索引が動いた", hit[0])

    def test_fresh_entries_are_not_named(self):
        """消えない行動を作らない。再判定すれば消える。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [_entry("対応計画あり", NEW)])
            self.assertEqual(
                [a for a in orchestrator.next_actions(index_sha=NEW)
                 if a.startswith("MAP_COVERAGE")], [])

    def test_settled_staleness_is_counted_but_not_named(self):
        """終端の項は数えるが挙げない —— 再照合は決定論でできるので評価を買わない。

        見ていないことにはしない（status が必ず数えて出す）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [_entry("実装・試験・証拠あり", OLD)])
            self.assertEqual(
                orchestrator.coverage_status(index_sha=NEW)["jerg"]["stale_settled"], 1)
            self.assertEqual(
                [a for a in orchestrator.next_actions(index_sha=NEW)
                 if a.startswith("MAP_COVERAGE")], [])

    def test_entry_without_a_fingerprint_is_stale(self):
        """指紋を持たない古い項は、どの索引に対する判定か判らない。前提欠如の側へ倒す。"""
        e = _entry("対応計画あり", OLD)
        e["assigned_by"].pop("index_sha256")
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [e])
            self.assertEqual(
                orchestrator.coverage_status(index_sha=NEW)["jerg"]["stale_open"], 1)

    def _stub(self, tmp, entries):
        cat = os.path.join(tmp, "catalogs")
        os.makedirs(cat, exist_ok=True)
        for book in ("jerg", "stpa", "cast"):
            with open(os.path.join(cat, "%s-principles.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"totals": {"principles": 1, "rejected": 0,
                                      "cost_usd": 0.0}, "chunks": [{}]}, f)
            with open(os.path.join(cat, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": entries if book == "jerg" else []}, f)
        for attr, value in (("CATALOG_DIR", cat), ("LANE_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "i.json")),
                            ("ASSUMPTIONS_PATH", os.path.join(tmp, "a.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)


class ReassessmentTest(unittest.TestCase):
    """(A) 再判定は古い判定を消さず積み増す。"""

    def test_prior_judgement_is_pushed_not_dropped(self):
        entry = _entry("対応計画あり", OLD)
        map_coverage.push_reassessment(entry)
        self.assertEqual(len(entry["reassessments"]), 1)
        kept = entry["reassessments"][0]
        self.assertEqual(kept["disposition"], "対応計画あり")
        self.assertEqual(kept["assigned_at"], "2026-08-05")
        self.assertEqual(kept["assigned_by"]["index_sha256"], OLD)

    def test_history_accumulates_in_order(self):
        entry = _entry("対応計画あり", OLD)
        map_coverage.push_reassessment(entry)
        entry["disposition"] = "実装・試験・証拠あり"
        entry["assigned_at"] = "2026-08-07"
        map_coverage.push_reassessment(entry)
        self.assertEqual([r["disposition"] for r in entry["reassessments"]],
                         ["対応計画あり", "実装・試験・証拠あり"])

    def test_unjudged_entry_pushes_nothing(self):
        """まだ判定の無い項は積むものが無い（空の履歴を作らない）。"""
        entry = {"key": "JERG:x", "disposition": "UNKNOWN"}
        map_coverage.push_reassessment(entry)
        self.assertNotIn("reassessments", entry)

    def test_history_is_never_overwritten(self):
        entry = _entry("対応計画あり", OLD)
        entry["reassessments"] = [{"disposition": "既存", "assigned_at": "2026-08-01"}]
        map_coverage.push_reassessment(entry)
        self.assertEqual(len(entry["reassessments"]), 2)
        self.assertEqual(entry["reassessments"][0]["disposition"], "既存")


if __name__ == "__main__":
    unittest.main()
