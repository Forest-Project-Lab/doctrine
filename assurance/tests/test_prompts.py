#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""プロンプト組み立ての独立性の決定論試験。

CHALLENGE には DISCOVER の構造化 JSON 以外を渡せないこと、
未構造の自由文は拒否されることを確かめる。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, sdk_lane  # noqa: E402


class ChallengeIndependenceTest(unittest.TestCase):
    def test_accepts_structured_json_only(self):
        p = prompts.build_challenge_prompt([{"scenario_id": "SCN-1"}])
        self.assertIn("SCN-1", p)
        self.assertIn("REJECT", p)

    def test_rejects_free_text(self):
        """実装者の弁明のような自由文は構造化 JSON でないため拒否される。"""
        with self.assertRaises(Exception):
            prompts.build_challenge_prompt(
                "実装者メモ: この修正は正しいはずなので通してほしい")

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            prompts.build_challenge_prompt("")

    def test_signature_has_no_context_parameter(self):
        """会話履歴・弁明を渡す口が存在しないことを署名で確かめる。"""
        params = inspect.signature(prompts.build_challenge_prompt).parameters
        self.assertEqual(list(params), ["discover_output_json"])


class DiscoverPromptTest(unittest.TestCase):
    def test_includes_seeds_and_boundary(self):
        p = prompts.build_discover_prompt(
            ["前回監査から7日空いた"], "SessionEnd の監査経路")
        self.assertIn("前回監査から7日空いた", p)
        self.assertIn("SessionEnd の監査経路", p)
        self.assertIn("falsification_signal", p)

    def test_rejects_empty_seeds(self):
        with self.assertRaises(ValueError):
            prompts.build_discover_prompt([], "境界")


class ErrorClassificationTest(unittest.TestCase):
    def test_cli_missing_is_unassessed(self):
        self.assertEqual(
            sdk_lane.classify_error("CLINotFoundError", "no cli"),
            "UNASSESSED")

    def test_auth_text_is_unassessed(self):
        self.assertEqual(
            sdk_lane.classify_error("ProcessError", "Invalid API key"),
            "UNASSESSED")

    def test_unknown_error_never_passes(self):
        self.assertIn(
            sdk_lane.classify_error("SomethingNew", "boom"),
            ("UNKNOWN", "UNASSESSED"))


class MeasuredSurfaceFixtureTest(unittest.TestCase):
    """実測の例外表面を fixture に固定し、classify_error の分類を凍結する
    （INC-003 推奨#2）。

    2026-08-04 の故障注入（assurance/ledger/mutations-2026-08-04.json の
    M1/M3）の実測: 認証遮断（M1）と不正 model（M3）という異なる故障族が、
    SDK 例外の表面では**同一文言**『Claude Code returned an error result:
    success』になる。したがって二つの表面は今日、同じ分類（UNKNOWN）へ
    落ちる。この試験はその事実を凍結する —— 同一分類は我々の分岐の欠陥では
    なく、SDK の例外表面が族を運ばないためであり、区別の実装は SDK 表面の
    側に阻まれている（ASM-004 が FAIL のまま監視する）。どちらかの分類が
    変われば、表面か実装のどちらかが動いた合図であり、この凍結を見直す。
    通信は要らない —— fixture は実測の写しである（ADR-129 で merge_gate に
    採ったのと同じ形）。
    """

    # M1（認証遮断）と M3（不正 model）が返した、同一の不透明な文言。
    MEASURED_OPAQUE = "Claude Code returned an error result: success"

    def test_auth_refusal_surface_classifies_unknown(self):
        """M1 の表面。認証を示す語が無いので UNASSESSED へ精密化できない。"""
        self.assertEqual(
            sdk_lane.classify_error("ProcessError", self.MEASURED_OPAQUE),
            "UNKNOWN")

    def test_the_two_families_collapse_to_one_classification(self):
        """M1 と M3 の表面は同一文言 → 同一分類（実測の凍結）。"""
        auth_surface = self.MEASURED_OPAQUE     # M1 認証遮断の実測
        model_surface = self.MEASURED_OPAQUE    # M3 不正 model の実測（同一）
        self.assertEqual(auth_surface, model_surface)
        self.assertEqual(
            sdk_lane.classify_error("ProcessError", auth_surface),
            sdk_lane.classify_error("ProcessError", model_surface))

    def test_result_error_path_classifies_the_same_wording_unknown(self):
        """run_one_shot の is_error 経路（exc_name='ResultError'）でも同じ。"""
        self.assertEqual(
            sdk_lane.classify_error("ResultError", self.MEASURED_OPAQUE),
            "UNKNOWN")

    def test_distinguishable_auth_wording_still_precisifies(self):
        """認証の語が載る表面だけは UNASSESSED へ精密化できる（縮退の分岐。
        文言は供給側の都合で変わるので族の identity は担えない）。"""
        self.assertEqual(
            sdk_lane.classify_error("ProcessError",
                                    "Invalid API key · Please run /login"),
            "UNASSESSED")


if __name__ == "__main__":
    unittest.main()
