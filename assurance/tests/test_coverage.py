#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""網羅台帳の骨組み生成の決定論試験（実カタログに依存しない）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import coverage  # noqa: E402


class CoverageInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig = coverage.CATALOG_DIR
        coverage.CATALOG_DIR = self.tmp.name
        self.addCleanup(setattr, coverage, "CATALOG_DIR", self._orig)

    def _write_catalog(self, principles):
        with open(os.path.join(self.tmp.name, "jerg-principles.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"book_sha256": "abc", "principles": principles}, f)

    def _read_cov(self):
        with open(os.path.join(self.tmp.name, "jerg-coverage.json"),
                  encoding="utf-8") as f:
            return json.load(f)

    def test_missing_catalog_is_unassessed(self):
        self.assertEqual(coverage.init("jerg"), 3)

    def test_init_stands_all_unknown(self):
        self._write_catalog([
            {"title": "独立検証", "dedupe_key": "iv&v", "category": "独立性",
             "source_lines": "L10-L12"},
            {"title": "記録の追跡", "dedupe_key": "trace", "category": "証拠と記録",
             "source_lines": "L20-L22"},
        ])
        self.assertEqual(coverage.init("jerg"), 0)
        cov = self._read_cov()
        self.assertEqual(len(cov["entries"]), 2)
        self.assertTrue(all(e["disposition"] == "UNKNOWN"
                            for e in cov["entries"]))

    def test_reinit_keeps_existing_assignment(self):
        """再生成は評価済みの割当を上書きしない（証拠の消失防止）。"""
        self._write_catalog([{"title": "t", "dedupe_key": "k1",
                              "category": "証拠と記録", "source_lines": "L1-L2"}])
        coverage.init("jerg")
        cov = self._read_cov()
        cov["entries"][0]["disposition"] = "実装・試験・証拠あり"
        cov["entries"][0]["evidence"] = "plugin/tests/test_audit.py"
        with open(os.path.join(self.tmp.name, "jerg-coverage.json"),
                  "w", encoding="utf-8") as f:
            json.dump(cov, f, ensure_ascii=False)
        coverage.init("jerg")
        cov2 = self._read_cov()
        self.assertEqual(cov2["entries"][0]["disposition"], "実装・試験・証拠あり")

    def test_duplicate_dedupe_keys_both_survive(self):
        self._write_catalog([
            {"title": "a", "dedupe_key": "same", "category": "その他",
             "source_lines": "L1-L2"},
            {"title": "b", "dedupe_key": "same", "category": "その他",
             "source_lines": "L3-L4"},
        ])
        coverage.init("jerg")
        keys = [e["key"] for e in self._read_cov()["entries"]]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
