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

    def test_evaluated_unknown_is_not_re_listed(self):
        """評価の結果としての UNKNOWN は割当済みである。未評価の UNKNOWN と混ぜると
        同じ項目を永久に引き直す『消えない行動』になる（INC-006 と同型）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0, evaluated_unknown=4)
            actions = orchestrator.next_actions()
            self.assertEqual(
                [a for a in actions if a.startswith("MAP_COVERAGE")], [], actions)

    def test_unevaluated_and_evaluated_unknown_are_counted_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=3, evaluated_unknown=4)
            cov = orchestrator.coverage_status()["jerg"]
            self.assertEqual(cov["unmapped"], 3)
            self.assertEqual(cov["unknown"], 7)

    def test_unassessed_disposition_is_not_unmapped_work(self):
        """五値の UNASSESSED（前提欠如で評価できないという結論）は割当済みである。
        集計キー unmapped（まだ評価していない）と同じ語で数えてはならない
        —— 一語に二つの意味を持たせる取り違えは INC-006・INC-010 で二度起きた。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0, unassessed_disposition=2)
            cov = orchestrator.coverage_status()["jerg"]
            self.assertEqual(cov["unmapped"], 0)
            self.assertEqual(cov["status"], "MAPPED")
            self.assertEqual(
                [a for a in orchestrator.next_actions()
                 if a.startswith("MAP_COVERAGE")], [])

    def test_mapped_coverage_is_not_an_action(self):
        """全件が割り当て済みなら MAP_COVERAGE は挙げない（消えない行動を作らない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0)
            self.assertEqual(
                [a for a in orchestrator.next_actions()
                 if a.startswith("MAP_COVERAGE")], [])

    def test_formalize_is_named_when_survivors_exist(self):
        """創出と批判が済んだら、次は定式化である。DISCOVER を挙げ続けない。

        走らせ手を作ったのに正本がその成果を見ないと、同じ創出を毎回買い直す
        『消えない行動』になる（INC-012 と同型を、その修正の直後にまた作りかけた。
        事象 INC-015）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0, survivors=["SCN-1", "SCN-2"])
            actions = orchestrator.next_actions()
            self.assertTrue([a for a in actions if a.startswith("FORMALIZE")],
                            actions)
            self.assertEqual([a for a in actions if a.startswith("DISCOVER")], [])

    def test_discover_returns_when_no_survivor_remains(self):
        """生き残りがゼロなら、定式化する物が無いので創出へ戻る。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0, survivors=[])
            actions = orchestrator.next_actions()
            self.assertTrue([a for a in actions if a.startswith("DISCOVER")],
                            actions)

    def test_attack_evaluator_is_nameable(self):
        """評価器の成果物が、故障注入の証拠より新しければ ATTACK_EVALUATOR を挙げる。

        状態機械に在るのに next_actions が一度も名指しできない状態は、手で選ばない
        規律（ADR-115）の下では**決して起きない**。ATTACK_EVALUATOR は実際に5反復
        手つかずだった（事象 INC-012）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0, attack_evidence=None)
            actions = orchestrator.next_actions()
            self.assertTrue(
                [a for a in actions if a.startswith("ATTACK_EVALUATOR")], actions)

    def test_attack_evaluator_clears_when_evidence_is_newer(self):
        """証拠が成果物より新しければ挙げない（消えない行動を作らない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(tmp, coverage_unknown=0,
                              attack_evidence="2099-01-01")
            self.assertEqual(
                [a for a in orchestrator.next_actions()
                 if a.startswith("ATTACK_EVALUATOR")], [])

    def test_every_state_is_either_nameable_or_declared_unnameable(self):
        """正本の状態は、名指しできるか、名指しできないと明記されているかのどちらか。

        黙って名指しされない状態を増やさない —— それが ATTACK_EVALUATOR で起きた形。
        """
        covered = orchestrator.NAMEABLE_STATES | orchestrator.WITHIN_CYCLE_STATES
        self.assertEqual(set(orchestrator.STATES) - covered, set())

    def _stub_ledger(self, tmp, coverage_unknown, evaluated_unknown=0,
                     unassessed_disposition=0, attack_evidence="2099-01-01",
                     survivors=None):
        """実台帳に依存しない一時の帳簿を立てる（三冊とも抽出済み扱い）。"""
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(ledger, exist_ok=True)
        if attack_evidence:
            with open(os.path.join(ledger, "mutations-x.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"date": attack_evidence}, f)
        if survivors is not None:
            scn_dir = os.path.join(ledger, "scenarios")
            os.makedirs(scn_dir, exist_ok=True)
            with open(os.path.join(scn_dir, "2026-08-06.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"date": "2026-08-06", "survivors": survivors}, f)
        for attr, value in (("CATALOG_DIR", tmp),
                            ("LANE_DIR", tmp),
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
            entries += [{"key": "e%d" % i, "disposition": "UNKNOWN",
                         "assigned_at": "2026-08-05T00:00:00Z",
                         "reason": "索引から判定できない"}
                        for i in range(evaluated_unknown)]
            entries += [{"key": "u%d" % i, "disposition": "UNASSESSED",
                         "assigned_at": "2026-08-05T00:00:00Z",
                         "reason": "前提が欠けて評価できない"}
                        for i in range(unassessed_disposition)]
            entries.append({"key": "done", "disposition": "非該当で理由あり",
                            "assigned_at": "2026-08-05T00:00:00Z"})
            with open(os.path.join(tmp, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f)

    def test_challenge_sits_between_discover_and_formalize(self):
        ev = {t["event"]: t for t in orchestrator.TRANSITIONS}
        self.assertEqual(ev["SCENARIOS_READY"]["from"], "DISCOVER")
        self.assertEqual(ev["SCENARIOS_READY"]["to"], "CHALLENGE")
        self.assertEqual(ev["CHALLENGE_DONE"]["to"], "FORMALIZE")


class LedgerKindTest(unittest.TestCase):
    """台帳の成果物種別は、読む経路か読まない理由のどちらかを必ず持つ（ADR-124）。

    一段ごとの受入試験は、その一段しか守らない。INC-012・INC-015 で同型の未接続が
    三度通ったので、症状ではなく不変条件で蓋をする。
    """

    def test_every_kind_is_either_read_or_declared_unread(self):
        for entry in orchestrator.LEDGER_KINDS:
            read_by = entry.get("read_by") or ()
            why = entry.get("why_not_read")
            self.assertNotEqual(
                bool(read_by), bool(why),
                "%s は読取経路と読まない理由のちょうど一方を持つこと" % entry["kind"])

    def test_declared_readers_exist(self):
        """宣言が嘘をつけないようにする。名は実在する呼べる関数へ解決すること。"""
        for entry in orchestrator.LEDGER_KINDS:
            for fn_name in entry.get("read_by") or ():
                self.assertTrue(callable(getattr(orchestrator, fn_name, None)),
                                "%s の %r" % (entry["kind"], fn_name))

    def test_real_ledger_has_no_undeclared_artifact(self):
        """実台帳に、どの宣言にも当たらない成果物が無い（差集合が空）。"""
        self.assertEqual(orchestrator.undeclared_ledger_files(), [])

    def test_novel_artifact_kind_turns_the_canon_red(self):
        """未知の種別を台帳へ注入したら赤で止まる。

        これは今回の一段（FORMALIZE）の受入試験ではなく、次に走らせ手が増えた
        ときにも効く不変条件であることの確認である（INC-015 の事故分析が挙げた
        P1 仮説の反証試験）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "ledger")
            os.makedirs(os.path.join(ledger, "brand-new-lane"))
            with open(os.path.join(ledger, "brand-new-lane", "out.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"date": "2099-01-01"}, f)
            undeclared = orchestrator.undeclared_ledger_files(ledger)
            self.assertEqual(undeclared, ["brand-new-lane/out.json"])

    def test_hidden_files_are_not_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "ledger")
            os.makedirs(os.path.join(ledger, ".cache"))
            for path in (os.path.join(ledger, ".DS_Store"),
                         os.path.join(ledger, ".cache", "x.json")):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("{}")
            self.assertEqual(orchestrator.undeclared_ledger_files(ledger), [])


if __name__ == "__main__":
    unittest.main()
