#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""想定の独立検証（verify_assumptions.py）の決定論試験（SDK 不要）。

凍結したいこと:
- 評価者への入力が構造化された登記だけであること（会話・弁明の口が無い）。
- 応答スキーマが asm_id・holds・reasons を必ず要求すること。
- 判定は observation_history へ追記のみで、observations を書き換えないこと。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, schemas, verify_assumptions  # noqa: E402


class PromptIndependenceTest(unittest.TestCase):
    def test_prompt_takes_only_structured_input(self):
        p = prompts.build_assumption_verification_prompt(
            {"asm_id": "ASM-001", "assumption": "x"})
        self.assertIn("ASM-001", p)
        self.assertIn("唯一の入力", p)

    def test_prose_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_assumption_verification_prompt("自由文の弁明")

    def test_missing_asm_id_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_assumption_verification_prompt({"assumption": "x"})


class SchemaTest(unittest.TestCase):
    def test_schema_requires_the_three_fields(self):
        s = schemas.ASSUMPTION_VERDICT_SCHEMA
        self.assertEqual(sorted(s["required"]), ["asm_id", "holds", "reasons"])
        self.assertEqual(s["properties"]["holds"]["enum"],
                         ["PASS", "FAIL", "UNKNOWN"])
        self.assertFalse(s["additionalProperties"])


class BuildInputTest(unittest.TestCase):
    def test_input_carries_the_ledger_fields_only(self):
        row = {"id": "ASM-009", "assumption": "a",
               "leading_indicators": [1], "observations": [2],
               "observation_history": [3], "verified_by": "秘密"}
        payload = verify_assumptions.build_input(row)
        self.assertEqual(sorted(payload),
                         ["asm_id", "assumption", "leading_indicators",
                          "observation_history", "observations"])
        self.assertNotIn("verified_by", payload)  # 前の検証者を評価者に見せない


if __name__ == "__main__":
    unittest.main()
