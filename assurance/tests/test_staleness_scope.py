#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""古びの見方を種別ごとの指紋と閾値で決める（ADR-134。INC-025 の是正）。

INC-025: ADR-130 は「索引全体の指紋が変わったら全件を古びさせる」を**却下した
選択肢**として明記しながら、実装がそのまま採っていた。試験ファイルを 1 件足した
だけで非終端 286 件が全件古び、反復ごとに約 $13.7・約 95 分を要求していた。

所有者の判断は「種別ごとの指紋＋閾値で挙げる」（2026-08-07）。

凍結したいこと:
- 索引が**種別ごとの指紋**を持ち、種別が動いたことと索引全体が動いたことを分ける。
- 証拠を持つ判定は、**その証拠が属する種別**が動いたときだけ古びる。
  関係の無い種別が動いても古びない（試験を 1 件足しただけで文書の判定が古びない）。
- 証拠を持たない非終端（「何も無い」という主張）は、種別が**増えた**ときだけ古びる。
  既存要素の並べ替えや削除では古びない —— 増えた物だけが「無い」を覆せる。
- 古びは**閾値**に達するまで next_actions に挙げない。数えて出すのは常に行う
  （黙って隠さない。INC-006）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator, system_index  # noqa: E402


class CategoryFingerprintTest(unittest.TestCase):
    def test_index_carries_a_fingerprint_per_category(self):
        idx = system_index.build()
        cats = idx["category_sha256"]
        for name in ("documents", "scripts", "test_files", "audit_checks",
                     "linter_codes", "hooks", "skills"):
            self.assertIn(name, cats, name)
            self.assertEqual(len(cats[name]), 64, name)

    def test_index_carries_a_count_per_category(self):
        """「増えたか」を判ずるには件数が要る（指紋は増減を区別しない）。"""
        idx = system_index.build()
        for name, n in idx["category_counts"].items():
            self.assertEqual(n, len(idx[name]), name)

    def test_whole_index_fingerprint_is_kept(self):
        """全体の指紋を消さない —— 既存の記録との突き合わせに要る。"""
        self.assertEqual(len(system_index.build()["sha256"]), 64)


class ScopedStalenessTest(unittest.TestCase):
    """証拠の属する種別だけを見る。"""

    def _stamp(self, **cats):
        base = {"documents": "a" * 64, "scripts": "b" * 64,
                "test_files": "c" * 64, "audit_checks": "d" * 64,
                "linter_codes": "e" * 64, "hooks": "f" * 64, "skills": "g" * 64}
        base.update(cats)
        return base

    def _now(self, **cats):
        return {"category_sha256": self._stamp(**cats),
                "category_counts": {"documents": 10, "scripts": 10,
                                    "test_files": 10, "audit_checks": 10,
                                    "linter_codes": 10, "hooks": 10,
                                    "skills": 10}}

    def _entry(self, disposition, evidence, counts=None):
        return {"key": "K1", "disposition": disposition, "evidence": evidence,
                "assigned_at": "2026-08-07T00:00:00Z",
                "assigned_by": {"category_sha256": self._stamp(),
                                "category_counts": counts or {
                                    "documents": 10, "scripts": 10,
                                    "test_files": 10, "audit_checks": 10,
                                    "linter_codes": 10, "hooks": 10,
                                    "skills": 10}}}

    def test_unrelated_category_does_not_stale_an_evidenced_entry(self):
        """INC-025 そのもの —— 試験を 1 件足しても、文書を証拠にした判定は古びない。"""
        e = self._entry("実装・試験・証拠あり", ["ADR-051"])
        now = self._now(test_files="z" * 64)          # 試験だけが動いた
        self.assertFalse(orchestrator.is_stale(
            e, now, lambda p: "document"))

    def test_the_cited_category_moving_stales_the_entry(self):
        e = self._entry("実装・試験・証拠あり", ["adr_not_landed"])
        now = self._now(audit_checks="z" * 64)        # 引いた種別が動いた
        self.assertTrue(orchestrator.is_stale(
            e, now, lambda p: "audit_check"))

    def test_entry_without_evidence_stales_only_when_a_category_grew(self):
        """「何も無い」という主張は、**増えた**物だけが覆せる。

        並べ替えや削除で古びさせると、また全件が毎回古びる形へ戻る。
        """
        e = self._entry("対応計画あり", [])
        grew = self._now(test_files="z" * 64)
        grew["category_counts"]["test_files"] = 11    # 増えた
        self.assertTrue(orchestrator.is_stale(e, grew, lambda p: None))

        shrank = self._now(test_files="z" * 64)
        shrank["category_counts"]["test_files"] = 9   # 減った
        self.assertFalse(orchestrator.is_stale(e, shrank, lambda p: None))

    def test_nothing_moved_is_not_stale(self):
        e = self._entry("対応計画あり", [])
        self.assertFalse(orchestrator.is_stale(e, self._now(), lambda p: None))

    def test_missing_stamp_is_stale(self):
        """種別の指紋を持たない古い記録は「どの索引に対する判定か判らない」。

        ADR-130 の第1項と同じ向き —— 判らないものは前提欠如の側へ倒す。
        """
        e = {"key": "K1", "disposition": "対応計画あり",
             "assigned_at": "2026-08-07T00:00:00Z", "assigned_by": {}}
        self.assertTrue(orchestrator.is_stale(e, self._now(), lambda p: None))


class ThresholdTest(unittest.TestCase):
    """閾値に達するまで行動に挙げない。ただし数えるのは常に行う。"""

    def test_threshold_is_declared_once(self):
        self.assertIsInstance(orchestrator.STALE_RAISE_THRESHOLD, int)
        self.assertGreater(orchestrator.STALE_RAISE_THRESHOLD, 1)

    def test_below_threshold_is_counted_but_not_raised(self):
        """挙げないが、数えて出す —— 黙って隠すと INC-006 の形になる。"""
        self.assertFalse(orchestrator.should_raise_stale(
            orchestrator.STALE_RAISE_THRESHOLD - 1))

    def test_at_threshold_it_is_raised(self):
        self.assertTrue(orchestrator.should_raise_stale(
            orchestrator.STALE_RAISE_THRESHOLD))

    def test_zero_is_never_raised(self):
        self.assertFalse(orchestrator.should_raise_stale(0))


if __name__ == "__main__":
    unittest.main()
