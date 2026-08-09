#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""SessionEnd の口が予算内で返り、走らなかったことが消えないこと(INC-039)。

実測(使い捨て worktree・claude -p・各 3 回):

    遅延 0 秒 → 完了 3/3     遅延 2 秒 → 打ち切り 3/3
    遅延 1 秒 → 完了 3/3     遅延 3 秒 → 打ち切り 3/3
    遅延 9 秒 → 打ち切り 3/3

一方、全件監査の所要は 8.46 / 8.21 / 9.52 秒だった。口に監査を直に置いている限り
必ず打ち切られる。実環境では 5 日・7 セッションにわたって要約が一度も更新されず、
SessionStart は 5 日前の error 0 を「前回監査」として注入し続けていた。

ここで凍結するのは三つ。
1. 口(--detach)が仕事をせずに返ること —— 予算を時間で測らない(WATCH-001 第8項)。
   構造で測る: 監査の本体を呼ばないこと、負債を置くこと、子を切り離すこと。
2. 負債が残ること、そして**要約を書けたときだけ**消えること。
3. 契約注入が負債を告げること —— 暦の閾値(7 日)に届かなくても告げる。
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import _auditcache            # noqa: E402
import importlib.util         # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


docs_audit = _load("docs-audit")
inject = _load("inject-contract")


class DueLedgerTest(unittest.TestCase):
    """負債の印そのもの。置く・読む・消す。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_write_then_read_roundtrip(self):
        _auditcache.write_due("sess-1", proj=self.tmp)
        due = _auditcache.read_due(proj=self.tmp)
        self.assertEqual([t for t, _ in due], ["sess-1"])
        self.assertTrue(due[0][1], "queued_at が空")

    def test_clear_removes_it(self):
        _auditcache.write_due("sess-1", proj=self.tmp)
        self.assertTrue(_auditcache.clear_due("sess-1", proj=self.tmp))
        self.assertEqual(_auditcache.read_due(proj=self.tmp), [])

    def test_missing_directory_reads_empty_without_raising(self):
        self.assertEqual(
            _auditcache.read_due(proj=os.path.join(self.tmp, "nope")), [])

    def test_unreadable_mark_is_kept_not_dropped(self):
        # 「在るが読めない」を「無い」と取り違えない。
        d = _auditcache.due_dir(self.tmp)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "broken.json"), "w", encoding="utf-8") as fh:
            fh.write("{ truncated")
        due = _auditcache.read_due(proj=self.tmp)
        self.assertEqual([t for t, _ in due], ["broken"])
        self.assertIsNone(due[0][1])

    def test_token_is_sanitised_for_the_filename(self):
        # ファイル名による経路の細工を作らない(NONGOAL-001 の注入境界)。
        _auditcache.write_due("../../etc/passwd", proj=self.tmp)
        names = os.listdir(_auditcache.due_dir(self.tmp))
        self.assertEqual(names, ["etcpasswd.json"])

    def test_empty_token_writes_nothing(self):
        self.assertIsNone(_auditcache.write_due("", proj=self.tmp))
        self.assertEqual(_auditcache.read_due(proj=self.tmp), [])


class DetachEntryTest(unittest.TestCase):
    """口は仕事をしない。時間ではなく構造で凍結する。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "doctrine_docs", "_system"))

    def _run_detach(self, popen):
        argv = ["--root-from", self.tmp, "--detach", "--json",
                "--summary-in-project", "--fail-on", "never"]
        saved_popen = subprocess.Popen
        saved_run = docs_audit.run_audit
        called = {"audit": 0}

        def _no_audit(*a, **k):
            called["audit"] += 1
            raise AssertionError("口が監査本体を呼んだ（予算を超える）")

        subprocess.Popen = popen
        docs_audit.run_audit = _no_audit
        try:
            rc = docs_audit.main(argv)
        finally:
            subprocess.Popen = saved_popen
            docs_audit.run_audit = saved_run
        return rc, called

    def test_entry_returns_zero_without_running_the_audit(self):
        seen = {}

        def fake(cmd, **kw):
            seen["cmd"] = cmd
            seen["kw"] = kw
            return None

        rc, called = self._run_detach(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(called["audit"], 0)
        self.assertIn("cmd", seen, "子を起こしていない")

    def test_child_is_detached_and_silenced(self):
        seen = {}

        def fake(cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw
            return None

        self._run_detach(fake)
        kw = seen["kw"]
        self.assertTrue(kw.get("start_new_session"),
                        "切り離していない。ホストがセッション終了で殺す")
        self.assertEqual(kw.get("stdin"), subprocess.DEVNULL)
        self.assertEqual(kw.get("stdout"), subprocess.DEVNULL)
        self.assertEqual(kw.get("stderr"), subprocess.DEVNULL)

    def test_child_argv_drops_detach_and_carries_clear_due(self):
        seen = {}

        def fake(cmd, **kw):
            seen["cmd"] = cmd
            return None

        self._run_detach(fake)
        cmd = seen["cmd"]
        self.assertNotIn("--detach", cmd, "子が無限に自分を起こす")
        self.assertIn("--clear-due", cmd)
        self.assertIn("--root-from", cmd)
        self.assertIn("--summary-in-project", cmd)

    def test_debt_is_left_behind_before_the_child_starts(self):
        def fake(cmd, **kw):
            return None

        self._run_detach(fake)
        self.assertEqual(len(_auditcache.read_due(proj=self.tmp)), 1)

    def test_debt_survives_when_the_child_cannot_be_started(self):
        # 切り離せない環境。監査は走らないが、負債は残り、次のセッションが見る。
        def boom(cmd, **kw):
            raise OSError("no fork here")

        out = io.StringIO()
        saved = sys.stdout
        sys.stdout = out
        try:
            rc, _ = self._run_detach(boom)
        finally:
            sys.stdout = saved
        self.assertEqual(rc, 0, "SessionEnd の口を壊してはいけない")
        self.assertEqual(len(_auditcache.read_due(proj=self.tmp)), 1)
        self.assertIn("切り離せなかった", out.getvalue(),
                      "沈黙して開いた（DECIDED-001 第12項）")


class DueClearingTest(unittest.TestCase):
    """負債は、要約を書けたときだけ消える。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        sysdir = os.path.join(self.tmp, "doctrine_docs", "_system")
        os.makedirs(sysdir)
        with open(os.path.join(sysdir, "decided-facts.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("---\nid: DECIDED-001\ntitle: t\ntype: DECIDED\n"
                     "domain: d\nstatus: accepted\nowner: o\n"
                     "updated: 2026-01-01\nreview_by: 2099-01-01\n"
                     "sources: []\n---\n\n# t\n\n- a\n")

    def _audit(self, token, break_write=False):
        _auditcache.write_due(token, proj=self.tmp)
        argv = ["--root-from", self.tmp, "--json", "--summary-in-project",
                "--fail-on", "never", "--today", "2026-01-02",
                "--clear-due", token]
        saved = docs_audit._atomic_write
        if break_write:
            def boom(path, text):
                raise OSError("read-only")
            docs_audit._atomic_write = boom
        out, err = io.StringIO(), io.StringIO()
        so, se = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            docs_audit.main(argv)
        finally:
            sys.stdout, sys.stderr = so, se
            docs_audit._atomic_write = saved

    def test_successful_audit_clears_the_debt(self):
        self._audit("sess-ok")
        self.assertEqual(_auditcache.read_due(proj=self.tmp), [])

    def test_audit_that_cannot_write_keeps_the_debt(self):
        # 走っただけで消すと、書けなかった実行が負債を帳消しにする。
        self._audit("sess-bad", break_write=True)
        self.assertEqual([t for t, _ in _auditcache.read_due(proj=self.tmp)],
                         ["sess-bad"])


class InjectionReportsDebtTest(unittest.TestCase):
    """契約注入は負債を告げる。暦の閾値に届かなくても告げる。"""

    SUMMARY = {"schema": "docs-audit/1", "today": "2026-08-04",
               "generated_at": "2026-08-04T00:00:00Z",
               "totals": {"error": 0, "warn": 0, "advisory": 0}}

    def test_five_day_old_green_with_debt_is_flagged(self):
        # 暦では 5 日 < 7 日なので従来は無警告だった。負債は一件目から出る。
        lines = inject._render_audit_summary(
            self.SUMMARY, today=__import__("datetime").date(2026, 8, 9),
            due=[("s1", "2026-08-05T00:00:00Z")])
        text = "\n".join(lines)
        self.assertIn("監査の負債 1 件", text)
        self.assertIn("2026-08-05T00:00:00Z", text)
        self.assertTrue(lines[0].startswith("⚠"),
                        "緑より先に但し書きが来ていない")

    def test_no_debt_says_nothing(self):
        lines = inject._render_audit_summary(
            self.SUMMARY, today=__import__("datetime").date(2026, 8, 9), due=[])
        self.assertNotIn("負債", "\n".join(lines))

    def test_debt_is_reported_even_without_a_summary(self):
        lines = inject._render_audit_summary(
            None, due=[("s1", "2026-08-05T00:00:00Z")])
        self.assertIn("監査の負債", "\n".join(lines))

    def test_level_two_does_not_invent_debt(self):
        # Level 2 に SessionEnd の監査は無い(ADR-019)。誤報を出さない。
        lines = inject._render_audit_summary(
            None, docs_level=2, due=[("s1", "2026-08-05T00:00:00Z")])
        self.assertNotIn("負債", "\n".join(lines))

    def test_unreadable_mark_still_counts(self):
        lines = inject._render_audit_summary(self.SUMMARY, due=[("s1", None)])
        self.assertIn("監査の負債 1 件", "\n".join(lines))


class ManifestTest(unittest.TestCase):
    def test_session_end_uses_detach(self):
        path = os.path.join(os.path.dirname(HERE), "hooks", "hooks.json")
        with open(path, encoding="utf-8") as fh:
            cmd = json.load(fh)["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
        self.assertIn("--detach", cmd,
                      "口に監査を直に置くと必ず打ち切られる(INC-039)")


if __name__ == "__main__":
    unittest.main()
