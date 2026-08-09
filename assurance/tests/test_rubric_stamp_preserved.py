#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""決定論の掃引は規準の刻印を上書きしない（INC-037。ADR-133 決定3 の保全）。

`recheck_evidence` の掃引が引き直すのは**証拠のポインタ**であって、規準
そのものを当て直すわけではない。それなのに `rubric_sha256` を現行の値で
上書きしていたので、規準が動いた後に掃引を回すと、台帳が「どの規準に対する
判定か」を言えなくなる —— ADR-133 決定3 が持たせた性質が静かに失われる。

規準が動いたときの引き直しは意味の再判定（MAP_COVERAGE）の仕事である。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import recheck_evidence  # noqa: E402


def _idx():
    return {"sha256": "新しい索引", "category_sha256": {"documents": "新"},
            "category_counts": {"documents": 2}}


class RubricStampIsPreservedTest(unittest.TestCase):
    def test_an_existing_rubric_stamp_survives_the_sweep(self):
        e = {"key": "K", "disposition": "実装・試験・証拠あり",
             "assigned_by": {"rubric_sha256": "古い規準",
                             "index_sha256": "古い索引"}}
        recheck_evidence._refresh_stamp(e, _idx(), "新しい規準", ["p"], [])
        self.assertEqual(e["assigned_by"]["rubric_sha256"], "古い規準",
                         "決定論の掃引が規準の刻印を上書きした")

    def test_the_index_stamps_are_refreshed(self):
        """射程を狭めすぎない —— 索引の刻印は掃引の務めなので更新する。"""
        e = {"key": "K", "disposition": "実装・試験・証拠あり",
             "assigned_by": {"rubric_sha256": "古い規準",
                             "index_sha256": "古い索引"}}
        recheck_evidence._refresh_stamp(e, _idx(), "新しい規準", ["p"], [])
        by = e["assigned_by"]
        self.assertEqual(by["index_sha256"], "新しい索引")
        self.assertEqual(by["category_sha256"], {"documents": "新"})
        self.assertTrue(by["rechecked_deterministically"])

    def test_a_record_without_a_rubric_stamp_gets_one(self):
        """刻印を持たない古い記録には付ける（無いより在るほうがよい）。"""
        e = {"key": "K", "disposition": "非該当で理由あり", "assigned_by": {}}
        recheck_evidence._refresh_stamp(e, _idx(), "新しい規準", ["p"], [])
        self.assertEqual(e["assigned_by"]["rubric_sha256"], "新しい規準")

    def test_the_real_ledger_carries_one_rubric_per_record(self):
        """実台帳に規準の刻印が在ること（空の緑にしない）。"""
        import glob
        import json
        seen = 0
        for path in sorted(glob.glob(
                os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), "ledger", "catalogs",
                    "*-coverage.json"))):
            with open(path, encoding="utf-8") as fh:
                for e in json.load(fh).get("entries", []):
                    by = e.get("assigned_by") or {}
                    if by.get("rubric_sha256"):
                        seen += 1
        self.assertGreater(seen, 0, "規準の刻印を持つ記録が一件も無い")


if __name__ == "__main__":
    unittest.main()
