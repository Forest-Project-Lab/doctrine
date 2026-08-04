#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""schemas.validate が「壊れた応答を本当に拒否する」ことの決定論試験。

検証器が緑へ倒れると、以後の全証拠が偽りになる。だから検証器自身を
先に疑う（campaign: 評価機構も検証対象）。SDK 不要・通信不要・時計不要。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import schemas  # noqa: E402


class SmokeSchemaTest(unittest.TestCase):
    def test_valid_echo_passes(self):
        s = schemas.smoke_schema("abc123")
        obj = {"lane_echo": "abc123", "self_check": "ok"}
        self.assertEqual(schemas.validate(s, obj), [])

    def test_wrong_nonce_fails(self):
        s = schemas.smoke_schema("abc123")
        obj = {"lane_echo": "zzz999", "self_check": "ok"}
        self.assertNotEqual(schemas.validate(s, obj), [])

    def test_missing_key_fails(self):
        s = schemas.smoke_schema("abc123")
        self.assertNotEqual(schemas.validate(s, {"lane_echo": "abc123"}), [])

    def test_extra_key_fails(self):
        s = schemas.smoke_schema("abc123")
        obj = {"lane_echo": "abc123", "self_check": "ok", "extra": 1}
        self.assertNotEqual(schemas.validate(s, obj), [])

    def test_non_object_fails(self):
        s = schemas.smoke_schema("abc123")
        self.assertNotEqual(schemas.validate(s, "abc123"), [])


class VerdictSchemaTest(unittest.TestCase):
    def test_valid_verdict(self):
        obj = {"verdict": "REJECT", "reasons": ["oracle が非観測"]}
        self.assertEqual(schemas.validate(schemas.VERDICT_SCHEMA, obj), [])

    def test_unknown_verdict_value_fails(self):
        obj = {"verdict": "MAYBE", "reasons": ["x"]}
        self.assertNotEqual(schemas.validate(schemas.VERDICT_SCHEMA, obj), [])

    def test_empty_reasons_fails(self):
        obj = {"verdict": "ACCEPT", "reasons": []}
        self.assertNotEqual(schemas.validate(schemas.VERDICT_SCHEMA, obj), [])


class ScenarioSchemaTest(unittest.TestCase):
    def _valid(self):
        return {
            "scenario_id": "SCN-0001",
            "normative_refs": ["WATCH-001"],
            "system_boundary": "docs-linter の用語検査",
            "loss": "書き手が偽の違反対応で正しい記述を壊す",
            "hazard": "誤検知の助言が正しい文書に出る",
            "unsafe_control_action": "検査器が部分文字列で禁止語を判定する",
            "event_sequence": ["体系のビューに VERIFY と書く", "IF が検知される"],
            "fault": "ASCII 語境界の欠如",
            "injection_point": "PostToolUse の docs-linter",
            "expected_safe_behavior": "長い語の内部は禁止語と照合しない",
            "oracle": "VERIFY を含む文書で BANNED_SYNONYM(IF) が 0 件",
            "falsification_signal": "IF の所見が出続ける",
            "severity": "P2",
            "confidence": "high",
        }

    def test_valid_scenario(self):
        self.assertEqual(
            schemas.validate(schemas.SCENARIO_SCHEMA, self._valid()), [])

    def test_missing_oracle_fails(self):
        obj = self._valid()
        del obj["oracle"]
        self.assertNotEqual(
            schemas.validate(schemas.SCENARIO_SCHEMA, obj), [])

    def test_bad_severity_fails(self):
        obj = self._valid()
        obj["severity"] = "P9"
        self.assertNotEqual(
            schemas.validate(schemas.SCENARIO_SCHEMA, obj), [])


class ValidatorSelfTest(unittest.TestCase):
    def test_unsupported_keyword_raises(self):
        """未対応キーワードの沈黙は偽りの緑になる。例外で止まること。"""
        with self.assertRaises(ValueError):
            schemas.validate({"type": "string", "pattern": "x"}, "x")

    def test_bool_is_not_integer(self):
        self.assertNotEqual(
            schemas.validate({"type": "integer"}, True), [])

    def test_sha256_stable_for_dict_key_order(self):
        a = schemas.sha256_of({"a": 1, "b": 2})
        b = schemas.sha256_of({"b": 2, "a": 1})
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
