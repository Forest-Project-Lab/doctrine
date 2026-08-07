#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""想定の観測器の決定論試験（SDK 不要・通信不要。ADR-144）。

凍結したいこと:
- observation_history は追記だけ（既存のどの欄も書き換えない）。
- --today は必須（実時計を読まない。ADR-094 と同じ規律）。
- --dry-run は登記簿に何も書かない。
- 各観測器は日付と状態語彙を持つ構造化された観測を返す。
- set_verified_by は検証の主体と方式を名指しする文を要す（空文は拒む）。
"""
import calendar
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import observe_assumptions, orchestrator, sdk_lane  # noqa: E402

ASM_IDS = (observe_assumptions.ASM_001, observe_assumptions.ASM_002,
           observe_assumptions.ASM_003, observe_assumptions.ASM_004)


def _row(aid):
    return {"id": aid, "verified_by": None,
            "leading_indicators": [{"observe_where": "w", "abnormal_when": "a"}]}


def _obs(aid, state="PASS"):
    return {"id": aid, "date": "2026-08-07", "state": state, "observed": ["o"]}


def _epoch(day):
    """YYYY-MM-DD → UTC のその日の正午の epoch 秒（実時計を読まない）。"""
    y, m, d = (int(x) for x in day.split("-"))
    return calendar.timegm((y, m, d, 12, 0, 0))


class ObservationHistoryTest(unittest.TestCase):
    def test_apply_appends_and_never_rewrites(self):
        """追記だけ。既存の欄（指標の観測・verified_by）に触れない。"""
        doc = {"assumptions": [_row("ASM-X")]}
        before_indicators = json.dumps(doc["assumptions"][0]["leading_indicators"])
        observe_assumptions.apply_observations(doc, [_obs("ASM-X")])
        observe_assumptions.apply_observations(doc, [_obs("ASM-X", "FAIL")])
        row = doc["assumptions"][0]
        self.assertEqual(len(row["observation_history"]), 2)
        self.assertEqual([e["state"] for e in row["observation_history"]],
                         ["PASS", "FAIL"])
        self.assertEqual(json.dumps(row["leading_indicators"]),
                         before_indicators)
        self.assertIsNone(row["verified_by"])

    def test_history_entry_carries_date_and_observer(self):
        doc = {"assumptions": [_row("ASM-X")]}
        observe_assumptions.apply_observations(doc, [_obs("ASM-X")])
        entry = doc["assumptions"][0]["observation_history"][0]
        self.assertEqual(entry["date"], "2026-08-07")
        self.assertEqual(entry["observed_by"], observe_assumptions.OBSERVED_BY)
        self.assertEqual(entry["observed"], ["o"])

    def test_unmatched_id_is_reported_not_silently_dropped(self):
        doc = {"assumptions": [_row("ASM-X")]}
        applied, unmatched = observe_assumptions.apply_observations(
            doc, [_obs("ASM-NOPE")])
        self.assertEqual(applied, [])
        self.assertEqual(unmatched, ["ASM-NOPE"])

    def test_written_history_passes_the_canon_validator(self):
        """観測器の書く形は、正本の登記簿検査（ADR-126/144）を通ること。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assumptions.json")
            doc = {"assumptions": [_row("ASM-X")]}
            observe_assumptions.apply_observations(doc, [_obs("ASM-X")])
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            self.assertEqual(
                orchestrator._validate_assumptions(path, incident_ids=set()), [])


class CliContractTest(unittest.TestCase):
    def test_today_is_required(self):
        """実時計を読まない。日付の無い観測は組み立ての段階で拒む。"""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                observe_assumptions.main(["--dry-run"])
        self.assertEqual(ctx.exception.code, 2)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assumptions.json")
            original = json.dumps(
                {"assumptions": [_row(a) for a in ASM_IDS]}, ensure_ascii=False)
            with open(path, "w", encoding="utf-8") as f:
                f.write(original)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = observe_assumptions.main(
                    ["--today", "2026-08-07", "--dry-run", "--ledger", path])
            self.assertEqual(code, 0)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), original)
            self.assertIn("dry_run", out.getvalue())

    def test_write_mode_appends_one_entry_per_assumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "assumptions.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"assumptions": [_row(a) for a in ASM_IDS]}, f,
                          ensure_ascii=False)
            with contextlib.redirect_stdout(io.StringIO()):
                code = observe_assumptions.main(
                    ["--today", "2026-08-07", "--ledger", path])
            self.assertEqual(code, 0)
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
            for row in doc["assumptions"]:
                history = row.get("observation_history")
                self.assertEqual(len(history), 1, row["id"])
                self.assertEqual(history[0]["date"], "2026-08-07")
                self.assertIn(history[0]["state"], orchestrator.ASSUMPTION_STATES)
            # 書いた後も正本の登記簿検査を通る（追記が形を壊さない）。
            self.assertEqual(
                orchestrator._validate_assumptions(path, incident_ids=set()), [])

    def test_help_says_who_fills_verified_by(self):
        """--help が『verified_by は独立の評価セッションが埋める』と告げる。"""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit):
                observe_assumptions.main(["--help"])
        self.assertIn("独立の評価セッション", out.getvalue())
        self.assertIn("verified_by", out.getvalue())


class ObserverStructureTest(unittest.TestCase):
    """各観測器は、日付と状態語彙を持つ構造化された観測を返す。"""

    def test_every_observer_returns_a_structured_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            observations = observe_assumptions.observe_all(
                "2026-08-07", project_dir=tmp, home=tmp)
        self.assertEqual([o["id"] for o in observations], list(ASM_IDS))
        for obs in observations:
            self.assertEqual(obs["date"], "2026-08-07", obs["id"])
            self.assertIn(obs["state"], orchestrator.ASSUMPTION_STATES,
                          obs["id"])
            self.assertTrue(obs["observed"], obs["id"])
            for line in obs["observed"]:
                self.assertIsInstance(line, str)

    def test_asm001_missing_summary_is_unknown_not_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = observe_assumptions.observe_asm_001(
                "2026-08-07", project_dir=tmp)
        self.assertEqual(obs["state"], "UNKNOWN")

    def _project_with_sessions(self, tmp, generated_at, session_days):
        cache = os.path.join(tmp, ".claude", ".cache")
        flags = os.path.join(cache, "session-flags")
        os.makedirs(flags, exist_ok=True)
        with open(os.path.join(cache, "last-audit.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"generated_at": generated_at, "checks_run": []}, f)
        for i, day in enumerate(session_days):
            path = os.path.join(flags, "edits-%d" % i)
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
            os.utime(path, (_epoch(day), _epoch(day)))

    def test_asm001_two_newer_sessions_raise_the_indicator(self):
        """連続 2 セッション（N=2。INC-001 推奨#8）で先行指標が立つ。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._project_with_sessions(tmp, "2026-08-04T00:00:00Z",
                                        ["2026-08-05", "2026-08-06"])
            obs = observe_assumptions.observe_asm_001(
                "2026-08-07", project_dir=tmp)
        self.assertEqual(obs["state"], "FAIL")
        self.assertTrue(any("N=2" in line for line in obs["observed"]),
                        obs["observed"])

    def test_asm001_one_newer_session_is_explained_by_the_current_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project_with_sessions(tmp, "2026-08-04T00:00:00Z",
                                        ["2026-08-03", "2026-08-05"])
            obs = observe_assumptions.observe_asm_001(
                "2026-08-07", project_dir=tmp)
        self.assertEqual(obs["state"], "PASS")

    def _project_with_checks(self, tmp, checks_run):
        cache = os.path.join(tmp, ".claude", ".cache")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "last-audit.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"generated_at": "2026-08-04T00:00:00Z",
                       "checks_run": checks_run}, f)

    def test_asm002_set_equality_is_pass_and_mismatch_is_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "fake-audit.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write('AUDIT_CHECKS = ("a", "b")\n')
            self._project_with_checks(tmp, ["b", "a"])
            obs = observe_assumptions.observe_asm_002(
                "2026-08-07", project_dir=tmp, audit_script=script)
            self.assertEqual(obs["state"], "PASS")
            self._project_with_checks(tmp, ["a"])
            obs = observe_assumptions.observe_asm_002(
                "2026-08-07", project_dir=tmp, audit_script=script)
            self.assertEqual(obs["state"], "FAIL")

    def test_asm002_unimportable_checks_are_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._project_with_checks(tmp, ["a"])
            obs = observe_assumptions.observe_asm_002(
                "2026-08-07", project_dir=tmp,
                audit_script=os.path.join(tmp, "no-such-audit.py"))
        self.assertEqual(obs["state"], "UNKNOWN")

    def _home_with_copy(self, tmp, sha, version):
        plugins = os.path.join(tmp, ".claude", "plugins")
        os.makedirs(plugins, exist_ok=True)
        with open(os.path.join(plugins, "installed_plugins.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"version": 2, "plugins": {"doctrine@x": [
                {"gitCommitSha": sha, "version": version}]}}, f)

    def _patch_head(self, value):
        original = observe_assumptions._git_head
        observe_assumptions._git_head = lambda repo: value
        self.addCleanup(setattr, observe_assumptions, "_git_head", original)

    def _repo_with_version(self, tmp, version):
        meta = os.path.join(tmp, "plugin", ".claude-plugin")
        os.makedirs(meta, exist_ok=True)
        with open(os.path.join(meta, "plugin.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"version": version}, f)

    def test_asm003_unreadable_copy_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = observe_assumptions.observe_asm_003(
                "2026-08-07", home=tmp, repo_dir=tmp)
        self.assertEqual(obs["state"], "UNKNOWN")

    def test_asm003_same_sha_is_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._home_with_copy(tmp, "abc123", "0.10.0")
            self._repo_with_version(tmp, "0.10.0")
            self._patch_head("abc123")
            obs = observe_assumptions.observe_asm_003(
                "2026-08-07", home=tmp, repo_dir=tmp)
        self.assertEqual(obs["state"], "PASS")

    def test_asm003_equal_version_with_different_sha_is_fail(self):
        """版番号が動かないまま中身が進む —— ASM-003 の abnormal_when。"""
        with tempfile.TemporaryDirectory() as tmp:
            self._home_with_copy(tmp, "abc123", "0.10.0")
            self._repo_with_version(tmp, "0.10.0")
            self._patch_head("def456")
            obs = observe_assumptions.observe_asm_003(
                "2026-08-07", home=tmp, repo_dir=tmp)
        self.assertEqual(obs["state"], "FAIL")

    def test_asm004_string_matching_branch_is_fail(self):
        """認証判定が文言の部分一致のままなら、想定は破れたまま。"""
        obs = observe_assumptions.observe_asm_004("2026-08-07")
        self.assertEqual(obs["state"], "FAIL")
        self.assertTrue(any("部分一致" in line for line in obs["observed"]),
                        obs["observed"])

    def test_asm004_without_the_branch_is_unknown_not_green(self):
        """分岐が消えても PASS へは倒さない（族の区別は実行時でしか判らない）。"""
        original = sdk_lane._AUTH_MARKERS
        sdk_lane._AUTH_MARKERS = ()
        try:
            obs = observe_assumptions.observe_asm_004("2026-08-07")
        finally:
            sdk_lane._AUTH_MARKERS = original
        self.assertEqual(obs["state"], "UNKNOWN")


class SetVerifiedByTest(unittest.TestCase):
    def test_empty_text_is_rejected(self):
        """検証の主体と方式を名指ししない verified_by は書けない。"""
        doc = {"assumptions": [_row("ASM-X")]}
        for text in ("", "   ", None):
            with self.assertRaises(ValueError):
                observe_assumptions.set_verified_by(doc, "ASM-X", text)
        self.assertIsNone(doc["assumptions"][0]["verified_by"])

    def test_mechanism_naming_text_is_written(self):
        doc = {"assumptions": [_row("ASM-X")]}
        row = observe_assumptions.set_verified_by(
            doc, "ASM-X",
            "独立の評価セッション 2026-08-07 が checks_run の照合を再実施")
        self.assertIn("再実施", row["verified_by"])
        self.assertIs(row, doc["assumptions"][0])

    def test_unknown_assumption_raises(self):
        with self.assertRaises(KeyError):
            observe_assumptions.set_verified_by(
                {"assumptions": []}, "ASM-X", "text")


if __name__ == "__main__":
    unittest.main()
