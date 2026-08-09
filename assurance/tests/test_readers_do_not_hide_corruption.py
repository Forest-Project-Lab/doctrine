#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""読み手は黙って劣化してよいが、読めなかった事実まで消してはならない。

INC-027 の事故分析が挙げた推奨#0。読み手（latest_formalize・latest_scenarios・
load_verify_records・load_recommendation_status）は `ValueError` を握り潰す。
帳簿が読めない日でもレーンは走れた方がよいので、その寛容さ自体は正しい。
しかし**読めなかったという事実まで消える**ので、切り詰めと不在が区別できない
（INC-006 の沈黙の型）。

三分は保つ: 行動の導出は黙って劣化・読み手は None を返す・validate が名指す。
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import ledger_io, orchestrator  # noqa: E402


class ReadersRecordWhatTheySwallowTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="swallow-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.ledger = os.path.join(self.dir, "ledger")
        for sub in ("formalize", "scenarios", "verify"):
            os.makedirs(os.path.join(self.ledger, sub))
        self._real_lane = orchestrator.LANE_DIR
        orchestrator.LANE_DIR = self.dir
        self.addCleanup(setattr, orchestrator, "LANE_DIR", self._real_lane)
        orchestrator._CORRUPT_SEEN.clear()
        self.addCleanup(orchestrator._CORRUPT_SEEN.clear)

    def _truncate(self, sub, name):
        path = os.path.join(self.ledger, sub, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"plans": [{"scenario_id": "SCN-1", "verd')
        return path

    def test_a_truncated_formalize_is_recorded_not_erased(self):
        self._truncate("formalize", "2026-08-09.json")
        self.assertIsNone(orchestrator.latest_formalize(),
                          "読み手は黙って劣化してよい（None を返す）")
        self.assertTrue(orchestrator.corrupt_seen(),
                        "読めなかった事実まで消してはならない")

    def test_a_truncated_scenarios_is_recorded(self):
        self._truncate("scenarios", "2026-08-09.json")
        self.assertIsNone(orchestrator.latest_scenarios())
        self.assertTrue(orchestrator.corrupt_seen())

    def test_a_truncated_verify_record_is_recorded(self):
        self._truncate("verify", "INC-900-x.json")
        self.assertEqual(orchestrator.load_verify_records(), {})
        self.assertTrue(orchestrator.corrupt_seen())

    def test_a_healthy_ledger_records_nothing(self):
        ledger_io.write_json(
            os.path.join(self.ledger, "formalize", "2026-08-09.json"),
            {"kind": "formalize", "plans": []})
        self.assertIsNotNone(orchestrator.latest_formalize())
        self.assertEqual(orchestrator.corrupt_seen(), [],
                         "健全な台帳で破損を記録してはならない")

    def test_an_absent_ledger_records_nothing(self):
        """欠落は破損ではない。"""
        self.assertIsNone(orchestrator.latest_formalize())
        self.assertEqual(orchestrator.corrupt_seen(), [])

    def test_validate_names_what_was_swallowed(self):
        self._truncate("formalize", "2026-08-09.json")
        orchestrator.latest_formalize()
        problems = orchestrator._validate_no_swallowed_corruption()
        self.assertEqual(len(problems), 1)
        self.assertIn("2026-08-09.json", problems[0])

    def test_validate_is_wired(self):
        import inspect
        self.assertIn("_validate_no_swallowed_corruption",
                      inspect.getsource(orchestrator.validate))


class NoReaderCrashesOnACorruptLedgerTest(unittest.TestCase):
    """軸で持つ —— 台帳を全件壊しても、読み口はどれも例外で落ちない。

    INC-027 の推奨#11。`LedgerCorrupt` が `ValueError` を継がなくなったので、
    従来 `except ValueError` に守られていた経路が未捕捉例外へ転じうる。
    実際に三つ（load_red_records・unreproduced_plans・reproduce_red_summary）が
    転じており、**壊れた台帳 1 件で `orchestrator status` 自体が落ちる**状態
    だった。読み手は黙って劣化し、validate が名指す —— その三分を軸で守る。
    """

    READERS = ("load_incidents", "latest_scenarios", "latest_formalize",
               "load_verify_records", "load_recommendation_status",
               "recommendation_backlog", "load_assumptions",
               "assumption_backlog", "coverage_status", "load_red_records",
               "unreproduced_plans", "reproduce_red_summary",
               "attack_evidence_latest", "unknown_aging", "next_actions")

    def test_every_reader_survives_a_fully_corrupt_ledger(self):
        real = orchestrator.LANE_DIR
        d = tempfile.mkdtemp(prefix="corrupt-axis-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.addCleanup(setattr, orchestrator, "LANE_DIR", real)
        shutil.copytree(os.path.join(real, "ledger"),
                        os.path.join(d, "ledger"),
                        ignore=shutil.ignore_patterns("runs"))
        broken = 0
        for root, _dirs, files in os.walk(os.path.join(d, "ledger")):
            for n in files:
                if n.endswith(".json"):
                    with open(os.path.join(root, n), "w", encoding="utf-8") as fh:
                        fh.write("{")
                    broken += 1
        self.assertGreater(broken, 10, "壊す対象が足りない（空の緑にしない）")
        orchestrator.LANE_DIR = d
        orchestrator._CORRUPT_SEEN.clear()
        crashed = []
        for name in self.READERS:
            fn = getattr(orchestrator, name, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception as exc:            # noqa: BLE001 - 軸の検査
                crashed.append((name, type(exc).__name__))
        self.assertEqual(crashed, [],
                         "壊れた台帳で読み口が落ちた: %r" % (crashed,))
        self.assertTrue(orchestrator.corrupt_seen(),
                        "落ちない代わりに、破損を覚えていること")


if __name__ == "__main__":
    unittest.main()
