#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""フックの境界は沈黙して開かない（DECIDED-001 第12項・WATCH-001 第9項。INC-032）。

独立再監査 2026-08-09 が三つの経路を実測した。

1. `--root-from ""`（`CLAUDE_PROJECT_DIR` が未設定・空のときの展開）を偽と見て
   素通りし、`walkup_docs_root(os.getcwd())` で見つけた木を**勝手に監査した**。
   告げられていない木を、告げられていないまま読む。
2. SessionEnd の配線を空の変数で展開すると `--summary-out` が
   `/.claude/.cache/last-audit.json`（ファイルシステムの根）になる。
3. 相対の値（`CLAUDE_PROJECT_DIR=sub`）で走らせると、印の置き場が作業ディレクトリ
   からの相対になり、**リポジトリの作業木の中へ実際に `sub/.claude/.cache/` が
   生成された**。WATCH-001 第9項は置き場を `${CLAUDE_PROJECT_DIR}/.claude/.cache`
   に限っている。

空白入りの値は配線が引用しているので安全である。回帰の錨として残す。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

sys.path.insert(0, _util.SCRIPTS)
import _auditcache  # noqa: E402

AUDIT = os.path.join(_util.SCRIPTS, "docs-audit.py")
PLUGIN_ROOT = os.path.dirname(_util.SCRIPTS)
HOOKS_JSON = os.path.join(PLUGIN_ROOT, "hooks", "hooks.json")


class RootFromEmptyDoesNotOpenSilentlyTest(unittest.TestCase):
    """1. 空の `--root-from` で、告げられていない木を読まないこと。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hookb-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        # cwd の上流に統治木を置く（walkup が見つけてしまう配置）。
        self.proj = _util.make_repo({"docs/_system/glossary.md": "# g\n"})
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)
        self.inner = os.path.join(self.proj, "deep", "inner")
        os.makedirs(self.inner, exist_ok=True)

    def _run(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, AUDIT, "--json", "--today", "2026-08-09"] + list(args),
            capture_output=True, text=True, timeout=300, cwd=cwd or self.inner,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                     CLAUDE_PLUGIN_ROOT=PLUGIN_ROOT))

    def test_empty_root_from_does_not_audit_a_tree_found_by_walking_up(self):
        proc = self._run("--root-from", "")
        self.assertNotEqual(
            proc.returncode, 0,
            "空の --root-from が素通りし、歩いて見つけた木を監査した")
        self.assertNotIn('"root"', proc.stdout,
                         "監査の要約を出してはならない（読んでいないこと）")

    def test_a_real_root_from_still_works(self):
        """射程を狭めすぎない —— 実在の値は従来どおり通ること。"""
        proc = self._run("--root-from", self.proj)
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])
        self.assertIn('"root"', proc.stdout)

    def test_no_root_argument_at_all_still_walks_up(self):
        """引数を一つも与えない従来の呼び方は変えない（互換）。"""
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stdout[-400:])


class TheSessionEndWiringNeverTargetsTheFilesystemRootTest(unittest.TestCase):
    """2. 配線を空の変数で展開しても、根へ書こうとしないこと。"""

    def test_summary_out_is_not_root_relative_when_the_variable_is_empty(self):
        import shlex
        with open(HOOKS_JSON, encoding="utf-8") as fh:
            hooks = json.load(fh)
        cmds = [h["command"]
                for entry in hooks["hooks"].get("SessionEnd", [])
                for h in entry["hooks"]]
        self.assertTrue(cmds, "SessionEnd の配線が無い")
        for cmd in cmds:
            expanded = (cmd.replace("${CLAUDE_PROJECT_DIR}", "")
                           .replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN_ROOT))
            parts = shlex.split(expanded)
            for i, part in enumerate(parts):
                if part == "--summary-out":
                    target = parts[i + 1]
                    self.assertFalse(
                        os.path.isabs(target),
                        "空の変数で --summary-out が絶対パス %r になる"
                        "（ファイルシステムの根へ書く）" % target)


class StampsPathIsAlwaysAbsoluteTest(unittest.TestCase):
    """3. 相対の値で、印の置き場が作業ディレクトリからの相対にならないこと。"""

    def test_a_relative_project_dir_is_not_trusted(self):
        """相対の値から場所を作らない。

        絶対へ寄せるだけでは駄目である —— `sub` を作業ディレクトリに対して
        解決すると、まさにリポジトリの作業木の中へ書く形になる（実測）。
        信じられない値は「与えられていない」と同じ既定へ倒す。
        """
        default = _auditcache.stamps_path("")
        for value in ("sub", "./sub", "a/b", "../elsewhere"):
            with self.subTest(value=value):
                path = _auditcache.stamps_path(value)
                self.assertTrue(os.path.isabs(path))
                self.assertEqual(
                    path, default,
                    "相対の値 %r から置き場を作った: %s" % (value, path))
                self.assertNotIn(
                    value.strip("./"), os.path.dirname(path).split(os.sep)[-3:],
                    "相対の値の断片が置き場に混ざった")

    def test_a_project_dir_that_does_not_exist_is_not_trusted(self):
        default = _auditcache.stamps_path("")
        self.assertEqual(_auditcache.stamps_path("/nonexistent-xyz-123"), default)

    def test_a_project_dir_pointing_at_a_file_is_not_trusted(self):
        fd, path = tempfile.mkstemp(prefix="hookb-file-")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        self.assertEqual(_auditcache.stamps_path(path),
                         _auditcache.stamps_path(""))

    def test_the_resolver_is_shared_not_redefined(self):
        """置き場の解決を各所で二重定義しない（DECIDED-001 事実1）。"""
        import glob
        offenders = []
        for f in sorted(glob.glob(os.path.join(_util.SCRIPTS, "*.py"))):
            if os.path.basename(f) == "_auditcache.py":
                continue
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
            if 'os.environ.get("CLAUDE_PROJECT_DIR")' in text and ".cache" in text:
                offenders.append(os.path.basename(f))
        self.assertEqual(offenders, [],
                         "実行時の置き場を自前で解いている: %r" % (offenders,))

    def test_absolute_and_empty_are_unchanged(self):
        d = tempfile.mkdtemp(prefix="hookb-abs-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertTrue(_auditcache.stamps_path(d).startswith(d))
        self.assertTrue(os.path.isabs(_auditcache.stamps_path("")))
        self.assertTrue(os.path.isabs(_auditcache.stamps_path()))

    def test_a_path_with_spaces_round_trips(self):
        """空白入りは現状も安全。回帰の錨として残す。"""
        d = tempfile.mkdtemp(prefix="hook b ")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self.assertTrue(_auditcache.stamps_path(d).startswith(d))


if __name__ == "__main__":
    unittest.main()
