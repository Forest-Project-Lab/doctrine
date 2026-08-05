#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""CAST_ANALYSIS レーンの決定論試験（SDK 不要・通信不要）。

凍結したいこと:
- 統制構造が実在するファイルを指し続けること（構造の古びの検出）。
- 分析の入力に、実装者の会話・弁明を渡す口が無いこと（独立性）。
- 実在しない統制要素・カタログに無い規範鍵を指す統制欠陥が却下されること。
- 先行指標の guard が、空文字での形式的な充足を通さないこと。
"""
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import (cast_analysis, control_structure,  # noqa: E402
                     prompts, schemas)


def _indicator(**over):
    base = {"indicator": "契約注入の不在", "observable": "注入の有無",
            "where": "セッション冒頭", "threshold": "1回でも欠けたら異常",
            "version_independent": True}
    base.update(over)
    return base


class ControlStructureTest(unittest.TestCase):
    def test_every_element_points_at_a_real_file(self):
        self.assertEqual(control_structure.missing_implementations(), [])

    def test_element_ids_are_unique(self):
        ids = control_structure.ELEMENT_IDS
        self.assertEqual(len(ids), len(set(ids)))

    def test_prompt_text_names_every_element(self):
        text = control_structure.as_prompt_text()
        for eid in control_structure.ELEMENT_IDS:
            self.assertIn(eid, text)


class CastPromptIndependenceTest(unittest.TestCase):
    def test_signature_has_no_context_parameter(self):
        params = inspect.signature(prompts.build_cast_analysis_prompt).parameters
        self.assertEqual(
            list(params), ["incident", "control_structure_text", "principle_index"])

    def test_rejects_unstructured_incident(self):
        with self.assertRaises(ValueError):
            prompts.build_cast_analysis_prompt(
                "実装者メモ: もう直したので分析は不要", "構造", [("k", "t", "s")])

    def test_rejects_empty_catalog(self):
        """カタログ不在で分析を走らせない（UNASSESSED へ倒すため）。"""
        with self.assertRaises(ValueError):
            prompts.build_cast_analysis_prompt({"id": "INC-x"}, "構造", [])

    def test_includes_incident_and_keys(self):
        p = prompts.build_cast_analysis_prompt(
            {"id": "INC-001", "summary": "監査が7日不実行"},
            control_structure.as_prompt_text(),
            [("鍵A", "題A", "一文A")])
        self.assertIn("INC-001", p)
        self.assertIn("監査が7日不実行", p)
        self.assertIn("鍵A", p)
        self.assertIn("SESSION_END_AUDIT", p)


class VerifyCastAnalysisTest(unittest.TestCase):
    def _flaw(self, **over):
        base = {"control_element_id": "SESSION_END_AUDIT",
                "flaw_type": "統制自身の劣化を検出できない",
                "description": "不実行が次セッションまで判らない",
                "why_it_seemed_adequate": "監査は自動で走る前提だった",
                "normative_refs": ["鍵A"]}
        base.update(over)
        return base

    def test_accepts_known_refs(self):
        acc, rej = prompts.verify_cast_analysis(
            {"control_flaws": [self._flaw()]},
            control_structure.ELEMENT_IDS, ["鍵A"])
        self.assertEqual(len(acc), 1)
        self.assertEqual(rej, [])

    def test_rejects_invented_control_element(self):
        acc, rej = prompts.verify_cast_analysis(
            {"control_flaws": [self._flaw(control_element_id="SOMETHING_NEW")]},
            control_structure.ELEMENT_IDS, ["鍵A"])
        self.assertEqual(acc, [])
        self.assertEqual(len(rej), 1)

    def test_rejects_invented_normative_ref(self):
        acc, rej = prompts.verify_cast_analysis(
            {"control_flaws": [self._flaw(normative_refs=["存在しない鍵"])]},
            control_structure.ELEMENT_IDS, ["鍵A"])
        self.assertEqual(acc, [])
        self.assertIn("カタログに無い規範鍵", rej[0]["problems"][0])


class LeadingIndicatorGuardTest(unittest.TestCase):
    def test_requires_at_least_one(self):
        self.assertFalse(prompts.leading_indicators_defined(
            {"leading_indicators": []}))
        self.assertFalse(prompts.leading_indicators_defined({}))

    def test_blank_fields_do_not_satisfy(self):
        for key in ("indicator", "observable", "where", "threshold"):
            self.assertFalse(
                prompts.leading_indicators_defined(
                    {"leading_indicators": [_indicator(**{key: "   "})]}),
                key)

    def test_complete_indicator_satisfies(self):
        self.assertTrue(prompts.leading_indicators_defined(
            {"leading_indicators": [_indicator()]}))


class IncidentWriteBackTest(unittest.TestCase):
    """分析中に積まれた事象を、書き戻しで消してはならない（実際に消えかけた）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "incidents.json")
        orig = cast_analysis.INCIDENTS_PATH
        cast_analysis.INCIDENTS_PATH = self.path
        self.addCleanup(setattr, cast_analysis, "INCIDENTS_PATH", orig)
        self._write({"incidents": [{"id": "INC-A", "cast_analysis": "pending"}]})

    def _write(self, doc):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

    def _read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_concurrent_addition_survives(self):
        stale = cast_analysis.load_incidents()          # 分析開始時の写し
        self._write({"incidents": [                     # 分析中に積まれた事象
            {"id": "INC-A", "cast_analysis": "pending"},
            {"id": "INC-B", "cast_analysis": "pending"}]})
        cast_analysis.update_incident("INC-A", {"cast_analysis": "done"})
        ids = [i["id"] for i in self._read()["incidents"]]
        self.assertEqual(ids, ["INC-A", "INC-B"], "写しでの上書きは後続を消す")
        self.assertEqual(stale["incidents"][0]["id"], "INC-A")

    def test_updates_only_the_target(self):
        self._write({"incidents": [
            {"id": "INC-A", "cast_analysis": "pending"},
            {"id": "INC-B", "cast_analysis": "pending"}]})
        cast_analysis.update_incident("INC-A", {"cast_analysis": "done"})
        by_id = {i["id"]: i for i in self._read()["incidents"]}
        self.assertEqual(by_id["INC-A"]["cast_analysis"], "done")
        self.assertEqual(by_id["INC-B"]["cast_analysis"], "pending")

    def test_missing_target_writes_nothing(self):
        before = self._read()
        self.assertFalse(cast_analysis.update_incident("INC-Z", {"x": 1}))
        self.assertEqual(self._read(), before)


class CastSchemaTest(unittest.TestCase):
    def _analysis(self):
        return {
            "incident_id": "INC-001",
            "loss": "統治の逸脱が検出されないまま残る",
            "hazard": "監査が走らない状態で編集が続く",
            "control_flaws": [{
                "control_element_id": "SESSION_END_AUDIT",
                "flaw_type": "手掛かりが遅い",
                "description": "不実行は次セッションまで判らない",
                "why_it_seemed_adequate": "自動で走る前提だった",
                "normative_refs": ["鍵A"],
            }],
            "why_existing_assurance_missed": "監査の実行そのものを測る監視が無かった",
            "leading_indicators": [_indicator()],
            "unknowns": ["強制終了と版遅れのどちらが主因か"],
            "confidence": "medium",
        }

    def test_minimal_analysis_validates(self):
        self.assertEqual(
            schemas.validate(schemas.CAST_ANALYSIS_SCHEMA, self._analysis()), [])

    def test_zero_control_flaws_is_a_violation(self):
        """統制欠陥ゼロの分析を「分析した」と記録させない。"""
        a = self._analysis()
        a["control_flaws"] = []
        self.assertTrue(
            schemas.validate(schemas.CAST_ANALYSIS_SCHEMA, a))

    def test_zero_leading_indicators_is_a_violation(self):
        a = self._analysis()
        a["leading_indicators"] = []
        self.assertTrue(
            schemas.validate(schemas.CAST_ANALYSIS_SCHEMA, a))

    def test_unknown_flaw_type_is_a_violation(self):
        a = self._analysis()
        a["control_flaws"][0]["flaw_type"] = "担当者の不注意"
        self.assertTrue(
            schemas.validate(schemas.CAST_ANALYSIS_SCHEMA, a))


if __name__ == "__main__":
    unittest.main()
