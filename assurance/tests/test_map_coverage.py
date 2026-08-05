#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""MAP_COVERAGE レーンの決定論試験（SDK 不要・通信不要）。

凍結したいこと:
- 索引が実在するものだけを指し、実在しないポインタを解決しないこと。
- 証拠ポインタの無い「実装・試験・証拠あり」が UNKNOWN へ落ちること（緑へ倒さない）。
- 依頼していない key の割当を台帳へ入れないこと。
- 評価へ渡す口に、実装者の会話・弁明を入れる余地が無いこと。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, schemas, system_index  # noqa: E402


def _assign(**over):
    base = {"key": "JERG:k1", "disposition": "実装・試験・証拠あり",
            "reason": "監査が検査を持つ", "evidence": ["adr_not_landed"],
            "recheck_trigger": "検査名の変更", "confidence": "high"}
    base.update(over)
    return base


class SystemIndexTest(unittest.TestCase):
    def setUp(self):
        self.idx = system_index.build()

    def test_index_is_not_empty(self):
        self.assertTrue(self.idx["documents"])
        self.assertTrue(self.idx["scripts"])
        self.assertTrue(self.idx["audit_checks"])

    def test_seven_skills_are_fixed(self):
        """技能は7個に固定する（DECIDED-001 事実8）。索引が増減を映す。"""
        self.assertEqual(len(self.idx["skills"]), 7, self.idx["skills"])

    def test_resolves_each_pointer_kind(self):
        kinds = {
            system_index.resolve_pointer(self.idx, self.idx["documents"][0]["id"]),
            system_index.resolve_pointer(self.idx, self.idx["audit_checks"][0]),
            system_index.resolve_pointer(self.idx, "plugin/scripts/docs-audit.py"),
            system_index.resolve_pointer(self.idx, "SessionEnd"),
        }
        self.assertEqual(
            kinds, {"document", "audit_check", "file", "hook_event"})

    def test_rejects_invented_pointers(self):
        for bogus in ("SPEC-9999", "plugin/scripts/does-not-exist.py",
                      "no_such_check", "", None,
                      "plugin/tests/test_termcheck.py::test_does_not_exist"):
            self.assertIsNone(system_index.resolve_pointer(self.idx, bogus), bogus)

    def test_test_pointer_needs_a_real_function(self):
        real = "plugin/tests/test_termcheck.py::test_hyphen_joined_identifier_is_one_token"
        self.assertEqual(system_index.resolve_pointer(self.idx, real), "test")

    def test_prompt_text_carries_the_index(self):
        text = system_index.as_prompt_text(self.idx)
        self.assertIn("SessionEnd", text)
        self.assertIn("plugin/scripts/docs-audit.py", text)
        self.assertIn(self.idx["documents"][0]["id"], text)


class VerifyAssignmentsTest(unittest.TestCase):
    def _resolve(self, pointer):
        return "audit_check" if pointer == "adr_not_landed" else None

    def test_resolvable_evidence_is_accepted(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign()], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down), len(rej)), (1, 0, 0))
        self.assertEqual(acc[0]["disposition"], "実装・試験・証拠あり")

    def test_green_without_evidence_is_downgraded(self):
        """証拠ポインタの無い『実装・試験・証拠あり』を書かない（ADR-115）。"""
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(evidence=[])], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down)), (0, 1))
        self.assertEqual(down[0]["disposition"], "UNKNOWN")
        self.assertEqual(down[0]["original_disposition"], "実装・試験・証拠あり")

    def test_unresolvable_evidence_is_downgraded_and_recorded(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(evidence=["SPEC-9999", "plugin/scripts/nope.py"])],
            self._resolve, ["JERG:k1"])
        self.assertEqual(len(down), 1)
        self.assertEqual(down[0]["disposition"], "UNKNOWN")
        self.assertEqual(len(down[0]["unresolved_evidence"]), 2)

    def test_other_dispositions_need_no_evidence(self):
        for disp in ("対応計画あり", "非該当で理由あり", "UNKNOWN", "UNASSESSED"):
            acc, down, _rej = prompts.verify_coverage_assignments(
                [_assign(disposition=disp, evidence=[])],
                self._resolve, ["JERG:k1"])
            self.assertEqual((len(acc), len(down)), (1, 0), disp)

    def test_unrequested_key_is_rejected(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(key="JERG:not-asked")], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down), len(rej)), (0, 0, 1))

    def test_unresolvable_pointers_are_stripped_from_evidence(self):
        acc, _down, _rej = prompts.verify_coverage_assignments(
            [_assign(evidence=["adr_not_landed", "SPEC-9999"])],
            self._resolve, ["JERG:k1"])
        self.assertEqual(acc[0]["evidence"], ["adr_not_landed"])
        self.assertEqual(acc[0]["unresolved_evidence"], ["SPEC-9999"])


class MapCoveragePromptTest(unittest.TestCase):
    def test_signature_has_no_context_parameter(self):
        params = inspect.signature(prompts.build_map_coverage_prompt).parameters
        self.assertEqual(list(params), ["principles", "system_index_text"])

    def test_rejects_empty_batch(self):
        with self.assertRaises(ValueError):
            prompts.build_map_coverage_prompt([], "索引")

    def test_rejects_empty_index(self):
        with self.assertRaises(ValueError):
            prompts.build_map_coverage_prompt([{"key": "k"}], "   ")

    def test_carries_keys_and_states_the_count(self):
        p = prompts.build_map_coverage_prompt(
            [{"key": "JERG:a", "title": "独立検証", "statement": "s",
              "category": "独立性", "applicability": "x", "suggested_oracle": "y"}],
            "索引の本文")
        self.assertIn("JERG:a", p)
        self.assertIn("索引の本文", p)
        self.assertIn("1 件", p)


class CoverageSchemaTest(unittest.TestCase):
    def test_minimal_assignment_validates(self):
        self.assertEqual(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            {"assignments": [_assign()]}), [])

    def test_unknown_disposition_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            {"assignments": [_assign(disposition="たぶん大丈夫")]}))

    def test_empty_assignments_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA, {"assignments": []}))


if __name__ == "__main__":
    unittest.main()
