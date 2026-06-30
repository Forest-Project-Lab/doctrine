"""Tests for the 用語チェッカー core + CLI + glossary template.

Covers MASTER §6 and design/10-scenarios.md TCs targeting term-check (R6/R10):
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


class MaskingTest(unittest.TestCase):
    """擬陽性回避: mask code fences / inline code / URLs (MASTER §6)."""

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


class SuppressionTest(unittest.TestCase):
    """Skip the GLOSSARY正本 body and projection docs (MASTER §6)."""

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
        self.assertEqual(len(g.approved_terms), 20)     # spec §1 table = 20 rows
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
