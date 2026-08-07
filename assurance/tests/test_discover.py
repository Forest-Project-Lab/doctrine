#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""DISCOVER / CHALLENGE レーンの決定論試験（SDK 不要・通信不要）。

凍結したいこと:
- 出発点の事実を台帳から決定論で組むこと（手で選ばない）。
- 創出された候補の出典を、主張単位の規則で照合すること（ADR-121 と同じ）。
- 批判の沈黙を ACCEPT と読まないこと。
- 依頼していない候補への判定を受け取らないこと。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import discover, prompts, schemas  # noqa: E402


def _scn(sid, refs):
    return {"scenario_id": sid, "normative_refs": refs,
            "system_boundary": "b", "loss": "l", "hazard": "h",
            "unsafe_control_action": "u", "event_sequence": ["e"],
            "fault": "f", "injection_point": "i",
            "expected_safe_behavior": "s", "oracle": "o",
            "falsification_signal": "x", "severity": "P1",
            "confidence": "medium"}


class VerifyScenariosTest(unittest.TestCase):
    def test_partly_resolving_refs_keep_the_scenario_but_mark_it(self):
        acc, rej = prompts.verify_scenarios(
            [_scn("SCN-1", ["鍵A", "捏造"])], ["鍵A"])
        self.assertEqual(len(acc), 1)
        self.assertEqual(rej, [])
        self.assertTrue(acc[0]["citation_defect"])
        self.assertEqual(acc[0]["normative_refs"], ["鍵A"])

    def test_no_resolving_ref_is_rejected(self):
        acc, rej = prompts.verify_scenarios([_scn("SCN-1", ["捏造"])], ["鍵A"])
        self.assertEqual(acc, [])
        self.assertEqual(len(rej), 1)

    def test_clean_scenario_carries_no_mark(self):
        acc, _rej = prompts.verify_scenarios([_scn("SCN-1", ["鍵A"])], ["鍵A"])
        self.assertNotIn("citation_defect", acc[0])


class VerifyVerdictsTest(unittest.TestCase):
    def test_silence_is_reported_as_missing(self):
        """判定が返らなかった候補を ACCEPT と読まない。"""
        matched, unreq, missing = prompts.verify_verdicts(
            [{"scenario_id": "SCN-1", "verdict": "ACCEPT", "reasons": ["r"]}],
            ["SCN-1", "SCN-2"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(missing, ["SCN-2"])
        self.assertEqual(unreq, [])

    def test_unrequested_verdict_is_not_taken(self):
        matched, unreq, _missing = prompts.verify_verdicts(
            [{"scenario_id": "SCN-9", "verdict": "ACCEPT", "reasons": ["r"]}],
            ["SCN-1"])
        self.assertEqual(matched, [])
        self.assertEqual(len(unreq), 1)


class SeedFactsTest(unittest.TestCase):
    def test_seeds_are_deterministic(self):
        self.assertEqual(discover.seed_facts(), discover.seed_facts())

    def test_seeds_are_not_empty_in_this_repository(self):
        """台帳に未修正の事象と網羅の穴が在る限り、出発点は空にならない。"""
        self.assertTrue(discover.seed_facts())

    def test_seed_facts_takes_no_hand_picked_list(self):
        """seed を外から差し込む口を作らない（選り好みを構造で防ぐ）。"""
        params = inspect.signature(discover.seed_facts).parameters
        self.assertEqual(list(params), ["limit_per_kind"])

    def test_cost_accepted_incident_is_not_a_seed(self):
        """受容済み（cost_accepted）の形を新しい仮説の種にしない（ADR-144）。

        所有者が費用として受け入れた形を創出の種へ流すと、裁定済みの選択肢を
        毎反復問い直す「消えない行動」になる。未修正でも受容済みなら種から外す。
        """
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "incidents.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"incidents": [
                    {"id": "INC-open", "fixed": False,
                     "summary": "未修正で未受容"},
                    {"id": "INC-acc", "fixed": False, "cost_accepted": True,
                     "cost_accepted_by": "所有者裁定 2026-08-07（会話）",
                     "summary": "未修正だが費用として受容済み"}]}, f,
                    ensure_ascii=False)
            original = discover.INCIDENTS_PATH
            discover.INCIDENTS_PATH = path
            try:
                facts = discover.seed_facts()
            finally:
                discover.INCIDENTS_PATH = original
        self.assertTrue(any("INC-open" in fact for fact in facts), facts)
        self.assertEqual([fact for fact in facts if "INC-acc" in fact], [])


class ChallengeIndependenceTest(unittest.TestCase):
    def test_challenge_prompt_takes_only_the_structured_output(self):
        params = inspect.signature(prompts.build_challenge_prompt).parameters
        self.assertEqual(list(params), ["discover_output_json"])

    def test_challenge_prompt_states_that_silence_is_not_accept(self):
        p = prompts.build_challenge_prompt([_scn("SCN-1", ["鍵A"])])
        self.assertIn("沈黙", p)


class ContainerSchemaTest(unittest.TestCase):
    def test_scenarios_container_validates(self):
        self.assertEqual(schemas.validate(
            schemas.SCENARIOS_SCHEMA, {"scenarios": [_scn("SCN-1", ["鍵A"])]}), [])

    def test_empty_scenarios_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.SCENARIOS_SCHEMA, {"scenarios": []}))

    def test_verdict_without_a_scenario_id_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.CHALLENGE_SCHEMA,
            {"verdicts": [{"verdict": "ACCEPT", "reasons": ["r"]}]}))


if __name__ == "__main__":
    unittest.main()
