#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""処遇の `investigated` は「観測」であって「現状」ではない（INC-050 推奨#0）。

INC-050 の形は、処遇に付く所見が**ある時点の観測**なのに、後の反復がそれを
**現状**として読むことだった。実測で 2026-08-08 の一括トリアージの所見が
既に誤っており、着手前に測り直さなければ既に在る物を二重に足すところだった。

分析の推奨#0 が求めるのは欄の構造化である:

  「investigated 欄を自由型から構造（observed_at・observed_by・method・claim）へ
    移し、str/bool/None をそのまま受け付けない検査を決定論試験に加える。
    既存 429 件は移行時に observed_at 不明として明示的に印を付け、
    **欠測を欠測として残す（true を日付へ推測変換しない）**。」

自由型のままだと二つのことが起きる。(1) `investigated: true` は「調べた」と
主張しながら、いつ何を見たかを持たない —— 古びを問うことすらできない。
(2) 散文の中の日付は読み手が拾うしかなく、機械は経過日数を数えられない。

**欄が無いことは咎めない。**処遇に所見が無いのは「観測していない」であって、
偽の観測ではない。咎めるのは**観測を騙る非構造**である。
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator  # noqa: E402

LEDGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ledger", "recommendation-status.json")

REQUIRED = ("observed_at", "observed_by", "method", "claim")


def _rows():
    with open(LEDGER, encoding="utf-8") as fh:
        return json.load(fh)["dispositions"]


class InvestigatedIsAnObservationTest(unittest.TestCase):
    def test_the_real_ledger_has_no_free_form_investigated(self):
        """実台帳に自由型の所見が残っていない。"""
        offenders = [
            (e["incident_id"], e["index"], type(e["investigated"]).__name__)
            for e in _rows()
            if "investigated" in e and not isinstance(e["investigated"], dict)]
        self.assertEqual(
            offenders, [],
            "所見が自由型のまま残っている。観測は observed_at/observed_by/"
            "method/claim を持つ構造で書く（INC-050 推奨#0）: %r" % (offenders,))

    def test_every_observation_carries_the_four_fields(self):
        """構造は四つの欄をすべて持つ（欠けた欄は沈黙になる）。"""
        offenders = []
        for e in _rows():
            obs = e.get("investigated")
            if not isinstance(obs, dict):
                continue
            missing = [k for k in REQUIRED if k not in obs]
            if missing:
                offenders.append((e["incident_id"], e["index"], missing))
        self.assertEqual(offenders, [], "所見に欠けた欄がある: %r" % (offenders,))

    def test_a_missing_date_is_marked_not_guessed(self):
        """observed_at が無いときは、その理由が method に書かれている。

        **推測で埋めない。**元が真偽値だった 23 件は「いつ見たか」を持たない
        —— 移行で日付を捏造すれば、古びの計算が嘘の値を返すようになる。
        欠測は欠測として残し、なぜ欠けているかを method が言う。
        """
        offenders = []
        for e in _rows():
            obs = e.get("investigated")
            if not isinstance(obs, dict):
                continue
            if obs.get("observed_at") is None and not (obs.get("method") or "").strip():
                offenders.append((e["incident_id"], e["index"]))
        self.assertEqual(
            offenders, [],
            "観測日が無いのに、無い理由も無い。沈黙は理由ではない: %r" % (offenders,))

    def test_the_canon_rejects_a_free_form_observation(self):
        """正本の validate が自由型を赤にする（試験の側だけで持たない）。"""
        rows = {("INC-x", 0): {"state": "pending", "investigated": True}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertTrue(
            [p for p in problems if "所見" in p],
            "自由型の所見を正本が咎めない: %r" % (problems,))

    def test_the_canon_rejects_an_observation_missing_a_field(self):
        rows = {("INC-x", 0): {
            "state": "pending",
            "investigated": {"observed_at": "2026-08-16", "claim": "見た"}}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertTrue(
            [p for p in problems if "欄" in p],
            "欠けた欄を正本が咎めない: %r" % (problems,))

    def test_the_canon_rejects_a_missing_date_without_a_reason(self):
        rows = {("INC-x", 0): {
            "state": "pending",
            "investigated": {"observed_at": None, "observed_by": "x",
                             "method": "", "claim": None}}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertTrue(
            [p for p in problems if "観測日" in p],
            "理由なき欠測を正本が咎めない: %r" % (problems,))

    def test_an_absent_field_is_not_an_offence(self):
        """欄が無いこと自体は咎めない（観測していないのは偽の観測ではない）。"""
        rows = {("INC-x", 0): {"state": "pending"}}
        problems = orchestrator._validate_recommendation_status(rows)
        self.assertEqual(
            [p for p in problems if "所見" in p or "観測" in p], [],
            "所見の無い処遇まで咎めている（過剰是正）: %r" % (problems,))
