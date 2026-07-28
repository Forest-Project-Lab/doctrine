"""リリース整合の門の受入 (SPEC-027 / TEST-027 / ADR-071)。

対象はリポジトリ直下 scripts/release-check.py(自己適用。配布物に含めない)。
版の整合(CHANGELOG 先頭の版付き節 ⇔ plugin.json)・日付の存在・記録の義務
(--diff-base)・題名 [no-changelog] による明示の免除・前提が読めないときの
終了コード 2 を凍結する。marketplace.json との一致は test_packaging が
強制する(二重定義しない)。
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_REPO, "scripts", "release-check.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("release_check", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load_module()


def _make_repo(tmp, version="1.2.3", changelog=None):
    """plugin.json と CHANGELOG.md を持つ最小の擬似リポジトリを作る。"""
    os.makedirs(os.path.join(tmp, "plugin", ".claude-plugin"), exist_ok=True)
    with open(os.path.join(tmp, "plugin", ".claude-plugin", "plugin.json"),
              "w", encoding="utf-8") as f:
        json.dump({"name": "doctrine", "version": version}, f)
    if changelog is None:
        changelog = (
            "# 変更履歴\n\n## [未リリース]\n\n- 積み中の一行\n\n"
            "## [1.2.3] — 2026-07-28\n\n- 何かの変更\n"
        )
    with open(os.path.join(tmp, "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write(changelog)


class VersionIntegrityTest(unittest.TestCase):
    """版の整合 — 先頭の版付き節の版と日付。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relcheck-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_match_with_date_is_clean(self):
        _make_repo(self.tmp)
        self.assertEqual(rc.check_version_integrity(self.tmp), [])

    def test_unreleased_section_is_skipped(self):
        _make_repo(self.tmp, changelog=(
            "# 変更履歴\n\n## [未リリース]\n\n## [1.2.3] — 2026-07-28\n"))
        self.assertEqual(rc.check_version_integrity(self.tmp), [])

    def test_version_mismatch_is_violation(self):
        _make_repo(self.tmp, version="1.2.4")
        violations = rc.check_version_integrity(self.tmp)
        self.assertEqual(len(violations), 1)
        self.assertIn("版の不整合", violations[0])
        self.assertIn("1.2.3", violations[0])
        self.assertIn("1.2.4", violations[0])

    def test_missing_date_is_violation(self):
        _make_repo(self.tmp, changelog="# 変更履歴\n\n## [1.2.3]\n")
        violations = rc.check_version_integrity(self.tmp)
        self.assertEqual(len(violations), 1)
        self.assertIn("日付の欠落", violations[0])

    def test_hyphen_date_separator_is_accepted(self):
        _make_repo(self.tmp, changelog="# 変更履歴\n\n## [1.2.3] - 2026-07-28\n")
        self.assertEqual(rc.check_version_integrity(self.tmp), [])

    def test_no_versioned_section_is_fatal(self):
        _make_repo(self.tmp, changelog="# 変更履歴\n\n## [未リリース]\n")
        with self.assertRaises(rc.ReleaseCheckError):
            rc.check_version_integrity(self.tmp)

    def test_missing_plugin_json_is_fatal(self):
        _make_repo(self.tmp)
        os.remove(os.path.join(self.tmp, "plugin", ".claude-plugin", "plugin.json"))
        with self.assertRaises(rc.ReleaseCheckError):
            rc.check_version_integrity(self.tmp)

    def test_missing_changelog_is_fatal(self):
        _make_repo(self.tmp)
        os.remove(os.path.join(self.tmp, "CHANGELOG.md"))
        with self.assertRaises(rc.ReleaseCheckError):
            rc.check_version_integrity(self.tmp)


def _git(repo, *args):
    r = subprocess.run(
        ["git", "-C", repo, "-c", "user.email=t@example.com",
         "-c", "user.name=t", "-c", "commit.gpgsign=false"] + list(args),
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("git %s failed: %s" % (args, r.stderr))
    return r.stdout


class RecordDutyTest(unittest.TestCase):
    """記録の義務 — plugin/ に触れる差分は CHANGELOG.md にも触れる。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relcheck-git-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _make_repo(self.tmp)
        _git(self.tmp, "init", "-q", "-b", "main")
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-q", "-m", "base")
        self.base = _git(self.tmp, "rev-parse", "HEAD").strip()

    def _commit_change(self, paths_content, msg="change"):
        for rel, content in paths_content.items():
            path = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-q", "-m", msg)

    def test_plugin_touch_without_changelog_is_violation(self):
        self._commit_change({"plugin/scripts/x.py": "# x\n"})
        violations = rc.check_record_duty(self.tmp, self.base, "")
        self.assertEqual(len(violations), 1)
        self.assertIn("記録の欠落", violations[0])

    def test_plugin_touch_with_changelog_is_clean(self):
        self._commit_change({"plugin/scripts/x.py": "# x\n",
                             "CHANGELOG.md": "- 一行\n"})
        self.assertEqual(rc.check_record_duty(self.tmp, self.base, ""), [])

    def test_non_plugin_touch_needs_no_record(self):
        self._commit_change({"README2.md": "note\n"})
        self.assertEqual(rc.check_record_duty(self.tmp, self.base, ""), [])

    def test_skip_marker_in_title_exempts(self):
        self._commit_change({"plugin/scripts/x.py": "# x\n"})
        self.assertEqual(
            rc.check_record_duty(self.tmp, self.base,
                                 "fix: typo [no-changelog]"), [])

    def test_skip_marker_does_not_exempt_version_integrity(self):
        # 免除は記録の義務だけ。版の不整合は題名に関わらず違反のまま。
        shutil.rmtree(os.path.join(self.tmp, "plugin"))
        _make_repo(self.tmp, version="9.9.9")
        self.assertEqual(len(rc.check_version_integrity(self.tmp)), 1)

    def test_bad_base_ref_is_fatal(self):
        with self.assertRaises(rc.ReleaseCheckError):
            rc.check_record_duty(self.tmp, "0000000000000000000000000000000000000000", "")


class SelfApplicationTest(unittest.TestCase):
    """本リポジトリ自身が門を通ること(自己適用の実走)。"""

    def test_this_repo_passes_version_integrity(self):
        r = subprocess.run([sys.executable, _SCRIPT],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("整合", r.stdout)

    def test_usage_error_exits_2(self):
        r = subprocess.run([sys.executable, _SCRIPT, "--nonsense"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
