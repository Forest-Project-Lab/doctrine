#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
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

    def test_value_stamp_roundtrips_via_raw_reader(self):
        """値付きの印(ADR-066)。時刻の読み手には混ざらず、生の読み手で読める。"""
        A.write_stamp("hook_inject_version", value="0.4.0", proj=self.proj)
        raw = A.read_stamp_values(self.proj)
        self.assertEqual(raw.get("hook_inject_version"), "0.4.0")
        self.assertNotIn("hook_inject_version", A.read_stamps(self.proj),
                         "時刻でない値は時刻の読み手に混ざらない")

    def test_value_with_whitespace_is_not_written(self):
        A.write_stamp("bad_key", value="has space", proj=self.proj)
        self.assertNotIn("bad_key", A.read_stamp_values(self.proj),
                         "状態行の文法に収まらない値は書かない")

    def test_plugin_version_matches_the_packaged_manifest(self):
        import json as _json
        here = os.path.dirname(os.path.abspath(_util.__file__))
        manifest = os.path.join(here, "..", ".claude-plugin", "plugin.json")
        with open(manifest, "r", encoding="utf-8-sig") as fh:
            expected = _json.load(fh)["version"]
        self.assertEqual(A.plugin_version(), expected)

    def test_version_drift_detects_a_mid_session_switch(self):
        gap = A.version_drift({"hook_inject_version": "0.0.1"}, current="0.4.0")
        self.assertIsNotNone(gap)
        self.assertIn("0.0.1", gap)
        self.assertIn("0.4.0", gap)
        self.assertIn("新しいセッション", gap)

    def test_version_drift_is_silent_when_equal_or_unknown(self):
        self.assertIsNone(A.version_drift(
            {"hook_inject_version": "0.4.0"}, current="0.4.0"))
        self.assertIsNone(A.version_drift({}, current="0.4.0"),
                          "印が無ければ判じない(前方寛容)")
        self.assertIsNone(A.version_drift(
            {"hook_inject_version": "0.4.0"}, current=""),
            "今の版が読めなければ判じない")

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


class VersionLagTest(unittest.TestCase):
    """導入済みの複製の遅れの判定(ADR-070)。

    照合が成立するのは、プロジェクト自身がマーケットプレイスの正本である
    (自己適用の)ときだけ。マニフェストを持たない導入先では黙る。正本の版は
    項目の source が指す先の plugin.json を優先し、項目の version は退避先。
    """

    def setUp(self):
        self.proj = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)
        here = os.path.dirname(os.path.abspath(_util.__file__))
        with open(os.path.join(here, "..", ".claude-plugin", "plugin.json"),
                  "r", encoding="utf-8-sig") as fh:
            self.name = json.load(fh)["name"]

    def _manifest(self, entry, mkt="mkt"):
        d = os.path.join(self.proj, ".claude-plugin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "marketplace.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"name": mkt, "plugins": [entry]}, fh)

    def _source_plugin(self, version):
        d = os.path.join(self.proj, "plugin", ".claude-plugin")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": self.name, "version": version}, fh)

    def test_silent_without_a_manifest(self):
        self.assertIsNone(A.version_lag(proj=self.proj, current="0.4.0"),
                          "マニフェストの無い導入先では黙る")

    def test_silent_when_versions_agree(self):
        self._manifest({"name": self.name, "version": "0.4.0"})
        self.assertIsNone(A.version_lag(proj=self.proj, current="0.4.0"))

    def test_advises_update_on_mismatch(self):
        self._manifest({"name": self.name, "version": "0.5.0"})
        msg = A.version_lag(proj=self.proj, current="0.4.0")
        self.assertIsNotNone(msg)
        self.assertIn("0.4.0", msg)
        self.assertIn("0.5.0", msg)
        self.assertIn("claude plugin update %s@mkt" % self.name, msg)
        self.assertIn("新しいセッション", msg)

    def test_source_manifest_wins_over_entry_version(self):
        self._source_plugin("0.4.0")
        self._manifest({"name": self.name, "version": "9.9.9",
                        "source": "./plugin"})
        self.assertIsNone(A.version_lag(proj=self.proj, current="0.4.0"),
                          "正本は source の plugin.json(項目の version は退避先)")

    def test_falls_back_to_entry_version_when_source_unreadable(self):
        self._manifest({"name": self.name, "version": "0.5.0",
                        "source": "./no-such-dir"})
        msg = A.version_lag(proj=self.proj, current="0.4.0")
        self.assertIsNotNone(msg)
        self.assertIn("0.5.0", msg)

    def test_silent_for_a_foreign_plugin_name(self):
        self._manifest({"name": "someone-else", "version": "9.9.9"})
        self.assertIsNone(A.version_lag(proj=self.proj, current="0.4.0"),
                          "同名の項目が無ければ判じない")


class ErrorJournalTest(unittest.TestCase):
    """エラージャーナル(ADR-074): 許可制・上限・決して例外を投げない。"""

    def setUp(self):
        self.proj = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)

    def test_records_only_whitelisted_fields(self):
        """例外の自由文(統治対象のパスが混入しうる)は決して写さない。"""
        try:
            raise ValueError("secret: /home/user/repo/SPEC-999.md の内容")
        except ValueError as exc:
            A.record_error("docs-audit", exc, proj=self.proj)
        entries = A.read_errors(proj=self.proj)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(sorted(e.keys()),
                         ["component", "error", "ts", "version"])
        self.assertEqual(e["component"], "docs-audit")
        self.assertTrue(e["error"].startswith("ValueError"), e)
        raw = open(A.errors_path(self.proj), encoding="utf-8").read()
        self.assertNotIn("secret", raw)
        self.assertNotIn("SPEC-999", raw)

    def test_location_is_plugin_internal_basename_only(self):
        """発生位置は plugin 内フレームの基底名:行だけ(このテストのパスは載らない)。"""
        try:
            A._parse_ts(object())   # コア内で TypeError にならず None — 実際に投げさせる
            raise RuntimeError("x")
        except Exception as exc:
            A.record_error("t", exc, proj=self.proj)
        e = A.read_errors(proj=self.proj)[0]
        self.assertNotIn("test_auditcache", e["error"])

    def test_cap_keeps_the_newest_20(self):
        for i in range(25):
            A.record_error("c%d" % i, ValueError(), proj=self.proj)
        entries = A.read_errors(proj=self.proj)
        self.assertEqual(len(entries), 20)
        self.assertEqual(entries[-1]["component"], "c24")
        self.assertEqual(entries[0]["component"], "c5")

    def test_read_missing_is_empty(self):
        self.assertEqual(A.read_errors(proj=self.proj), [])

    def test_unreadable_lines_are_skipped(self):
        path = A.errors_path(self.proj)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("not json\n{\"component\": \"ok\"}\n[1,2]\n")
        entries = A.read_errors(proj=self.proj)
        self.assertEqual([e.get("component") for e in entries], ["ok"])

    def test_record_never_raises(self):
        """書けない置き場でも黙って諦める(フックの本務を妨げない)。"""
        A.record_error("t", ValueError(), proj="/nonexistent/readonly")


if __name__ == "__main__":
    unittest.main()


class AuditWriteGapTest(unittest.TestCase):
    """監査の走った証跡と要約の食い違い(ADR-119)。

    INC-001 では監査の要約が 8 日更新されず、鮮度の警告は出たが『走らなかった』と
    『走ったが書けなかった』を区別できなかった。区別の材料は、監査自身の発火の印と
    要約の日付の対にある(ADR-062 と同じ形の対の比較。印の不在からは何も言わない)。
    """

    def _ts(self, s):
        return datetime.datetime.strptime(
            s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

    def test_silent_without_an_audit_stamp(self):
        """印が無ければ判じない(前方寛容。ADR-062 と同じ規律)。"""
        self.assertIsNone(A.audit_write_gap({}, {"today": "2026-07-28"}))
        self.assertIsNone(A.audit_write_gap(None, {"today": "2026-07-28"}))

    def test_gap_when_the_write_flag_says_failed(self):
        gap = A.audit_write_gap(
            {"hook_session_end_audit": self._ts("2026-08-04T10:00:00Z")},
            {"today": "2026-08-04"},
            write_ok=False)
        self.assertIsNotNone(gap)
        self.assertIn("書け", gap)

    def test_gap_when_the_stamp_is_newer_than_the_summary(self):
        """走った証跡が要約より新しい = 走ったが要約が更新されていない。"""
        gap = A.audit_write_gap(
            {"hook_session_end_audit": self._ts("2026-08-04T10:00:00Z")},
            {"today": "2026-07-28"})
        self.assertIsNotNone(gap)
        self.assertIn("2026-07-28", gap)

    def test_no_gap_when_the_summary_keeps_up(self):
        self.assertIsNone(A.audit_write_gap(
            {"hook_session_end_audit": self._ts("2026-08-04T10:00:00Z")},
            {"today": "2026-08-04"}))

    def test_no_gap_without_a_summary(self):
        """要約が一度も無い状態は別の警告(鮮度側)が扱う。ここでは黙る。"""
        self.assertIsNone(A.audit_write_gap(
            {"hook_session_end_audit": self._ts("2026-08-04T10:00:00Z")}, None))

    def test_broken_summary_date_is_silent(self):
        self.assertIsNone(A.audit_write_gap(
            {"hook_session_end_audit": self._ts("2026-08-04T10:00:00Z")},
            {"today": "きのう"}))
