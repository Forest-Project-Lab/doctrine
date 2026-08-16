#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""語境界の判定を、失敗様式の軸ごとに当てる（INC-002 推奨#2・INC-053）。

INC-002 の類型は「日本語に語の境界が無い」ことだった。同じ根から二つの向きの
欠陥が出る:

- **偽陽性**: 部分文字列照合が正当な語の一部を咎める（INC-002 そのもの）。
- **偽陰性**: `\\b` が和文に密着した英字語を見落とす（INC-053）。
  Python の `\\w` は和文を含むので、「はstatusを」に語境界は立たない。

推奨#2 は「既知類型を**失敗様式の軸**（文字体系・語境界・大小文字・全角半角・
正規化）へ展開して反例集合へ変換する」と言う。ここが軸の表であり、
**軸は表として持ち、事例は軸から機械で生む**（`_GLUE` が接着文字の軸を
そう持っているのと同じ形。ただしあちらの軸は接着文字で、こちらは文字体系）。

軸を足すときは表へ一行足す。足した瞬間、既存の全規則にその軸が当たる。
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import _termcheck as tc            # noqa: E402

DOCS_ROOT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "doctrine_docs")
META = {"id": "SPEC-999", "type": "SPEC", "status": "current"}

#: 失敗様式の軸。**事例の一覧ではなく軸の一覧である。**
#: 各軸は「英字語 w を和文の散文へ置く置き方」を返す。軸を足すと、
#: 下の全規則に対してその軸の反例が自動で生まれる。
AXES = {
    "空白で挟む": lambda w: "この文書は %s を扱う。" % w,
    "鉤括弧で囲む": lambda w: "この文書は「%s」を扱う。" % w,
    "読点の直後": lambda w: "まず、%s。" % w,
    # ここが INC-053。日本語の散文では**これが普通の書き方**である。
    "仮名・漢字に密着": lambda w: "この文書は%sを扱う。" % w,
    "行頭": lambda w: "%s を扱う。" % w,
}

#: 軸を当てる対象。(規則の名, その規則が拾うべき語を返す関数, 期待する code)
def _a_wordtrap(glossary):
    return sorted(glossary.wordtrap)[0]


def _an_acronym(_glossary):
    return "TDD"


RULES = (
    ("一語訳の罠", _a_wordtrap, "CALQUE_WORDTRAP"),
    ("未定義語", _an_acronym, "UNDEFINED_TERM"),
)


class ScriptBoundaryAxisTest(unittest.TestCase):
    def setUp(self):
        self.glossary = tc.load_glossary(DOCS_ROOT)

    def test_every_rule_holds_on_every_axis(self):
        """どの軸で置いても、拾うべき語は拾う。

        軸によって拾えたり拾えなかったりするのは、**判定が書き方に依存して
        いる**ということであり、和文では書き方は自由なので保証にならない。
        """
        misses = []
        for rule, pick, code in RULES:
            word = pick(self.glossary)
            for axis, place in sorted(AXES.items()):
                body = place(word)
                codes = [f.code for f in tc.check(body, META, self.glossary)]
                if code not in codes:
                    misses.append((rule, axis, body, codes))
        self.assertEqual(
            misses, [],
            "軸によって拾えていない。語境界の判定が書き方に依存している"
            "（INC-053。Python の \\w は和文を含むので \\b は和文密着で成立"
            "しない）: %r" % (misses,))

    def test_the_axis_table_is_not_a_case_list(self):
        """軸の表であることを保つ —— 各軸は関数であり、固定の文字列ではない。"""
        for axis, place in AXES.items():
            self.assertTrue(callable(place), axis)
            self.assertIn("XYZ", place("XYZ"), axis)

    def test_the_japanese_adjacent_axis_is_present(self):
        """INC-053 の軸が表から消えたら赤にする（軸の後退を許さない）。"""
        self.assertIn("仮名・漢字に密着", AXES)

    def test_a_word_that_should_not_be_flagged_stays_unflagged(self):
        """軸を当てても偽陽性を増やしていない（過剰是正の歯止め）。

        『substatus』は罠語『status』を部分文字列に含むが別の語である。
        どの軸で置いても咎めてはならない —— INC-002 の向きの回帰を防ぐ。
        """
        offenders = []
        for axis, place in sorted(AXES.items()):
            body = place("substatus")
            codes = [f.code for f in tc.check(body, META, self.glossary)]
            if "CALQUE_WORDTRAP" in codes:
                offenders.append((axis, body, codes))
        self.assertEqual(
            offenders, [],
            "別の語の一部を罠語として咎めている（INC-002 の向きの回帰）: %r"
            % (offenders,))
