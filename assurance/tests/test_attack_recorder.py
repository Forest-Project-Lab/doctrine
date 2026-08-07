#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""攻撃の記録が自分の欄を常に持つこと（ADR-142）の決定論試験。

実測: 2026-08-06 の記録は findings と residual_risks を持ち、2026-08-07 の
記録はどちらも持たなかった。discover.seed_facts は mutations-*.json の
residual_risks を種として読むので、**最新の攻撃の残余リスクが黙って消えた**。
空欄は「無かった」と読まれる —— 空配列が正直な記録である。

凍結したいこと:
- 記録が常に generated_at・findings・residual_risks を持つこと。
- 全注入 PASS でも findings が空**配列**として書かれること（欄ごと消さない）。
- PASS でない注入が機械的に finding になること（書き忘れの余地が無い）。
- 残余リスクの土台（RESIDUAL_RISKS）がどの記録からも落ちないこと。
- SDK・分類の失敗が在った注入に故障族ラベルが付くこと（INC-003 推奨#1）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import attack_evaluator  # noqa: E402


def _pass_run(rid="A3-verifier-direct", **over):
    base = {"id": rid, "fault": "f", "expected": "e",
            "observed": "UNKNOWN", "execution_kind": "deterministic",
            "status": "PASS", "verdict": "安全側成立"}
    base.update(over)
    return base


def _sdk_fail_run(rid="A1-evidence-deprivation", **over):
    base = {"id": rid, "fault": "f", "target": "JERG:x",
            "expected": "緑を維持しない", "sdk_status": "UNKNOWN",
            "status": "UNKNOWN",
            "note": ["TimeoutError: 900 秒で打ち切った"]}
    base.update(over)
    return base


def _build(runs):
    return attack_evaluator.build_document(
        runs, "2026-08-07", git_sha="deadbeef", git_dirty=False,
        generated_at="2026-08-07T12:00:00Z")


class RecordAlwaysCarriesItsFieldsTest(unittest.TestCase):
    def test_record_always_has_generated_at_findings_and_residual_risks(self):
        doc = _build([_pass_run()])
        for key in ("generated_at", "findings", "residual_risks"):
            self.assertIn(key, doc, key)
        self.assertEqual(doc["generated_at"], "2026-08-07T12:00:00Z")

    def test_generated_at_defaults_to_the_start_of_the_day(self):
        """時点が渡されなければ、その日の始まりとして刻む（INC-023 の安全側）。"""
        doc = attack_evaluator.build_document(
            [_pass_run()], "2026-08-07", git_sha=None, git_dirty=False)
        self.assertEqual(doc["generated_at"], "2026-08-07T00:00:00Z")

    def test_all_pass_still_writes_an_empty_findings_list(self):
        """全注入 PASS のときも findings は空**配列**。欄ごと消すと
        「無かった」と「書かなかった」が読み分けられない。"""
        doc = _build([_pass_run(), _pass_run("A1"), _pass_run("A2")])
        self.assertEqual(doc["findings"], [])

    def test_a_failed_injection_becomes_a_finding(self):
        run = _pass_run("A1-evidence-deprivation",
                        status="FAIL",
                        verdict="安全側が破れた（証拠が無いのに緑のまま）")
        doc = _build([_pass_run(), run])
        self.assertEqual(len(doc["findings"]), 1)
        finding = doc["findings"][0]
        self.assertEqual(finding["id"], "A1-evidence-deprivation")
        self.assertEqual(finding["severity"], "high")
        self.assertIn("安全側が破れた", finding["summary"])

    def test_unmeasured_injection_is_a_finding_too_but_not_high(self):
        """UNKNOWN / UNASSESSED は「破れていない」ではない。落とさず medium。"""
        doc = _build([_sdk_fail_run()])
        self.assertEqual(len(doc["findings"]), 1)
        self.assertEqual(doc["findings"][0]["severity"], "medium")


class ResidualRisksTest(unittest.TestCase):
    def test_baseline_residual_risks_are_never_dropped(self):
        """土台の残余リスクはどの記録からも落ちない（消すには決定が要る）。"""
        for runs in ([_pass_run()], [_sdk_fail_run()], []):
            doc = _build(runs)
            for risk in attack_evaluator.RESIDUAL_RISKS:
                self.assertIn(risk, doc["residual_risks"], risk[:40])

    def test_baseline_has_the_four_standing_risks(self):
        """2026-08-06 の記録に在った四つの残余リスクが土台に転記されている。"""
        self.assertEqual(len(attack_evaluator.RESIDUAL_RISKS), 4)
        joined = "".join(attack_evaluator.RESIDUAL_RISKS)
        self.assertIn("OBS-RESOLVER-SPLIT-AUTHORITY", joined)
        self.assertIn("共通原因故障", joined)

    def test_unmeasured_injection_adds_a_residual_risk(self):
        doc = _build([_sdk_fail_run()])
        extra = [r for r in doc["residual_risks"]
                 if r not in attack_evaluator.RESIDUAL_RISKS]
        self.assertEqual(len(extra), 1)
        self.assertIn("A1-evidence-deprivation", extra[0])
        self.assertIn("測れていない", extra[0])

    def test_all_pass_adds_no_extra_risk(self):
        doc = _build([_pass_run()])
        self.assertEqual(list(doc["residual_risks"]),
                         list(attack_evaluator.RESIDUAL_RISKS))


class FaultFamilyTest(unittest.TestCase):
    """故障族の軸（INC-003 推奨#1）。状態は「どれだけ観測できたか」を言い、
    族は「何が壊れたか」を言う —— 別の軸として記録に載る。"""

    def test_fault_family_present_when_a_run_carries_an_error_classification(self):
        doc = _build([_sdk_fail_run()])
        self.assertEqual(doc["injections"][0]["fault_family"], "timeout")
        self.assertEqual(doc["findings"][0]["fault_family"], "timeout")

    def test_auth_markers_classify_as_auth_refusal(self):
        run = _sdk_fail_run(sdk_status="UNASSESSED", status="UNASSESSED",
                            note=["ProcessError: authentication failed"])
        self.assertEqual(attack_evaluator.fault_family(run), "auth-refusal")

    def test_sdk_absence_classifies_as_sdk_missing(self):
        run = _sdk_fail_run(sdk_status="UNASSESSED", status="UNASSESSED",
                            note=["sdk-import: No module named claude_agent_sdk"])
        self.assertEqual(attack_evaluator.fault_family(run), "sdk-missing")

    def test_unrecognized_error_is_unclassified_not_silent(self):
        """分類不能は "unclassified" —— 無ラベルと混ぜない（沈黙させない）。"""
        run = _sdk_fail_run(note=["まったく新しい壊れ方"])
        self.assertEqual(attack_evaluator.fault_family(run), "unclassified")

    def test_pass_and_deterministic_runs_carry_no_family(self):
        self.assertIsNone(attack_evaluator.fault_family(_pass_run()))
        self.assertIsNone(attack_evaluator.fault_family(
            _pass_run("A1", sdk_status="PASS")))
        doc = _build([_pass_run()])
        self.assertNotIn("fault_family", doc["injections"][0])

    def test_build_document_does_not_mutate_its_input(self):
        """純関数。呼び手の runs を書き換えない。"""
        run = _sdk_fail_run()
        _build([run])
        self.assertNotIn("fault_family", run)


if __name__ == "__main__":
    unittest.main()
