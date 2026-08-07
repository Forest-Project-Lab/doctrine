#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""事故分析の新規仮説候補の取り込み口の凍結（ADR-140。INC-016 の残余）。

候補は仮説であり、判定済みの scenario ではない。取り込みは既存の
DISCOVER→CHALLENGE の独立構造を通し、第二の処遇の台帳は作らない ——
消化の記帳は scenarios 台帳の出自欄 candidates_considered が持つ。
"""
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator, prompts, triage_candidates  # noqa: E402


def _candidate(i, severity="P1"):
    return {"hypothesis": "仮説 %d" % i, "oracle": "観測 %d" % i,
            "falsification_signal": "反証 %d" % i, "severity": severity}


class CandidateFunnelStubMixin:
    """実台帳に依存しない一時の帳簿。三冊とも抽出済み・網羅は割当済みにする
    （候補の信号だけを測る。他の段の信号と混ぜない）。"""

    def _stub(self, tmp, candidates_by_incident, considered=None):
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(os.path.join(ledger, "cast"), exist_ok=True)
        catalogs = os.path.join(tmp, "catalogs")
        os.makedirs(catalogs, exist_ok=True)
        fresh = {"index_sha256": orchestrator.current_index_sha()}
        for attr, value in (("CATALOG_DIR", catalogs),
                            ("LANE_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "inc.json")),
                            ("ASSUMPTIONS_PATH", os.path.join(tmp, "asm.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)
        with open(os.path.join(tmp, "inc.json"), "w", encoding="utf-8") as f:
            json.dump({"incidents": []}, f)
        with open(os.path.join(ledger, "mutations-x.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"date": "2099-01-01"}, f)
        for incident_id, cands in candidates_by_incident.items():
            with open(os.path.join(ledger, "cast", "%s.json" % incident_id),
                      "w", encoding="utf-8") as f:
                json.dump({"analysis": {"incident_id": incident_id,
                                        "new_scenario_candidates": cands}}, f)
        if considered is not None:
            scn_dir = os.path.join(ledger, "scenarios")
            os.makedirs(scn_dir, exist_ok=True)
            with open(os.path.join(scn_dir, "2026-08-07.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"date": "2026-08-07", "kind": "candidate-triage",
                           "candidates_considered": considered,
                           "survivors": [], "dropped": []}, f)
        for book in ("jerg", "stpa", "cast"):
            with open(os.path.join(catalogs, "%s-principles.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"chunks": [], "principles": [],
                           "totals": {"cost_usd": 0.0, "principles": 0,
                                      "rejected": 0}}, f)
            with open(os.path.join(catalogs, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": [
                    {"key": "done", "disposition": "非該当で理由あり",
                     "assigned_at": "2026-08-05T00:00:00Z",
                     "assigned_by": dict(fresh)}]}, f)


class CandidateReaderTest(CandidateFunnelStubMixin, unittest.TestCase):
    def test_candidates_are_read_from_the_cast_ledger(self):
        """正本が候補の欄を読む（cast_recommendations と同じ鍵の付け方）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(0, "P0"), _candidate(1, "P2")]})
            rows = orchestrator.cast_scenario_candidates()
            self.assertEqual([(r["incident_id"], r["index"]) for r in rows],
                             [("INC-x", 0), ("INC-x", 1)])
            self.assertEqual(rows[0]["severity"], "P0")
            self.assertEqual(rows[0]["hypothesis"], "仮説 0")
            self.assertEqual(rows[1]["oracle"], "観測 1")
            self.assertEqual(rows[1]["falsification_signal"], "反証 1")

    def test_untriaged_count_appears_in_status_summary(self):
        """挙がらないときも必ず数えて出す（挙げないことと隠すことは違う）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(0, "P0"), _candidate(1, "P1"),
                                       _candidate(2, "P2")]})
            summary = orchestrator._candidate_summary()
            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["untriaged"], 3)
            self.assertEqual(summary["untriaged_by_severity"],
                             {"P0": 1, "P1": 1, "P2": 1})
            self.assertEqual(summary["raise_threshold"],
                             orchestrator.STALE_RAISE_THRESHOLD)

    def test_considered_candidates_are_not_recounted(self):
        """出自欄に載った候補は二度と数え直さない（消えない行動を作らない）。
        記帳は結果を選ばない —— 定式化済みも重複も定式化不能も消化である。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(0, "P0"), _candidate(1, "P1")]},
                       considered=[["INC-x", 0], ["INC-x", 1]])
            summary = orchestrator._candidate_summary()
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["triaged"], 2)
            self.assertEqual(summary["untriaged"], 0)
            self.assertEqual(
                orchestrator.triaged_candidate_keys(),
                {("INC-x", 0), ("INC-x", 1)})


class CandidateRaiseTest(CandidateFunnelStubMixin, unittest.TestCase):
    def test_below_threshold_is_counted_not_raised(self):
        """一束（ADR-134 の閾値）に満たない候補で評価を買いに行かない。
        件数は status に出続ける。"""
        n = orchestrator.STALE_RAISE_THRESHOLD - 1
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(i, "P1") for i in range(n)]})
            self.assertEqual(orchestrator._candidate_summary()["untriaged"], n)
            raised = [a for a in orchestrator.next_actions()
                      if "新規仮説" in a]
            self.assertEqual(raised, [])

    def test_at_threshold_discover_names_the_triage(self):
        """閾値に達したら DISCOVER の段で走らせ手を名指しする。"""
        n = orchestrator.STALE_RAISE_THRESHOLD
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(i, "P0") for i in range(10)]
                             + [_candidate(i + 10, "P1")
                                for i in range(n - 10)]})
            raised = [a for a in orchestrator.next_actions()
                      if "新規仮説" in a]
            self.assertEqual(len(raised), 1, orchestrator.next_actions())
            self.assertTrue(raised[0].startswith("DISCOVER:"), raised[0])
            self.assertIn("triage_candidates.py", raised[0])
            self.assertIn("%d 件" % n, raised[0])
            self.assertIn("P0 10", raised[0])
            self.assertIn("P1 %d" % (n - 10), raised[0])

    def test_p2_and_p3_do_not_count_toward_the_threshold(self):
        """閾値を測るのは P0・P1 だけ。低い重大度の山で口を鳴らさない。"""
        n = orchestrator.STALE_RAISE_THRESHOLD
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {"INC-x": [_candidate(i, "P1")
                                       for i in range(n - 1)]
                             + [_candidate(i + 100, "P2") for i in range(n)]})
            raised = [a for a in orchestrator.next_actions()
                      if "新規仮説" in a]
            self.assertEqual(raised, [])

    def test_considered_candidates_do_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = orchestrator.STALE_RAISE_THRESHOLD
            self._stub(tmp, {"INC-x": [_candidate(i, "P0") for i in range(n)]},
                       considered=[["INC-x", i] for i in range(n)])
            raised = [a for a in orchestrator.next_actions()
                      if "新規仮説" in a]
            self.assertEqual(raised, [])


class FormulationPromptTest(unittest.TestCase):
    def test_formulation_prompt_takes_only_structured_inputs(self):
        """引数は四つの構造化された入力だけ。会話・弁明を渡す口は無い。"""
        params = list(inspect.signature(
            prompts.build_candidate_formulation_prompt).parameters)
        self.assertEqual(params, ["candidates", "principle_index",
                                  "boundary", "existing_scenarios"])
        cand = {"incident_id": "INC-x", "index": 0, "hypothesis": "h",
                "oracle": "o", "falsification_signal": "f", "severity": "P1"}
        keys = [("k1", "題", "一文")]
        prompt = prompts.build_candidate_formulation_prompt(
            [cand], keys, "境界", ["SCN-OLD-1"])
        self.assertIn("INC-x#0", prompt)
        self.assertIn("SCN-OLD-1", prompt)
        self.assertIn("k1", prompt)
        with self.assertRaises(ValueError):
            prompts.build_candidate_formulation_prompt([], keys, "境界", [])
        with self.assertRaises(ValueError):
            prompts.build_candidate_formulation_prompt(
                ["自由文の仮説"], keys, "境界", [])
        with self.assertRaises(ValueError):
            prompts.build_candidate_formulation_prompt([cand], [], "境界", [])
        with self.assertRaises(ValueError):
            prompts.build_candidate_formulation_prompt([cand], keys, "", [])
        with self.assertRaises(ValueError):
            prompts.build_candidate_formulation_prompt(
                [cand], keys, "境界", "SCN-OLD-1")


class PartitionTest(unittest.TestCase):
    """一括の全候補が帳合いされる（considered = 定式化済み + dropped）。"""

    BATCH = [{"incident_id": "INC-x", "index": 0},
             {"incident_id": "INC-x", "index": 1},
             {"incident_id": "INC-y", "index": 0}]

    def _scn(self, sid, src, **over):
        base = {"scenario_id": sid, "source_candidate": src}
        base.update(over)
        return base

    def test_every_batched_candidate_is_accounted(self):
        to_challenge, duplicates, dropped, invented = \
            triage_candidates.partition_formulated(self.BATCH, [
                self._scn("SCN-A", "INC-x#0"),
                self._scn("SCN-B", "INC-x#1", duplicate_of="SCN-OLD-1"),
                self._scn("SCN-Z", "INC-nope#9"),   # 発明 → 捨てる
            ])
        formulated = {s["source_candidate"] for s in to_challenge}
        dropped_keys = {d["key"] for d in dropped}
        considered = {triage_candidates.candidate_key(c) for c in self.BATCH}
        # 帳合い: 一括の全候補 = 定式化済み + dropped（漏れも重なりも無い）。
        self.assertEqual(formulated | dropped_keys, considered)
        self.assertEqual(formulated & dropped_keys, set())
        self.assertEqual(invented, ["SCN-Z"])
        # 定式化されなかった INC-y#0 は理由つきで dropped。
        reasons = {d["key"]: d["reason"] for d in dropped}
        self.assertIn("定式化されなかった", reasons["INC-y#0"])
        self.assertIn("SCN-OLD-1", reasons["INC-x#1"])

    def test_dropped_duplicates_do_not_reach_challenge(self):
        to_challenge, duplicates, dropped, _ = \
            triage_candidates.partition_formulated(self.BATCH, [
                self._scn("SCN-A", "INC-x#0"),
                self._scn("SCN-B", "INC-x#1", duplicate_of="SCN-OLD-1"),
            ])
        self.assertEqual([s["scenario_id"] for s in to_challenge], ["SCN-A"])
        # 重複は記録には残る（消さない）が、批判へは渡らない。
        self.assertEqual([s["scenario_id"] for s in duplicates], ["SCN-B"])
        self.assertNotIn("SCN-B", [s["scenario_id"] for s in to_challenge])

    def test_scenario_without_a_source_key_is_discarded(self):
        """出自の鍵の無い scenario は受け取らない（発明の機械の床）。"""
        to_challenge, duplicates, dropped, invented = \
            triage_candidates.partition_formulated(
                self.BATCH[:1], [{"scenario_id": "SCN-N"}])
        self.assertEqual(to_challenge, [])
        self.assertEqual(invented, ["SCN-N"])
        self.assertEqual([d["key"] for d in dropped], ["INC-x#0"])


class TriageRecordShapeTest(CandidateFunnelStubMixin, unittest.TestCase):
    """取り込みの記録は既存の scenarios 記録の形に、出自欄を足しただけの物。

    既存の読む段（latest_scenarios・unformalized_survivors）が追加の欄に
    寛容であることを凍結する —— 寛容でなくなった瞬間、記帳の欄が正本を壊す。
    """

    def test_extra_fields_are_tolerated_by_existing_readers(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, {})
            scn_dir = os.path.join(tmp, "ledger", "scenarios")
            os.makedirs(scn_dir, exist_ok=True)
            doc = {"date": "2026-08-08", "kind": "candidate-triage",
                   "scenarios": [{"scenario_id": "SCN-C1"}],
                   "survivors": ["SCN-C1"],
                   "candidates_considered": [["INC-x", 0], ["INC-x", 1]],
                   "dropped": [{"key": "INC-x#1", "reason": "重複"}]}
            with open(os.path.join(scn_dir, "2026-08-08.json"),
                      "w", encoding="utf-8") as f:
                json.dump(doc, f)
            latest = orchestrator.latest_scenarios()
            self.assertEqual(latest["kind"], "candidate-triage")
            self.assertEqual(latest["survivors"], ["SCN-C1"])
            # 生き残りは既存の読む段が FORMALIZE へ渡す（第二の待ち行列は無い）。
            self.assertEqual(orchestrator.unformalized_survivors(), ["SCN-C1"])
            raised = [a for a in orchestrator.next_actions()
                      if a.startswith("FORMALIZE")]
            self.assertTrue(raised, orchestrator.next_actions())

    def test_merge_batch_accounts_every_candidate(self):
        """記帳は一括の全候補を覆う（considered = 定式化済み + dropped）。"""
        doc = {"scenarios": [], "duplicates": [], "survivors": [],
               "candidates_considered": [], "dropped": []}
        batch = [{"incident_id": "INC-x", "index": 0},
                 {"incident_id": "INC-x", "index": 1}]
        triage_candidates.merge_batch(
            doc, batch,
            to_challenge=[{"scenario_id": "SCN-A",
                           "source_candidate": "INC-x#0"}],
            duplicates=[], dropped=[{"key": "INC-x#1", "reason": "r"}],
            verdicts=[{"scenario_id": "SCN-A", "verdict": "ACCEPT",
                       "reasons": ["ok"]}],
            survivors=["SCN-A"], batch_meta={"batch": ["INC-x#0", "INC-x#1"]})
        self.assertEqual(doc["candidates_considered"],
                         [["INC-x", 0], ["INC-x", 1]])
        self.assertEqual(doc["survivors"], ["SCN-A"])
        self.assertEqual([d["key"] for d in doc["dropped"]], ["INC-x#1"])

    def test_selection_is_deterministic_and_severity_first(self):
        cands = [{"incident_id": "INC-b", "index": 0, "severity": "P1"},
                 {"incident_id": "INC-a", "index": 1, "severity": "P0"},
                 {"incident_id": "INC-a", "index": 0, "severity": "P1"},
                 {"incident_id": "INC-c", "index": 0, "severity": "P2"}]
        picked = triage_candidates.select_untriaged(
            cands, set(), ["P0", "P1"])
        self.assertEqual([triage_candidates.candidate_key(c) for c in picked],
                         ["INC-a#1", "INC-a#0", "INC-b#0"])


if __name__ == "__main__":
    unittest.main()
