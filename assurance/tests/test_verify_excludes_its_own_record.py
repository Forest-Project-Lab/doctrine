#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""検証の記録は、自分が検証する diff に含めない（INC-028）。

記録は commit 前の diff に対して作られるのに、その記録自体が次の commit で
同じ枝へ入る。すると記録と「それが検証した変更集合」が原理的に一致せず、
独立検証は毎回それを single_change の減点材料として正しく挙げる。
実測では INC-027 の検証が二度ともこの指摘を受けた。

記録は**評価の成果**であって、評価される変更ではない。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import verify_fix  # noqa: E402


class TheVerifyRecordIsNotPartOfTheDiffTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="vfx-")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self._run("git", "init", "-q")
        self._run("git", "config", "user.email", "t@example.invalid")
        self._run("git", "config", "user.name", "t")
        self._write("plugin/scripts/thing.py", "x = 1\n")
        self._run("git", "add", "-A")
        self._run("git", "commit", "-qm", "base")
        self.base = self._out("git", "rev-parse", "HEAD").strip()
        # 修正と、その検証の記録を同じ枝へ積む（現に起きていた形）。
        self._write("plugin/scripts/thing.py", "x = 2\n")
        self._write("assurance/ledger/verify/INC-999-x.json",
                    '{"kind": "verify-record", "target_id": "INC-999-x"}\n')
        self._run("git", "add", "-A")
        self._run("git", "commit", "-qm", "fix + record")

    def _run(self, *args):
        subprocess.run(args, cwd=self.repo, check=True,
                       capture_output=True, text=True)

    def _out(self, *args):
        return subprocess.run(args, cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout

    def _write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _diff(self, *extra):
        return self._out("git", "diff", "%s..HEAD" % self.base, "--", *extra)

    def test_without_the_exclusion_the_record_is_in_the_diff(self):
        """害の対照 —— 除外しないと記録が自分の検証対象に混ざる。"""
        self.assertIn("INC-999-x.json", self._diff("."))

    def test_with_the_exclusion_the_record_is_gone(self):
        out = self._diff(".", ":(exclude)assurance/ledger/verify/")
        self.assertNotIn("INC-999-x.json", out,
                         "検証の記録が自分の検証対象に残っている")

    def test_the_fix_itself_is_still_in_the_diff(self):
        """射程を狭めすぎない —— 修正そのものは検証対象に残ること。"""
        out = self._diff(".", ":(exclude)assurance/ledger/verify/")
        self.assertIn("thing.py", out)

    def test_the_runner_uses_the_exclusion(self):
        """走らせ手が実際にその形で git を呼ぶこと。"""
        import inspect
        src = inspect.getsource(verify_fix)
        self.assertIn(':(exclude)assurance/ledger/verify/', src,
                      "verify_fix が記録を検証対象から外していない")


if __name__ == "__main__":
    unittest.main()
