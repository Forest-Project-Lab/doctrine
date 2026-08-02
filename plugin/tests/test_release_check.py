# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util                                            # noqa: E402

# 対象はリポジトリ直下 scripts/ に在り、配布物には複製されない(公式仕様)。
# 導入先では読み込み自体が失敗するため、取得を遅延させ、無ければ skip(ADR-075)。
_SCRIPT = (os.path.join(_util.REPO_ROOT, "scripts", "release-check.py")
           if _util.REPO_ROOT else None)


def _load_module():
    if not _SCRIPT or not os.path.isfile(_SCRIPT):
        return None
    spec = importlib.util.spec_from_file_location("release_check", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = _load_module()


def setUpModule():
    if rc is None:
        raise unittest.SkipTest(
            "scripts/release-check.py が無い(導入されたプラグインの複製)。"
            "この受入は開発木と CI でだけ走る")


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


def _add_views(tmp, as_of="1.2.3", skip=(), break_src=()):
    """公開ビュー3件を刻印つきで置く。skip は刻印なし、break_src は src 欠落。"""
    for rel in rc.PUBLIC_VIEWS:
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path) or tmp, exist_ok=True)
        if rel in skip:
            body = "# %s\n" % rel
        elif rel in break_src:
            body = "# %s\n<!-- doctrine:view as-of=%s date=2026-07-28 -->\n" % (
                rel, as_of)
        else:
            body = ("# %s\n<!-- doctrine:view src=doctrine as-of=%s "
                    "date=2026-07-28 -->\n" % (rel, as_of))
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)


class ViewStampTest(unittest.TestCase):
    """公開ビューの刻印 — as-of と版番号の正本の一致(ADR-073)。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="relcheck-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _make_repo(self.tmp)

    def test_all_stamped_and_matching_is_clean(self):
        _add_views(self.tmp)
        self.assertEqual(rc.check_view_stamps(self.tmp), [])

    def test_missing_stamp_is_violation(self):
        _add_views(self.tmp, skip=("README.md",))
        violations = rc.check_view_stamps(self.tmp)
        self.assertEqual(len(violations), 1)
        self.assertIn("刻印の欠落", violations[0])
        self.assertIn("README.md", violations[0])

    def test_as_of_lag_is_violation(self):
        _add_views(self.tmp, as_of="1.2.2")
        violations = rc.check_view_stamps(self.tmp)
        self.assertEqual(len(violations), len(rc.PUBLIC_VIEWS))
        self.assertTrue(all("刻印の版の遅れ" in v for v in violations))

    def test_unreadable_stamp_is_violation(self):
        _add_views(self.tmp, break_src=("CONTRIBUTING.md",))
        violations = rc.check_view_stamps(self.tmp)
        self.assertEqual(len(violations), 1)
        self.assertIn("刻印が読めない", violations[0])

    def test_missing_view_file_is_violation(self):
        _add_views(self.tmp)
        os.remove(os.path.join(self.tmp, "plugin", "README.md"))
        violations = rc.check_view_stamps(self.tmp)
        self.assertEqual(len(violations), 1)
        self.assertIn("読めない", violations[0])


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


class DistributionHygieneTest(unittest.TestCase):
    """配布物の衛生(ADR-075)。合成木で決定的に凍結する。"""

    def _tree(self, extra_dirs=()):
        tmp = tempfile.mkdtemp(prefix="relcheck-hyg-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "plugin", "scripts"), exist_ok=True)
        for rel in extra_dirs:
            os.makedirs(os.path.join(tmp, "plugin", rel), exist_ok=True)
        return tmp

    def test_clean_tree_has_no_violation(self):
        self.assertEqual(rc.check_distribution_hygiene(self._tree()), [])

    def test_state_directories_are_reported(self):
        for rel in (".cache", ".claude", "scripts/__pycache__"):
            with self.subTest(rel=rel):
                out = rc.check_distribution_hygiene(self._tree([rel]))
                self.assertEqual(1, len(out), out)
                self.assertIn(rel.split("/")[-1], out[0])


class SelfApplicationTest(unittest.TestCase):
    """本リポジトリ自身が門を通ること(自己適用の実走)。"""

    def test_this_repo_passes_version_integrity(self):
        """版の整合と刻印は常に成り立つ(決定的)。

        配布物の衛生はここでは見ない。開発中に道具が置く一時物(py_compile・
        エディタの点検・直に叩いた unittest が生む __pycache__)で揺れるため、
        単体試験の緑をそれに縛ると、誰かが py_compile を叩いた日に全体が
        赤くなる(ADR-075)。衛生そのものは下の合成木の試験が凍結する。
        """
        self.assertEqual(rc.check_version_integrity(_util.REPO_ROOT), [])
        self.assertEqual(rc.check_view_stamps(_util.REPO_ROOT), [])

    def test_this_repo_passes_view_stamps(self):
        """公開ビュー3件の刻印が版番号の正本と一致している(ADR-073)。"""
        self.assertEqual(rc.check_view_stamps(_util.REPO_ROOT), [])

    def test_usage_error_exits_2(self):
        r = subprocess.run([sys.executable, _SCRIPT, "--nonsense"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
