#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""オーケストレーションの正本(LANES/TRANSITIONS)の自己整合の凍結。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator  # noqa: E402


class OrchestratorTest(unittest.TestCase):
    def test_validate_is_clean(self):
        self.assertEqual(orchestrator.validate(), [])

    def test_every_book_has_a_lane(self):
        lane_books = {l["book"] for l in orchestrator.LANES.values()}
        for book_id in ("jerg", "stpa", "cast"):
            self.assertIn(book_id, lane_books)

    def test_evaluation_lanes_never_use_weak_model(self):
        from harness import model_policy
        for name, lane in orchestrator.LANES.items():
            if lane["role"] == "evaluation":
                opts = model_policy.options_for("evaluation")
                self.assertTrue(model_policy.assert_evaluation_floor(
                    opts["model"], opts["effort"]), name)

    def test_incident_can_fire_from_any_state(self):
        incident = [t for t in orchestrator.TRANSITIONS
                    if t["event"] == "INCIDENT"]
        self.assertEqual(len(incident), 1)
        self.assertEqual(incident[0]["from"], "*")
        self.assertEqual(incident[0]["to"], "CAST_ANALYSIS")

    def test_red_impossible_does_not_reach_fix(self):
        """再現不能は実装へ進まず記録へ落ちる(campaign 原則)。"""
        t = [t for t in orchestrator.TRANSITIONS
             if t["event"] == "RED_IMPOSSIBLE"][0]
        self.assertEqual(t["to"], "RECORD")

    def test_next_actions_is_never_silently_empty(self):
        """空の next_actions は「やることが無い」と読める。台帳が UNKNOWN だらけでも
        止まって見える形を許さない（事象 INC-006）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0)
            self.assertTrue(orchestrator.next_actions())

    def test_unmapped_coverage_is_an_action(self):
        """骨組みが在るだけでは MAP_COVERAGE は済んでいない。UNKNOWN が残る限り
        次の行動として挙げる（骨組みの存在を済みと読んだのが INC-006）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=3)
            actions = orchestrator.next_actions()
            self.assertTrue([a for a in actions if a.startswith("MAP_COVERAGE")],
                            actions)

    def test_mapped_coverage_is_not_an_action(self):
        """全件が割り当て済みなら MAP_COVERAGE は挙げない（消えない行動を作らない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0)
            self.assertEqual(
                [a for a in orchestrator.next_actions()
                 if a.startswith("MAP_COVERAGE")], [])

    def _stub_ledger(self, tmp, coverage_unknown):
        """実台帳に依存しない一時の帳簿を立てる（三冊とも抽出済み扱い）。"""
        for attr, value in (("CATALOG_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "inc.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)
        with open(os.path.join(tmp, "inc.json"), "w", encoding="utf-8") as f:
            json.dump({"incidents": []}, f)
        for book in ("jerg", "stpa", "cast"):
            with open(os.path.join(tmp, "%s-principles.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"chunks": [], "principles": [],
                           "totals": {"cost_usd": 0.0, "principles": 0,
                                      "rejected": 0}}, f)
            entries = [{"key": "k%d" % i, "disposition": "UNKNOWN"}
                       for i in range(coverage_unknown)]
            entries.append({"key": "done", "disposition": "非該当で理由あり"})
            with open(os.path.join(tmp, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f)

    def test_challenge_sits_between_discover_and_formalize(self):
        ev = {t["event"]: t for t in orchestrator.TRANSITIONS}
        self.assertEqual(ev["SCENARIOS_READY"]["from"], "DISCOVER")
        self.assertEqual(ev["SCENARIOS_READY"]["to"], "CHALLENGE")
        self.assertEqual(ev["CHALLENGE_DONE"]["to"], "FORMALIZE")


if __name__ == "__main__":
    unittest.main()
