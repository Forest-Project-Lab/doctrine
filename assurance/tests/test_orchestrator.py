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
                     survivors=None, plans=None):
        """実台帳に依存しない一時の帳簿を立てる（三冊とも抽出済み扱い）。

        割当済みの項には現行の索引の指紋を持たせる。持たせないと ADR-130 の
        古びの判定が別の理由で MAP_COVERAGE を挙げ、ここで守りたい不変条件
        （評価済み UNKNOWN を未評価と混ぜない）と信号が混ざるためである。
        """
        fresh = {"index_sha256": orchestrator.current_index_sha()}
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
        if plans is not None:
            fm_dir = os.path.join(ledger, "formalize")
            os.makedirs(fm_dir, exist_ok=True)
            with open(os.path.join(fm_dir, "2026-08-07.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"date": "2026-08-07", "kind": "formalize-plans",
                           "generated_at": "2026-08-07T00:00:00Z",
                           "plans": plans}, f)
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
                         "assigned_by": dict(fresh),
                         "reason": "索引から判定できない"}
                        for i in range(evaluated_unknown)]
            entries += [{"key": "u%d" % i, "disposition": "UNASSESSED",
                         "assigned_at": "2026-08-05T00:00:00Z",
                         "assigned_by": dict(fresh),
                         "reason": "前提が欠けて評価できない"}
                        for i in range(unassessed_disposition)]
            entries.append({"key": "done", "disposition": "非該当で理由あり",
                            "assigned_at": "2026-08-05T00:00:00Z",
                            "assigned_by": dict(fresh)})
            with open(os.path.join(tmp, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": entries}, f)

    def test_challenge_sits_between_discover_and_formalize(self):
        ev = {t["event"]: t for t in orchestrator.TRANSITIONS}
        self.assertEqual(ev["SCENARIOS_READY"]["from"], "DISCOVER")
        self.assertEqual(ev["SCENARIOS_READY"]["to"], "CHALLENGE")
        self.assertEqual(ev["CHALLENGE_DONE"]["to"], "FORMALIZE")

    def test_formalize_clears_once_plans_exist(self):
        """計画審査の判定が揃ったら FORMALIZE は挙げない（ADR-138）。

        REJECT も消化と数える —— 判定は評価の結論であり、割当済みである
        （評価済み UNKNOWN を引き直さないのと同じ規則。INC-006）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(
                tmp, coverage_unknown=0, survivors=["SCN-1", "SCN-2"],
                plans=[{"scenario_id": "SCN-1", "verdict": "APPROVE"},
                       {"scenario_id": "SCN-2", "verdict": "REJECT"}])
            actions = orchestrator.next_actions()
            self.assertEqual(
                [a for a in actions if a.startswith("FORMALIZE")], [], actions)
            self.assertTrue([a for a in actions if a.startswith("DISCOVER")],
                            actions)

    def test_unplanned_survivor_still_raises_formalize(self):
        """計画が返らなかった生き残り（沈黙）は挙がり続ける。

        沈黙を APPROVE と読まない（ADR-138。verify_verdicts の missing と
        同じ規則）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_ledger(
                tmp, coverage_unknown=0, survivors=["SCN-1", "SCN-2"],
                plans=[{"scenario_id": "SCN-1", "verdict": "APPROVE"}])
            self.assertEqual(orchestrator.unformalized_survivors(), ["SCN-2"])
            raised = [a for a in orchestrator.next_actions()
                      if a.startswith("FORMALIZE")]
            self.assertTrue(raised)
            self.assertIn("1 件", raised[0])
            self.assertIn("SCN-2", raised[0])

    def test_formalize_ledger_kind_is_declared(self):
        """走らせ手と読む段と種別の三点は同じ変更で入る（ADR-128 の不変条件）。"""
        kinds = {e["kind"] for e in orchestrator.LEDGER_KINDS}
        self.assertIn("formalize/<日付>.json", kinds)
        entry = orchestrator.ledger_kind_of("formalize/2026-08-07.json")
        self.assertIsNotNone(entry)
        self.assertIn("latest_formalize", entry["read_by"])


class RecommendationBacklogTest(unittest.TestCase):
    """事故分析の推奨は、terminal な処遇に至るまで次の行動に挙がる（ADR-125）。

    ADR-124 の不変条件は種別の粒度までしか見ない。cast/*.json は「読まれている」と
    宣言できたが、読み手は generated_at だけで、推奨は正本へ一度も届いていなかった
    （INC-016。同型の四度目）。
    """

    def _stub(self, tmp, recommendations, dispositions=None):
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(os.path.join(ledger, "cast"), exist_ok=True)
        with open(os.path.join(ledger, "cast", "INC-x.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"analysis": {"incident_id": "INC-x",
                                    "recommendations": recommendations}}, f)
        if dispositions is not None:
            with open(os.path.join(ledger, "recommendation-status.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"dispositions": dispositions}, f)
        orig = orchestrator.LANE_DIR
        orchestrator.LANE_DIR = tmp
        self.addCleanup(setattr, orchestrator, "LANE_DIR", orig)

    def test_recommendation_without_disposition_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [{"action": "a", "kind": "機構の変更",
                              "owner_decision_required": False}])
            self.assertEqual(
                [r["index"] for r in orchestrator.recommendation_backlog()["pending"]],
                [0])

    def test_owner_decision_is_not_lane_work(self):
        """成立した所有者判断は、レーンの未着手として並べない。

        並べると、勝手に進めてよい物と判断を仰ぐ物が同じ列に混ざる（§7 の境界）。

        ADR-127 で境界の引き方が変わった。かつては評価者の申告
        （owner_decision_required）だけで棚へ落としていたが、その申告は権限の
        判定ではなく評価者の視野の申告である（分析の入力に統治木が入っていない）。
        いま棚へ入るのは、処遇の行が明示的に owner と書き、六類型のどれかを
        名指したときだけ。守るべき不変条件は「**成立した**所有者判断が未着手に
        混ざらないこと」であって、申告で棚へ落とすことではない。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [{"action": "a", "kind": "所有者判断",
                              "owner_decision_required": True}])
            # 申告だけ: 棚には入らず、未着手に並ぶ（材料が届いていないだけ）。
            backlog = orchestrator.recommendation_backlog()
            self.assertEqual(backlog["owner"], [])
            self.assertEqual(len(backlog["pending"]), 1)

            # 明示の処遇 + 類型: 棚へ入り、未着手から消える。
            original = orchestrator.load_recommendation_status
            stub_row = {"incident_id": "INC-x", "index": 0, "state": "owner",
                        "owner_decision_kind": "配布境界や保証範囲の変更"}
            orchestrator.load_recommendation_status = \
                lambda: {("INC-x", 0): stub_row}
            try:
                backlog = orchestrator.recommendation_backlog()
            finally:
                orchestrator.load_recommendation_status = original
            self.assertEqual(backlog["pending"], [])
            self.assertEqual(len(backlog["owner"]), 1)
            self.assertEqual(backlog["owner"][0]["owner_decision_kind"],
                             "配布境界や保証範囲の変更")

    def test_apply_findings_is_named_while_pending_remains(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, [{"action": "a", "kind": "機構の変更",
                              "owner_decision_required": False}])
            actions = [a for a in orchestrator.next_actions()
                       if a.startswith("APPLY_FINDINGS")]
            self.assertTrue(actions, orchestrator.next_actions())
            self.assertIn("未調査 1 件", actions[0])

    def test_apply_findings_clears_when_all_are_terminal(self):
        """処遇が済んだら消える。消えない行動を作らない（INC-006・INC-012）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "landed",
                         "evidence_ref": "assurance/harness/orchestrator.py"}])
            self.assertEqual([a for a in orchestrator.next_actions()
                              if a.startswith("APPLY_FINDINGS")], [])

    def test_rejection_without_a_reason_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "rejected"}])
            self.assertTrue([p for p in orchestrator.validate()
                             if "却下に理由が無い" in p], orchestrator.validate())

    def test_landed_without_evidence_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "landed"}])
            self.assertTrue([p for p in orchestrator.validate()
                             if "証拠のポインタが無い" in p], orchestrator.validate())

    def test_disposition_for_a_missing_recommendation_is_red(self):
        """指す先の無い処遇は、片づいた件数を水増しする。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 9, "state": "rejected",
                         "note": "理由"}])
            self.assertTrue([p for p in orchestrator.validate()
                             if "存在しない推奨を指している" in p],
                            orchestrator.validate())

    def test_unknown_disposition_word_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "done"}])
            self.assertTrue([p for p in orchestrator.validate()
                             if "語彙に無い" in p], orchestrator.validate())

    def test_examined_pending_is_not_untouched_pending(self):
        """『調べたうえで未着手』と『まだ調べていない』を一語で混ぜない。

        混ぜると、見ていない山を見た山と同じ顔で数える（INC-006・INC-010 で
        二度起きた、一語に二つの意味を持たせる取り違え）。処遇を実際に付け始めて
        初めて見えた穴である。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "a", "kind": "機構の変更",
                         "owner_decision_required": False},
                        {"action": "b", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "pending",
                         "note": "調べたが未着手"}])
            examined, untouched = orchestrator._split_pending(
                orchestrator.recommendation_backlog()["pending"])
            self.assertEqual([r["index"] for r in examined], [0])
            self.assertEqual([r["index"] for r in untouched], [1])

    def test_untouched_is_named_before_examined(self):
        """見ていない山の中身は優先順を付けられないので、先に調べる。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp,
                       [{"action": "調べ済み", "kind": "機構の変更",
                         "owner_decision_required": False},
                        {"action": "未調査", "kind": "機構の変更",
                         "owner_decision_required": False}],
                       [{"incident_id": "INC-x", "index": 0, "state": "pending",
                         "note": "調べたが未着手"}])
            head = [a for a in orchestrator.next_actions()
                    if a.startswith("APPLY_FINDINGS")][0]
            self.assertIn("未調査", head)
            self.assertIn("未調査 1 件", head)
            self.assertIn("調査済み未着手 1 件", head)

    def test_terminal_states_are_a_subset_of_the_vocabulary(self):
        self.assertTrue(orchestrator.TERMINAL_RECOMMENDATION_STATES
                        <= set(orchestrator.RECOMMENDATION_STATES))
        self.assertNotIn("pending", orchestrator.TERMINAL_RECOMMENDATION_STATES)


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


class FiringPointTest(unittest.TestCase):
    """宣言された評価の発火点は、走らせ手を持つか、持たないと明記されるか（ADR-128）。

    ADR-120 は状態の二分を、ADR-124 は台帳の成果物の二分を課した。どちらも
    「在る物」を入力に走るので、走らせ手の無い段は成果物を生まず、台帳に欠落の
    記録すら現れない。宣言された発火点と実行器の対応という三面目は、両者の
    対象範囲の外にあった（INC-021）。
    """

    def test_every_firing_point_is_either_run_or_declared_unimplemented(self):
        for state, entry in orchestrator.FIRING_POINTS.items():
            runs = bool(entry.get("runner"))
            why = entry.get("unimplemented")
            self.assertNotEqual(
                bool(runs), bool(why),
                "%s は走らせ手か未実装の明記のちょうど一方を持つこと" % state)

    def test_declared_runners_exist_on_disk(self):
        """宣言が嘘をつけないようにする（ADR-124 と同じ原理）。"""
        harness_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")
        for state, entry in orchestrator.FIRING_POINTS.items():
            runner = entry.get("runner")
            if not runner:
                continue
            self.assertTrue(os.path.isfile(os.path.join(harness_dir, runner)),
                            "%s の走らせ手 %r が harness/ に無い" % (state, runner))

    def test_declared_prompt_builders_resolve(self):
        from harness import prompts
        for state, entry in orchestrator.FIRING_POINTS.items():
            for name in entry.get("prompt_builders") or ():
                self.assertTrue(callable(getattr(prompts, name, None)),
                                "%s の %r が prompts に無い" % (state, name))

    def test_declared_ledger_kinds_are_registered(self):
        known = {e["kind"] for e in orchestrator.LEDGER_KINDS}
        for state, entry in orchestrator.FIRING_POINTS.items():
            kind = entry.get("ledger_kind")
            if not kind:
                continue
            self.assertIn(kind, known, "%s の成果物種別" % state)

    def test_table_matches_the_union_of_lane_firing_points(self):
        """両方向の差集合が空。宣言だけの段も、宣言の無い実行器も許さない。

        逆向きの穴が実在した —— INGEST_NORMS は extract_principles.py が実 opus
        セッションを走らせるのに、どのレーンの fires_on にも現れていなかった。
        """
        declared = set()
        for lane in orchestrator.LANES.values():
            declared.update(lane["fires_on"])
        self.assertEqual(declared - set(orchestrator.FIRING_POINTS), set())
        self.assertEqual(set(orchestrator.FIRING_POINTS) - declared, set())

    def test_ingest_norms_is_declared_by_the_book_lanes(self):
        for name in ("jerg", "stpa", "cast"):
            self.assertIn("INGEST_NORMS", orchestrator.LANES[name]["fires_on"],
                          "%s レーンが INGEST_NORMS を宣言していない" % name)

    def test_no_firing_point_is_left_unimplemented(self):
        """FORMALIZE と VERIFY は走らせ手を持つ（ADR-138・ADR-139）。

        INC-021 推奨#3 の所有者裁定（2026-08-07）で両方を実装した。ADR-128 の
        不変条件（走らせ手か未実装の明記のちょうど一方）はそのまま —— 倒れた
        のはエントリの側であって、二分の側ではない。
        """
        summary = orchestrator._firing_point_summary()
        self.assertEqual(summary["unimplemented"], {})
        self.assertIn("FORMALIZE", summary["runnable"])
        self.assertIn("VERIFY", summary["runnable"])

    def test_a_new_firing_point_without_a_runner_turns_the_canon_red(self):
        """次に発火点が増えたときにも効く不変条件であることの確認。"""
        original = dict(orchestrator.FIRING_POINTS)
        orchestrator.FIRING_POINTS["BRAND_NEW"] = {}
        try:
            problems = orchestrator._validate_firing_points()
        finally:
            orchestrator.FIRING_POINTS.clear()
            orchestrator.FIRING_POINTS.update(original)
        self.assertTrue(any("BRAND_NEW" in p for p in problems), problems)


class VerifyGateTest(unittest.TestCase):
    """新規の fixed:true は PASS の verify 記録を要す（ADR-139）。

    修正したという申告は検証ではない。祖父条項は 2026-08-07 時点の全事象
    （26 件）で凍結し、以後に増える fixed:true だけに門を課す。
    """

    def test_new_fixed_incident_without_verify_ref_is_red(self):
        problems = orchestrator._validate_verify_refs(
            incidents=[{"id": "INC-099-brand-new", "fixed": True}],
            verify_records={})
        self.assertTrue(any("verify_ref が無い" in p for p in problems),
                        problems)

    def test_grandfathered_incidents_stay_green(self):
        incidents = [{"id": iid, "fixed": True}
                     for iid in orchestrator.VERIFY_GRANDFATHERED]
        self.assertEqual(
            orchestrator._validate_verify_refs(incidents=incidents,
                                               verify_records={}), [])

    def test_grandfathered_tuple_is_frozen_at_the_26_of_2026_08_07(self):
        """凍結は 2026-08-07 時点の全事象。列を増やすのは所有者判断。"""
        self.assertEqual(len(orchestrator.VERIFY_GRANDFATHERED), 26)
        self.assertIsInstance(orchestrator.VERIFY_GRANDFATHERED, tuple)
        self.assertIn("INC-001-sessionend-audit-gap",
                      orchestrator.VERIFY_GRANDFATHERED)
        self.assertIn("INC-026-accepted-adr-has-no-sanctioned-repair-path",
                      orchestrator.VERIFY_GRANDFATHERED)

    def test_verify_ref_must_resolve_to_a_pass_record(self):
        inc = [{"id": "INC-099-brand-new", "fixed": True,
                "verify_ref": "assurance/ledger/verify/INC-099-brand-new.json"}]
        # 指す先が無い → 赤。
        problems = orchestrator._validate_verify_refs(
            incidents=inc, verify_records={})
        self.assertTrue(any("記録" in p and "無い" in p for p in problems),
                        problems)
        # 記録は在るが PASS でない → 赤（UNASSESSED の記録も門を通らない）。
        problems = orchestrator._validate_verify_refs(
            incidents=inc,
            verify_records={"INC-099-brand-new":
                            {"record": {"verdict": "FAIL"}}})
        self.assertTrue(any("PASS でない" in p for p in problems), problems)
        problems = orchestrator._validate_verify_refs(
            incidents=inc,
            verify_records={"INC-099-brand-new":
                            {"record": None, "sdk_status": "UNASSESSED"}})
        self.assertTrue(any("PASS でない" in p for p in problems), problems)
        # PASS の記録 → 緑。
        self.assertEqual(orchestrator._validate_verify_refs(
            incidents=inc,
            verify_records={"INC-099-brand-new":
                            {"record": {"verdict": "PASS"}}}), [])

    def test_unfixed_incident_needs_no_verify_record(self):
        self.assertEqual(orchestrator._validate_verify_refs(
            incidents=[{"id": "INC-099-brand-new", "fixed": False}],
            verify_records={}), [])

    def test_verify_ledger_kind_is_declared(self):
        kinds = {e["kind"] for e in orchestrator.LEDGER_KINDS}
        self.assertIn("verify/<対象 id>.json", kinds)
        entry = orchestrator.ledger_kind_of("verify/INC-099-brand-new.json")
        self.assertIsNotNone(entry)
        self.assertIn("load_verify_records", entry["read_by"])

    def test_load_verify_records_keys_by_target_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            v_dir = os.path.join(tmp, "ledger", "verify")
            os.makedirs(v_dir)
            with open(os.path.join(v_dir, "INC-099-brand-new.json"),
                      "w", encoding="utf-8") as f:
                json.dump({"target_id": "INC-099-brand-new",
                           "record": {"verdict": "PASS"}}, f)
            orig = orchestrator.LANE_DIR
            orchestrator.LANE_DIR = tmp
            self.addCleanup(setattr, orchestrator, "LANE_DIR", orig)
            records = orchestrator.load_verify_records()
            self.assertEqual(list(records), ["INC-099-brand-new"])
            self.assertEqual(records["INC-099-brand-new"]["record"]["verdict"],
                             "PASS")


class OwnerDecisionKindTest(unittest.TestCase):
    """所有者判断は、六類型のどれかを名指してはじめて成立する（ADR-127）。

    評価者が付ける `owner_decision_required` は、所有者の権限についての判定では
    なく**評価者の視野の申告**である。事故分析の入力は事象・統制構造・カタログ
    だけで、統治木（確定事実・非目標・退行監視・ADR）は一つも渡っていない。
    何も決まっていない場所から見れば、すべてが未決に見える。申告をそのまま
    権限の判定として読み替える形は、この体系が三度「やらない」と決めた
    「検証できない申告を信じる」形の四度目である。
    """

    def test_the_six_kinds_are_the_canon(self):
        """類型は所有者が書いた六つ。ここで勝手に増やさない。"""
        self.assertEqual(len(orchestrator.OWNER_DECISION_KINDS), 6)
        for kind in ("互換性を壊す変更", "配布境界や保証範囲の変更",
                     "復旧不能な削除", "外部費用や credential",
                     "評価 model 最低線の引き下げ",
                     "配布物の版番号の変更とリリース"):
            self.assertIn(kind, orchestrator.OWNER_DECISION_KINDS)

    def test_evaluator_flag_alone_does_not_make_it_an_owner_decision(self):
        """申告だけでは owner にならない。既定は pending（未調査）。"""
        buckets = orchestrator.recommendation_backlog()
        for row in buckets["owner"]:
            self.assertTrue(
                row.get("owner_decision_kind"),
                "%s#%s が類型を名指さずに owner へ入っている"
                % (row["incident_id"], row["index"]))

    def test_owner_disposition_without_a_kind_is_red(self):
        rows = {("INC-001-sessionend-audit-gap", 3):
                {"incident_id": "INC-001-sessionend-audit-gap", "index": 3,
                 "state": "owner"}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertTrue(any("類型" in p for p in problems), problems)

    def test_owner_disposition_with_an_unknown_kind_is_red(self):
        rows = {("INC-001-sessionend-audit-gap", 3):
                {"incident_id": "INC-001-sessionend-audit-gap", "index": 3,
                 "state": "owner", "owner_decision_kind": "なんとなく重そう"}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertTrue(any("類型" in p for p in problems), problems)

    def test_owner_disposition_with_a_named_kind_is_accepted(self):
        rows = {("INC-001-sessionend-audit-gap", 3):
                {"incident_id": "INC-001-sessionend-audit-gap", "index": 3,
                 "state": "owner",
                 "owner_decision_kind": "配布境界や保証範囲の変更",
                 "note": "根拠"}}
        self.assertEqual(orchestrator._validate_recommendation_status(rows), [])

    def test_status_separates_the_claim_from_the_finding(self):
        """申告の件数と、成立した件数を別々に出す。

        一語に二つの意味を持たせない（INC-006・INC-010・INC-018 と同型）。
        混ぜると、見ていない山を裁いた山と同じ顔で数えることになる。
        """
        summary = orchestrator._recommendation_summary()
        self.assertIn("evaluator_claimed_owner", summary)
        self.assertIn("owner", summary["counts"])
        self.assertGreaterEqual(summary["evaluator_claimed_owner"],
                                summary["counts"]["owner"])


class AssumptionRegisterTest(unittest.TestCase):
    """保証が寄りかかる想定の登記簿（ADR-126）。

    想定は「何も検証していない前提」を名指しする物なので、検証者が居ないこと
    自体は欠陥ではない。欠陥なのは、欄が無いこと・指標が無いこと・観測に
    根拠が無いことである。
    """

    def _write(self, tmp, assumptions):
        path = os.path.join(tmp, "assumptions.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"assumptions": assumptions}, f, ensure_ascii=False)
        return path

    def _indicator(self, **over):
        base = {"observe_where": "どこか", "abnormal_when": "何か"}
        base.update(over)
        return base

    def test_real_register_is_well_formed(self):
        self.assertEqual(orchestrator._validate_assumptions(), [])

    def test_real_register_is_not_empty(self):
        """空の登記簿は『想定が無い』ではなく『まだ書いていない』である。"""
        self.assertTrue(orchestrator.load_assumptions())

    def test_missing_verified_by_field_is_red(self):
        """null は可、欄の不在は不可（沈黙は理由ではない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [self._indicator()]}])
            self.assertEqual(
                orchestrator._validate_assumptions(path, incident_ids=set()), [])
            path = self._write(tmp, [{"id": "ASM-X",
                                      "leading_indicators": [self._indicator()]}])
            problems = orchestrator._validate_assumptions(path, incident_ids=set())
            self.assertTrue(any("verified_by" in p for p in problems), problems)

    def test_indicator_needs_both_conditions(self):
        """ADR-117 と同じ二条件。どこで観測するかと、何を異常と見るか。"""
        for missing in ("observe_where", "abnormal_when"):
            with tempfile.TemporaryDirectory() as tmp:
                ind = self._indicator(**{missing: ""})
                path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                          "leading_indicators": [ind]}])
                problems = orchestrator._validate_assumptions(
                    path, incident_ids=set())
                self.assertTrue(any(missing in p for p in problems), problems)

    def test_assumption_without_indicator_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": []}])
            problems = orchestrator._validate_assumptions(path, incident_ids=set())
            self.assertTrue(any("先行指標が無い" in p for p in problems), problems)

    def test_observation_state_must_be_in_the_vocabulary(self):
        """根拠なき PASS を書かせないための語彙。ここで語を増やさない。"""
        with tempfile.TemporaryDirectory() as tmp:
            ind = self._indicator(state="緑", observed_at="2026-08-06")
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [ind]}])
            problems = orchestrator._validate_assumptions(path, incident_ids=set())
            self.assertTrue(any("語彙に無い" in p for p in problems), problems)

    def test_observation_without_a_date_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            ind = self._indicator(state="PASS")
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [ind]}])
            problems = orchestrator._validate_assumptions(path, incident_ids=set())
            self.assertTrue(any("日付が無い" in p for p in problems), problems)

    def test_incident_link_must_resolve(self):
        """宣言が嘘をつけないようにする（ADR-124 と同じ原理）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "incident_id": "INC-999-nope",
                                      "leading_indicators": [self._indicator()]}])
            problems = orchestrator._validate_assumptions(
                path, incident_ids={"INC-001-sessionend-audit-gap"})
            self.assertTrue(any("INC-999-nope" in p for p in problems), problems)

    def test_unobserved_assumption_is_named(self):
        """指標を書いただけで観測していない想定は、次の行動に挙がる。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [self._indicator()]}])
            backlog = orchestrator.assumption_backlog(path)
            self.assertEqual([r["reason"] for r in backlog], ["未観測"])

    def test_broken_assumption_without_an_incident_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            ind = self._indicator(state="FAIL", observed_at="2026-08-06")
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [ind]}])
            backlog = orchestrator.assumption_backlog(path)
            self.assertEqual([r["reason"] for r in backlog], ["破れている"])

    def test_broken_assumption_with_an_incident_is_not_named_twice(self):
        """是正は事象の側が持つ。二重に鳴らすと、どちらを踏んでも消えない。"""
        with tempfile.TemporaryDirectory() as tmp:
            ind = self._indicator(state="FAIL", observed_at="2026-08-06")
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "incident_id": "INC-001-sessionend-audit-gap",
                                      "leading_indicators": [ind]}])
            self.assertEqual(orchestrator.assumption_backlog(path), [])

    def test_passing_assumption_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            ind = self._indicator(state="PASS", observed_at="2026-08-06")
            path = self._write(tmp, [{"id": "ASM-X", "verified_by": None,
                                      "leading_indicators": [ind]}])
            self.assertEqual(orchestrator.assumption_backlog(path), [])

    def test_review_assumption_precedes_the_recommendation_backlog(self):
        """前提の点検は推奨の山より前に置く。

        後ろに置くと 100 件超の推奨の陰に隠れ、ATTACK_EVALUATOR が5反復
        飛ばされたのと同じ形になる（INC-012）。
        """
        original = orchestrator.assumption_backlog
        orchestrator.assumption_backlog = lambda path=None: [
            {"id": "ASM-X", "reason": "未観測", "detail": "d"}]
        try:
            actions = orchestrator.next_actions()
        finally:
            orchestrator.assumption_backlog = original
        review = [i for i, a in enumerate(actions)
                  if a.startswith("REVIEW_ASSUMPTION:")]
        apply_findings = [i for i, a in enumerate(actions)
                          if a.startswith("APPLY_FINDINGS:")]
        self.assertTrue(review, actions)
        if apply_findings:
            self.assertLess(review[0], apply_findings[0], actions)

    def test_state_is_partitioned(self):
        """REVIEW_ASSUMPTION も二分のどちらかに属する（ADR-120）。"""
        self.assertIn("REVIEW_ASSUMPTION", orchestrator.STATES)
        self.assertIn("REVIEW_ASSUMPTION", orchestrator.NAMEABLE_STATES)
        self.assertNotIn("REVIEW_ASSUMPTION", orchestrator.WITHIN_CYCLE_STATES)


if __name__ == "__main__":
    unittest.main()


class AttackFreshnessPrecisionTest(unittest.TestCase):
    """攻撃の鮮度は、日ではなく時点で比べる（事象 INC-023）。

    ADR-120 は「評価器の成果物が故障注入の証拠より新しければ、その評価器は
    まだ攻撃されていない」と決めた。だが比較が日で切り捨てられていたため、
    同じ日のうちに証拠より**後**で生まれた成果物が「攻撃済み」と読まれた。
    実測では 11 件の事故分析が、攻撃の証拠が指すコミットの子孫のコミットで
    生まれていたのに、正本は一度も ATTACK_EVALUATOR を挙げなかった。
    """

    def test_instant_comparison_keeps_the_time(self):
        self.assertEqual(
            orchestrator._max_instant(["2026-08-06", "2026-08-06T14:21:01Z"]),
            "2026-08-06T14:21:01Z")

    def test_instant_comparison_normalises_the_separator(self):
        """空白区切りの時刻を T 区切りと同じ順序で比べる。"""
        self.assertEqual(
            orchestrator._max_instant(["2026-08-06 23:00:00", "2026-08-06T09:00:00Z"]),
            "2026-08-06T23:00:00")

    def test_day_only_evidence_cannot_cover_the_same_day(self):
        """日付だけの証拠は、その日の中で先か後かを示さない。前提欠如の側へ倒す。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06",
                       cast_at="2026-08-06T14:21:01Z")
            actions = orchestrator.next_actions()
            self.assertTrue(
                [a for a in actions if a.startswith("ATTACK_EVALUATOR")], actions)

    def test_timestamped_evidence_after_the_output_clears_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06T23:59:00Z",
                       cast_at="2026-08-06T14:21:01Z")
            self.assertEqual(
                [a for a in orchestrator.next_actions()
                 if a.startswith("ATTACK_EVALUATOR")], [])

    def test_timestamped_evidence_before_the_output_raises_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06T09:00:00Z",
                       cast_at="2026-08-06T14:21:01Z")
            self.assertTrue(
                [a for a in orchestrator.next_actions()
                 if a.startswith("ATTACK_EVALUATOR")])

    def test_attack_evaluator_writes_a_timestamp(self):
        """証拠の側も時点を書く。読む段だけ精密にしても比べられない。"""
        import inspect
        from harness import attack_evaluator
        src = inspect.getsource(attack_evaluator.main)
        self.assertIn("generated_at", src)

    def _stub(self, tmp, attack, cast_at):
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(os.path.join(ledger, "cast"), exist_ok=True)
        with open(os.path.join(ledger, "mutations-x.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"date": attack[:10], "generated_at": attack}
                      if len(attack) > 10 else {"date": attack}, f)
        with open(os.path.join(ledger, "cast", "INC-x.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"generated_at": cast_at}, f)
        for attr, value in (("CATALOG_DIR", os.path.join(tmp, "catalogs")),
                            ("LANE_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "inc.json")),
                            ("ASSUMPTIONS_PATH", os.path.join(tmp, "asm.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)


class PriorityOrderTest(unittest.TestCase):
    """次の行動の**並び**を凍結する（ADR-131）。

    正本は「手で選ばない・先頭から着手する・飛ばさない」を定める（ADR-115、
    運転手順 §1）。だから並びそのものが規範である —— 並びが誤っていると、
    規律を守るほど本丸へ着かない。実際に APPLY_FINDINGS（推奨 177 件）が
    MAP_COVERAGE（本丸の欠落 299 件）の前に立ち、推奨を消化しきるまで本丸へ
    着かない形になっていた。

    順の意味は「前提 → 前提の破れ → 測る対象 → 測る道具」である:
      INGEST_NORMS      … 台帳が立たないと網羅は測れない（前提）
      CAST_ANALYSIS     … なぜ見逃したかを残す装置（動かさない）
      REVIEW_ASSUMPTION … 想定が破れれば下流の PASS が根拠を失う
      MAP_COVERAGE      … 本丸（Doctrine 本体）の欠落
      APPLY_FINDINGS    … 検証基盤の改善の推奨
      ATTACK_EVALUATOR  … 評価器自身への攻撃
    """

    ORDER = ("INGEST_NORMS", "CAST_ANALYSIS", "REVIEW_ASSUMPTION",
             "MAP_COVERAGE", "APPLY_FINDINGS", "ATTACK_EVALUATOR")

    def test_order_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_all_firing(tmp)
            actions = orchestrator.next_actions()
            ranks = [self._rank(a) for a in actions]
            self.assertEqual(ranks, sorted(ranks),
                             "次の行動の並びが正本の優先順と違う:\n%s"
                             % "\n".join(actions))

    def test_coverage_outranks_findings(self):
        """本丸の欠落は、検証基盤の推奨より先に来る。

        検証基盤は本丸を測るための道具であって、道具の完成度が目的ではない
        （ADR-131。所有者判断）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_all_firing(tmp)
            actions = orchestrator.next_actions()
            cov = self._first(actions, "MAP_COVERAGE")
            fnd = self._first(actions, "APPLY_FINDINGS")
            self.assertLess(cov, fnd, actions)

    def test_incident_analysis_stays_at_the_head(self):
        """事象の分析は動かさない —— 先に立つのは CAST_ANALYSIS だけ。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub_all_firing(tmp)
            actions = orchestrator.next_actions()
            self.assertLess(self._first(actions, "CAST_ANALYSIS"),
                            self._first(actions, "REVIEW_ASSUMPTION"), actions)
            self.assertLess(self._first(actions, "CAST_ANALYSIS"),
                            self._first(actions, "MAP_COVERAGE"), actions)

    def test_every_nameable_state_has_a_rank(self):
        """順位表に載らない状態を作らない。

        載らない状態は「並びの中で自分の位置を主張できない」状態であり、
        黙って末尾へ落ちる。ATTACK_EVALUATOR が5反復飛ばされたのと同じ形
        （INC-012）。
        """
        for state in orchestrator.NAMEABLE_STATES:
            self.assertIn(state, orchestrator.ACTION_PRIORITY, state)

    def test_priority_matches_the_documented_order(self):
        """コードの順位表が、この試験の凍結する並びと一致する。"""
        ordered = sorted(orchestrator.ACTION_PRIORITY,
                         key=lambda s: orchestrator.ACTION_PRIORITY[s])
        self.assertEqual([s for s in ordered if s in self.ORDER],
                         list(self.ORDER))

    def _rank(self, action):
        return orchestrator.ACTION_PRIORITY[action.split(":", 1)[0]]

    def _first(self, actions, prefix):
        for i, a in enumerate(actions):
            if a.startswith(prefix):
                return i
        self.fail("%s が挙がっていない: %s" % (prefix, actions))

    def _stub_all_firing(self, tmp):
        """五種すべてが同時に鳴る帳簿を立てる。

        並びは「どれか一つだけが鳴る」状況では測れない。同時に鳴らして初めて、
        どちらが先かという問いが立つ。
        """
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(os.path.join(ledger, "cast"), exist_ok=True)
        catalogs = os.path.join(tmp, "catalogs")
        os.makedirs(catalogs, exist_ok=True)
        for attr, value in (("CATALOG_DIR", catalogs),
                            ("LANE_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "inc.json")),
                            ("ASSUMPTIONS_PATH", os.path.join(tmp, "asm.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)

        # CAST_ANALYSIS: 分析待ちの事象。
        with open(os.path.join(tmp, "inc.json"), "w", encoding="utf-8") as f:
            json.dump({"incidents": [{"id": "INC-x", "cast_analysis": "pending"}]}, f)
        # REVIEW_ASSUMPTION: 先行指標が一つも観測されていない想定。
        with open(os.path.join(tmp, "asm.json"), "w", encoding="utf-8") as f:
            json.dump({"assumptions": [{"id": "ASM-x",
                                        "leading_indicators": [{"id": "LI-x"}]}]}, f)
        # APPLY_FINDINGS: 処遇の付いていない推奨。
        with open(os.path.join(ledger, "cast", "INC-x.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"analysis": {"incident_id": "INC-x",
                                    "recommendations": [
                                        {"action": "a", "kind": "機構の変更",
                                         "owner_decision_required": False}]}}, f)
        # MAP_COVERAGE: 索引が動いた後の非終端の項（種別の指紋を持たせない
        # ＝どの索引に対する判定か判らないので古い側へ倒れる）。
        # 件数は閾値（ADR-134）を越えさせる —— ここで測りたいのは**並び**で
        # あって閾値ではない。信号を混ぜない（閾値は test_staleness_scope が持つ）。
        # ATTACK_EVALUATOR: 故障注入の証拠を置かない（成果物の方が新しくなる）。
        stale_n = orchestrator.STALE_RAISE_THRESHOLD
        for book in ("jerg", "stpa", "cast"):
            with open(os.path.join(catalogs, "%s-principles.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"chunks": [], "principles": [],
                           "totals": {"cost_usd": 0.0, "principles": 0,
                                      "rejected": 0}}, f)
            with open(os.path.join(catalogs, "%s-coverage.json" % book),
                      "w", encoding="utf-8") as f:
                json.dump({"entries": [
                    {"key": "stale%d" % i, "disposition": "対応計画あり",
                     "assigned_at": "2026-08-05T00:00:00Z",
                     "assigned_by": {"index_sha256": "0" * 64}}
                    for i in range(stale_n)]}, f)
