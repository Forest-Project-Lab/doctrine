#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""本プラグインが書けと定めた語を、自分の禁止同義語で咎めない（INC-002 推奨#1）。

INC-002 は、日本語に語の境界が無いために、禁止同義語が**正当な語の一部**として
現れたときに咎める偽陽性だった。実害は二度出ている（WATCH-001 第2項）——
承認複合語『入出力』⊃『出力』と、雛形が定める節見出し「却下した選択肢」⊃『選択肢』。
後者は**雛形どおりに書いた ADR が全て咎められる**という形で現れた。

推奨#1 は「語彙表の各語について、その語を部分文字列として含む正当語の反例試験を
**機械生成**し、反例を伴わない語が追加された時点で CI を赤にする」と言う。

**反例は発明しない。**この体系が「こう書け」と定めている語 —— 登録簿の必須節名
（`_registry.REQUIRED_SECTIONS`）・語彙表の承認語／借用語／固有名・雛形の見出し ——
を容れ物として機械的に列挙し、禁止同義語を部分文字列に持つものだけを対にする。
容れ物は**名づけられた単位**に限る。散文から文字の連なりを拾うと助詞をまたいだ
非語（「過去の状態の記録」など）が混ざり、実測で 1 組が 10 組へ膨らんだ。

新しい禁止同義語が、この体系が書けと定めた語と衝突した瞬間にここが赤くなる。
覆い（`_APPROVED_COMPOUNDS`）へ加えるか、同義語の側を考え直すかは人が決める。
"""

import glob
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")
sys.path.insert(0, SCRIPTS)

import _termcheck as tc            # noqa: E402

DOCS_ROOT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "doctrine_docs")
META = {"id": "SPEC-999", "type": "SPEC", "status": "current"}
#: 名づけられた単位だけを拾う（助詞をまたぐ連なりは語ではない）。
_WORD = re.compile(r"[一-鿿ぁ-んァ-ヶー]{2,}")


def _mandated_words():
    """この体系が「こう書け」と定めている語の集合。"""
    words = set()
    try:
        words |= set(tc._registry_section_names())
    except Exception:                                    # noqa: BLE001
        pass                                             # 登録簿が無ければ助言層へ退く
    for path in sorted(glob.glob(os.path.join(TEMPLATES, "*.tmpl"))):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for heading in re.findall(r"^#{1,4}\s+(.+)$", text, re.M):
            words |= set(_WORD.findall(heading))
    return words


def _pairs(glossary):
    """(禁止語, それを部分文字列に含む「書けと定めた語」) の全対。"""
    banned = [b for b, _ in glossary.banned_synonyms] + list(glossary.wordtrap)
    words = _mandated_words() | set(glossary.approved_terms) \
        | set(glossary.loanwords) | set(glossary.proper_nouns)
    return sorted({(t, w) for t in banned for w in words if t != w and t in w})


class MandatedWordsAreNotFlaggedTest(unittest.TestCase):
    def setUp(self):
        self.glossary = tc.load_glossary(DOCS_ROOT)

    def test_the_corpus_is_derived_not_invented(self):
        """反例は語彙表と雛形と登録簿から導く（手で書かない）。"""
        self.assertTrue(_mandated_words(), "書けと定めた語が一つも導けていない")

    def test_no_mandated_word_is_flagged(self):
        """機械生成した反例のすべてで、検査器は咎めない。"""
        offenders = []
        for term, word in _pairs(self.glossary):
            findings = tc.check(word, META, self.glossary)
            codes = [f.code for f in findings]
            if codes:
                offenders.append((term, word, codes))
        self.assertEqual(
            offenders, [],
            "この体系が書けと定めた語を、自分の禁止同義語で咎めている。"
            "覆い（_APPROVED_COMPOUNDS）へ加えるか、同義語の側を考え直すこと"
            "（INC-002 推奨#1・WATCH-001 第2項）: %r" % (offenders,))

    def test_a_new_colliding_synonym_turns_it_red(self):
        """**新しい禁止同義語が衝突した瞬間に赤くなる**ことを確かめる。

        現在の語彙表で緑であることは、機構が効いていることの証拠にならない
        （覆いが既に在るから緑なのである）。覆いの無い衝突を注入して赤を見る。
        """
        word = sorted(_mandated_words())[0]
        self.assertGreaterEqual(len(word), 2, word)
        injected = word[:-1] if len(word) > 2 else word[0]
        glossary = tc.Glossary(
            approved_terms=self.glossary.approved_terms,
            banned_synonyms=tuple(self.glossary.banned_synonyms)
            + ((injected, "承認語"),),
            calque_table=self.glossary.calque_table,
            wordtrap=self.glossary.wordtrap,
            loanwords=self.glossary.loanwords,
            source=self.glossary.source,
            parse_error=self.glossary.parse_error,
            proper_nouns=self.glossary.proper_nouns)
        offenders = [(t, w) for t, w in _pairs(glossary)
                     if t == injected and tc.check(w, META, glossary)]
        self.assertTrue(
            offenders,
            "覆いの無い衝突（%r ⊂ %r）を注入しても赤にならない。"
            "機構が形を捕らえていない" % (injected, word))

    def test_a_standalone_banned_word_is_still_caught(self):
        """覆いが効きすぎていない —— 単独で出てくる禁止同義語は依然咎める。"""
        term = [b for b, _ in self.glossary.banned_synonyms][0]
        findings = tc.check("この文書は%sを扱う。" % term, META, self.glossary)
        self.assertTrue(
            [f for f in findings if f.code == "BANNED_SYNONYM"],
            "単独の %r を咎めなくなっている（覆いが効きすぎ）" % (term,))
