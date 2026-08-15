#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""鮮度の丸めは辺ごとに逆へ倒す（ADR-167。事象 INC-044）。

REPRODUCE_RED である。**是正の前に赤であることが要件**で、最初から緑なら
再現と認めない（運転手順 §2）。

比較は「評価器の成果物（左辺） > 故障注入の証拠（右辺）なら未攻撃」である。
INC-023 は右辺の日付だけの証拠を**その日の始まり**として並べた —— 覆う力を
弱める向きで、安全側である。同じ丸めが左辺にも当たっており、そちらでは
**覆われやすくする**向き、すなわち危険側になる。

ADR-167 の決定は一つの原則から出る ——「順序が判らないなら、攻撃が覆って
いないほうへ倒す」。右辺は始まりへ、左辺は終わりへ。

ここで凍結するのは振る舞いであって関数の形ではない。実装が丸めをどこに
持つかは決めていない。
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator  # noqa: E402


class FreshnessRoundingBySide(unittest.TestCase):

    def _stub(self, tmp, attack, evaluator_at):
        """攻撃証拠と評価器の成果物を一つずつ持つ帳簿を立てる。"""
        ledger = os.path.join(tmp, "ledger")
        os.makedirs(os.path.join(ledger, "cast"), exist_ok=True)
        doc = ({"date": attack[:10], "generated_at": attack}
               if len(attack) > 10 else {"date": attack})
        with open(os.path.join(ledger, "mutations-x.json"), "w",
                  encoding="utf-8") as f:
            json.dump(doc, f)
        with open(os.path.join(ledger, "cast", "INC-x.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"generated_at": evaluator_at}, f)
        for attr, value in (("CATALOG_DIR", os.path.join(tmp, "catalogs")),
                            ("LANE_DIR", tmp),
                            ("INCIDENTS_PATH", os.path.join(tmp, "inc.json")),
                            ("ASSUMPTIONS_PATH", os.path.join(tmp, "asm.json"))):
            orig = getattr(orchestrator, attr)
            setattr(orchestrator, attr, value)
            self.addCleanup(setattr, orchestrator, attr, orig)

    def _attack_raised(self):
        return [a for a in orchestrator.next_actions()
                if a.startswith("ATTACK_EVALUATOR")]

    def test_day_only_output_is_not_covered_by_an_earlier_same_day_attack(self):
        """左辺が日付だけなら、同じ日の**先に**走った攻撃は覆わない。

        評価器がその日のいつ走ったかは記録が示さない。攻撃の後だったかも
        しれない以上、覆ったと見なさない（ADR-167 第1項の左辺）。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06T09:00:00Z",
                       evaluator_at="2026-08-06")
            self.assertTrue(self._attack_raised(),
                            "日付だけの成果物を、同じ日の先行する攻撃が覆っている")

    def test_both_day_only_on_the_same_day_stays_unattacked(self):
        """両辺とも日付だけなら前後は決められない。攻撃していない側へ倒す。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06", evaluator_at="2026-08-06")
            self.assertTrue(self._attack_raised(),
                            "前後を決められない対を『攻撃済み』と読んでいる")

    def test_a_later_attack_still_covers_a_day_only_output(self):
        """翌日の攻撃は覆う。過剰に赤くしないための歯止め（是正後も緑）。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-07T09:00:00Z",
                       evaluator_at="2026-08-06")
            self.assertEqual(self._attack_raised(), [],
                             "翌日の攻撃まで覆わないのは過剰是正である")

    def test_the_right_side_rounding_is_unchanged(self):
        """右辺は今までどおりその日の始まり（INC-023 のまま）。

        日付だけの攻撃証拠は、同じ日の成果物を覆わない。ADR-167 は
        右辺を変えない —— 変えると今度は右辺が危険側へ倒れる。
        """
        with tempfile.TemporaryDirectory() as tmp:
            self._stub(tmp, attack="2026-08-06",
                       evaluator_at="2026-08-06T14:21:01Z")
            self.assertTrue(self._attack_raised(),
                            "日付だけの攻撃証拠が同じ日の成果物を覆っている")


if __name__ == "__main__":
    unittest.main()
