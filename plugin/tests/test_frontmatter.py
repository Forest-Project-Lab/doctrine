#!/usr/bin/env python3
"""Tests for scripts/_frontmatter.py — the shared frontmatter parser.

Covers MASTER §1 (the frozen `_frontmatter` API) and the slice-02 27-case
matrix (T1..T27), plus dedicated `as_list` and `parse_frontmatter` tests, plus
the cross-slice integration semantics (None vs [] vs "" distinct; list fields
read via as_list).

This module imports `_frontmatter` directly via sys.path (it is importable; an
underscore name). It deliberately does NOT use tests/_util (owned by another
agent) so it stays decoupled and runnable on its own.
"""
import os
import sys
import unittest

SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
)
sys.path.insert(0, SCRIPTS)

import _frontmatter  # noqa: E402


def codes(errors):
    """Extract the ordered list of error codes from a parse() errors list."""
    return [e["code"] for e in errors]


class TestMatrix(unittest.TestCase):
    """Slice-02 T1..T27 matrix. Each maps to MASTER §1 frozen semantics."""

    def test_T1_happy_path(self):
        """T1 — happy path: scalar keys, body after closer (MASTER §1 string-by-default)."""
        fm, body, errs = _frontmatter.parse(
            "---\nid: SPEC-014\ntitle: Refund\ntype: SPEC\n---\n# Body\n"
        )
        self.assertEqual(fm, {"id": "SPEC-014", "title": "Refund", "type": "SPEC"})
        self.assertEqual(body, "# Body\n")
        self.assertEqual(errs, [])

    def test_T2_no_frontmatter(self):
        """T2 — no frontmatter (line0 != ---): ({}, original, []), NOT an error."""
        text = "# Just markdown\ntext\n"
        fm, body, errs = _frontmatter.parse(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)
        self.assertEqual(errs, [])

    def test_T3_leading_bom(self):
        """T3 — leading UTF-8 BOM stripped before processing (MASTER §1 BOM strip)."""
        fm, body, errs = _frontmatter.parse("﻿---\nid: A\n---\nbody\n")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "body\n")
        self.assertEqual(errs, [])

    def test_T4_crlf_preserved(self):
        """T4 — CRLF throughout: scan normalizes, body preserves CRLF verbatim."""
        fm, body, errs = _frontmatter.parse(
            "---\r\nid: A\r\ntitle: B\r\n---\r\nbody line\r\n"
        )
        self.assertEqual(fm, {"id": "A", "title": "B"})
        self.assertEqual(body, "body line\r\n")
        self.assertEqual(errs, [])

    def test_T5_missing_opening_fence(self):
        """T5 — leading whitespace before --- on line0 => no frontmatter."""
        text = " ---\nid: A\n"
        fm, body, errs = _frontmatter.parse(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)
        self.assertEqual(errs, [])

    def test_T6_missing_closing_fence(self):
        """T6 — no closer: parse remaining lines, body="", error missing_close."""
        fm, body, errs = _frontmatter.parse("---\nid: A\ntitle: B\n")
        self.assertEqual(fm, {"id": "A", "title": "B"})
        self.assertEqual(body, "")
        self.assertEqual(codes(errs), ["missing_close"])

    def test_T7_inline_flow_list(self):
        """T7 — inline flow list [a, b, c] -> list of scalars."""
        fm, body, errs = _frontmatter.parse("---\nsources: [a, b, c]\n---\n")
        self.assertEqual(fm, {"sources": ["a", "b", "c"]})
        self.assertEqual(body, "")
        self.assertEqual(errs, [])

    def test_T8_block_list(self):
        """T8 — block list (empty key followed by - item lines)."""
        fm, body, errs = _frontmatter.parse("---\nsources:\n  - a\n  - b\n---\nx\n")
        self.assertEqual(fm, {"sources": ["a", "b"]})
        self.assertEqual(body, "x\n")
        self.assertEqual(errs, [])

    def test_T9_empty_flow_list(self):
        """T9 — explicit empty flow list [] -> [] (distinct from None)."""
        fm, body, errs = _frontmatter.parse("---\ndepends_on: []\n---\n")
        self.assertEqual(fm, {"depends_on": []})
        self.assertIsInstance(fm["depends_on"], list)
        self.assertEqual(errs, [])

    def test_T10_empty_scalar_none(self):
        """T10 — empty scalar key -> None (distinct from [] and "")."""
        fm, body, errs = _frontmatter.parse("---\nsuperseded_by:\n---\n")
        self.assertEqual(fm, {"superseded_by": None})
        self.assertIsNone(fm["superseded_by"])
        self.assertEqual(errs, [])

    def test_T11_comment_lines(self):
        """T11 — full-line comments (# ...) ignored, no error."""
        fm, body, errs = _frontmatter.parse("---\n# c1\nid: A\n  # c2\n---\n")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(errs, [])

    def test_T12_inline_comment_stripped(self):
        """T12 — inline '# comment' (preceded by ws) stripped from value."""
        fm, body, errs = _frontmatter.parse("---\nowner: alice # primary\n---\n")
        self.assertEqual(fm, {"owner": "alice"})
        self.assertEqual(errs, [])

    def test_T13_hash_no_space_literal(self):
        """T13 — '#' with no preceding space is literal (SPEC-014#3)."""
        fm, body, errs = _frontmatter.parse("---\nid: SPEC-014#3\n---\n")
        self.assertEqual(fm, {"id": "SPEC-014#3"})
        self.assertEqual(errs, [])

    def test_T14_hash_inside_quotes_literal(self):
        """T14 — '#' inside quotes is literal (C# notes)."""
        fm, body, errs = _frontmatter.parse('---\ntitle: "C# notes"\n---\n')
        self.assertEqual(fm, {"title": "C# notes"})
        self.assertEqual(errs, [])

    def test_T15_double_quoted_escape(self):
        """T15 — double-quoted with \" escape."""
        fm, body, errs = _frontmatter.parse('---\ntitle: "a \\"b\\" c"\n---\n')
        self.assertEqual(fm, {"title": 'a "b" c'})
        self.assertEqual(errs, [])

    def test_T16_single_quoted_escape(self):
        """T16 — single-quoted with '' -> ' escape."""
        fm, body, errs = _frontmatter.parse("---\ntitle: 'it''s ok'\n---\n")
        self.assertEqual(fm, {"title": "it's ok"})
        self.assertEqual(errs, [])

    def test_T17_unquoted_value_with_colon(self):
        """T17 — split on FIRST colon; later colons stay in value."""
        fm, body, errs = _frontmatter.parse(
            "---\ntitle: Refund: full vs partial\n---\n"
        )
        self.assertEqual(fm, {"title": "Refund: full vs partial"})
        self.assertEqual(errs, [])

    def test_T18_colon_inside_quotes(self):
        """T18 — colon inside quotes is literal, not the separator."""
        fm, body, errs = _frontmatter.parse('---\ntitle: "a: b"\n---\n')
        self.assertEqual(fm, {"title": "a: b"})
        self.assertEqual(errs, [])

    def test_T19_boolean_coercion(self):
        """T19 — unquoted true/false coerce to bool (only these two)."""
        fm, body, errs = _frontmatter.parse(
            "---\ndraft: true\nlocked: False\n---\n"
        )
        self.assertEqual(fm, {"draft": True, "locked": False})
        self.assertEqual(errs, [])

    def test_T20_quoted_bool_stays_string(self):
        """T20 — quoted "true" stays the string, never coerced."""
        fm, body, errs = _frontmatter.parse('---\nflag: "true"\n---\n')
        self.assertEqual(fm, {"flag": "true"})
        self.assertEqual(errs, [])

    def test_T21_duplicate_key_last_wins(self):
        """T21 — duplicate key: last-wins AND duplicate_key error."""
        fm, body, errs = _frontmatter.parse(
            "---\nstatus: draft\nstatus: current\n---\n"
        )
        self.assertEqual(fm, {"status": "current"})
        self.assertEqual(codes(errs), ["duplicate_key"])
        # duplicate occurs on original line 3 (1-based: ---=1, draft=2, current=3)
        self.assertEqual(errs[0]["line"], 3)
        self.assertEqual(errs[0]["key"], "status")

    def test_T22_bad_line_no_colon(self):
        """T22 — a non-colon, non-list, non-comment line -> bad_line, skipped."""
        fm, body, errs = _frontmatter.parse(
            "---\nid: A\nthis is not yaml\ntitle: B\n---\n"
        )
        self.assertEqual(fm, {"id": "A", "title": "B"})
        self.assertEqual(codes(errs), ["bad_line"])
        self.assertEqual(errs[0]["line"], 3)

    def test_T23_orphan_list_item(self):
        """T23 — a '- item' with no open list key -> orphan_list_item."""
        fm, body, errs = _frontmatter.parse("---\nid: A\n  - x\n---\n")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(codes(errs), ["orphan_list_item"])
        self.assertEqual(errs[0]["line"], 3)

    def test_T24_flow_quoted_comma_and_typing(self):
        """T24 — flow list with quoted comma protected; dates stay strings."""
        fm, body, errs = _frontmatter.parse(
            '---\nsources: ["a, b", c]\nupdated: 2026-06-30\n---\n'
        )
        self.assertEqual(fm, {"sources": ["a, b", "c"], "updated": "2026-06-30"})
        self.assertEqual(errs, [])

    def test_T25_dots_closer_and_body_blanks(self):
        """T25 — '...' closer accepted (no error); leading body blank preserved."""
        fm, body, errs = _frontmatter.parse("---\nid: A\n...\n\nbody\n")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "\nbody\n")
        self.assertEqual(errs, [])

    def test_T26_empty_input(self):
        """T26 — empty string -> ({}, "", [])."""
        fm, body, errs = _frontmatter.parse("")
        self.assertEqual(fm, {})
        self.assertEqual(body, "")
        self.assertEqual(errs, [])

    def test_T27_only_frontmatter_no_trailing_nl(self):
        """T27 — closer is last line, no trailing newline -> body=""."""
        fm, body, errs = _frontmatter.parse("---\nid: A\n---")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "")
        self.assertEqual(errs, [])


class TestNeverRaises(unittest.TestCase):
    """MASTER §1 — parse() NEVER raises on content."""

    def test_unterminated_quote_double(self):
        """Unterminated double quote -> unterminated_quote, literal best-effort."""
        fm, body, errs = _frontmatter.parse('---\ntitle: "open\n---\n')
        self.assertIn("unterminated_quote", codes(errs))
        self.assertEqual(fm.get("title"), "open")

    def test_unterminated_quote_single(self):
        """Unterminated single quote -> unterminated_quote."""
        fm, body, errs = _frontmatter.parse("---\ntitle: 'open\n---\n")
        self.assertIn("unterminated_quote", codes(errs))

    def test_unterminated_flow(self):
        """Unterminated flow list -> unterminated_flow, best-effort split."""
        fm, body, errs = _frontmatter.parse("---\nsources: [a, b\n---\n")
        self.assertIn("unterminated_flow", codes(errs))
        self.assertEqual(fm.get("sources"), ["a", "b"])

    def test_bad_flow_list_nested(self):
        """Nested flow not supported -> bad_flow_list, best-effort."""
        fm, body, errs = _frontmatter.parse("---\nsources: [[a, b], c]\n---\n")
        self.assertIn("bad_flow_list", codes(errs))

    def test_empty_key(self):
        """A line beginning ':' -> empty_key error, skipped."""
        fm, body, errs = _frontmatter.parse("---\n: value\nid: A\n---\n")
        self.assertEqual(fm, {"id": "A"})
        self.assertIn("empty_key", codes(errs))

    def test_none_text_does_not_raise(self):
        """parse(None) returns empty tuple rather than raising."""
        fm, body, errs = _frontmatter.parse(None)
        self.assertEqual((fm, body, errs), ({}, "", []))

    def test_non_str_does_not_raise(self):
        """parse(non-str) coerces best-effort, never raises."""
        fm, body, errs = _frontmatter.parse(12345)
        self.assertEqual(fm, {})

    def test_errors_json_serializable(self):
        """All error records are JSON-serializable (never raise on json.dumps)."""
        import json
        _, _, errs = _frontmatter.parse("---\nstatus: a\nstatus: b\n: x\nbad\n")
        json.dumps(errs)  # must not raise
        for e in errs:
            self.assertEqual(set(e.keys()), {"code", "line", "key", "detail"})
            self.assertIn(e["code"], _frontmatter._ERROR_CODES)


class TestDistinctEmpties(unittest.TestCase):
    """MASTER §1 — None vs [] vs "" are distinct, intentional."""

    def test_blank_is_none(self):
        """Blank key -> None."""
        fm, _, _ = _frontmatter.parse("---\nk:\n---\n")
        self.assertIsNone(fm["k"])

    def test_explicit_empty_list(self):
        """Explicit [] -> empty list."""
        fm, _, _ = _frontmatter.parse("---\nk: []\n---\n")
        self.assertEqual(fm["k"], [])

    def test_quoted_empty_string(self):
        """Quoted "" -> empty string (distinct from None)."""
        fm, _, _ = _frontmatter.parse('---\nk: ""\n---\n')
        self.assertEqual(fm["k"], "")
        self.assertIsNotNone(fm["k"])

    def test_three_distinct(self):
        """None != [] != "" in one document."""
        fm, _, _ = _frontmatter.parse('---\na:\nb: []\nc: ""\n---\n')
        self.assertIsNone(fm["a"])
        self.assertEqual(fm["b"], [])
        self.assertEqual(fm["c"], "")


class TestCoercionEdges(unittest.TestCase):
    """MASTER §1 — only true/false coerce; yes/no/on/off stay strings; ints stay strings."""

    def test_yes_no_on_off_stay_strings(self):
        fm, _, _ = _frontmatter.parse(
            "---\na: yes\nb: no\nc: on\nd: off\n---\n"
        )
        self.assertEqual(fm, {"a": "yes", "b": "no", "c": "on", "d": "off"})

    def test_null_variants(self):
        """null, ~, and empty all -> None."""
        fm, _, _ = _frontmatter.parse("---\na: null\nb: ~\nc:\n---\n")
        self.assertEqual(fm, {"a": None, "b": None, "c": None})

    def test_quoted_null_stays_string(self):
        fm, _, _ = _frontmatter.parse('---\na: "null"\nb: "~"\n---\n')
        self.assertEqual(fm, {"a": "null", "b": "~"})

    def test_int_stays_string(self):
        """Ints stay strings; leading zero preserved."""
        fm, _, _ = _frontmatter.parse("---\nn: 42\nz: 014\n---\n")
        self.assertEqual(fm, {"n": "42", "z": "014"})

    def test_true_case_insensitive(self):
        fm, _, _ = _frontmatter.parse("---\na: TRUE\nb: True\nc: tRuE\n---\n")
        self.assertEqual(fm, {"a": True, "b": True, "c": True})


class TestBodyExtraction(unittest.TestCase):
    """MASTER §1 — body newlines verbatim; single separator newline consumed."""

    def test_body_preserves_trailing_whitespace(self):
        fm, body, _ = _frontmatter.parse("---\nid: A\n---\nline  \n\n")
        self.assertEqual(body, "line  \n\n")

    def test_one_separator_newline_consumed(self):
        """Only one newline after the closer is the separator; rest is body."""
        fm, body, _ = _frontmatter.parse("---\nid: A\n---\n\n\nbody")
        self.assertEqual(body, "\n\nbody")

    def test_cr_only_newlines(self):
        """Lone-CR line endings handled by universal newline scan."""
        fm, body, errs = _frontmatter.parse("---\rid: A\r---\rbody\r")
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "body\r")

    def test_block_list_then_scalar_resets_open_key(self):
        """After a scalar key the open list key resets (no spurious attach)."""
        fm, _, errs = _frontmatter.parse(
            "---\nsources:\n  - a\nowner: bob\n  - x\n---\n"
        )
        self.assertEqual(fm["sources"], ["a"])
        self.assertEqual(fm["owner"], "bob")
        # '- x' after the scalar 'owner' is now orphaned.
        self.assertIn("orphan_list_item", codes(errs))


class TestAsList(unittest.TestCase):
    """MASTER §1 — as_list(None/''/'x'/['a','b']/scalar-int)."""

    def test_none(self):
        self.assertEqual(_frontmatter.as_list(None), [])

    def test_empty_string(self):
        self.assertEqual(_frontmatter.as_list(""), [])

    def test_whitespace_string(self):
        self.assertEqual(_frontmatter.as_list("   "), [])

    def test_single_string(self):
        self.assertEqual(_frontmatter.as_list("x"), ["x"])

    def test_list_passthrough(self):
        self.assertEqual(_frontmatter.as_list(["a", "b"]), ["a", "b"])

    def test_empty_list(self):
        self.assertEqual(_frontmatter.as_list([]), [])

    def test_scalar_int(self):
        self.assertEqual(_frontmatter.as_list(5), ["5"])

    def test_list_with_none_and_empty_dropped(self):
        self.assertEqual(_frontmatter.as_list(["a", None, "", "  ", "b"]), ["a", "b"])

    def test_list_with_int_stringified(self):
        self.assertEqual(_frontmatter.as_list([1, 2]), ["1", "2"])

    def test_bool_scalar(self):
        self.assertEqual(_frontmatter.as_list(True), ["True"])

    def test_never_raises(self):
        # Arbitrary object: stringified, never raises.
        self.assertIsInstance(_frontmatter.as_list(object()), list)


class TestParseFrontmatter(unittest.TestCase):
    """MASTER §1 — parse_frontmatter(text) == parse(text)[0]."""

    def test_returns_dict_only(self):
        d = _frontmatter.parse_frontmatter("---\nid: A\ntitle: B\n---\nbody\n")
        self.assertEqual(d, {"id": "A", "title": "B"})

    def test_no_frontmatter_empty_dict(self):
        self.assertEqual(_frontmatter.parse_frontmatter("# plain\n"), {})

    def test_matches_parse_zero(self):
        text = "---\ndepends_on: [ICD-3, SPEC-9]\n---\nx\n"
        self.assertEqual(
            _frontmatter.parse_frontmatter(text), _frontmatter.parse(text)[0]
        )

    def test_pseudo_spec_depends_on_get(self):
        """§4.2 pseudo-spec: proposed.get('depends_on', []) works on a list value."""
        proposed = _frontmatter.parse_frontmatter(
            "---\ndomain: refund\ndepends_on: [ICD-3]\n---\n"
        )
        deps = proposed.get("depends_on", [])
        self.assertEqual(list(deps), ["ICD-3"])


class TestIntegrationAsListOnFields(unittest.TestCase):
    """Cross-slice binding rule (MASTER §1): list fields may be None or scalar;
    consumers MUST read them via as_list. Verify the rule holds end-to-end."""

    def test_blank_depends_on_via_as_list(self):
        fm, _, _ = _frontmatter.parse("---\ndepends_on:\n---\n")
        self.assertIsNone(fm["depends_on"])
        self.assertEqual(_frontmatter.as_list(fm.get("depends_on")), [])

    def test_scalar_depends_on_via_as_list(self):
        """Author error: depends_on: ICD-3 (scalar) -> as_list normalizes."""
        fm, _, _ = _frontmatter.parse("---\ndepends_on: ICD-3\n---\n")
        self.assertEqual(fm["depends_on"], "ICD-3")  # parser does NOT rewrite
        self.assertEqual(_frontmatter.as_list(fm.get("depends_on")), ["ICD-3"])

    def test_missing_field_via_as_list(self):
        fm, _, _ = _frontmatter.parse("---\nid: A\n---\n")
        self.assertEqual(_frontmatter.as_list(fm.get("impacts")), [])

    def test_proper_list_field_via_as_list(self):
        fm, _, _ = _frontmatter.parse("---\nimpacts: [SPEC-1, SPEC-2]\n---\n")
        self.assertEqual(
            _frontmatter.as_list(fm.get("impacts")), ["SPEC-1", "SPEC-2"]
        )


class TestParseFile(unittest.TestCase):
    """MASTER §1 — parse_file: utf-8-sig, newline=''; raises only on I/O/decode."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write_bytes(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def test_reads_utf8_sig_strips_bom(self):
        """utf-8-sig transparently strips a real file BOM."""
        path = self._write_bytes(
            "a.md", "﻿---\nid: A\n---\nbody\n".encode("utf-8")
        )
        fm, body, errs = _frontmatter.parse_file(path)
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "body\n")
        self.assertEqual(errs, [])

    def test_crlf_survives_newline_empty(self):
        """newline='' keeps CRLF in the body (no translation)."""
        path = self._write_bytes(
            "b.md", "---\r\nid: A\r\n---\r\nbody\r\n".encode("utf-8")
        )
        fm, body, errs = _frontmatter.parse_file(path)
        self.assertEqual(fm, {"id": "A"})
        self.assertEqual(body, "body\r\n")

    def test_accepts_pathlike(self):
        import pathlib
        path = self._write_bytes("c.md", b"---\nid: A\n---\n")
        fm, _, _ = _frontmatter.parse_file(pathlib.Path(path))
        self.assertEqual(fm, {"id": "A"})

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            _frontmatter.parse_file(os.path.join(self.dir, "nope.md"))

    def test_directory_raises(self):
        with self.assertRaises((IsADirectoryError, PermissionError, OSError)):
            _frontmatter.parse_file(self.dir)

    def test_non_utf8_raises(self):
        """A non-UTF-8 doc raises UnicodeDecodeError (no latin-1 fallback)."""
        path = self._write_bytes("d.md", b"---\nid: \xff\xfe\n---\n")
        with self.assertRaises(UnicodeDecodeError):
            _frontmatter.parse_file(path)

    def test_content_malformation_no_raise(self):
        """Content malformation flows through errors, never raises."""
        path = self._write_bytes("e.md", b"---\nid: A\nbadline\n")
        fm, body, errs = _frontmatter.parse_file(path)
        self.assertEqual(fm, {"id": "A"})
        self.assertIn("missing_close", codes(errs))
        self.assertIn("bad_line", codes(errs))


class TestVersionConstant(unittest.TestCase):
    """MASTER §1 — FRONTMATTER_VERSION = 1."""

    def test_version(self):
        self.assertEqual(_frontmatter.FRONTMATTER_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
