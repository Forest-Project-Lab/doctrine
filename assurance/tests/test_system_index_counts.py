#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""索引が数える試験の件数の決定論試験（SDK 不要・通信不要）。

事象 INC-029 の修正前再現。凍結したいこと:

- 索引の試験件数が、実際に走る試験の数と一致すること。
  `unittest` のメソッドはクラスの中で字下げされるので、桁 0 に錨を打つ
  正規表現は**一件も数えない**。索引はこれで全ファイル 0 件を報告していた。
- 評価プロンプトに「合計 0 件」という**偽の事実**が載らないこと。
  評価者は「この体系に試験は一つも無い」と告げられたうえで
  「実装・試験・証拠あり」を 240 件つけていた。
- 件数が 0 でないことを軸で持つ（例ではなく性質）。実ファイルの数と
  照合するので、試験が増減しても勝手に追随する。
"""
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import system_index  # noqa: E402

REPO_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN_TESTS = os.path.join(REPO_DIR, "plugin", "tests")

_ANY_TEST_DEF = re.compile(r"^[ \t]*def (test_[A-Za-z0-9_]+)", re.M)


def _truth_counts():
    """実ファイルから直に数えた {相対パス: 件数}（索引を経由しない対照）。"""
    truth = {}
    for name in sorted(os.listdir(PLUGIN_TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(PLUGIN_TESTS, name), encoding="utf-8") as fh:
            text = fh.read()
        truth["plugin/tests/%s" % name] = len(_ANY_TEST_DEF.findall(text))
    return truth


class IndexCountsTheTestsThatActuallyExistTest(unittest.TestCase):
    def setUp(self):
        self.indexed = {t["path"]: t["tests"] for t in system_index.test_files()}
        self.truth = _truth_counts()

    def test_the_index_finds_the_same_files(self):
        self.assertEqual(sorted(self.indexed), sorted(self.truth))

    def test_the_total_is_not_zero(self):
        """索引が『試験は一つも無い』と言わないこと（INC-029 の核心）。"""
        self.assertGreater(sum(self.indexed.values()), 0,
                           "索引が試験を一件も数えていない")

    def test_every_file_count_matches_the_file_itself(self):
        """軸で持つ —— 例ではなく、全ファイルの件数が実体と一致すること。"""
        self.assertEqual(self.indexed, self.truth)

    def test_no_test_file_is_reported_as_empty(self):
        empty = sorted(p for p, n in self.indexed.items() if n == 0)
        self.assertEqual(empty, [], "空と報告された試験ファイルがある")

    def test_the_total_matches_what_unittest_actually_collects(self):
        """実際に収集される数と突き合わせる（実体の grep でなく loader で数える）。

        自前の正規表現どうしを比べても、同じ思い違いを二度書けば緑になる。
        `unittest` の loader に収集させた数を第三の対照として置く。
        """
        proc = subprocess.run(
            [sys.executable, "-c",
             "import unittest;"
             "print(unittest.defaultTestLoader.discover("
             "'plugin/tests', pattern='test_*.py').countTestCases())"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=300,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        collected = int(proc.stdout.strip())
        self.assertEqual(sum(self.indexed.values()), collected,
                         "索引の合計が、loader が収集する数と一致すること")


class ThePromptDoesNotCarryAFalseFactTest(unittest.TestCase):
    def test_the_prompt_does_not_say_zero_tests(self):
        """評価プロンプトに「合計 0 件」が載らないこと。

        これが載ると、評価者は『この体系に試験は無い』という偽の前提で
        判定する。240 件の「実装・試験・証拠あり」はその入力の下で付いた。
        """
        idx = system_index.build() if hasattr(system_index, "build") \
            else system_index.index()
        text = system_index.as_prompt_text(idx)
        self.assertNotIn("合計 0 件", text)
        self.assertNotIn("（0 件）", text)

    def test_the_prompt_states_the_real_total(self):
        idx = system_index.build() if hasattr(system_index, "build") \
            else system_index.index()
        text = system_index.as_prompt_text(idx)
        total = sum(t["tests"] for t in idx["test_files"])
        self.assertIn("合計 %d 件" % total, text)


class TheRegexIsTheAxisTest(unittest.TestCase):
    """検出器そのものを試験する（空の緑にしない）。"""

    def test_it_matches_an_indented_unittest_method(self):
        src = ("import unittest\n"
               "class T(unittest.TestCase):\n"
               "    def test_a(self):\n"
               "        pass\n")
        self.assertEqual(
            len(system_index._DEF_TEST_RE.findall(src)), 1,
            "字下げされた unittest のメソッドを数えられること")

    def test_it_still_matches_a_module_level_function(self):
        src = "def test_b():\n    pass\n"
        self.assertEqual(len(system_index._DEF_TEST_RE.findall(src)), 1)

    def test_it_does_not_match_a_helper(self):
        src = ("class T:\n"
               "    def helper_test_thing(self):\n"
               "        pass\n"
               "    def _test_private(self):\n"
               "        pass\n")
        self.assertEqual(system_index._DEF_TEST_RE.findall(src), [])

    def test_it_does_not_match_a_test_named_in_a_comment_or_string(self):
        src = ('# def test_commented(self):\n'
               'DOC = "def test_in_a_string(self):"\n')
        self.assertEqual(system_index._DEF_TEST_RE.findall(src), [],
                         "註釈と文字列の中の綴りを数えない")


if __name__ == "__main__":
    unittest.main()
