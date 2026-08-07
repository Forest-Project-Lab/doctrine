# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""用語チェッカーの偽陽性コーパス試験（INC-004 の推奨 #0）。

INC-004 は、ハイフンで綴じた識別子の断片に UNDEFINED_TERM が誤反応した事象である
（`NOT-APPLICABLE` の `NOT`・`INC-005` の `INC`・`SHA-256` の `SHA`）。個別の例を
並べた試験は既に在るが、それは**挙げた例しか守らない**。

ここが守るのは**性質**である:

    点検器が指摘した語は、原文に**単独の語として実在**しなければならない。

長い綴りの一部を切り出して「未定義語だ」と言うことを禁ずる。この形の誤反応は
INC-004（ハイフン）・INC-011（ドット）で二度起きており、WATCH-001 第2項が
「長い語に含まれる部分文字列を禁止同義語と取り違えてはならない」として
戻してはならない事項に挙げている。

コーパスは体系が現に使う識別子で組む。新しい綴り方が入ったらここへ足す ——
足す先が一箇所であることが、この試験の値打ちである。
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

tc = _util.load_core("_termcheck")

import unittest


# 体系が現に使う複合語・識別子。断片を取り違えやすい綴りを集める。
# 追加するときは「その綴りが実際に体系のどこかに在る」ことを確かめてから足す。
CORPUS = """\
状態語彙は PASS / FAIL / UNKNOWN / UNASSESSED / DEGRADED / NOT-APPLICABLE とする。
事象 INC-005 と INC-011 は、いずれも綴りの断片に反応した誤検知であった。
指紋は SHA-256 で取る。決定は ADR-116 と ADR-133 に、非目標は NONGOAL-001 に置く。
退行監視は WATCH-001、確定は DECIDED-001、手順は PROC-001 に置く。
監査は docs-audit が、点検は docs-linter が、投影は render-projection が担う。
検査名は adr_not_landed・ext_anchor_broken・reverse_orphan_req_no_spec を用いる。
リンタの検査コードは MISSING_KEY・EMPTY_KEY・MISSING_SECTION・UNDEFINED_TERM である。
Hook は SessionStart・PostToolUse・PreToolUse・SessionEnd・PreCompact に配線する。
仕様は SPEC-011、要求は REQ-003、外部の錨は EXT-004 に置く。
再判定の口は map_coverage.py、独立の照合は independent_recheck.py が持つ。
"""

# 語として切り出してよい境界。ここに挙げた綴り記号で綴じられた語は
# 「単独の語」ではない（識別子の断片である）。
_GLUE = r"[-_./:]"


class FalsePositiveCorpusTest(unittest.TestCase):
    """指摘語が原文に単独の語として実在するかを機械照合する。"""

    def setUp(self):
        self.glossary = tc.load_glossary(None)
        self.meta = {"type": "SPEC"}

    def _flagged_terms(self, body):
        """助言の本文から、点検器が名指しした語を取り出す。

        助言は『未定義語『NOT』を初出で定義する(§1)。』のような形で語を鉤括弧に
        入れる。鉤括弧の中身を取り出せない助言は、この試験の対象外とする
        （語を名指ししていないので、照合すべき語が無い）。
        """
        terms = []
        for f in tc.check(body, self.meta, self.glossary):
            for m in re.finditer(r"『([^』]+)』", f.message):
                terms.append((f.code, m.group(1)))
        return terms

    def _is_standalone(self, body, term):
        """`term` が原文に単独の語として在るか（綴じ記号に挟まれていないか）。"""
        for m in re.finditer(re.escape(term), body):
            before = body[max(0, m.start() - 1):m.start()]
            after = body[m.end():m.end() + 1]
            if re.match(_GLUE, before) or re.match(_GLUE, after):
                continue          # 綴じられた識別子の断片
            return True
        return False

    def test_every_flagged_term_exists_as_a_standalone_word(self):
        """**性質**を守る —— 指摘語は原文に単独の語として実在すること。

        1 件でも実在しなければ赤で止める。長い綴りの一部を切り出して
        「未定義語だ」と言うことは、この試験が在るかぎり CI を通らない。
        """
        bad = [(code, term) for code, term in self._flagged_terms(CORPUS)
               if not self._is_standalone(CORPUS, term)]
        self.assertEqual(
            bad, [],
            "綴りの断片を語として指摘している（INC-004・INC-011 の再来）: %s" % bad)

    def test_known_identifier_fragments_are_not_flagged(self):
        """INC-004 で実測した断片が名指しされないこと（回帰の錨）。

        上の性質試験があれば理屈では要らないが、壊れたときに**どの断片で**
        壊れたかが読めるように残す。
        """
        flagged = {term for _code, term in self._flagged_terms(CORPUS)}
        for fragment in ("NOT", "INC", "SHA", "ADR", "SPEC", "REQ", "EXT",
                         "WATCH", "NONGOAL", "DECIDED", "MISSING", "EMPTY"):
            self.assertNotIn(fragment, flagged,
                             "識別子の断片 %r を語として指摘した" % fragment)

    def test_the_corpus_actually_exercises_the_checker(self):
        """コーパスが点検器を素通りしていないこと。

        すべての助言がゼロなら、上の二つは「何も起きなかった」ことしか言えない。
        空振りの試験を緑と読ませない（根拠なき PASS を書かない）。
        """
        masked = tc.mask_body(CORPUS)
        self.assertTrue(masked.strip(), "コーパスが丸ごと伏せられている")
        self.assertIn("NOT-APPLICABLE", CORPUS)
        self.assertGreater(len(CORPUS.splitlines()), 5)
        # 点検器が現に語を名指ししていること。ゼロなら上の性質試験は
        # 「何も指摘されなかった」ことしか言っておらず、空振りである。
        self.assertTrue(self._flagged_terms(CORPUS),
                        "点検器がコーパスで一語も名指ししていない（空振りの緑）")

    def test_the_oracle_can_fail(self):
        """照合器そのものが赤を出せること（試験が試験になっているか）。

        本文に単独では現れない綴りを渡せば、`_is_standalone` は偽を返す。
        ここが常に真を返す実装だと、上の性質試験は何も守らない。
        """
        self.assertFalse(self._is_standalone("状態は NOT-APPLICABLE とする。", "NOT"))
        self.assertTrue(self._is_standalone("NOT を単独で書く。", "NOT"))


if __name__ == "__main__":
    unittest.main()
