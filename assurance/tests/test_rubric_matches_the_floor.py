#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""規準が、床が実際に求めるものと食い違わない（INC-038）。

二つの食い違いを実測した。

- 規準は `plugin/tests/test_x.py::test_名` の形を案内するのに、索引は個々の
  試験の名を渡していない。**渡していない名を書かせる形を案内していた** ——
  実測では 253 件の緑のうち試験名を引くものは 0 件で、この形は一度も
  使われていない（使えない）。
- 五値の名は「実装・**試験**・証拠あり」だが、床が実際に求めるのは
  「機械が守っている証拠」であって unittest に限らない。実測では試験を
  引かない緑 125 件が、監査の検査 102・スクリプト 87・リンタの検査コード
  34・Hook 14・技能 8 を引いており、**決定や仕様だけの緑は 0 件**である。
  床は正しく働いている。狭いのは名の方だった。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import prompts, system_index  # noqa: E402


class TheRubricDoesNotOfferAnUnusablePointerTest(unittest.TestCase):
    def test_the_index_does_not_carry_test_names(self):
        """前提: 索引は件数を渡すが名は渡さない。"""
        idx = (system_index.build() if hasattr(system_index, "build")
               else system_index.index())
        for f in idx["test_files"]:
            self.assertNotIn("names", f, "索引が名を渡すなら案内してよい")

    def test_the_rubric_does_not_ask_for_a_test_name(self):
        text = prompts.rubric_text() if hasattr(prompts, "rubric_text") else None
        if text is None:
            import inspect
            text = inspect.getsource(prompts)
        self.assertNotIn("::test_名", text,
                         "渡していない名を書かせる形を案内している")

    def test_the_rubric_still_offers_the_file_form(self):
        import inspect
        text = inspect.getsource(prompts)
        self.assertIn("plugin/tests/test_audit.py", text,
                      "試験をファイルで指す形は残すこと")


class TheGreenLabelMatchesTheFloorTest(unittest.TestCase):
    def test_the_definition_does_not_narrow_to_unittest(self):
        import inspect
        text = inspect.getsource(prompts)
        i = text.find("- 実装・試験・証拠あり …")
        self.assertGreater(i, 0)
        block = text[i:i + 400]
        self.assertIn("機械が守っており", block,
                      "床が求めるのは機械の強制であって unittest ではない")

    def test_the_floor_still_rejects_documents_only(self):
        """射程を狭めすぎない —— 決定・仕様だけの緑は落ちること。"""
        idx = (system_index.build() if hasattr(system_index, "build")
               else system_index.index())
        resolve = lambda p: system_index.resolve_pointer(idx, p)
        self.assertFalse(
            prompts._has_enforcing_pointer(["SPEC-011", "ADR-008"], resolve),
            "決定・仕様だけを機械の強制と認めてはならない")

    def test_the_floor_accepts_mechanical_enforcement_other_than_tests(self):
        idx = (system_index.build() if hasattr(system_index, "build")
               else system_index.index())
        resolve = lambda p: system_index.resolve_pointer(idx, p)
        for pointer in ("plugin/scripts/docs-audit.py", "adr_not_landed"):
            with self.subTest(pointer=pointer):
                if resolve(pointer) is None:
                    self.skipTest("索引に %s が無い環境" % pointer)
                self.assertTrue(
                    prompts._has_enforcing_pointer([pointer], resolve),
                    "%s は機械の強制として認めること" % pointer)


if __name__ == "__main__":
    unittest.main()
