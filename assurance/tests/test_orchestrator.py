#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""オーケストレーションの正本(LANES/TRANSITIONS)の自己整合の凍結。"""
import os
import sys
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

    def test_challenge_sits_between_discover_and_formalize(self):
        ev = {t["event"]: t for t in orchestrator.TRANSITIONS}
        self.assertEqual(ev["SCENARIOS_READY"]["from"], "DISCOVER")
        self.assertEqual(ev["SCENARIOS_READY"]["to"], "CHALLENGE")
        self.assertEqual(ev["CHALLENGE_DONE"]["to"], "FORMALIZE")


if __name__ == "__main__":
    unittest.main()
