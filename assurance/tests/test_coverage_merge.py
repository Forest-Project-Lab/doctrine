#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""重複統合（merged_into。CURATE の重複原則の統合）の決定論試験。

凍結したいこと:
- 統合済みの項を作業として買い直さないこと（select_todo・未割当の計数）。
- 抜取りと標的再検が統合済みの項を引かないこと（引けば二重の判定を作る）。
- 統合の書き方（実在する生き残り・連鎖の禁止・merge_note）を validate が検めること。
- 統合しても評価者の判定は消えないこと（生き残りの項が正本。ADR-115）。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import independent_recheck, map_coverage, orchestrator  # noqa: E402


def _entry(key, merged_into=None, assigned=True, disposition="UNKNOWN"):
    e = {"key": key, "disposition": disposition,
         "reason": "r", "evidence": [], "recheck_trigger": "t"}
    if assigned:
        e["assigned_at"] = "2026-08-07T00:00:00Z"
        e["assigned_by"] = {"index_sha256": "x"}
    if merged_into:
        e["merged_into"] = merged_into
        e["merge_note"] = "2026-08-07 同一出典行の重複"
    return e


class MergedEntriesAreNotWorkTest(unittest.TestCase):
    def test_select_todo_skips_merged(self):
        merged = _entry("JERG:dup", merged_into="JERG:keep", assigned=False)
        keep = _entry("JERG:keep", assigned=False)
        todo = map_coverage.select_todo([merged, keep], None, lambda p: True)
        self.assertEqual([e["key"] for e in todo], ["JERG:keep"])

    def test_unmapped_count_skips_merged(self):
        cov = {"entries": [_entry("JERG:dup", merged_into="JERG:keep",
                                  assigned=False),
                           _entry("JERG:keep", assigned=False)]}
        self.assertEqual(orchestrator._count_unmapped(cov), 1)

    def test_sample_skips_merged(self):
        merged = _entry("JERG:dup", merged_into="JERG:keep")
        keep = _entry("JERG:keep")
        got = independent_recheck.sample([merged, keep], 5, seed=1)
        self.assertEqual([e["key"] for e in got], ["JERG:keep"])

    def test_pick_keys_refuses_merged(self):
        merged = _entry("JERG:dup", merged_into="JERG:keep")
        keep = _entry("JERG:keep")
        picked, problems = independent_recheck.pick_keys(
            [merged, keep], "JERG:dup")
        self.assertEqual(picked, [])
        self.assertTrue(any("統合済み" in p and "JERG:keep" in p
                            for p in problems))

    def test_merge_preserves_the_evaluated_assignment(self):
        """統合欄を書いても判定・履歴は残る（消さない）。"""
        merged = _entry("JERG:dup", merged_into="JERG:keep")
        self.assertIn("assigned_at", merged)
        self.assertEqual(merged["disposition"], "UNKNOWN")


class MergeValidationTest(unittest.TestCase):
    def _validate_with(self, entries):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "catalogs"))
            path = os.path.join(td, "catalogs", "jerg-coverage.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f, ensure_ascii=False)
            return orchestrator._validate_coverage_merges(ledger_dir=td)

    def test_proper_merge_is_green(self):
        problems = self._validate_with(
            [_entry("JERG:dup", merged_into="JERG:keep"), _entry("JERG:keep")])
        self.assertEqual(problems, [])

    def test_dangling_target_is_red(self):
        problems = self._validate_with(
            [_entry("JERG:dup", merged_into="JERG:ghost")])
        self.assertTrue(any("実在しない" in p for p in problems))

    def test_chained_merge_is_red(self):
        problems = self._validate_with(
            [_entry("JERG:a", merged_into="JERG:b"),
             _entry("JERG:b", merged_into="JERG:c"),
             _entry("JERG:c")])
        self.assertTrue(any("連鎖" in p for p in problems))

    def test_missing_note_is_red(self):
        e = _entry("JERG:dup", merged_into="JERG:keep")
        del e["merge_note"]
        problems = self._validate_with([e, _entry("JERG:keep")])
        self.assertTrue(any("merge_note" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
