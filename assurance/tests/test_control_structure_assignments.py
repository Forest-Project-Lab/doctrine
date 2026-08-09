"""統制構造の「誰が負うか」の割当を凍結する。

INC-006 推奨#5（進捗の停止を誰が観測するか）と INC-027 推奨#8（台帳の健全性を
誰が負うか）は、どちらも「割当が現に無い」という実測から出た。書いたあと黙って
消えることを防ぐ。

重複させないことも同時に凍結する —— 裁定の理由がそこにあるからである。二つの
要素が同じ責任を名乗ると、双方が他方を前提にして減衰する（推奨自身が指した危険）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import control_structure as cs  # noqa: E402


# 責任の名。要素 id と、control_actions の中で探す字面。
ASSIGNMENTS = (
    ("ASSURANCE_LANE", "進捗の停止を観測する", "INC-006 推奨#5"),
    ("ASSURANCE_LANE", "台帳の健全性を保つ", "INC-027 推奨#8"),
)


def _element(eid):
    for e in cs.ELEMENTS:
        if e["id"] == eid:
            return e
    return None


def unassigned():
    """割当の見当たらない責任を (origin, eid) で返す。判定の単一の源。

    subTest の中で assert を書くと失敗が握られて外へ出ないので、判定は素の
    関数として持ち、試験と oracle の両方がこれを呼ぶ。
    """
    missing = []
    for eid, needle, origin in ASSIGNMENTS:
        e = _element(eid)
        if e is None or len([a for a in e["control_actions"] if needle in a]) != 1:
            missing.append((origin, eid))
    return missing


class TestAssignmentsExist(unittest.TestCase):
    def test_each_responsibility_is_assigned_to_its_element(self):
        self.assertEqual(
            unassigned(), [],
            "割当が control_actions に無い: %s" % (unassigned(),),
        )

    def test_no_other_element_claims_the_same_responsibility(self):
        # 裁定の核心は一意であること。重複は減衰を生む。
        for eid, needle, origin in ASSIGNMENTS:
            with self.subTest(origin=origin):
                claimants = [
                    e["id"] for e in cs.ELEMENTS
                    if any(needle in a for a in e["control_actions"])
                ]
                self.assertEqual(
                    claimants, [eid],
                    "%s を名乗る要素が一つでない: %s" % (origin, claimants),
                )

    def test_the_oracle_can_fail(self):
        # 上の二つが構造を本当に見ていることを示す。字面を消せば落ちる。
        saved = _element("ASSURANCE_LANE")["control_actions"]
        try:
            _element("ASSURANCE_LANE")["control_actions"] = ["次の行動を決定論で導く"]
            self.assertEqual(len(unassigned()), len(ASSIGNMENTS),
                             "字面を消しても oracle が気づかない")
        finally:
            _element("ASSURANCE_LANE")["control_actions"] = saved
        # 復旧を確かめる（この試験が後続を壊さないこと）。
        self.assertEqual(unassigned(), [])


class TestSingleWriterGapIsDeclared(unittest.TestCase):
    """ASM-006 は覆っていない。覆っていないことを構造で言い続ける。"""

    def test_concurrent_write_is_declared_as_a_known_gap(self):
        e = _element("ASSURANCE_LANE")
        gaps = " ".join(e["known_gaps"])
        self.assertIn("同時書き込み", gaps)
        self.assertIn("ASM-006", gaps)


if __name__ == "__main__":
    unittest.main()
