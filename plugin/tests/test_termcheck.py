# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for the 用語チェッカー core + CLI + glossary template.

Covers 仕様 §6 and design/10-scenarios.md TCs targeting term-check (R6/R10):
  TC-062 approved word passes; TC-063 banned synonym 文書 family;
  TC-064 banned synonym ドメイン family; TC-065 clean prose passes;
  TC-066 calque 針を動かす/同じページにいる/深く潜る; TC-067 loanword/negation no FP;
  TC-068 specialist term defined at first use; TC-069 undefined acronym;
  TC-122 calque inside otherwise-valid SPEC; TC-128 novel calque out of scope.

Plus the critique gaps assigned to this component:
  - glossary not double-defined (no hardcoded approved-term TABLE in _termcheck);
  - fallback-to-template works; operational glossary parsed; parse-error -> WARN;
  - masking (code fence / inline code / URL no false positive);
  - GLOSSARY正本 body skipped; projection docs skipped;
  - Finding shape (code, severity, message, line) — linter + doc-review import it.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

tc = _util.load_core("_termcheck")
fm = _util.load_core("_frontmatter")

import unittest


def _g():
    """Seed glossary from the shipped template (docs_root=None -> template)."""
    return tc.load_glossary(None)


class FindingShapeTest(unittest.TestCase):
    """Risk: the Finding shape is imported by linter + doc-review. Pin it."""

    def test_finding_fields(self):
        f = tc.Finding("X", tc.ERROR, "msg")
        self.assertEqual(f.code, "X")
        self.assertEqual(f.severity, "ERROR")
        self.assertEqual(f.message, "msg")
        self.assertIsNone(f.line)               # line defaults to None
        f2 = tc.Finding("Y", tc.WARN, "m2", 7)
        self.assertEqual(f2.line, 7)
        # namedtuple positional + field order is the frozen contract.
        self.assertEqual(tuple(f2), ("Y", "WARN", "m2", 7))
        self.assertEqual(f._fields, ("code", "severity", "message", "line"))


class BannedSynonymTest(unittest.TestCase):
    """B7 term-check banned synonym — R6 (TC-062..064)."""

    def setUp(self):
        self.g = _g()

    def test_tc062_approved_word_passes(self):
        """TC-062: body uses approved 文書 -> no finding."""
        fs = tc.check("本文は文書を扱う。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_tc063_banned_synonym_document_family(self):
        """TC-063: ドキュメント/資料/ページ -> BANNED_SYNONYM -> 文書."""
        for syn in ("ドキュメント", "資料", "ページ"):
            fs = tc.check("これは%sだ。" % syn, {"type": "SPEC"}, self.g)
            codes = [f.code for f in fs]
            self.assertIn("BANNED_SYNONYM", codes, syn)
            msg = next(f.message for f in fs if f.code == "BANNED_SYNONYM")
            self.assertIn(syn, msg)
            self.assertIn("文書", msg)
            self.assertTrue(all(f.severity == "ERROR" for f in fs if f.code == "BANNED_SYNONYM"))

    def test_tc064_banned_synonym_domain_family(self):
        """TC-064: 領域/サブシステム/コンテキスト -> ドメイン."""
        for syn in ("領域", "サブシステム", "コンテキスト"):
            fs = tc.check("対象%sを切る。" % syn, {"type": "SPEC"}, self.g)
            msgs = [f.message for f in fs if f.code == "BANNED_SYNONYM"]
            self.assertTrue(msgs, syn)
            self.assertIn("ドメイン", msgs[0])

    def test_approved_compound_not_flagged(self):
        """#03/#09: 入出力 (⊃出力, banned for 投影) and 現在形 (⊃現在, banned for
        現行) are spec-mandated compounds -> must NOT draw BANNED_SYNONYM."""
        for compound in ("入出力", "現在形"):
            fs = tc.check("## %s\n本文。\n" % compound, {"type": "SPEC"}, self.g)
            bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
            self.assertEqual(bs, [], compound)

    def test_template_heading_vocabulary_not_flagged(self):
        """ADR-082 / #169: 『選択肢』は本プラグインの雛形が定める ADR の節見出し
        「却下した選択肢」の語である。その前半を禁止同義語に持つ体系(doctrine-lens は
        『起点』の同義語として持つ)で、雛形どおりに書いた ADR が全て咎められていた。
        実在の欠陥であり、既存の lens の ADR-012・ADR-013 も咎められていた。"""
        root = _util.make_repo({"docs/_system/glossary.md": (
            "---\nid: GLOSSARY-001\ntitle: t\ntype: GLOSSARY\ndomain: _system\n"
            "status: current\nowner: o\nupdated: 2026-06-01\nsources: []\n---\n\n"
            "# 用語辞書\n\n"
            "| 承認語 | 唯一の意味 | 禁止する同義語 |\n|---|---|---|\n"
            "| 起点 | いま開いている位置から決まる文書 | 基点、選択、フォーカス |\n")})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertIn("選択", [syn for syn, _a in g.banned_synonyms],
                      "この見本の辞書は『選択』を禁止しているはず")
        fs = tc.check("## 却下した選択肢\n本文。\n", {"type": "ADR"}, g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertEqual(bs, [], "雛形の節見出しを咎めてはならない")
        # 単独で現れたときは引き続き咎める(覆いは出現ごとで、語全体を免除しない)。
        fs2 = tc.check("これは選択だ。", {"type": "ADR"}, g)
        bs2 = [f for f in fs2 if f.code == "BANNED_SYNONYM"]
        self.assertTrue(bs2, "単独の『選択』は引き続き咎める")
        self.assertIn("起点", bs2[0].message)

    def test_standalone_synonym_still_caught(self):
        """#03/#09: masking the approved compound must NOT suppress a standalone
        banned synonym in ordinary prose (出力 -> 投影, 現在 -> 現行)."""
        for syn, approved in (("出力", "投影"), ("現在", "現行")):
            fs = tc.check("これは%sだ。" % syn, {"type": "SPEC"}, self.g)
            bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
            self.assertTrue(bs, syn)
            self.assertIn(approved, bs[0].message)

    def test_compound_masking_keeps_synonym_elsewhere(self):
        """A line with the approved compound AND a standalone synonym still flags
        the standalone occurrence (mask is occurrence-precise, not term-wide)."""
        fs = tc.check("入出力の節。なお出力する。", {"type": "SPEC"}, self.g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertTrue(bs)
        self.assertTrue(any("投影" in f.message for f in bs))

    def test_concrete_synonym_with_trailing_qualifier_is_matched(self):
        """Final-verify #1: a §1 synonym cell carrying a CONCRETE token with a
        trailing （...） usage note ('IF、インターフェース（単独語）、接続仕様') must surface
        the concrete token. Standalone インターフェース (banned for ICD) is caught."""
        syns = dict(self.g.banned_synonyms)
        self.assertIn("インターフェース", syns)
        self.assertEqual(syns["インターフェース"], "ICD")
        self.assertNotIn("インターフェース（単独語）", syns)  # the raw note is not a literal
        fs = tc.check("このインターフェースを公開する。", {"type": "SPEC"}, self.g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertTrue(bs)
        self.assertIn("ICD", bs[0].message)

    def test_conditionally_allowed_synonym_stays_context_only(self):
        """Final-verify #1: a synonym the spec allows in one sense
        ('差し替え（操作名としては可。状態名は置換）') must NOT be matched literally —
        the 可 note marks it conditional, so 差し替え as an operation is not flagged."""
        syns = dict(self.g.banned_synonyms)
        self.assertNotIn("差し替え", syns)
        fs = tc.check("内部をドメインごと差し替えられる。", {"type": "SPEC"}, self.g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertEqual(bs, [])

    def test_ascii_synonym_not_matched_inside_ascii_word(self):
        """保証キャンペーン実測 2026-08-04: ASCII 純字の禁止同義語『IF』(→ICD)が、
        ASCII 語 VERIFY / UNVERIFIED の内部へ部分一致していた(WATCH-001 の
        『部分文字列の取り違え』類型。『入出力』『選択肢』と同族の新事例)。
        日本語に語境界は無いが ASCII には在る。両隣のどちらかに ASCII の
        語構成字が続く出現は、その語ではないので咎めない。承認複合語の覆いへ
        VERIFY を足す対処は取らない(覆いは雛形・仕様が定める語に限る。ADR-082)。"""
        self.assertIn("IF", [syn for syn, _a in self.g.banned_synonyms])
        for word in ("VERIFY", "UNVERIFIED", "NOTIFY", "LIFECYCLE"):
            fs = tc.check("状態の名に %s を使う。" % word, {"type": "SPEC"}, self.g)
            bs = [f for f in fs
                  if f.code == "BANNED_SYNONYM" and "『IF』" in f.message]
            self.assertEqual(bs, [], word)

    def test_standalone_ascii_synonym_still_caught(self):
        """境界要求の後も、語として現れた IF は引き続き咎める。CJK 隣接
        (外部IF・IF仕様)は ASCII 語境界の外なので語のままである。"""
        for body in ("この IF を廃止する。", "外部IFを定義する。", "IF仕様を書く。",
                     "(IF)を使う。"):
            fs = tc.check(body, {"type": "SPEC"}, self.g)
            bs = [f for f in fs
                  if f.code == "BANNED_SYNONYM" and "『IF』" in f.message]
            self.assertTrue(bs, body)


class CalqueTest(unittest.TestCase):
    """B8 term-check calque — R10 (TC-065..067)."""

    def setUp(self):
        self.g = _g()

    def test_tc065_clean_prose_passes(self):
        """TC-065: clean Japanese, no listed calque -> no calque finding."""
        fs = tc.check("認識を揃える。詳しく見る。効果を出す。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs if f.code in ("CALQUE", "CALQUE_WORDTRAP")], [])

    def test_tc066_calque_phrases_caught(self):
        """TC-066: 針を動かす / 同じページにいる / 深く潜る -> CALQUE with 直す."""
        for surface, fix in (("針を動かす", "効果を出す"),
                             ("同じページにいる", "認識を揃える"),
                             ("深く潜る", "詳しく見る")):
            fs = tc.check("会議で%s。" % surface, {"type": "SPEC"}, self.g)
            cal = [f for f in fs if f.code == "CALQUE"]
            self.assertTrue(cal, surface)
            self.assertEqual(cal[0].severity, "ERROR")
            self.assertIn(fix, cal[0].message)

    def test_tc067_loanword_and_negation_no_false_positive(self):
        """TC-067: データ/リスク and plain negation must NOT be flagged (§1 擬陽性)."""
        fs = tc.check("データとリスクは扱うが、これはしない。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_wordtrap_warn(self):
        """#11 一語訳の罠: each of the four §1 source words (status/native/robust/
        leverage) in JP prose -> CALQUE_WORDTRAP WARN with its 直す suggestion."""
        cases = {
            "status": "位置づけ・区分",
            "native": "標準で・組み込みで",
            "robust": "壊れにくい",
            "leverage": "活かす",
        }
        # Confirm the seed actually carries all four mappings (single encoding).
        self.assertEqual(set(self.g.wordtrap), set(cases))
        for en, jp in cases.items():
            self.assertEqual(self.g.wordtrap[en], jp, en)
            fs = tc.check("この設計は %s だ。" % en, {"type": "SPEC"}, self.g)
            wt = [f for f in fs if f.code == "CALQUE_WORDTRAP"]
            self.assertTrue(wt, en)
            self.assertEqual(wt[0].severity, "WARN", en)
            self.assertIn(en, wt[0].message, en)
            self.assertIn(jp, wt[0].message, en)

    def test_tc128_novel_calque_out_of_scope(self):
        """TC-128: a 訳語臭 NOT in the §1 list is NOT caught (doc-review's job)."""
        # 'エコシステム的に' is translationese but absent from the calque table.
        fs = tc.check("エコシステム的に整える。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs if f.code.startswith("CALQUE")], [])


class UndefinedTermTest(unittest.TestCase):
    """B9 term-check undefined term — R6 (TC-068..069)."""

    def setUp(self):
        self.g = _g()

    def test_tc068_defined_at_first_use_passes(self):
        """TC-068: specialist term defined at first use -> no finding."""
        fs = tc.check("ARINC653（航空電子の規格）を採る。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs if f.code == "UNDEFINED_TERM"], [])

    def test_tc069_undefined_acronym_flagged(self):
        """TC-069: undefined acronym first occurrence -> UNDEFINED_TERM WARN."""
        fs = tc.check("ARINC653 を採る。", {"type": "SPEC"}, self.g)
        ut = [f for f in fs if f.code == "UNDEFINED_TERM"]
        self.assertTrue(ut)
        self.assertEqual(ut[0].severity, "WARN")

    def test_undefined_only_first_use(self):
        """First use only; second occurrence not re-flagged."""
        fs = tc.check("ARINC653 を採る。次も ARINC653 を使う。", {"type": "SPEC"}, self.g)
        ut = [f for f in fs if f.code == "UNDEFINED_TERM"]
        self.assertEqual(len(ut), 1)

    def test_approved_term_not_flagged_undefined(self):
        """An approved glossary term (e.g. 'ICD') is never UNDEFINED_TERM."""
        fs = tc.check("ICD を更新する。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs if f.code == "UNDEFINED_TERM"], [])

    def test_registry_type_codes_not_undefined(self):
        """Dogfood loop: type codes are defined ONCE in the registry (§3.2), so the
        term-checker must NOT flag them as undefined jargon (二重定義しない, §4.3) —
        their definition location is the registry, not the prose glossary."""
        for code in ("SPEC", "REQ", "TEST", "WATCH", "DECIDED", "IMPL", "NONGOAL"):
            fs = tc.check("%s を作る。" % code, {"type": "SPEC"}, self.g)
            ut = [f for f in fs if f.code == "UNDEFINED_TERM"]
            self.assertEqual(ut, [], code)

    def test_requirement_tags_not_undefined(self):
        """[R番号] tags reference §2 requirements (their definition location), not
        jargon -> never UNDEFINED_TERM."""
        fs = tc.check("本仕様は R7 と R10 を満たす。", {"type": "SPEC"}, self.g)
        self.assertEqual([f for f in fs if f.code == "UNDEFINED_TERM"], [])

    def test_external_acronym_still_flagged(self):
        """A genuine external acronym (not a type code / R-tag) is still flagged."""
        fs = tc.check("ARINC653 を採る。", {"type": "SPEC"}, self.g)
        self.assertTrue([f for f in fs if f.code == "UNDEFINED_TERM"])

    def test_hyphen_joined_identifier_is_one_token(self):
        """WATCH-001 の類型（ASCII 語境界）: ハイフンで綴じた識別子の前半を、
        単独の未定義略語と取り違えてはならない。'INC-005' の 'INC'、
        'NOT-APPLICABLE' の 'NOT' で実測した誤検知（事象 INC-004）。"""
        for body, fragment in (("事象 INC-005 を参照する。", "INC"),
                               ("状態は NOT-APPLICABLE とする。", "NOT"),
                               ("鍵は SHA-256 で採る。", "SHA")):
            fs = tc.check(body, {"type": "SPEC"}, self.g)
            ut = [f for f in fs if f.code == "UNDEFINED_TERM"]
            self.assertEqual(ut, [], "%s → %s" % (body, fragment))

    def test_identifier_glue_axis_is_covered(self):
        """既知類型を『失敗様式の軸』へ展開する（接着文字の軸）。

        INC-004 はハイフン、INC-011 はドットで同じ取り違えが起きた。個別の事例を
        一つずつ潰す形では三例目・四例目が出る。接着文字をこの表の行として持ち、
        新しい接着を足すときは**先にここへ行を足す**。
        """
        for glue in ("-", "."):
            for head, tail in (("INC", "005"), ("NOT", "APPLICABLE"),
                               ("SHA", "256"), ("v0", "7")):
                body = "識別子 %s%s%s を参照する。" % (head, glue, tail)
                fs = tc.check(body, {"type": "SPEC"}, self.g)
                ut = [f for f in fs if f.code == "UNDEFINED_TERM"]
                self.assertEqual(ut, [], body)

    def test_hyphen_joined_tail_is_not_flagged_alone(self):
        """後半だけを未定義語として挙げるのも同じ取り違えである。"""
        fs = tc.check("状態は NOT-APPLICABLE とする。", {"type": "SPEC"}, self.g)
        self.assertEqual(
            [f.message for f in fs if f.code == "UNDEFINED_TERM"], [])

    def test_standalone_acronym_next_to_punctuation_still_flagged(self):
        """ハイフン以外の区切りは従来どおり。語境界の緩和を広げすぎない。"""
        for body in ("ARINC653、を採る。", "（ARINC653）を採る。",
                     "ARINC653/他 を採る。"):
            fs = tc.check(body, {"type": "SPEC"}, self.g)
            self.assertTrue(
                [f for f in fs if f.code == "UNDEFINED_TERM"], body)


class MaskingTest(unittest.TestCase):
    """擬陽性回避: mask code fences / inline code / URLs (仕様 §6)."""

    def setUp(self):
        self.g = _g()

    def test_code_fence_masked(self):
        body = "通常の文。\n```\nドキュメント 領域\n```\n清書。\n"
        fs = tc.check(body, {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_inline_code_masked(self):
        fs = tc.check("インライン `ドキュメント` は無視。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_url_masked(self):
        fs = tc.check("参照 http://example.com/ドキュメント を見る。", {"type": "SPEC"}, self.g)
        self.assertEqual([f.code for f in fs if f.code == "BANNED_SYNONYM"], [])

    def test_line_number_preserved_after_mask(self):
        body = "一行目。\n二行目はドキュメント。\n"
        fs = tc.check(body, {"type": "SPEC"}, self.g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertTrue(bs)
        self.assertEqual(bs[0].line, 2)

    def test_line_number_preserved_after_actual_mask(self):
        """1行目にマスク対象(インラインコード)が実在しても2行目の所見は行2。
        _blank が改行だけを残す長さ保存の不変条件を固定する。"""
        body = "一行目に `code` を書く。\n二行目はドキュメント。\n"
        fs = tc.check(body, {"type": "SPEC"}, self.g)
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertTrue(bs)
        self.assertEqual(bs[0].line, 2)


class SuppressionTest(unittest.TestCase):
    """Skip GLOSSARY正本, projections, and never-context RESEARCH/ARCHIVE (ADR-023)."""

    def setUp(self):
        self.g = _g()

    def test_glossary_body_skipped(self):
        """The GLOSSARY正本 contains the banned words by definition -> skip body."""
        fs = tc.check("ドキュメント 領域 針を動かす", {"type": "GLOSSARY"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_projection_overview_skipped(self):
        fs = tc.check("ドキュメント 領域", {"type": "OVERVIEW"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_projection_ctxmap_skipped(self):
        fs = tc.check("ドキュメント 領域", {"type": "CTXMAP"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_research_body_skipped(self):
        """RESEARCH is llm_context: never + external vocabulary -> skip (ADR-023)."""
        fs = tc.check("ドキュメント 領域 要件定義書", {"type": "RESEARCH"}, self.g)
        self.assertEqual([f.code for f in fs], [])

    def test_archive_body_skipped(self):
        """ARCHIVE likewise -> skip body-level term checks (ADR-023)."""
        fs = tc.check("ドキュメント 領域 要件定義書", {"type": "ARCHIVE"}, self.g)
        self.assertEqual([f.code for f in fs], [])


class GlossaryResolutionTest(unittest.TestCase):
    """load_glossary: operational -> template fallback -> parse-error WARN."""

    def test_template_fallback_when_no_docs_root(self):
        """No operational glossary -> template seed (§1 lives once)."""
        g = tc.load_glossary(None)
        self.assertEqual(g.source, "template")
        self.assertFalse(g.parse_error)
        self.assertTrue(g.approved_terms)
        self.assertTrue(g.calque_table)

    def test_operational_glossary_parsed(self):
        """A target-repo docs/_system/glossary.md is read and is authoritative."""
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        root = _util.make_repo({"docs/_system/glossary.md": tmpl})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertEqual(g.source, "operational")
        self.assertFalse(g.parse_error)
        self.assertIn("文書", g.approved_terms)

    def test_unparsable_operational_falls_back_with_warn(self):
        """A present-but-broken operational glossary -> seed + GLOSSARY_PARSE_ERROR."""
        root = _util.make_repo({"docs/_system/glossary.md": "no table at all\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertTrue(g.parse_error)
        self.assertTrue(g.approved_terms)        # still enforced via seed
        fs = tc.check("本文。", {"type": "SPEC"}, g)
        self.assertIn("GLOSSARY_PARSE_ERROR", [f.code for f in fs])

    def test_partial_table_a_header_rejected(self):
        """第3列が『禁止する同義語』でない表は表Aと認めない(ヘッダは連言)。"""
        body = ("| 承認語 | 意味 | 備考 |\n"
                "|---|---|---|\n"
                "| 文書 | まとまり | メモにすぎない |\n")
        self.assertIsNone(tc.parse_glossary(body))

    def test_header_only_table_a_is_parse_error(self):
        """表Aのヘッダだけでデータ行が無い正本 -> 解析失敗としてテンプレへ退避。

        Regression: 空の承認語辞書を operational として受け入れると、全チェックが
        警告なしに沈黙する(検出の全面喪失)。"""
        body = "| 承認語 | 唯一の意味 | 禁止する同義語 |\n|---|---|---|\n"
        self.assertIsNone(tc.parse_glossary(body))
        root = _util.make_repo({"docs/_system/glossary.md": body})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertEqual(g.source, "template")
        self.assertTrue(g.parse_error)
        self.assertTrue(g.approved_terms)  # テンプレの辞書で検出は継続する

    def test_operational_extends_seed(self):
        """An operational glossary may add an approved term beyond the seed."""
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        extra = tmpl.replace(
            "| 文書 | 管理対象の最小単位",
            "| ワークフロー | 業務手順 | 流れ |\n| 文書 | 管理対象の最小単位")
        root = _util.make_repo({"docs/_system/glossary.md": extra})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertIn("ワークフロー", g.approved_terms)
        fs = tc.check("流れを定める。", {"type": "SPEC"}, g)
        self.assertTrue(any(f.code == "BANNED_SYNONYM" and "ワークフロー" in f.message
                            for f in fs))


class ProperNounExceptionTest(unittest.TestCase):
    """§1 固有名の例外(ADR-017/ADR-018): 意味欄が「固有名」の表A行は
    禁止同義語の照合から外れる。辞書登録だけで実装に触れない(ADR-005)。"""

    def _g_with(self, extra_row):
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        extended = tmpl.replace(
            "| 文書 | 管理対象の最小単位",
            extra_row + "\n| 文書 | 管理対象の最小単位")
        root = _util.make_repo({"docs/_system/glossary.md": extended})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return tc.load_glossary(os.path.join(root, "docs"))

    def test_proper_noun_row_parsed(self):
        g = self._g_with("| 情報マスター管理基準 | 固有名 | |")
        self.assertIn("情報マスター管理基準", g.proper_nouns)
        self.assertIn("情報マスター管理基準", g.approved_terms)

    def test_banned_synonym_inside_proper_noun_not_flagged(self):
        """固有名『情報マスター管理基準』の中の『マスター』(正本の禁止同義語)は
        照合から外れる。地の文の『マスター』単独は従来どおり検出する。"""
        g = self._g_with("| 情報マスター管理基準 | 固有名 | |")
        fs = tc.check("情報マスター管理基準に従い記載する。", {"type": "SPEC"}, g)
        self.assertEqual([f for f in fs if f.code == "BANNED_SYNONYM"], [])
        fs2 = tc.check("マスターを更新する。", {"type": "SPEC"}, g)
        self.assertTrue(any(f.code == "BANNED_SYNONYM" and "マスター" in f.message
                            for f in fs2))

    def test_registered_approved_compound_masked_dynamically(self):
        """禁止同義語を包含する承認語を辞書に登録すれば、コードに触れず
        照合から外れる(ADR-017 の前提を実装で成立させる)。"""
        g = self._g_with("| マスタープラン | 都市計画の公式の上位計画 | |")
        fs = tc.check("マスタープランを参照する。", {"type": "SPEC"}, g)
        self.assertEqual([f for f in fs if f.code == "BANNED_SYNONYM"], [])
        fs2 = tc.check("マスターを参照する。", {"type": "SPEC"}, g)
        self.assertTrue(any(f.code == "BANNED_SYNONYM" for f in fs2))


class NoDoubleDefinitionTest(unittest.TestCase):
    """Critique gap: §1 must not be double-defined. The approved-term TABLE and
    the synonym/calque tables live only in the glossary template — _termcheck
    holds NO independent hardcoded approved-term/synonym/calque table."""

    def test_no_hardcoded_approved_or_calque_tables_in_source(self):
        src_path = os.path.join(_util.SCRIPTS, "_termcheck.py")
        src = _util.read(src_path)
        # The §1 approved words / banned synonyms / calque surfaces must NOT
        # appear as literals in the core — they are parsed from the template.
        for token in ("ドキュメント", "針を動かす", "同じページにいる",
                      "領域", "サブシステム", "深く潜る", "ロールアップ"):
            self.assertNotIn(token, src,
                             "§1 token %r is hardcoded in _termcheck.py "
                             "(must come from the glossary template)" % token)

    def test_approved_terms_come_from_template(self):
        """If the template changes, the enforced set changes — proving the
        source of truth is the template, not a code constant."""
        g_default = tc.load_glossary(None)
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        trimmed = tmpl.replace(
            "| 用語チェッカー | リンタのうち、未承認語と未定義語を弾く機能 | （上記で統一） |\n",
            "")
        root = _util.make_repo({"docs/_system/glossary.md": trimmed})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g_trim = tc.load_glossary(os.path.join(root, "docs"))
        self.assertIn("用語チェッカー", g_default.approved_terms)
        self.assertNotIn("用語チェッカー", g_trim.approved_terms)


class TemplateContentTest(unittest.TestCase):
    """The glossary template seeds §1 EXACTLY (single encoding)."""

    def setUp(self):
        self.text = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        self.meta, self.body, self.errs = fm.parse(self.text)

    def test_frontmatter_keys(self):
        """type GLOSSARY, status current, llm_context always, canonical_for [glossary]."""
        self.assertEqual(self.errs, [])
        self.assertEqual(self.meta.get("type"), "GLOSSARY")
        self.assertEqual(self.meta.get("status"), "current")
        self.assertEqual(self.meta.get("llm_context"), "always")
        self.assertEqual(fm.as_list(self.meta.get("canonical_for")), ["glossary"])
        self.assertEqual(self.meta.get("domain"), "_system")
        # §3.4 required keys present (with placeholders allowed).
        for k in ("id", "title", "type", "domain", "status", "owner", "updated", "sources"):
            self.assertIn(k, self.meta, k)

    def test_seeds_both_tables_and_lines(self):
        g = tc.parse_glossary(self.body)
        self.assertIsNotNone(g)
        self.assertEqual(len(g.approved_terms), 22)     # spec §1 table = 22 rows
        self.assertEqual(len(g.calque_table), 9)        # 9-row calque table
        self.assertEqual(set(g.wordtrap), {"status", "native", "robust", "leverage"})
        # 定着した借用語: §1 の データ・リスク に、定着した外部の略語を加える
        # (JSON・YAML 等。新しい外部略語はこの行へ書き足す — 定義の在処を一つに保つ)。
        self.assertTrue({"データ", "リスク"}.issubset(set(g.loanwords)))
        self.assertTrue({"JSON", "YAML", "CLI", "LLM"}.issubset(set(g.loanwords)))

    def test_template_passes_its_own_term_check(self):
        """The deliverable must pass its own term-check: the GLOSSARY正本 body is
        skipped, so checking it yields no findings (no self-contradiction)."""
        g = tc.load_glossary(None)
        fs = tc.check(self.body, self.meta, g)
        self.assertEqual([f.code for f in fs], [])


class CliTest(unittest.TestCase):
    """term-check.py thin CLI — standalone, exit 0, advisory-only (TC-122)."""

    def test_tc122_calque_in_valid_spec_advisory(self):
        """TC-122: a structurally valid SPEC whose body has 針を動かす ->
        term-check reports it; CLI exits 0 (advisory, never blocks)."""
        root = _util.make_repo({
            "docs/_system/glossary.md": _util.read(
                os.path.join(_util.TEMPLATES, "glossary.md.tmpl")),
            "docs/billing/spec/SPEC-014-x.md": _util.fm_block({
                "id": "SPEC-014", "type": "SPEC", "domain": "billing",
                "status": "current",
            }) + "この変更で針を動かす。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "docs/billing/spec/SPEC-014-x.md")
        out, code = _util.invoke("term-check", argv=[path])
        self.assertEqual(code, 0)
        self.assertIn("CALQUE", out)
        self.assertIn("針を動かす", out)

    def test_clean_doc_no_output(self):
        root = _util.make_repo({
            "docs/billing/spec/SPEC-1-x.md": _util.fm_block({
                "id": "SPEC-1", "type": "SPEC", "domain": "billing",
            }) + "本文は文書を扱う。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "docs/billing/spec/SPEC-1-x.md")
        out, code = _util.invoke("term-check", argv=[path])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_clean_spec_with_mandated_headings_no_output(self):
        """#03/#09 regression pin: a compliant SPEC whose body carries the four
        spec-MANDATED headings (入出力/制約/エラー時挙動/受入基準) must emit NO
        findings via the CLI. '入出力' literally contains '出力' (banned synonym
        for 投影); the shared core must NOT false-flag it. Also assert a plain
        '現在形' (API guidance '中立・現在形') containing '現在' (banned for 現行)
        is clean, while a standalone '出力'/'現在' would still be caught."""
        body = (
            "## 入出力\n本文は文書を扱う。\n\n"
            "## 制約\n本文。\n\n"
            "## エラー時挙動\n本文。\n\n"
            "## 受入基準\n中立・現在形で書く。\n"
        )
        root = _util.make_repo({
            "docs/_system/glossary.md": _util.read(
                os.path.join(_util.TEMPLATES, "glossary.md.tmpl")),
            "docs/billing/spec/SPEC-3-x.md": _util.fm_block({
                "id": "SPEC-3", "type": "SPEC", "domain": "billing",
                "status": "current",
            }) + body,
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "docs/billing/spec/SPEC-3-x.md")
        out, code = _util.invoke("term-check", argv=[path])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_cli_resolves_glossary_via_docs_walk(self):
        """The CLI finds docs/_system/glossary.md by walking up from the file."""
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        # Add a synonym only the operational glossary has.
        op = tmpl.replace(
            "| 文書 | 管理対象の最小単位（S1000Dのデータモジュールに当たる） | ドキュメント、資料、ページ |",
            "| 文書 | 管理対象の最小単位（S1000Dのデータモジュールに当たる） | ドキュメント、資料、ページ、書類 |")
        root = _util.make_repo({
            "docs/_system/glossary.md": op,
            "docs/billing/spec/SPEC-2-x.md": _util.fm_block({
                "id": "SPEC-2", "type": "SPEC", "domain": "billing",
            }) + "これは書類だ。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "docs/billing/spec/SPEC-2-x.md")
        out, code = _util.invoke("term-check", argv=[path])
        self.assertEqual(code, 0)
        self.assertIn("書類", out)             # only present if operational glossary used

    def test_cli_missing_file_exit_zero(self):
        out, code = _util.invoke("term-check", argv=["/nonexistent/path.md"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main()


class FileLineNumberTest(unittest.TestCase):
    """ADR-083 / #170: 助言の行番号はファイルの行番号である。

    以前は本文内の行を返しており、フロントマターの行数だけずれていた。報告された行を
    開くと無関係な文が在るため、書き手は「誤検出だ」と判断して助言を捨てる。
    doctrine-lens の実在の ADR で実測した(実在 85 行 / 報告 72 行、ずれ 13)。
    **単体試験では出なかった欠陥である** —— 見本のフロントマターが短く、行番号を
    検めていなかった。
    """

    FM = ("---\nid: SPEC-9\ntitle: t\ntype: SPEC\ndomain: billing\n"
          "status: current\nowner: o\nupdated: 2026-06-01\nsources: []\n---\n")

    def _doc(self, blank_lines=0):
        """フロントマターの後ろに空行を挟んで、本文の開始行を動かした文書。"""
        return self.FM + "\n" * blank_lines + "\n## 入出力\n本文。\nこれはドキュメントだ。\n"

    def test_reported_line_is_the_file_line(self):
        for blanks in (0, 1, 5):
            text = self._doc(blanks)
            meta, body, _e = fm.parse(text)
            start = fm.body_start_line(text, body)
            fs = tc.check(body, meta, tc.load_glossary(None), start)
            bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
            self.assertTrue(bs, blanks)
            line = bs[0].line
            # 報告された行を開くと、そこに咎めた語が在る(これが直したかったこと)。
            self.assertEqual(text.splitlines()[line - 1], "これはドキュメントだ。",
                             "blanks=%d 報告 %d 行" % (blanks, line))

    def test_no_frontmatter_keeps_line_one_base(self):
        """フロントマターの無い文書では換算しない(いまと同じ挙動)。"""
        text = "これはドキュメントだ。\n"
        meta, body, _e = fm.parse(text)
        self.assertEqual(fm.body_start_line(text, body), 1)
        fs = tc.check(body, meta, tc.load_glossary(None),
                      fm.body_start_line(text, body))
        bs = [f for f in fs if f.code == "BANNED_SYNONYM"]
        self.assertEqual(bs[0].line, 1)

    def test_findings_without_a_line_are_untouched(self):
        """行を持たない助言(辞書の解析失敗など)は None のまま返る。"""
        root = _util.make_repo({"docs/_system/glossary.md": "no table at all\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = tc.load_glossary(os.path.join(root, "docs"))
        self.assertTrue(g.parse_error)
        fs = tc.check("本文。", {"type": "SPEC"}, g, 14)
        pe = [f for f in fs if f.code == "GLOSSARY_PARSE_ERROR"]
        self.assertTrue(pe)
        self.assertIsNone(pe[0].line)


class RegistryAbsenceTest(unittest.TestCase):
    """INC-007: _registry の import が失敗しても _termcheck は落ちない。

    失敗時は _registry_mod が None に束縛され、check() は NameError を出さずに
    助言を返す(覆いは手書きの一覧と辞書由来の源だけへ退く)。subprocess で
    import 失敗を実際に注入して検める(sys.modules に None を置くと
    `import _registry` は ImportError になる)。
    """

    def test_inc007_registry_import_failure_binds_none_and_never_raises(self):
        import subprocess
        code = (
            "import sys\n"
            "sys.dont_write_bytecode = True\n"  # 配布物に生成物を残さない(ADR-075)
            "sys.path.insert(0, %r)\n"
            "sys.modules['_registry'] = None\n"
            "import _termcheck as tc\n"
            "assert tc._registry_mod is None, '_registry_mod が束縛されていない'\n"
            "g = tc.load_glossary(None)\n"
            "fs = tc.check('# x\\n\\n## \\u5165\\u51fa\\u529b\\n\\n\\u672c\\u6587\\u3002\\n',"
            " {'type': 'SPEC'}, g)\n"
            "assert isinstance(fs, list)\n"
            "print('OK', len(fs))\n"
        ) % _util.SCRIPTS
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0,
                         "registry 不在で落ちた:\n%s" % out.stderr)
        self.assertTrue(out.stdout.startswith("OK"), out.stdout)


class RegistrySectionMaskTest(unittest.TestCase):
    """#197 / ADR-135: 登録簿の必須節名は、利用者の辞書が何を禁じても書ける。

    節名の正本は登録簿(_registry.REQUIRED_SECTIONS)であり、書き手は言い換え
    られない。言い換えられないものを禁止同義語の照合に掛けない。覆いは節の
    完全な名だけ —— 地の文の単独語は従来どおり検出する(ADR-082 の精度優先)。
    """

    def _g_with_rows(self, rows):
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        extended = tmpl.replace(
            "| 文書 | 管理対象の最小単位",
            "\n".join(rows) + "\n| 文書 | 管理対象の最小単位")
        root = _util.make_repo({"docs/_system/glossary.md": extended})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return tc.load_glossary(os.path.join(root, "docs"))

    def test_issue197_impact_doc_with_banned_test_word_not_flagged(self):
        """#197 の実測そのまま: 『テスト→試験』を禁じる辞書でも、IMPACT の
        必須節『影響するテスト』は書ける。"""
        g = self._g_with_rows(["| 試験 | 検証の実行 | テスト |"])
        body = ("## 影響する文書\nx\n## 影響する実装\ny\n"
                "## 影響するテスト\nz\n## 工数見積\nw\n")
        fs = tc.check(body, {"type": "IMPACT"}, g)
        self.assertEqual([f for f in fs if f.code == "BANNED_SYNONYM"], [],
                         "必須節の名が禁止同義語として咎められた(#197 の袋小路)")

    def test_issue197_standalone_banned_word_still_caught(self):
        """覆いは節の完全な名だけ。地の文の単独『テスト』は従来どおり咎める。"""
        g = self._g_with_rows(["| 試験 | 検証の実行 | テスト |"])
        fs = tc.check("テストを直す。", {"type": "IMPACT"}, g)
        self.assertTrue(any(f.code == "BANNED_SYNONYM" and "テスト" in f.message
                            for f in fs))

    def test_spec_error_section_with_banned_error_word_not_flagged(self):
        """#197 実測の第二例: 『エラー』を禁じる辞書でも SPEC の必須節
        『エラー時挙動』は書ける。"""
        g = self._g_with_rows(["| 不具合記録 | 検査で見つかった事実の記録 | エラー |"])
        fs = tc.check("## エラー時挙動\n仕様のとおり。\n", {"type": "SPEC"}, g)
        self.assertEqual([f for f in fs if f.code == "BANNED_SYNONYM"], [])

    def test_every_registry_section_name_is_writable(self):
        """性質の試験: 登録簿の全型・全節名について、その名そのものを禁じる
        辞書の下でも見出しが書ける(例ではなく全量で守る)。"""
        reg = _util.load_core("_registry")
        names = sorted({n for names in reg.REQUIRED_SECTIONS.values()
                        for n in names})
        rows = ["| 承認語%d | 意味%d | %s |" % (i, i, n)
                for i, n in enumerate(names)]
        g = self._g_with_rows(rows)
        offenders = []
        for type_code, secs in sorted(reg.REQUIRED_SECTIONS.items()):
            body = "".join("## %s\n本文。\n" % n for n in secs)
            fs = tc.check(body, {"type": type_code}, g)
            for f in fs:
                if f.code == "BANNED_SYNONYM":
                    offenders.append((type_code, f.message))
        self.assertEqual(offenders, [],
                         "節名が禁止同義語として咎められた: %r" % offenders)

    def test_section_mask_degrades_without_registry(self):
        """登録簿が無い環境では覆いは手書きの一覧と辞書由来の源だけへ退く
        (沈黙して広げない・落ちない)。節名『影響するテスト』は覆われなく
        なるが、袋小路の対(MISSING_SECTION)も登録簿が無ければ出ない。"""
        import subprocess
        code = (
            "import sys\n"
            "sys.dont_write_bytecode = True\n"
            "sys.path.insert(0, %r)\n"
            "sys.modules['_registry'] = None\n"
            "import _termcheck as tc\n"
            "assert tc._registry_section_names() == ()\n"
            "print('OK')\n"
        ) % _util.SCRIPTS
        out = subprocess.run([sys.executable, "-c", code],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("OK"), out.stdout)
