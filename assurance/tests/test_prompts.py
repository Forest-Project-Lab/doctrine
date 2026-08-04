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


if __name__ == "__main__":
    unittest.main()
