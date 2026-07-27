#!/usr/bin/env python3
"""_auditcache — 前回監査の要約を読む共有コアの単体試験(ADR-053)。

凍らせる不変条件は二つ。

1. 世代の照合: 統治木を消して同じ場所に作り直したとき、前の世代の要約を
   新しい木の健全さとして読ませない。root は同じ絶対パスなので一致して
   しまうため、`initialized` の日で世代を判じる。
2. 読み手をまたいだ一致: 注入(inject-contract)と鼓動(gov-heartbeat)が同じ
   関数を呼び、「どの要約を読むか」の答えが一つになる。条件を満たさない
   候補は、そこで止まらず次の候補へ進む。

いずれも、実測(導入・再導入シナリオ)で見つけた欠陥の回帰ガードである。
"""
import datetime
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

A = _util.load_core("_auditcache")

TODAY = datetime.date(2026, 7, 27)


def _summary(root, day="2026-07-27", schema="docs-audit/1", error=0):
    return {
        "schema": schema, "root": os.path.abspath(root),
        "today": day, "generated_at": day + "T00:00:00Z",
        "totals": {"error": error, "warn": 0, "advisory": 0},
        "counts_by_check": {}, "top_findings": [],
    }


class CacheBase(unittest.TestCase):
    def setUp(self):
        self.root = _util.make_repo({})
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.docs = os.path.join(self.root, "doctrine_docs")
        os.makedirs(os.path.join(self.docs, "_system"), exist_ok=True)
        self._env = {}
        for k in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT"):
            self._env[k] = os.environ.get(k)
        os.environ["CLAUDE_PROJECT_DIR"] = self.root
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def put_project_cache(self, obj):
        p = os.path.join(self.root, ".claude", ".cache", "last-audit.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def put_plugin_cache(self, obj):
        plug = os.path.join(self.root, "_plugin")
        p = os.path.join(plug, ".cache", "last-audit.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.environ["CLAUDE_PLUGIN_ROOT"] = plug

    def set_state(self, text):
        with open(os.path.join(self.docs, "_system", ".governance-state"),
                  "w", encoding="utf-8") as fh:
            fh.write(text)


class ReinstallGenerationTest(CacheBase):
    """世代の照合(ADR-053 決定 4)。"""

    def test_summary_older_than_initialized_is_discarded(self):
        """作り直した木に、前の世代の『error 0』を引き継がせない。

        実測で見つけた欠陥: 木を消して同じ場所に作り直すと root が一致し、
        一度も監査していない木へ健全信号が注入され、鼓動も黙った。
        """
        self.set_state("initialized: 2026-07-27\nlast_cadence_review: 2026-07-27\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-24"))
        self.assertIsNone(A.load(self.docs))

    def test_summary_on_the_same_day_is_kept(self):
        """初期化と同じ日の要約は捨てない(通常の初日: 初期化 → 監査)。

        これを捨てると、導入初日に監査を走らせても永久に『前回監査なし』に
        なる。厳密に古いものだけを捨てる。
        """
        self.set_state("initialized: 2026-07-27\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-27"))
        self.assertIsNotNone(A.load(self.docs))

    def test_summary_newer_than_initialized_is_kept(self):
        self.set_state("initialized: 2026-07-01\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-24"))
        self.assertIsNotNone(A.load(self.docs))

    def test_tree_without_marker_keeps_old_behaviour(self):
        """印を持たない木(この決定より前に作られた木)では判じない。前方寛容。"""
        self.set_state("last_cadence_review: 2026-07-01\n")
        self.put_project_cache(_summary(self.docs, day="2026-01-01"))
        self.assertIsNotNone(A.load(self.docs))

    def test_unparsable_initialized_does_not_discard(self):
        """印の日付が壊れていても、要約を捨てない(判じる材料が無い)。"""
        self.set_state("initialized: not-a-date\n")
        self.put_project_cache(_summary(self.docs, day="2026-01-01"))
        self.assertIsNotNone(A.load(self.docs))

    def test_full_width_colon_is_tolerated(self):
        """状態ファイルの全角コロンを、鼓動と同じ寛容度で読む(ADR-042)。"""
        self.set_state("initialized： 2026-07-27\n")
        self.assertEqual(A.initialized_date(self.docs),
                         datetime.date(2026, 7, 27))


class MarkerPresenceTest(CacheBase):
    """導入直後の判定は印の有無で行う(日付の可否は問わない。ADR-041 を壊さない)。"""

    def test_marker_present_even_when_date_is_broken(self):
        self.set_state("initialized: ????\n")
        self.assertTrue(A.has_initialized_marker(self.docs))
        self.assertIsNone(A.initialized_date(self.docs))

    def test_no_marker(self):
        self.set_state("last_cadence_review: 2026-07-01\n")
        self.assertFalse(A.has_initialized_marker(self.docs))

    def test_missing_state_file_never_raises(self):
        self.assertFalse(A.has_initialized_marker(self.docs))
        self.assertIsNone(A.initialized_date(self.docs))
        self.assertIsNone(A.initialized_date(None))


class SkipAndContinueTest(CacheBase):
    """条件を満たさない候補では止まらず、次の候補へ進む(ADR-053 決定)。"""

    def test_unknown_schema_first_does_not_hide_valid_later(self):
        """先頭に未知スキーマがあっても、後ろの正しい要約に届く。

        以前は注入だけがここで止まり、鼓動は進んだ(読み手ごとに別の答え)。
        """
        self.put_project_cache(_summary(self.docs, schema="docs-audit/2"))
        self.put_plugin_cache(_summary(self.docs, day="2026-07-26"))
        got = A.load(self.docs)
        self.assertIsNotNone(got)
        self.assertEqual(got["today"], "2026-07-26")

    def test_foreign_root_first_does_not_hide_valid_later(self):
        self.put_project_cache(_summary("/somewhere/else/doctrine_docs"))
        self.put_plugin_cache(_summary(self.docs, day="2026-07-26"))
        got = A.load(self.docs)
        self.assertIsNotNone(got)
        self.assertEqual(got["today"], "2026-07-26")

    def test_previous_generation_first_does_not_hide_valid_later(self):
        self.set_state("initialized: 2026-07-20\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-01"))
        self.put_plugin_cache(_summary(self.docs, day="2026-07-26"))
        got = A.load(self.docs)
        self.assertIsNotNone(got)
        self.assertEqual(got["today"], "2026-07-26")

    def test_corrupt_json_first_does_not_hide_valid_later(self):
        p = os.path.join(self.root, ".claude", ".cache", "last-audit.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{ これは JSON ではない")
        self.put_plugin_cache(_summary(self.docs, day="2026-07-26"))
        self.assertIsNotNone(A.load(self.docs))

    def test_project_scope_wins_over_plugin_root(self):
        """候補順は据え置き(ADR-037): プロジェクトスコープが先。"""
        self.put_project_cache(_summary(self.docs, day="2026-07-27"))
        self.put_plugin_cache(_summary(self.docs, day="2026-07-01"))
        self.assertEqual(A.load(self.docs)["today"], "2026-07-27")


class RootMatchingTest(CacheBase):
    def test_relative_root_is_rejected(self):
        s = _summary(self.docs)
        s["root"] = "doctrine_docs"
        self.put_project_cache(s)
        self.assertIsNone(A.load(self.docs))

    def test_missing_root_is_rejected(self):
        s = _summary(self.docs)
        del s["root"]
        self.put_project_cache(s)
        self.assertIsNone(A.load(self.docs))

    def test_non_dict_payload_is_rejected(self):
        self.put_project_cache(["not", "a", "dict"])
        self.assertIsNone(A.load(self.docs))


class ReaderAgreementTest(CacheBase):
    """注入と鼓動が同じ答えを返す(ADR-053 の中核の不変条件)。"""

    def _both(self):
        inject = _util.load_core("inject-contract")
        heartbeat = _util.load_core("gov-heartbeat")
        return (inject._load_audit_summary(self.docs),
                heartbeat._audit_summary(self.docs))

    def test_agree_on_previous_generation(self):
        self.set_state("initialized: 2026-07-27\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-24"))
        a, b = self._both()
        self.assertEqual(a, b)
        self.assertIsNone(a)

    def test_agree_when_unknown_schema_precedes_valid(self):
        self.put_project_cache(_summary(self.docs, schema="docs-audit/2"))
        self.put_plugin_cache(_summary(self.docs, day="2026-07-26"))
        a, b = self._both()
        self.assertEqual(a, b)
        self.assertIsNotNone(a)

    def test_agree_on_healthy_current_summary(self):
        self.set_state("initialized: 2026-07-01\n")
        self.put_project_cache(_summary(self.docs, day="2026-07-27"))
        a, b = self._both()
        self.assertEqual(a, b)
        self.assertIsNotNone(a)


class HookStampsTest(unittest.TestCase):
    """フックの発火の印と、拒否経路の欠落の判定(ADR-062)。

    判定はこの共有コアに一度だけ在る(鼓動と監査が同じ答えを得る。ADR-053 と
    同じ原理)。印が無ければ判じない(前方寛容)。
    """

    def setUp(self):
        self.proj = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)

    def _ts(self, s):
        return datetime.datetime.strptime(
            s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

    def test_write_and_read_roundtrip(self):
        now = self._ts("2026-07-27T10:00:00Z")
        A.write_stamp("hook_docs_linter", now=now, proj=self.proj)
        stamps = A.read_stamps(self.proj)
        self.assertEqual(stamps.get("hook_docs_linter"), now)

    def test_upsert_keeps_unknown_lines_and_overwrites_the_key(self):
        path = A.stamps_path(self.proj)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("hook_docs_linter: 2026-07-27T09:00:00Z\n"
                     "future_key: keep-me\n"
                     "壊れた行 まるごと\n")
        A.write_stamp("hook_docs_linter",
                      now=self._ts("2026-07-27T10:00:00Z"), proj=self.proj)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("hook_docs_linter: 2026-07-27T10:00:00Z", text)
        self.assertIn("future_key: keep-me", text, "知らない鍵の行を消さない")
        self.assertIn("壊れた行", text, "読めない行も消さない(ADR-042 の寛容)")

    def test_gap_is_none_without_a_linter_stamp(self):
        self.assertIsNone(A.liveness_gap({}))
        self.assertIsNone(A.liveness_gap(
            {"hook_policy_guard_pre": self._ts("2026-07-27T10:00:00Z")}))

    def test_gap_when_guard_stamp_is_missing(self):
        gap = A.liveness_gap(
            {"hook_docs_linter": self._ts("2026-07-27T10:00:00Z")})
        self.assertIsNotNone(gap)
        self.assertIn("ガード", gap)

    def test_gap_when_guard_is_older_than_the_skew(self):
        gap = A.liveness_gap({
            "hook_docs_linter": self._ts("2026-07-27T10:10:00Z"),
            "hook_policy_guard_pre": self._ts("2026-07-27T10:00:00Z"),
        })
        self.assertIsNotNone(gap)

    def test_no_gap_for_a_fresh_pair(self):
        self.assertIsNone(A.liveness_gap({
            "hook_docs_linter": self._ts("2026-07-27T10:00:30Z"),
            "hook_policy_guard_pre": self._ts("2026-07-27T10:00:00Z"),
        }))

    def test_writers_leave_stamps_via_the_hook_entrypoints(self):
        """統合: リンタとガードの入口が印を残す(ADR-062 の書き手)。"""
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.proj
        self.addCleanup(
            lambda: (os.environ.__setitem__("CLAUDE_PROJECT_DIR", old)
                     if old is not None
                     else os.environ.pop("CLAUDE_PROJECT_DIR", None)))
        target = os.path.join(self.proj, "note.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("x\n")
        _util.invoke("docs-linter", stdin_obj={
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": target}})
        _util.invoke("policy-guard", stdin_obj={
            "hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": target, "old_string": "x",
                           "new_string": "y"}})
        stamps = A.read_stamps(self.proj)
        self.assertIn("hook_docs_linter", stamps)
        self.assertIn("hook_policy_guard_pre", stamps)


if __name__ == "__main__":
    unittest.main()
