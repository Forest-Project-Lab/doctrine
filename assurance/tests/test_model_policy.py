#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""model 方針の決定論試験。

所有者指示(2026-08-04)の最低線「評価は opus の high 以上、haiku は配管と
劣化プローブだけ」が、コードの形で破れないことを凍結する。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import model_policy  # noqa: E402


class ModelPolicyTest(unittest.TestCase):
    def test_evaluation_is_opus_high(self):
        opts = model_policy.options_for("evaluation")
        self.assertEqual(opts["model"], "claude-opus-5")
        self.assertEqual(opts["effort"], "high")

    def test_evaluation_floor_rejects_haiku(self):
        with self.assertRaises(ValueError):
            model_policy.assert_evaluation_floor("claude-haiku-4-5", "high")

    def test_evaluation_floor_rejects_low_effort(self):
        for effort in ("low", "medium", None):
            with self.assertRaises(ValueError):
                model_policy.assert_evaluation_floor("claude-opus-5", effort)

    def test_evaluation_floor_allows_higher_effort(self):
        for effort in ("high", "xhigh", "max"):
            self.assertTrue(
                model_policy.assert_evaluation_floor("claude-opus-5", effort))

    def test_degradation_probe_is_explicit_role(self):
        opts = model_policy.options_for("degradation-probe")
        self.assertEqual(opts["model"], "claude-haiku-4-5")

    def test_unknown_role_raises(self):
        """未知の役割を黙って既定へ倒さない。"""
        with self.assertRaises(ValueError):
            model_policy.options_for("cheap")


if __name__ == "__main__":
    unittest.main()
