#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""VERIFY レーンの決定論試験（SDK 不要・通信不要。ADR-139）。

凍結したいこと:
- 記録の schema が三つの checks（red_was_red / green_is_green / single_change）を
  必須に持つこと。
- 検証のプロンプトが構造化された一つの対象しか受け取らないこと（会話の口が無い）。
- before_fail_after_pass は verdict PASS かつ三 checks 全 PASS のときだけ真で、
  UNKNOWN を通さないこと（判定できなかったことを、通ったことと読まない）。
- 赤の証拠が無いときの記録が UNASSESSED の形で、fixed:true の門を通らないこと。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, schemas, verify_fix  # noqa: E402


def _record(verdict="PASS", **checks):
    base_checks = {"red_was_red": "PASS", "green_is_green": "PASS",
                   "single_change": "PASS"}
    base_checks.update(checks)
    return {"target_id": "INC-099-x", "verdict": verdict,
            "reasons": ["r"], "checks": base_checks}


class VerifyRecordSchemaTest(unittest.TestCase):
    def test_minimal_record_validates(self):
        self.assertEqual(
            schemas.validate(schemas.VERIFY_RECORD_SCHEMA, _record()), [])

    def test_missing_checks_is_a_violation(self):
        rec = _record()
        del rec["checks"]
        self.assertTrue(schemas.validate(schemas.VERIFY_RECORD_SCHEMA, rec))

    def test_missing_single_check_is_a_violation(self):
        rec = _record()
        del rec["checks"]["single_change"]
        self.assertTrue(schemas.validate(schemas.VERIFY_RECORD_SCHEMA, rec))

    def test_check_outside_the_vocabulary_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.VERIFY_RECORD_SCHEMA, _record(red_was_red="緑")))


class VerifyIndependenceTest(unittest.TestCase):
    def test_prompt_takes_only_the_structured_input(self):
        """会話履歴・弁明を渡す口を作らない（CHALLENGE と同じ独立性）。"""
        params = inspect.signature(prompts.build_verify_prompt).parameters
        self.assertEqual(list(params), ["verify_input_json"])

    def test_unstructured_string_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_verify_prompt("散文の弁明")

    def test_object_without_target_id_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_verify_prompt({"claim": "直した"})

    def test_prompt_states_that_silence_is_not_pass(self):
        p = prompts.build_verify_prompt(
            {"target_id": "INC-099-x", "claim": "c", "red_evidence": {},
             "diff": "", "post_fix_observation": None})
        self.assertIn("沈黙", p)


class BeforeFailAfterPassTest(unittest.TestCase):
    """VERIFIED の guard（TRANSITIONS と同名の呼べる実体）。"""

    def test_requires_all_three_checks_pass(self):
        self.assertTrue(verify_fix.before_fail_after_pass(_record()))
        for key in ("red_was_red", "green_is_green", "single_change"):
            self.assertFalse(verify_fix.before_fail_after_pass(
                _record(**{key: "FAIL"})), key)

    def test_unknown_check_does_not_satisfy(self):
        """判定できなかったことを、通ったことと読まない。"""
        for key in ("red_was_red", "green_is_green", "single_change"):
            self.assertFalse(verify_fix.before_fail_after_pass(
                _record(**{key: "UNKNOWN"})), key)

    def test_unknown_or_fail_verdict_does_not_satisfy(self):
        self.assertFalse(verify_fix.before_fail_after_pass(
            _record(verdict="UNKNOWN")))
        self.assertFalse(verify_fix.before_fail_after_pass(
            _record(verdict="FAIL")))

    def test_missing_record_does_not_satisfy(self):
        self.assertFalse(verify_fix.before_fail_after_pass(None))
        self.assertFalse(verify_fix.before_fail_after_pass({}))


class BuildRecordTest(unittest.TestCase):
    """台帳の記録の形（純関数）。書き込みは main が行う。"""

    def test_unassessed_record_shape_without_red_evidence(self):
        """赤の証拠が無い検証は UNASSESSED で、fixed:true の門を通らない。"""
        doc = verify_fix.build_record(
            "INC-099-x", diff_range="a..b", sdk_status="UNASSESSED",
            reason="赤の証拠が無い", generated_at="2026-08-07T00:00:00Z")
        self.assertEqual(doc["kind"], "verify-record")
        self.assertEqual(doc["target_id"], "INC-099-x")
        self.assertEqual(doc["sdk_status"], "UNASSESSED")
        self.assertIsNone(doc["record"])
        self.assertIn("赤の証拠", doc["reason"])
        # 前提欠如の記録は guard を満たさない（閉じる側へ倒す）。
        self.assertFalse(verify_fix.before_fail_after_pass(doc["record"]))

    def test_record_carries_the_evidence_fingerprints(self):
        doc = verify_fix.build_record(
            "INC-099-x", diff_range="a..b", diff_sha256="d" * 64,
            red_sha256="r" * 64, prompt_sha256="p" * 64,
            model="claude-opus-5", effort="high", cost_usd=0.1,
            record=_record(), sdk_status="PASS",
            generated_at="2026-08-07T00:00:00Z")
        for key in ("diff_range", "diff_sha256", "red_sha256", "prompt_sha256",
                    "model", "effort", "cost_usd", "record", "sdk_status",
                    "generated_at"):
            self.assertIsNotNone(doc[key], key)
        self.assertTrue(verify_fix.before_fail_after_pass(doc["record"]))

    def test_diff_char_limit_is_a_refusal_not_a_truncation(self):
        """上限は「黙って切り詰める」ためではなく「止まる」ための線である。"""
        self.assertEqual(verify_fix.DIFF_CHAR_LIMIT, 30000)
        src = inspect.getsource(verify_fix.main)
        self.assertNotIn("[:DIFF_CHAR_LIMIT]", src)


if __name__ == "__main__":
    unittest.main()
