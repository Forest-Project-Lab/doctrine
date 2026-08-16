#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""観測器は監査の負債の印を読む（INC-001 推奨#7）。

推奨は「終端は起きたが監査は走っていないセッションを検出する照合を台帳側に
追加する」と言う。**その直接の証拠は既に在る** —— INC-039 の是正が入れた
負債の印は、まさに「SessionEnd は発火したが監査が完走しなかった」を
ファイルの実在として残す（`_auditcache.write_due`/`read_due`）。

ところが `observe_asm_001` はそれを読んでいなかった。読んでいたのは
last-audit.json の刻印・hook-stamps・`session-flags/edits-*` の三つで、
**編集の無いセッションは検出外**であり、しかも「終端は起きたか」を
編集の有無から推し量っていた。負債の印は推し量りではなく直接の記録である。

INC-039 は書き手（印を置く）と配布側の読み手（SessionStart の警告）を同時に
入れたが、**保証レーンの観測器は読む段を持たないままだった** ——
運転手順 §2 の「走らせ手を足すときは正本が読む段も同時に足す」の族
（INC-012・INC-015・INC-048）が、レーンの側で再演していた。

**印の在処を二重定義しない。**置き場の正本は `_auditcache.due_dir` であり、
観測器が組む道がそれと一致することを下の試験が機械で確かめる。
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import observe_assumptions  # noqa: E402


def _project_with(cache_files=None, due_tokens=()):
    """last-audit.json と負債の印を持つ使い捨てのプロジェクトを作る。"""
    proj = tempfile.mkdtemp()
    cache = os.path.join(proj, ".claude", ".cache")
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, "last-audit.json"), "w", encoding="utf-8") as fh:
        json.dump(cache_files or {"generated_at": "2026-08-16T00:00:00Z"}, fh)
    if due_tokens:
        due = os.path.join(cache, "audit-due")
        os.makedirs(due, exist_ok=True)
        for token in due_tokens:
            with open(os.path.join(due, token + ".json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"token": token, "queued_at": "2026-08-16T00:00:00Z"}, fh)
    return proj


class ObserverReadsTheDebtTest(unittest.TestCase):
    def test_the_observation_names_the_debt(self):
        proj = _project_with(due_tokens=("run-a", "run-b"))
        out = observe_assumptions.observe_asm_001("2026-08-16", project_dir=proj)
        joined = "・".join(out["observed"])
        self.assertIn("負債", joined,
                      "観測に負債の印が現れない（INC-039 の証拠を読んでいない）")
        self.assertIn("2", joined, "負債の件数が観測に出ていない")

    def test_debt_alone_makes_the_observation_fail(self):
        """編集が無くても、負債が在れば先行指標は立つ。

        従来は `session-flags/edits-*` の数だけで判じており、**編集の無い
        セッションは検出外**だった。負債の印は編集の有無に依らない。
        """
        proj = _project_with(due_tokens=("run-a",))
        out = observe_assumptions.observe_asm_001("2026-08-16", project_dir=proj)
        self.assertEqual(out["state"], "FAIL",
                         "負債が在るのに先行指標が立たない: %r" % (out["observed"],))

    def test_no_debt_does_not_invent_one(self):
        """負債が無いときに立てない（過剰是正の歯止め）。"""
        proj = _project_with()
        out = observe_assumptions.observe_asm_001("2026-08-16", project_dir=proj)
        self.assertEqual(out["state"], "PASS", out["observed"])

    def test_an_unreadable_mark_still_counts(self):
        """読めない印を「無い」と読み替えない（read_due と同じ規律）。"""
        proj = _project_with()
        due = os.path.join(proj, ".claude", ".cache", "audit-due")
        os.makedirs(due, exist_ok=True)
        with open(os.path.join(due, "broken.json"), "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        out = observe_assumptions.observe_asm_001("2026-08-16", project_dir=proj)
        self.assertEqual(out["state"], "FAIL",
                         "読めない印を無かったことにした: %r" % (out["observed"],))

    def test_the_directory_matches_the_canonical_one(self):
        """印の在処を二重定義しない —— 正本は `_auditcache.due_dir`。

        観測器が組む道が正本とずれた日にここが赤くなる。ずれたまま黙ると、
        観測器は永遠に「負債 0 件」を報せ続ける（無いのではなく見ていない）。
        """
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "plugin", "scripts"))
        import _auditcache                                   # noqa: E402
        proj = tempfile.mkdtemp()
        self.assertEqual(
            os.path.normpath(observe_assumptions.audit_due_dir(proj)),
            os.path.normpath(_auditcache.due_dir(proj)),
            "観測器の見る場所と、印を置く場所が食い違っている")
