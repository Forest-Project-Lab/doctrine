# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for R11 (統治の生存性) / R12 (会話知識の捕捉) and the ADR-025/026/027 checks.

Covers:
- gov-heartbeat.py: audit-freshness and cadence-overdue warnings, once-per-session,
  silence outside a governed tree and before first use.
- capture-nudge.py: Stop-time one-shot block when governed docs were edited but no
  record (ADR/DECIDED/WATCH/CHANGE or .session-notes) was touched; loop guards.
- precompact-dump.py: dump instruction envelope.
- review-nudge.py: session flags (edits-/recorded-) written at every Level.
- docs-audit.py new checks: stale_current (ADR-025), source_drift,
  archive_integrity (ADR-027), adr_not_landed, orphan skips archived.
- docs-linter.py: ARCHIVED_LOCATION_MISMATCH (ADR-027).
- policy-guard.py: status:archived immutability outside archive/ (ADR-027).
- inject-contract.py: audit staleness warning, pending session-notes section,
  extended curate/doc-review nudges (R11/R12).
- SKILL.md descriptions are quoted (strict-YAML safety).
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _util  # noqa: E402


def _set_env(case, **kv):
    """Set env vars for a test and restore after."""
    for k, v in kv.items():
        old = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

        def _restore(k=k, old=old):
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        case.addCleanup(_restore)


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _summary_json(root, today):
    return json.dumps({
        "schema": "docs-audit/1", "root": os.path.abspath(root),
        "today": today, "generated_at": today + "T00:00:00Z",
        "totals": {"error": 0, "warn": 0, "advisory": 0},
        "counts_by_check": {}, "top_findings": [], "findings": [],
    })


class LivenessBase(unittest.TestCase):
    def setUp(self):
        self.base = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = os.path.join(self.base, "doctrine_docs")
        os.makedirs(os.path.join(self.root, "_system"), exist_ok=True)
        self.plugin_root = os.path.join(self.base, "plugin-root")
        os.makedirs(os.path.join(self.plugin_root, ".cache"), exist_ok=True)
        _set_env(self, CLAUDE_PLUGIN_ROOT=self.plugin_root,
                 CLAUDE_PROJECT_DIR=self.base)

    def _hb(self, today, sid):
        stdin = {"hook_event_name": "UserPromptSubmit", "session_id": sid}
        return _util.invoke("gov-heartbeat", argv=["--today", today],
                            stdin_obj=stdin)

    def _put_summary(self, today):
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               _summary_json(self.root, today))

    def _put_state(self, text):
        _write(os.path.join(self.root, "_system", ".governance-state"), text)


class TestHeartbeat(LivenessBase):
    def test_fresh_audit_and_recent_cadence_is_silent(self):
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, code = self._hb("2026-07-26", "s1")
        self.assertEqual((out, code), ("", 0))

    def _put_summary_with_trace(self, today, undeclared, next_id,
                                streak=0, unmarked=10):
        obj = json.loads(_summary_json(self.root, today))
        sc = {"traced": 1, "no_code": 0, "undeclared": undeclared}
        if next_id is not None:
            sc["next_undeclared"] = next_id
        obj["trace_coverage"] = {
            "unmarked_files": unmarked, "exempt_files": 0,
            "spec_coverage": sc, "stagnation_streak": streak,
        }
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               json.dumps(obj))

    def test_trace_campaign_prompts_the_next_undeclared_spec(self):
        """紐づけキャンペーン(ADR-065): 未宣言の先頭一件を三つの出口つきで促す。"""
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_summary_with_trace("2026-07-25", undeclared=2,
                                     next_id="SPEC-006")
        out, code = self._hb("2026-07-26", "s-camp1")
        self.assertEqual(code, 0)
        self.assertIn("紐づけ整理", out)
        self.assertIn("SPEC-006", out)
        self.assertIn("残り 2 件", out)
        self.assertIn("コード対応なし", out)
        self.assertIn("exempt", out)

    def test_trace_campaign_mentions_stagnation(self):
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_summary_with_trace("2026-07-25", undeclared=1,
                                     next_id="SPEC-006", streak=5)
        out, _ = self._hb("2026-07-26", "s-camp2")
        self.assertIn("5 回の監査で動いていない", out)

    def test_trace_campaign_rejects_a_malformed_id(self):
        """要約は攻撃者制御になりうる。書式に合わない id は文面に載せない。"""
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_summary_with_trace("2026-07-25", undeclared=1,
                                     next_id="../evil\nSPEC-1")
        out, code = self._hb("2026-07-26", "s-camp3")
        self.assertEqual((out.strip(), code), ("", 0))

    def test_trace_campaign_waits_for_md_migration(self):
        """位相: 体系外 .md の整理が先。移行キャンペーンが出す間は順番を待つ。

        移行キャンペーンの種は要約の所見(stray_document の「未分類」)から導く
        設計(ADR-034)なので、fixture も所見で与える。
        """
        self._put_state("last_cadence_review: 2026-07-20\n")
        obj = json.loads(_summary_json(self.root, "2026-07-25"))
        obj["trace_coverage"] = {
            "unmarked_files": 10, "exempt_files": 0,
            "spec_coverage": {"traced": 1, "no_code": 0, "undeclared": 1,
                              "next_undeclared": "SPEC-006"},
            "stagnation_streak": 0,
        }
        obj["findings"] = [{
            "check": "stray_document", "severity": "advisory", "doc_id": "",
            "path": "notes/old.md", "message": "未分類の体系外 .md", "refs": [],
        }]
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               json.dumps(obj))
        out, _ = self._hb("2026-07-26", "s-camp4")
        self.assertIn("【移行", out, "移行キャンペーンが先に出る")
        self.assertNotIn("紐づけ整理", out)

    def test_version_drift_is_announced_every_session(self):
        """版の切替(ADR-066): 冒頭と今の版が違えば、再起動を促す行が付く。"""
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        _write(os.path.join(self.base, ".claude", ".cache", "hook-stamps"),
               "hook_inject_version: 0.0.1\n")
        out, code = self._hb("2026-07-26", "s-ver1")
        self.assertEqual(code, 0)
        self.assertIn("版の切替", out)
        self.assertIn("新しいセッション", out)

    def test_no_version_drift_without_the_stamp(self):
        """印が無ければ黙る(古い版からの更新直後を騒がせない)。"""
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, _ = self._hb("2026-07-26", "s-ver2")
        self.assertNotIn("版の切替", out)

    def test_version_lag_advises_update_in_a_self_marketplace_repo(self):
        """版の遅れ(ADR-070): 正本の宣言と実行中の版が食い違えば更新を促す。"""
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        here = os.path.dirname(os.path.abspath(_util.__file__))
        with open(os.path.join(here, "..", ".claude-plugin", "plugin.json"),
                  "r", encoding="utf-8-sig") as fh:
            name = json.load(fh)["name"]
        _write(os.path.join(self.base, ".claude-plugin", "marketplace.json"),
               json.dumps({"name": "mkt",
                           "plugins": [{"name": name,
                                        "version": "9999.0.0"}]}))
        out, code = self._hb("2026-07-26", "s-lag1")
        self.assertEqual(code, 0)
        self.assertIn("版の遅れ", out)
        self.assertIn("claude plugin update", out)
        self.assertIn("新しいセッション", out)

    def test_no_version_lag_without_a_manifest(self):
        """マニフェストの無い導入先では黙る(通常の利用者を騒がせない)。"""
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, _ = self._hb("2026-07-26", "s-lag2")
        self.assertNotIn("版の遅れ", out)

    def _put_trace_summary(self, today, undeclared, unmarked, next_id=None):
        """trace_coverage 入りの要約(悉皆の案内の条件を組むための道具)。"""
        obj = json.loads(_summary_json(self.root, today))
        sc = {"traced": 1, "no_code": 0, "undeclared": undeclared}
        if next_id:
            sc["next_undeclared"] = next_id
        obj["trace_coverage"] = {
            "unmarked_files": unmarked, "spec_coverage": sc}
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               json.dumps(obj))

    def test_trace_mode_hint_appears_once_when_specs_are_done(self):
        """悉皆の案内(ADR-072): 未宣言0+印なし残で一度だけ。以後は印で黙る。"""
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 3\n")
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_trace_summary("2026-07-25", undeclared=0, unmarked=5)
        first, code = self._hb("2026-07-26", "s-exh1")
        self.assertEqual(code, 0)
        self.assertIn("悉皆", first)
        self.assertIn("trace_mode", first)
        second, _ = self._hb("2026-07-26", "s-exh2")
        self.assertNotIn("悉皆", second, "案内は一度だけ(印で黙る)")

    def test_no_trace_mode_hint_when_already_on(self):
        """モードを既に入れた体系に案内は出ない。"""
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 3\n")
        _write(os.path.join(self.root, "_system", ".context-config.json"),
               json.dumps({"trace_mode": "exhaustive"}))
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_trace_summary("2026-07-25", undeclared=0, unmarked=5)
        out, _ = self._hb("2026-07-26", "s-exh3")
        self.assertNotIn("悉皆", out)

    def test_no_trace_mode_hint_while_undeclared_remain(self):
        """未宣言が残る間は出ない(位相: 仕様側の悉皆が先)。"""
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 3\n")
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_trace_summary("2026-07-25", undeclared=1, unmarked=5,
                                next_id="SPEC-900")
        out, _ = self._hb("2026-07-26", "s-exh4")
        self.assertNotIn("悉皆", out)

    def test_level_hint_appears_once_for_a_level2_tree_with_audit_record(self):
        """段階の案内(ADR-066): Level 2 + 監査の実績で一度だけ。以後は黙る。"""
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 2\n")
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        first, _ = self._hb("2026-07-26", "s-lv1")
        self.assertIn("Level 3", first)
        self.assertIn("一度だけ", first)
        second, _ = self._hb("2026-07-26", "s-lv2")
        self.assertNotIn("Level 3", second, "案内は一度きり(印で黙る)")

    def test_no_level_hint_without_an_audit_record(self):
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 2\n")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, _ = self._hb("2026-07-26", "s-lv3")
        self.assertNotIn("Level 3", out)

    def test_guard_liveness_gap_is_announced(self):
        """拒否経路の欠落の疑い(ADR-062)を、他が健全でも鼓動が告げる。"""
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        _write(os.path.join(self.base, ".claude", ".cache", "hook-stamps"),
               "hook_docs_linter: 2026-07-26T10:00:00Z\n")
        out, code = self._hb("2026-07-26", "s-gap")
        self.assertEqual(code, 0)
        self.assertIn("拒否経路の疑い", out)
        self.assertIn("ADR-062", out)

    def test_stale_audit_warns(self):
        self._put_summary("2026-07-01")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, code = self._hb("2026-07-26", "s2")
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("前回監査から", ctx)
        self.assertIn("R11", ctx)

    def test_unknown_schema_summary_is_not_read(self):
        """#77: 未知スキーマ(docs-audit/2 等)の要約は読まない。注入と読者間で
        判定を揃える(形が違えば today の解釈も誤りうる)。前回監査なし扱い。"""
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               json.dumps({"schema": "docs-audit/2",
                           "root": os.path.abspath(self.root),
                           "today": "2020-01-01", "totals": {}}))
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, code = self._hb("2026-07-26", "s2b")
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        # 巨大な鮮度超過(2020)を読んでいない=schema で弾いた。要約なし扱いになる。
        self.assertNotIn("2020", ctx)
        self.assertIn("見つからない", ctx)

    def test_missing_audit_with_state_warns(self):
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, _ = self._hb("2026-07-26", "s3")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("前回監査の記録が見つからない", ctx)

    def test_brand_new_tree_is_silent(self):
        # 要約も状態も無い(使い始めの前) → 黙る。SessionStart の案内に譲る。
        out, code = self._hb("2026-07-26", "s4")
        self.assertEqual((out, code), ("", 0))

    def test_cadence_overdue_warns(self):
        self._put_summary("2026-07-26")
        self._put_state("last_cadence_review: 2026-01-01\n")
        out, _ = self._hb("2026-07-26", "s5")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("定例", ctx)
        self.assertIn("last_cadence_review", ctx)

    def test_missing_cadence_record_with_audit_prompts(self):
        self._put_summary("2026-07-26")
        out, _ = self._hb("2026-07-26", "s6")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("実施記録が無い", ctx)

    def test_once_per_session(self):
        self._put_summary("2026-07-01")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out1, _ = self._hb("2026-07-26", "s7")
        out2, _ = self._hb("2026-07-26", "s7")
        self.assertTrue(out1)
        self.assertEqual(out2, "")

    def test_no_tree_is_silent(self):
        empty = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        _set_env(self, CLAUDE_PROJECT_DIR=empty)
        # cwd の退避解決が本物のリポジトリを見つけないよう、cwd も空へ移す
        # (実運用では cwd=プロジェクトであり、この退避は正しい挙動)。
        prev = os.getcwd()
        os.chdir(empty)
        self.addCleanup(os.chdir, prev)
        out, code = self._hb("2026-07-26", "s8")
        self.assertEqual((out, code), ("", 0))


class TestCaptureNudge(LivenessBase):
    def _flags(self):
        # 印はプロジェクトスコープに置く(ADR-075)。${CLAUDE_PLUGIN_ROOT} は版ごとに
        # 別ディレクトリで、更新のたび印が消え、配布実体へも混ざる。
        d = os.path.join(self.base, ".claude", ".cache", "session-flags")
        os.makedirs(d, exist_ok=True)
        return d

    def _stop(self, sid, active=False):
        stdin = {"hook_event_name": "Stop", "session_id": sid,
                 "stop_hook_active": active}
        return _util.invoke("capture-nudge", stdin_obj=stdin)

    def test_edits_without_record_blocks_once(self):
        d = self._flags()
        _write(os.path.join(d, "edits-cap1"), "")
        out1, code = self._stop("cap1")
        self.assertEqual(code, 0)
        resp = json.loads(out1)
        self.assertEqual(resp["decision"], "block")
        self.assertIn("記録", resp["reason"])
        # 二度目は黙る(nudged 印)。
        out2, _ = self._stop("cap1")
        self.assertEqual(out2, "")

    def test_recorded_session_is_silent(self):
        d = self._flags()
        _write(os.path.join(d, "edits-cap2"), "")
        _write(os.path.join(d, "recorded-cap2"), "")
        out, _ = self._stop("cap2")
        self.assertEqual(out, "")

    def test_no_edits_is_silent(self):
        self._flags()
        out, _ = self._stop("cap3")
        self.assertEqual(out, "")

    def test_stop_hook_active_is_silent(self):
        d = self._flags()
        _write(os.path.join(d, "edits-cap4"), "")
        out, _ = self._stop("cap4", active=True)
        self.assertEqual(out, "")


class TestPrecompactDump(unittest.TestCase):
    """退避の指示。統治木は自前で作る(ADR-075)。

    以前は cwd の統治木に頼っていたため、開発木の外(導入されたプラグインの
    複製)で走らせると木が無く、応答の形が変わって error になっていた。
    """

    def _run(self, root):
        cwd = os.getcwd()
        os.chdir(root)
        try:
            return _util.invoke("precompact-dump", stdin_obj={
                "hook_event_name": "PreCompact", "trigger": "auto",
                "cwd": root})
        finally:
            os.chdir(cwd)

    def test_emits_dump_instruction(self):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, "doctrine_docs", "_system"),
                    exist_ok=True)
        out, code = self._run(root)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(resp["hookSpecificOutput"]["hookEventName"], "PreCompact")
        self.assertIn(".session-notes", resp["hookSpecificOutput"]["additionalContext"])

    def test_no_tree_still_answers_without_error(self):
        """統治木が無い土地でも例外を出さない(導入直後・体系外の作業ディレクトリ)。"""
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        _out, code = self._run(root)
        self.assertEqual(code, 0)


class TestReviewNudgeFlags(LivenessBase):
    def _edit(self, path, sid="test-session"):
        stdin = _util.hook_stdin("PostToolUse", tool_name="Edit",
                                 tool_input={"file_path": path})
        stdin["session_id"] = sid
        return _util.invoke("review-nudge", stdin_obj=stdin)

    def test_spec_edit_writes_edits_flag(self):
        p = _util.write_doc(self.root, "model/spec/SPEC-901-x.md", {
            "id": "SPEC-901", "title": "x", "type": "SPEC", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "本文。\n")
        self._edit(p, "rn1")
        d = os.path.join(self.base, ".claude", ".cache", "session-flags")
        self.assertTrue(os.path.isfile(os.path.join(d, "edits-rn1")))
        self.assertFalse(os.path.isfile(os.path.join(d, "recorded-rn1")))

    def test_adr_edit_writes_recorded_flag(self):
        p = _util.write_doc(self.root, "model/decisions/ADR-901-x.md", {
            "id": "ADR-901", "title": "x", "type": "ADR", "domain": "model",
            "status": "accepted", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "本文。\n")
        self._edit(p, "rn2")
        d = os.path.join(self.base, ".claude", ".cache", "session-flags")
        self.assertTrue(os.path.isfile(os.path.join(d, "recorded-rn2")))

    def test_session_notes_write_counts_as_recorded(self):
        notes = os.path.join(self.root, "_system", ".session-notes")
        _write(notes, "- 決定の一文 (出所: 会話, 2026-07-26)\n")
        out, _ = self._edit(notes, "rn3")
        self.assertEqual(out, "")  # ナッジは出ない(印だけ)。
        d = os.path.join(self.base, ".claude", ".cache", "session-flags")
        self.assertTrue(os.path.isfile(os.path.join(d, "recorded-rn3")))


class AuditChecksBase(unittest.TestCase):
    def setUp(self):
        self.base = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = os.path.join(self.base, "doctrine_docs")
        os.makedirs(os.path.join(self.root, "_system"), exist_ok=True)

    def _audit(self):
        out, code = _util.invoke("docs-audit", argv=[
            "--root", self.root, "--json", "--today", "2026-07-26"])
        return json.loads(out), code

    def _codes(self, summary, check):
        return [f for f in summary["findings"] if f["check"] == check]


class TestStaleCurrent(AuditChecksBase):
    def test_old_spec_without_review_by_warns(self):
        _util.write_doc(self.root, "model/spec/SPEC-901-x.md", {
            "id": "SPEC-901", "title": "x", "type": "SPEC", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [], "depends_on": ["REQ-901"],
        }, "[R1]\n## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n")
        _util.write_doc(self.root, "model/REQ-901-x.md", {
            "id": "REQ-901", "title": "x", "type": "REQ", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [],
        }, "本文。\n")
        _util.write_doc(self.root, "model/test/TEST-901-x.md", {
            "id": "TEST-901", "title": "x", "type": "TEST", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [], "depends_on": ["SPEC-901"],
        }, "本文。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "stale_current")
        self.assertTrue(any(f["doc_id"] == "SPEC-901" for f in hits))
        for f in hits:
            self.assertEqual(f["severity"], "warn")

    def test_explicit_review_by_defers_to_review_by_check(self):
        _util.write_doc(self.root, "model/spec/SPEC-902-x.md", {
            "id": "SPEC-902", "title": "x", "type": "SPEC", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [], "review_by": "2027-01-01", "depends_on": ["REQ-902"],
        }, "[R1]\n## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n")
        _util.write_doc(self.root, "model/REQ-902-x.md", {
            "id": "REQ-902", "title": "x", "type": "REQ", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [],
        }, "本文。\n")
        _util.write_doc(self.root, "model/test/TEST-902-x.md", {
            "id": "TEST-902", "title": "x", "type": "TEST", "domain": "model",
            "status": "current", "owner": "a", "updated": "2020-01-01",
            "sources": [], "depends_on": ["SPEC-902"],
        }, "本文。\n")
        summary, _ = self._audit()
        self.assertFalse(
            [f for f in self._codes(summary, "stale_current")
             if f["doc_id"] == "SPEC-902"])


class TestSourceDrift(AuditChecksBase):
    def test_upstream_newer_than_downstream_advises(self):
        _util.write_doc(self.root, "model/REQ-903-x.md", {
            "id": "REQ-903", "title": "x", "type": "REQ", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-20",
            "sources": [],
        }, "本文。\n")
        _util.write_doc(self.root, "model/spec/SPEC-903-x.md", {
            "id": "SPEC-903", "title": "x", "type": "SPEC", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-01",
            "sources": [], "depends_on": ["REQ-903"],
        }, "[R1]\n## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n")
        _util.write_doc(self.root, "model/test/TEST-903-x.md", {
            "id": "TEST-903", "title": "x", "type": "TEST", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-20",
            "sources": [], "depends_on": ["SPEC-903"],
        }, "本文。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "source_drift")
        self.assertTrue(any(f["doc_id"] == "SPEC-903" and "REQ-903" in f["refs"]
                            for f in hits))
        for f in hits:
            self.assertEqual(f["severity"], "advisory")


class TestArchiveIntegrity(AuditChecksBase):
    def test_archived_outside_archive_dir_errors(self):
        _util.write_doc(self.root, "model/research/RESEARCH-901-x.md", {
            "id": "RESEARCH-901", "title": "x", "type": "RESEARCH",
            "domain": "model", "status": "archived", "owner": "a",
            "updated": "2026-07-01", "sources": [], "llm_context": "never",
        }, "本文。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "archive_integrity")
        self.assertTrue(any(f["severity"] == "error" for f in hits))

    def test_archived_inside_archive_dir_is_clean_and_not_orphan(self):
        _util.write_doc(self.root, "model/archive/RESEARCH-902-x.md", {
            "id": "RESEARCH-902", "title": "x", "type": "RESEARCH",
            "domain": "model", "status": "archived", "owner": "a",
            "updated": "2020-01-01", "sources": [], "llm_context": "never",
        }, "本文。\n")
        summary, _ = self._audit()
        self.assertFalse([f for f in self._codes(summary, "archive_integrity")
                          if f["severity"] == "error"])
        # 孤児にも数えない(ADR-027: 倉庫の中身を削除候補へ昇格させない)。
        self.assertFalse([f for f in self._codes(summary, "orphan")
                          if f["doc_id"] == "RESEARCH-902"])

    def test_non_research_without_successor_advises(self):
        _util.write_doc(self.root, "model/archive/SPEC-904-x.md", {
            "id": "SPEC-904", "title": "x", "type": "SPEC", "domain": "model",
            "status": "archived", "owner": "a", "updated": "2026-07-01",
            "sources": [],
        }, "本文。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "archive_integrity")
        self.assertTrue(any(f["severity"] == "advisory" and
                            "superseded_by" in f["message"] for f in hits))


class TestAdrNotLanded(AuditChecksBase):
    def _adr(self, num):
        _util.write_doc(self.root, "model/decisions/ADR-9%02d-x.md" % num, {
            "id": "ADR-9%02d" % num, "title": "x", "type": "ADR",
            "domain": "model", "status": "accepted", "owner": "a",
            "updated": "2026-07-01", "sources": [],
        }, "決定の本文。\n")

    def test_unreferenced_accepted_adr_warns(self):
        self._adr(5)
        summary, _ = self._audit()
        hits = self._codes(summary, "adr_not_landed")
        self.assertTrue(any(f["doc_id"] == "ADR-905" for f in hits))

    def test_adr_cited_from_current_spec_is_landed(self):
        self._adr(6)
        _util.write_doc(self.root, "model/spec/SPEC-905-x.md", {
            "id": "SPEC-905", "title": "x", "type": "SPEC", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-02",
            "sources": [], "depends_on": ["REQ-905"],
        }, "[R1] ADR-906 の決定を実装する。\n"
           "## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n")
        _util.write_doc(self.root, "model/REQ-905-x.md", {
            "id": "REQ-905", "title": "x", "type": "REQ", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-01",
            "sources": [],
        }, "本文。\n")
        _util.write_doc(self.root, "model/test/TEST-905-x.md", {
            "id": "TEST-905", "title": "x", "type": "TEST", "domain": "model",
            "status": "current", "owner": "a", "updated": "2026-07-02",
            "sources": [], "depends_on": ["SPEC-905"],
        }, "本文。\n")
        summary, _ = self._audit()
        self.assertFalse([f for f in self._codes(summary, "adr_not_landed")
                          if f["doc_id"] == "ADR-906"])


class TestExtAnchors(AuditChecksBase):
    def _ext(self, num, body):
        _util.write_doc(self.root, "packaging/external/EXT-9%02d-x.md" % num, {
            "id": "EXT-9%02d" % num, "title": "x", "type": "EXT",
            "domain": "packaging", "status": "current", "owner": "a",
            "updated": "2026-07-26", "sources": [], "review_by": "2027-01-01",
        }, body)

    def test_missing_target_errors(self):
        self._ext(1, "## 期待\n\n- 対象: `no/such/file.md`\n- 検査: exists\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "ext_anchor_broken")
        self.assertTrue(any(f["severity"] == "error" for f in hits))

    def test_existing_target_is_clean(self):
        _write(os.path.join(self.base, "present.md"), "x\n")
        self._ext(2, "## 期待\n\n- 対象: `present.md`\n- 検査: exists\n")
        summary, _ = self._audit()
        self.assertFalse(self._codes(summary, "ext_anchor_broken"))

    def test_review_by_only_anchor_is_not_checked(self):
        self._ext(3, "## 期待\n\n- 対象: `実行環境の仕様(ファイルではない)`\n"
                     "- 検査: review_by のみ\n")
        summary, _ = self._audit()
        self.assertFalse(self._codes(summary, "ext_anchor_broken"))

    def test_anchor_without_target_line_warns(self):
        self._ext(4, "本文だけ。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "ext_anchor_broken")
        self.assertTrue(any(f["severity"] == "warn" for f in hits))


class TestMemoryShadow(AuditChecksBase):
    def _memdir(self):
        cfg = os.path.join(self.base, "cfg")
        munged = os.path.abspath(self.base).replace("\\", "/").replace("/", "-")
        d = os.path.join(cfg, "projects", munged, "memory")
        os.makedirs(d, exist_ok=True)
        _set_env(self, CLAUDE_CONFIG_DIR=cfg)
        return d

    def _seed_doc(self):
        _util.write_doc(self.root, "model/decisions/ADR-950-x.md", {
            "id": "ADR-950", "title": "x", "type": "ADR", "domain": "model",
            "status": "accepted", "owner": "a", "updated": "2026-07-01",
            "sources": [],
        }, "決定。\n")

    def test_memory_referencing_governance_advises(self):
        self._seed_doc()
        d = self._memdir()
        _write(os.path.join(d, "note.md"),
               "---\nname: note\n---\n\nADR-950 は不要になった気がする。\n")
        summary, _ = self._audit()
        hits = self._codes(summary, "memory_shadow")
        self.assertTrue(any("note.md" in f["path"] and "ADR-950" in f["message"]
                            for f in hits))
        for f in hits:
            self.assertEqual(f["severity"], "advisory")

    def test_plain_memory_and_index_are_silent(self):
        self._seed_doc()
        d = self._memdir()
        _write(os.path.join(d, "MEMORY.md"), "- ADR-950 への言及(索引は対象外)\n")
        _write(os.path.join(d, "env.md"), "---\nname: env\n---\n\n端末は bash。\n")
        summary, _ = self._audit()
        self.assertFalse(self._codes(summary, "memory_shadow"))

    def test_no_memory_dir_is_silent(self):
        self._seed_doc()
        _set_env(self, CLAUDE_CONFIG_DIR=os.path.join(self.base, "nocfg"))
        summary, _ = self._audit()
        self.assertFalse(self._codes(summary, "memory_shadow"))


class TestErrorReportPrompt(LivenessBase):
    """不具合の兆候の促し(ADR-074): 記録があれば承認ゲートと感謝つきの手順を
    促し、無ければ黙り、記録ファイルの削除で消える。死活の警告が勝つ。"""

    def _put_errors(self, n=1):
        lines = "".join(
            json.dumps({"ts": "2026-07-26T00:00:00Z", "component": "docs-audit",
                        "error": "ValueError at docs-audit.py:12",
                        "version": "0.6.0"}) + "\n"
            for _ in range(n))
        _write(os.path.join(self.base, ".claude", ".cache",
                            "doctrine-errors.jsonl"), lines)

    def test_journal_prompts_consented_report_with_thanks(self):
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_errors(2)
        out, code = self._hb("2026-07-26", "s-err1")
        self.assertEqual(code, 0)
        self.assertIn("不具合の疑い", out)
        self.assertIn("2 件", out)
        self.assertIn("承認", out)
        self.assertIn("gh issue create --repo Forest-Project-Lab/doctrine", out)
        self.assertIn("決して入れない", out)
        self.assertIn("ありがとうございます", out)
        self.assertIn("任意", out)

    def test_no_journal_is_silent(self):
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        out, _ = self._hb("2026-07-26", "s-err2")
        self.assertEqual(out, "")

    def test_deleting_the_journal_silences(self):
        self._put_summary("2026-07-25")
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_errors()
        out, _ = self._hb("2026-07-26", "s-err3")
        self.assertIn("不具合の疑い", out)
        os.remove(os.path.join(self.base, ".claude", ".cache",
                               "doctrine-errors.jsonl"))
        out, _ = self._hb("2026-07-26", "s-err4")
        self.assertEqual(out, "")

    def test_audit_liveness_beats_the_error_report(self):
        """梯子の優先: 監査の死活(R11)が不具合の促しより重い。"""
        self._put_summary("2026-07-01")   # 鮮度超過
        self._put_state("last_cadence_review: 2026-07-20\n")
        self._put_errors()
        out, _ = self._hb("2026-07-26", "s-err5")
        self.assertIn("前回監査から", out)
        self.assertNotIn("不具合の疑い", out)


class TestMigrationCampaign(LivenessBase):
    def _summary_with_strays(self, n):
        fs = [{"check": "stray_document", "severity": "advisory", "doc_id": "",
               "path": "notes/n%d.md" % i,
               "message": "統治木の外の .md が未分類。docs-curate(external-md-intake)で三分類し…",
               "refs": []} for i in range(n)]
        import json as _j
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"), _j.dumps({
            "schema": "docs-audit/1", "root": os.path.abspath(self.root),
            "today": "2026-07-26", "generated_at": "2026-07-26T00:00:00Z",
            "totals": {"error": 0, "warn": 0, "advisory": n},
            "counts_by_check": {"stray_document": n}, "top_findings": [],
            "findings": fs}))

    def test_migration_drips_one_item(self):
        self._summary_with_strays(3)
        self._put_state("last_cadence_review: 2026-07-25\n")
        _write(os.path.join(self.root, "_system", ".md-intake"), "a.md: 非文書\n")
        out, _ = self._hb("2026-07-26", "mig1")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("【移行 1/4】", ctx)
        self.assertIn("notes/n0.md", ctx)

    def test_no_strays_is_silent(self):
        self._summary_with_strays(0)
        self._put_state("last_cadence_review: 2026-07-25\n")
        out, _ = self._hb("2026-07-26", "mig2")
        self.assertEqual(out, "")

    def test_level2_missing_audit_is_not_flagged(self):
        # Level 2 に SessionEnd の監査は無い(ADR-019)。誤報を出さない。
        _write(os.path.join(self.root, "_system", ".docs-level"), "level: 2\n")
        self._put_state("last_cadence_review: 2026-07-25\n")
        out, code = self._hb("2026-07-26", "lv2a")
        self.assertEqual((out, code), ("", 0))


class TestLinterArchivedLocation(unittest.TestCase):
    def setUp(self):
        self.base = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = os.path.join(self.base, "doctrine_docs")
        os.makedirs(os.path.join(self.root, "_system"), exist_ok=True)

    def _lint(self, path):
        out, code = _util.invoke("docs-linter", argv=[path])
        return out, code

    def test_archived_outside_archive_flags(self):
        p = _util.write_doc(self.root, "model/spec/SPEC-906-x.md", {
            "id": "SPEC-906", "title": "x", "type": "SPEC", "domain": "model",
            "status": "archived", "owner": "a", "updated": "2026-07-01",
            "sources": [],
        }, "本文。\n")
        out, code = self._lint(p)
        self.assertEqual(code, 0)
        self.assertIn("ARCHIVED_LOCATION_MISMATCH", out)

    def test_archived_inside_archive_passes_location(self):
        p = _util.write_doc(self.root, "model/archive/RESEARCH-907-x.md", {
            "id": "RESEARCH-907", "title": "x", "type": "RESEARCH",
            "domain": "model", "status": "archived", "owner": "a",
            "updated": "2026-07-01", "sources": [], "llm_context": "never",
        }, "本文。\n")
        out, _ = self._lint(p)
        self.assertNotIn("ARCHIVED_LOCATION_MISMATCH", out)
        self.assertNotIn("TYPE_LOCATION_MISMATCH", out)


class TestGuardArchivedImmutability(unittest.TestCase):
    def setUp(self):
        self.base = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = os.path.join(self.base, "doctrine_docs")
        os.makedirs(os.path.join(self.root, "_system"), exist_ok=True)

    def test_editing_archived_doc_outside_archive_denied(self):
        p = _util.write_doc(self.root, "model/research/RESEARCH-908-x.md", {
            "id": "RESEARCH-908", "title": "x", "type": "RESEARCH",
            "domain": "model", "status": "archived", "owner": "a",
            "updated": "2026-07-01", "sources": [], "llm_context": "never",
        }, "本文。\n")
        stdin = _util.hook_stdin("PreToolUse", tool_name="Edit", tool_input={
            "file_path": p, "old_string": "本文。", "new_string": "改変。"})
        out, code = _util.invoke("policy-guard", stdin_obj=stdin)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(
            resp["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("archived", resp["hookSpecificOutput"]["permissionDecisionReason"])

    def test_demoting_write_to_archived_is_still_allowed(self):
        # 現行 → archived への遷移そのもの(アーカイブする操作)は不変ガードの対象外。
        p = _util.write_doc(self.root, "model/research/RESEARCH-909-x.md", {
            "id": "RESEARCH-909", "title": "x", "type": "RESEARCH",
            "domain": "model", "status": "current", "owner": "a",
            "updated": "2026-07-01", "sources": [], "llm_context": "never",
        }, "本文。\n")
        new_text = _util.read(p).replace("status: current", "status: archived")
        stdin = _util.hook_stdin("PreToolUse", tool_name="Write", tool_input={
            "file_path": p, "content": new_text})
        out, code = _util.invoke("policy-guard", stdin_obj=stdin)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(
            resp["hookSpecificOutput"]["permissionDecision"], "allow")


class TestInjectLiveness(unittest.TestCase):
    def setUp(self):
        self.base = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.root = os.path.join(self.base, "doctrine_docs")
        os.makedirs(os.path.join(self.root, "_system"), exist_ok=True)
        self.plugin_root = os.path.join(self.base, "plugin-root")
        os.makedirs(os.path.join(self.plugin_root, ".cache"), exist_ok=True)
        _set_env(self, CLAUDE_PLUGIN_ROOT=self.plugin_root,
                 CLAUDE_PROJECT_DIR=self.base)
        _util.write_doc(self.root, "_system/decided-facts.md", {
            "id": "DECIDED-901", "title": "d", "type": "DECIDED",
            "domain": "_system", "status": "current", "owner": "a",
            "updated": "2026-07-01", "sources": [], "review_by": "2027-01-01",
        }, "- 事実。\n")

    def _inject(self, today):
        out, code = _util.invoke(
            "inject-contract",
            argv=["--docs-root", self.root, "--today", today])
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        return ctx, code

    def test_stale_audit_summary_warns(self):
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               _summary_json(self.root, "2026-07-01"))
        ctx, code = self._inject("2026-07-26")
        self.assertEqual(code, 0)
        self.assertIn("日が経っている", ctx)
        self.assertIn("R11", ctx)

    def test_fresh_audit_summary_no_staleness_warning(self):
        _write(os.path.join(self.plugin_root, ".cache", "last-audit.json"),
               _summary_json(self.root, "2026-07-25"))
        ctx, _ = self._inject("2026-07-26")
        self.assertNotIn("日が経っている", ctx)

    def test_pending_session_notes_section(self):
        _write(os.path.join(self.root, "_system", ".session-notes"),
               "- 決定A (出所: 会話, 2026-07-25)\n- 決定B (出所: 会話, 2026-07-25)\n")
        ctx, _ = self._inject("2026-07-26")
        self.assertIn("未選別のセッションメモ", ctx)
        self.assertIn("2 行", ctx)

    def test_curate_nudge_covers_new_checks(self):
        mod = _util.load_script("inject-contract")
        line = mod._curate_nudge({"error": 0}, {"review_by_overrun": 2})
        self.assertIn("doc-review", line)
        line = mod._curate_nudge({"error": 0}, {"stale_current": 3})
        self.assertIn("docs-curate", line)
        line = mod._curate_nudge({"error": 0}, {"adr_not_landed": 1})
        self.assertIn("doc-review", line)
        line = mod._curate_nudge({"error": 0}, {"near_duplicate": 1})
        self.assertIn("定例", line)


class TestSkillDescriptionsQuoted(unittest.TestCase):
    """S11: 全 SKILL.md の description は引用符で囲む(厳格YAMLでの解析失敗を防ぐ)。"""

    def test_all_descriptions_quoted(self):
        skills_dir = os.path.join(_util.PLUGIN_ROOT, "skills")
        found = 0
        for name in sorted(os.listdir(skills_dir)):
            path = os.path.join(skills_dir, name, "SKILL.md")
            if not os.path.isfile(path):
                continue
            found += 1
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("description:"):
                        value = line[len("description:"):].strip()
                        self.assertTrue(
                            value.startswith("'") or value.startswith('"'),
                            "%s: description は引用符で囲む(平文スカラの『: 』は"
                            "厳格YAMLで壊れる)" % name)
                        break
        self.assertEqual(found, 7)


if __name__ == "__main__":
    unittest.main()
