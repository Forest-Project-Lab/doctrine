#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""採点規準の境界の判定規則（ADR-133）の決定論試験。

INC-024 で、規準が最も使われる境界で判定を決めていないことが判った ——
「その原則を求める決定や仕様が現に在る」ことを『実装・試験・証拠あり』と読むか
『対応計画あり』と読むかが、文面から一意に決まらない。抜取り 25 件のうち 7 件が
割れ、すべてこの一つの境界に集まっていた。

凍結したいこと:
- 規準が二つの判定規則を明文で持つこと（決定だけを証拠にしない・検出は阻止でない）。
- **機械で決まる床**: 解決した証拠が文書 id だけの割当は緑にしない。
- 規準の指紋が本文から導かれ、本文を変えれば必ず動くこと（宣言と実体がずれない）。
- 判定に規準の指紋が刻まれること（どの規準に対する判定かを後から言えるように）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts  # noqa: E402


class CharterStatesTheBoundaryTest(unittest.TestCase):
    def test_charter_says_decisions_alone_are_not_green(self):
        """決定や仕様だけを証拠にした緑を禁ずる文が在ること。"""
        text = prompts._MAP_COVERAGE_CHARTER
        self.assertIn("決定や仕様", text)
        self.assertIn("そう決めた", text)

    def test_charter_says_detection_is_not_prevention(self):
        """『事後に検出する』機構を『事前に阻止する』原則の証拠にしない。

        観測された不一致の典型がこれである（STPA:no-skipping-upstream-activities
        は adr_not_landed という実在の監査検査を証拠に挙げていたが、独立の判定は
        「これらは事後の欠落検出であり、工程を止める門は索引に無い」とした）。
        """
        text = prompts._MAP_COVERAGE_CHARTER
        self.assertIn("検出", text)
        self.assertIn("阻止", text)

    def test_charter_keeps_the_do_not_lean_green_rule(self):
        """既存の『緑へ倒さない』を消していないこと（規則を足す変更である）。"""
        self.assertIn("緑へ倒さない", prompts._MAP_COVERAGE_CHARTER)


class MachineFloorTest(unittest.TestCase):
    """機械で決まる床。規準の全部ではなく、決められるところだけを決める。"""

    def _resolve(self, mapping):
        return lambda p: mapping.get(p)

    def test_document_only_evidence_cannot_be_green(self):
        """解決した証拠が文書 id だけの緑は『対応計画あり』へ落ちる。

        決定は「そう決めた」ことの記録であって、決めたことが現に効いている
        証拠ではない。ADR-118 が『解決しないポインタしか無い緑』を落としたのと
        同じ形を、一段内側の境界に適用する。
        """
        accepted, downgraded, _ = prompts.verify_coverage_assignments(
            [{"key": "K1", "disposition": "実装・試験・証拠あり",
              "evidence": ["ADR-051", "SPEC-025"], "reason": "決定が在る"}],
            self._resolve({"ADR-051": "document", "SPEC-025": "document"}),
            ["K1"])
        self.assertEqual(accepted, [])
        self.assertEqual(len(downgraded), 1)
        self.assertEqual(downgraded[0]["disposition"], "対応計画あり")
        self.assertEqual(downgraded[0]["original_disposition"],
                         "実装・試験・証拠あり")

    def test_one_enforcing_pointer_keeps_it_green(self):
        """機構を指すポインタが一つでも在れば床は効かない。

        床は「決定しか無い」を落とすためのものであり、機構の当てはまりの
        良し悪しを判ずるものではない —— そこは意味の判断であって機械では
        閉じない（NONGOAL-001 第1項）。
        """
        accepted, downgraded, _ = prompts.verify_coverage_assignments(
            [{"key": "K1", "disposition": "実装・試験・証拠あり",
              "evidence": ["ADR-051", "adr_not_landed"], "reason": "検査が在る"}],
            self._resolve({"ADR-051": "document",
                           "adr_not_landed": "audit_check"}),
            ["K1"])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(downgraded, [])
        self.assertEqual(accepted[0]["disposition"], "実装・試験・証拠あり")

    def test_unresolved_pointers_still_fall_to_unknown(self):
        """ADR-118 の既存の規則を壊していないこと。

        解決するポインタが一つも無い緑は UNKNOWN であって『対応計画あり』では
        ない。新しい床が既存の床を上書きしない。
        """
        _accepted, downgraded, _ = prompts.verify_coverage_assignments(
            [{"key": "K1", "disposition": "実装・試験・証拠あり",
              "evidence": ["存在しない"], "reason": "x"}],
            self._resolve({}), ["K1"])
        self.assertEqual(downgraded[0]["disposition"], "UNKNOWN")

    def test_floor_does_not_touch_other_dispositions(self):
        """文書 id だけでも『対応計画あり』はそのまま通る（床は緑にだけ効く）。"""
        accepted, downgraded, _ = prompts.verify_coverage_assignments(
            [{"key": "K1", "disposition": "対応計画あり",
              "evidence": ["ADR-051"], "reason": "x"}],
            self._resolve({"ADR-051": "document"}), ["K1"])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(downgraded, [])


class RubricFingerprintTest(unittest.TestCase):
    def test_fingerprint_is_derived_from_the_charter_text(self):
        """指紋は本文から導く。手で書いた版番号は本文とずれる（INC-019 の形）。"""
        self.assertEqual(prompts.rubric_fingerprint(),
                         prompts.sha256_of(prompts._MAP_COVERAGE_CHARTER))

    def test_fingerprint_moves_when_the_charter_moves(self):
        original = prompts._MAP_COVERAGE_CHARTER
        try:
            prompts._MAP_COVERAGE_CHARTER = original + "\n- 追記\n"
            self.assertNotEqual(prompts.rubric_fingerprint(),
                                prompts.sha256_of(original))
        finally:
            prompts._MAP_COVERAGE_CHARTER = original


class DeterministicSweepTest(unittest.TestCase):
    """終端の判定を評価を買わずに引き直す口（ADR-133）。

    ADR-130 は「決定論の再照合で足りる」と書きながら走らせ手を作らなかった。
    ここがその口である。
    """

    def setUp(self):
        from harness import recheck_evidence
        self.mod = recheck_evidence
        # 索引の stub。ADR-134 で種別ごとの指紋と件数を持つようになったので、
        # sweep が現行へ揃える先としてそれらも用意する。
        cats = ("documents", "audit_checks", "linter_codes", "scripts",
                "test_files", "hooks", "skills")
        self.idx = {"sha256": "n" * 64,
                    "category_sha256": {c: "n" * 64 for c in cats},
                    "category_counts": {c: 1 for c in cats}}

    def _sweep(self, entries, kinds):
        import harness.system_index as si
        original = si.resolve_pointer
        si.resolve_pointer = lambda idx, p: kinds.get(p)
        try:
            return self.mod.sweep({"entries": entries}, self.idx, "r" * 64)
        finally:
            si.resolve_pointer = original

    def _green(self, **over):
        e = {"key": "K1", "disposition": "実装・試験・証拠あり",
             "evidence": ["adr_not_landed"], "assigned_at": "2026-08-05T00:00:00Z",
             "assigned_by": {"index_sha256": "o" * 64}}
        e.update(over)
        return e

    def test_evidence_that_vanished_falls_to_unknown(self):
        """解決するポインタが一つも無くなった緑は UNKNOWN（ADR-118 の規則）。"""
        e = self._green(evidence=["消えた検査"])
        moved = self._sweep([e], {})
        self.assertEqual(e["disposition"], "UNKNOWN")
        self.assertEqual(moved[0]["to"], "UNKNOWN")

    def test_decisions_only_falls_to_plan(self):
        """解決するのが決定・仕様だけになった緑は『対応計画あり』（ADR-133 の床）。"""
        e = self._green(evidence=["ADR-051"])
        self._sweep([e], {"ADR-051": "document"})
        self.assertEqual(e["disposition"], "対応計画あり")

    def test_still_enforcing_keeps_its_disposition_and_refreshes_the_fingerprint(self):
        """証拠が現に解決するなら判定はそのまま。指紋だけ現行へ揃える。"""
        e = self._green()
        moved = self._sweep([e], {"adr_not_landed": "audit_check"})
        self.assertEqual(moved, [])
        self.assertEqual(e["disposition"], "実装・試験・証拠あり")
        self.assertEqual(e["assigned_by"]["index_sha256"], self.idx["sha256"])
        self.assertEqual(e["assigned_by"]["category_sha256"],
                         self.idx["category_sha256"])
        self.assertTrue(e["assigned_by"]["rechecked_deterministically"])

    def test_sweep_never_turns_anything_green(self):
        """決定論では緑を増やせない。片方向にしか動かさない。

        「証拠が消えた」は決定論で言えるが、「新たに実装された」は言えない
        —— それは評価の仕事である。ここが双方向に動くと、評価を買わずに
        緑を増やす道ができる。
        """
        e = {"key": "K1", "disposition": "対応計画あり",
             "evidence": ["adr_not_landed"], "assigned_at": "2026-08-05T00:00:00Z",
             "assigned_by": {}}
        self._sweep([e], {"adr_not_landed": "audit_check"})
        self.assertEqual(e["disposition"], "対応計画あり")

    def test_unjudged_entries_are_left_alone(self):
        """未割当の項には触らない（決定論に引き直す前の判定が無い）。"""
        e = {"key": "K1", "disposition": "UNKNOWN"}
        self.assertEqual(self._sweep([e], {}), [])
        self.assertEqual(e["disposition"], "UNKNOWN")

    def test_downgrade_keeps_the_previous_judgement_in_history(self):
        e = self._green(evidence=["ADR-051"])
        self._sweep([e], {"ADR-051": "document"})
        self.assertEqual(e["reassessments"][-1]["disposition"],
                         "実装・試験・証拠あり")


class NotApplicableSweepTest(unittest.TestCase):
    """決定論の再照合は「非該当で理由あり」も掃く（ADR-143）。

    この口が終端の緑だけを見ていたため、80 件の非該当が決定論の再照合の
    範囲外に置かれていた（実測。ADR-134 の帰結が「埋まっていない」と名指した
    穴）。非該当の根拠は境界を引いた決定・機構のポインタに在るので、緑と同じ
    形で索引へ引き直せる —— ただし決定だけを根拠にしてよい（ADR-133 の床は
    「効いている証拠」を求める緑の規則であり、範囲の主張には当てはめない）。
    """

    setUp = DeterministicSweepTest.setUp
    _sweep = DeterministicSweepTest._sweep

    def _na(self, **over):
        e = {"key": "K1", "disposition": "非該当で理由あり",
             "reason": "範囲の外である", "evidence": ["ADR-015"],
             "assigned_at": "2026-08-05T00:00:00Z",
             # 種別の指紋を持たない古い記録 = 正本の規則で古び（ADR-134）。
             "assigned_by": {"index_sha256": "o" * 64}}
        e.update(over)
        return e

    def test_na_with_resolving_evidence_refreshes_the_stamp(self):
        """根拠が一つでも解決すれば判定を保ち、指紋だけ現行へ揃える。"""
        e = self._na(evidence=["ADR-015", "消えた検査"])
        moved = self._sweep([e], {"ADR-015": "document"})
        self.assertEqual(moved, [])
        self.assertEqual(e["disposition"], "非該当で理由あり")
        self.assertEqual(e["evidence"], ["ADR-015"])
        self.assertEqual(e["unresolved_evidence"], ["消えた検査"])
        self.assertEqual(e["assigned_by"]["index_sha256"], self.idx["sha256"])
        self.assertEqual(e["assigned_by"]["category_sha256"],
                         self.idx["category_sha256"])
        self.assertTrue(e["assigned_by"]["rechecked_deterministically"])

    def test_na_kept_by_decisions_alone_is_not_downgraded(self):
        """ADR-133 の床（決定だけの緑を落とす）を非該当へ**流用しない**。

        非該当は「範囲の外」という主張であり、境界を引いた決定こそが根拠で
        ある。決定だけでも判定は保つ。
        """
        e = self._na(evidence=["ADR-015"])
        self._sweep([e], {"ADR-015": "document"})
        self.assertEqual(e["disposition"], "非該当で理由あり")

    def test_na_that_lost_all_evidence_falls_to_unknown(self):
        """根拠が一つも解決しなくなった非該当は UNKNOWN へ落ちる。"""
        e = self._na(evidence=["消えた決定", "消えた検査"])
        moved = self._sweep([e], {})
        self.assertEqual(e["disposition"], "UNKNOWN")
        self.assertIn("非該当の根拠が一つも解決しなくなった", e["reason"])
        self.assertEqual(moved, [{"key": "K1", "to": "UNKNOWN",
                                  "lost": ["消えた決定", "消えた検査"]}])
        # 決定論で結論が出ているので評価済みのまま（未評価と混ぜない。INC-006）。
        self.assertIn("assigned_at", e)
        self.assertEqual(e["reassessments"][-1]["disposition"],
                         "非該当で理由あり")

    def test_fresh_na_is_left_alone(self):
        """正本の規則で古びていない非該当は触らない（掃く理由が無い）。"""
        e = self._na(assigned_by={
            "index_sha256": self.idx["sha256"],
            "category_sha256": dict(self.idx["category_sha256"]),
            "category_counts": dict(self.idx["category_counts"])})
        self.assertEqual(self._sweep([e], {}), [])
        self.assertEqual(e["disposition"], "非該当で理由あり")
        self.assertNotIn("rechecked_deterministically", e["assigned_by"])

    def test_na_without_pointers_is_left_alone(self):
        """根拠ポインタの無い非該当は決定論では検めようがない。落とさない。"""
        e = self._na(evidence=[])
        self.assertEqual(self._sweep([e], {}), [])
        self.assertEqual(e["disposition"], "非該当で理由あり")

    def test_sweep_never_creates_green_or_na(self):
        """片方向。緑にも非該当にも動かさない —— それは評価の仕事である。

        「根拠が消えた」は決定論で言えるが、「新たに実装された」「新たに
        範囲外になった」は言えない。ここが双方向に動くと、評価を買わずに
        終端が増える道ができる。
        """
        for disp in ("対応計画あり", "UNKNOWN", "UNASSESSED"):
            e = {"key": "K1", "disposition": disp,
                 "evidence": ["adr_not_landed"],
                 "assigned_at": "2026-08-05T00:00:00Z",
                 "assigned_by": {"index_sha256": "o" * 64}}
            self._sweep([e], {"adr_not_landed": "audit_check"})
            self.assertEqual(e["disposition"], disp)


if __name__ == "__main__":
    unittest.main()
