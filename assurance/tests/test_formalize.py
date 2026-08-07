#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""FORMALIZE レーンの決定論試験（SDK 不要・通信不要。ADR-138）。

凍結したいこと:
- 計画の schema が反証条件（受入条件）と証拠仕様を必須に持つこと。
- 審査のプロンプトが構造化された入力しか受け取らないこと（会話の口が無い）。
- 沈黙を APPROVE と読まないこと（missing が残る）。
- 依頼していない scenario への計画を受け取らないこと。
- 出典の照合が ADR-121 の主張単位の規則であること。
- oracle_observable が空欄の形式的な充足と REJECT を通さないこと。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, schemas  # noqa: E402


def _plan(sid="SCN-1", verdict="APPROVE", refs=("鍵A",), **over):
    base = {
        "scenario_id": sid,
        "verdict": verdict,
        "reasons": ["r"],
        "red_reproduction_design": {
            "procedure": ["一時ディレクトリで再現手順を走らせる"],
            "injection_point": "settings の hook 登録",
            "isolation": "使い捨ての worktree",
        },
        "acceptance_criteria": {
            "before_fix_fails_when": "差集合が非空なのに合格が出る",
            "after_fix_passes_when": "差集合が非空なら非合格になる",
        },
        "evidence_spec": {
            "artifact": "ledger/red/<事象 id>.json",
            "must_record": ["差集合の中身", "実行時刻"],
        },
        "normative_refs": list(refs),
    }
    base.update(over)
    return base


class FormalizePlanSchemaTest(unittest.TestCase):
    def test_minimal_plan_validates(self):
        self.assertEqual(schemas.validate(
            schemas.FORMALIZE_PLAN_SCHEMA, {"plans": [_plan()]}), [])

    def test_missing_acceptance_criteria_is_a_violation(self):
        plan = _plan()
        del plan["acceptance_criteria"]
        self.assertTrue(schemas.validate(
            schemas.FORMALIZE_PLAN_SCHEMA, {"plans": [plan]}))

    def test_empty_reasons_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.FORMALIZE_PLAN_SCHEMA, {"plans": [_plan(reasons=[])]}))

    def test_unknown_key_is_a_violation(self):
        """additionalProperties false を全層で守る（黙って余計を通さない）。"""
        self.assertTrue(schemas.validate(
            schemas.FORMALIZE_PLAN_SCHEMA,
            {"plans": [_plan(extra="x")]}))
        plan = _plan()
        plan["evidence_spec"]["surprise"] = "x"
        self.assertTrue(schemas.validate(
            schemas.FORMALIZE_PLAN_SCHEMA, {"plans": [plan]}))


class FormalizeIndependenceTest(unittest.TestCase):
    def test_prompt_takes_only_structured_inputs(self):
        """会話履歴・弁明を渡す口を作らない（CHALLENGE と同じ独立性）。"""
        params = inspect.signature(prompts.build_formalize_prompt).parameters
        self.assertEqual(list(params), ["scenarios_json", "principle_index"])

    def test_unstructured_string_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_formalize_prompt("散文の弁明", [("鍵A", "t", "s")])

    def test_prompt_states_that_silence_is_not_approve(self):
        p = prompts.build_formalize_prompt(
            [{"scenario_id": "SCN-1"}], [("鍵A", "t", "s")])
        self.assertIn("沈黙", p)


class VerifyFormalizePlansTest(unittest.TestCase):
    def test_silence_is_reported_as_missing(self):
        """計画が返らなかった scenario を APPROVE と読まない。"""
        matched, unreq, missing = prompts.verify_formalize_plans(
            [_plan("SCN-1")], ["鍵A"], ["SCN-1", "SCN-2"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(missing, ["SCN-2"])
        self.assertEqual(unreq, [])

    def test_unrequested_plan_is_not_taken(self):
        matched, unreq, _missing = prompts.verify_formalize_plans(
            [_plan("SCN-9")], ["鍵A"], ["SCN-1"])
        self.assertEqual(matched, [])
        self.assertEqual(len(unreq), 1)

    def test_partly_resolving_refs_keep_the_plan_but_mark_it(self):
        """ADR-121 の主張単位の規則。解決しない鍵は外して刻む。"""
        matched, _unreq, missing = prompts.verify_formalize_plans(
            [_plan("SCN-1", refs=["鍵A", "捏造"])], ["鍵A"], ["SCN-1"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(missing, [])
        self.assertTrue(matched[0]["citation_defect"])
        self.assertEqual(matched[0]["normative_refs"], ["鍵A"])
        self.assertEqual(matched[0]["unresolved_refs"], ["捏造"])

    def test_zero_resolving_ref_is_rejected_and_stays_missing(self):
        """解決する出典がゼロの計画は台帳へ入れず、scenario は沈黙のまま残る。"""
        matched, _unreq, missing = prompts.verify_formalize_plans(
            [_plan("SCN-1", refs=["捏造"])], ["鍵A"], ["SCN-1"])
        self.assertEqual(matched, [])
        self.assertEqual(missing, ["SCN-1"])

    def test_clean_plan_carries_no_mark(self):
        matched, _unreq, _missing = prompts.verify_formalize_plans(
            [_plan("SCN-1")], ["鍵A"], ["SCN-1"])
        self.assertNotIn("citation_defect", matched[0])


class OracleObservableTest(unittest.TestCase):
    """PLAN_APPROVED の guard。空欄の形式的な充足を通さない。"""

    def test_complete_approve_plan_is_observable(self):
        self.assertTrue(prompts.oracle_observable(_plan()))

    def test_blank_fields_are_rejected(self):
        cases = []
        p = _plan()
        p["red_reproduction_design"]["injection_point"] = "  "
        cases.append(p)
        p = _plan()
        p["red_reproduction_design"]["isolation"] = ""
        cases.append(p)
        p = _plan()
        p["red_reproduction_design"]["procedure"] = ["手順", "  "]
        cases.append(p)
        p = _plan()
        p["red_reproduction_design"]["procedure"] = []
        cases.append(p)
        p = _plan()
        p["acceptance_criteria"]["before_fix_fails_when"] = ""
        cases.append(p)
        p = _plan()
        p["acceptance_criteria"]["after_fix_passes_when"] = "  "
        cases.append(p)
        p = _plan()
        p["evidence_spec"]["artifact"] = ""
        cases.append(p)
        p = _plan()
        p["evidence_spec"]["must_record"] = []
        cases.append(p)
        p = _plan()
        p["evidence_spec"]["must_record"] = ["記録", ""]
        cases.append(p)
        for i, plan in enumerate(cases):
            self.assertFalse(prompts.oracle_observable(plan), "case %d" % i)

    def test_reject_verdict_is_never_observable_approval(self):
        """欄が全部埋まっていても REJECT・UNKNOWN は承認とは読まない。"""
        self.assertFalse(prompts.oracle_observable(_plan(verdict="REJECT")))
        self.assertFalse(prompts.oracle_observable(_plan(verdict="UNKNOWN")))


if __name__ == "__main__":
    unittest.main()
