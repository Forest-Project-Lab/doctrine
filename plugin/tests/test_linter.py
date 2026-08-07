# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for docs-linter.py (PostToolUse single-doc, advisory only).

Covers 仕様 §5.1 / §3.3 / §6 and design/10-scenarios.md TCs targeting the
linter:
  Status allow/deny per type: TC-001..038 (representative + the ADR/RESEARCH
    carve-outs TC-023/025/035).
  id<->filename: TC-051/052/053. type<->location: TC-054/055/056.
  llm_context: TC-057/058. RESEARCH 決定 heading: TC-109/110.
  SPEC 4 sections: TC-059/060/061. Required keys: TC-047/048/049/050.
  Traceability: TC-040/111/112. Level-2 reduced keys: TC-039/120.
  term-check integration (advisory, no block): TC-122/063/066.
  ICD-dep post-detection: TC-070/071/072 (advisory form).

Plus the critique gap assigned to this component:
  - docs-linter NEVER emits a 'decision' key (advisory only).
  - a valid doc yields no findings (empty stdout).

Top-of-file harness import per BRIEF2.
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

import unittest

DL = "docs-linter"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _valid_spec_fm(**over):
    fm = {
        "id": "SPEC-014", "title": "Refund", "type": "SPEC",
        "domain": "billing", "status": "current", "owner": "alice",
        "updated": "2026-01-01", "depends_on": ["REQ-2"], "sources": [],
    }
    fm.update(over)
    return fm


_SPEC_BODY_4 = (
    "## 入出力\n本文がある。\n"
    "## 制約\n本文がある。\n"
    "## エラー時挙動\n本文がある。\n"
    "## 受入基準\n本文がある。\n"
)


def _req_fm(**over):
    fm = {
        "id": "REQ-2", "title": "r", "type": "REQ", "domain": "billing",
        "status": "current", "owner": "a", "updated": "2026-01-01",
        "sources": [],
    }
    fm.update(over)
    return fm


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _write(self, relpath, fm, body=""):
        return _util.write_doc(self.root, relpath, fm, body)

    def _lint(self, path):
        """Invoke the linter via stdin envelope; return (stdout, code)."""
        stdin = _util.hook_stdin(
            "PostToolUse", tool_name="Write",
            tool_input={"file_path": path})
        return _util.invoke(DL, stdin_obj=stdin)

    def _codes(self, path):
        """Run the linter; return the set of finding codes in additionalContext."""
        out, code = self._lint(path)
        self.assertEqual(code, 0, "linter must always exit 0")
        if not out.strip():
            return set(), ""
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        codes = set()
        for line in ctx.splitlines():
            line = line.strip()
            if line.startswith("["):
                # '[SEVERITY] CODE: ...'
                after = line.split("]", 1)[1].strip()
                codes.add(after.split(":", 1)[0].strip())
        return codes, ctx


# ---------------------------------------------------------------------------
# Valid doc + advisory-only contract (critique gap)
# ---------------------------------------------------------------------------
class BatchModeTest(_Base):
    """#91: --batch は統治木の全 .md を点検し、ERROR で終了コード 1 を返す(CI ゲート)。"""

    def _batch(self):
        return _util.invoke(DL, argv=["--batch",
                            os.path.join(self.root, "doctrine_docs")])

    def _valid_spec(self, doc_id):
        return ({"id": doc_id, "title": "t", "type": "SPEC", "domain": "billing",
                 "status": "current", "owner": "o", "updated": "2026-07-01",
                 "sources": [], "depends_on": ["REQ-1"]},
                "## 入出力\na\n## 制約\nb\n## エラー時挙動\nc\n## 受入基準\nd\n")

    def test_clean_tree_exits_0(self):
        fm, body = self._valid_spec("SPEC-1")
        self._write("doctrine_docs/billing/spec/SPEC-1-x.md", fm, body)
        out, code = self._batch()
        self.assertEqual(code, 0, out)
        self.assertIn("ERROR なし", out)

    def test_bad_doc_exits_1(self):
        # 必須キー owner 欠落 + status 不正。
        self._write("doctrine_docs/billing/spec/SPEC-2-x.md",
                    {"id": "SPEC-2", "title": "t", "type": "SPEC",
                     "domain": "billing", "status": "draft",
                     "updated": "2026-07-01", "sources": []},
                    "## 入出力\na [R1]\n## 制約\nb\n## エラー時挙動\nc\n## 受入基準\nd\n")
        out, code = self._batch()
        self.assertEqual(code, 1, out)
        self.assertIn("[ERROR]", out)

    def test_no_tree_exits_0(self):
        # 実在するが統治木でない場所は CI で落とさない(素の docs/ への配慮)。
        out, code = _util.invoke(DL, argv=["--batch", self.root])
        self.assertEqual(code, 0)
        self.assertIn("統治木が無い", out)
        self.assertIn("点検 0 文書", out)

    # -- ADR-110: 使い方の誤りを場所として飲まない ------------------------
    #
    # 変更前は --batch の次の語を無条件に場所として飲み、旗の綴り違いでも 0 を
    # 返していた。利用者側がその形のまま門を回しており、正しく呼び直したら
    # 85 文書に 241 件の ERROR が出た(門は在ったが効いていなかった)。

    def test_unknown_flag_is_not_taken_as_a_root(self):
        for argv in (["--batch", "--root", "doctrine_docs"],
                     ["--batch", "--fail-on", "error"],
                     ["--batch", ".", "--fail-on", "error"]):
            out, code = _util.invoke(DL, argv=argv)
            self.assertEqual(code, 2, "%s => %s" % (argv, out))
            self.assertIn("不明な引数", out)

    def test_extra_word_is_a_usage_error(self):
        out, code = _util.invoke(DL, argv=["--batch", self.root, "extra"])
        self.assertEqual(code, 2, out)
        self.assertIn("余分な引数", out)

    def test_missing_place_exits_3(self):
        out, code = _util.invoke(
            DL, argv=["--batch", os.path.join(self.root, "no-such-place")])
        self.assertEqual(code, 3, out)
        self.assertIn("実在しない", out)

    def test_scanned_count_is_always_reported(self):
        fm, body = self._valid_spec("SPEC-9")
        self._write("doctrine_docs/billing/spec/SPEC-9-x.md", fm, body)
        out, code = self._batch()
        self.assertEqual(code, 0, out)
        self.assertIn("1 文書を点検し", out)


class ValidAndAdvisoryTest(_Base):
    """Critique gap: valid doc -> no findings; linter NEVER emits 'decision'."""

    def test_valid_spec_no_findings(self):
        """§8.A.1 / TC-059: well-formed SPEC -> empty stdout, exit 0."""
        self._write("docs/billing/REQ-2-refunds.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-refund-policy.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        out, code = self._lint(p)
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_valid_icd_no_findings(self):
        """§8.A.3 / TC-056: a valid ICD.md at <domain>/ -> empty stdout."""
        p = self._write("docs/billing/ICD.md", {
            "id": "ICD-01", "title": "Billing ICD", "type": "ICD",
            "domain": "billing", "status": "current", "owner": "a",
            "updated": "2026-01-01", "canonical_for": ["billing"],
            "sources": [],
        }, "## 公開する用語\nx\n## 正本である事実\ny\n"
           "## データ契約\n公開する用語とデータ契約。\n## 依存してよい入口\nz\n")
        out, code = self._lint(p)
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_valid_adr_accepted_no_findings(self):
        """§8.A.2 / TC-023: ADR status:accepted under decisions/ -> clean."""
        p = self._write("docs/billing/decisions/ADR-3-refund.md", {
            "id": "ADR-3", "title": "Refund ADR", "type": "ADR",
            "domain": "billing", "status": "accepted", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "## 背景\nx\n## 却下した選択肢\ny\n## 決定\n決定の記録。\n## 帰結\nz\n")
        out, _ = self._lint(p)
        self.assertEqual(out, "")

    def test_never_emits_decision_key_when_findings(self):
        """CRITIQUE GAP: even with violations the linter never emits 'decision'.

        Build a doc with multiple violations; assert response carries
        hookSpecificOutput.additionalContext and NO 'decision'/'permissionDecision'.
        """
        p = self._write("docs/billing/spec/SPEC-014-bad.md",
                        _valid_spec_fm(status="accepted"), "## 入出力\nx\n")
        out, code = self._lint(p)
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertNotIn("decision", obj)
        self.assertNotIn("permissionDecision", obj)
        self.assertNotIn("continue", obj)
        self.assertIn("hookSpecificOutput", obj)
        self.assertEqual(obj["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("additionalContext", obj["hookSpecificOutput"])

    def test_response_format_shape(self):
        """Risk: pin the additionalContext finding format other agents assert on."""
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(owner=None), _SPEC_BODY_4)
        _codes, ctx = self._codes(p)
        self.assertIn("Self-correct the following before continuing.", ctx)
        self.assertIn("docs-linter: %s" % p, ctx)
        # Each finding line: '  [SEVERITY] CODE: message  (§ref)'
        self.assertRegex(ctx, r"\n  \[(ERROR|WARN)\] [A-Z_]+: .+  \(§")


# ---------------------------------------------------------------------------
# Status allow-list per type (§3.3 — TC-001..038)
# ---------------------------------------------------------------------------
class StatusAllowListTest(_Base):
    """B2 / TC-001..038: status per-type allow/deny."""

    def _status_codes(self, type_code, status, relpath, extra=None):
        fm = {
            "id": "%s-1" % type_code, "title": "t", "type": type_code,
            "domain": "billing", "status": status, "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }
        if extra:
            fm.update(extra)
        p = self._write(relpath, fm)
        codes, _ = self._codes(p)
        return codes

    def test_tc002_icd_accepted_denied(self):
        """TC-002: ICD status:accepted -> BAD_STATUS."""
        codes = self._status_codes("ICD", "accepted", "docs/billing/ICD.md")
        self.assertIn("BAD_STATUS", codes)

    def test_tc023_adr_accepted_allowed(self):
        """TC-023: ADR accepted is the ONLY type+status where accepted is OK."""
        codes = self._status_codes(
            "ADR", "accepted", "docs/billing/decisions/ADR-1-x.md")
        self.assertNotIn("BAD_STATUS", codes)

    def test_tc025_adr_current_denied(self):
        """TC-025: ADR status:current is NOT in the ADR allow-list."""
        codes = self._status_codes(
            "ADR", "current", "docs/billing/decisions/ADR-1-x.md")
        self.assertIn("BAD_STATUS", codes)

    def test_tc035_research_draft_allowed(self):
        """TC-035: RESEARCH draft carve-out (C5) -> no BAD_STATUS."""
        codes = self._status_codes(
            "RESEARCH", "draft", "docs/billing/research/RESEARCH-1-x.md")
        self.assertNotIn("BAD_STATUS", codes)

    def test_tc036_research_accepted_denied(self):
        """TC-036: RESEARCH status:accepted -> BAD_STATUS."""
        codes = self._status_codes(
            "RESEARCH", "accepted", "docs/billing/research/RESEARCH-1-x.md")
        self.assertIn("BAD_STATUS", codes)

    def test_tc017_spec_superseded_allowed(self):
        """TC-017: SPEC may be superseded (old version)."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        codes = self._status_codes(
            "SPEC", "superseded", "docs/billing/spec/SPEC-1-x.md",
            extra={"depends_on": ["REQ-2"]})
        self.assertNotIn("BAD_STATUS", codes)

    def test_unknown_status_value_denied(self):
        """B2: a status outside the global vocabulary -> BAD_STATUS."""
        codes = self._status_codes(
            "REQ", "wip", "docs/billing/REQ-1-x.md")
        self.assertIn("BAD_STATUS", codes)

    def test_non_adr_accepted_denied_family(self):
        """TC-004/006/.../038: accepted denied for every non-ADR type."""
        cases = [
            ("OVERVIEW", "docs/_system/overview.md"),
            ("REQ", "docs/billing/REQ-1-x.md"),
            ("DATA", "docs/billing/spec/DATA-1-x.md"),
            ("TEST", "docs/billing/test/TEST-1-x.md"),
        ]
        for tcode, rel in cases:
            with self.subTest(type=tcode):
                codes = self._status_codes(tcode, "accepted", rel)
                self.assertIn("BAD_STATUS", codes)


# ---------------------------------------------------------------------------
# id <-> filename (§3.4/§3.7 — TC-051..053)
# ---------------------------------------------------------------------------
class IdFilenameTest(_Base):
    def test_tc051_id_matches_filename_prefix(self):
        """TC-051: id SPEC-014 in SPEC-014-refund-policy.md -> no mismatch."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-refund-policy.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("ID_FILENAME_MISMATCH", codes)

    def test_tc052_id_filename_mismatch(self):
        """TC-052: id SPEC-014 in file SPEC-015-... -> ID_FILENAME_MISMATCH."""
        p = self._write("docs/billing/spec/SPEC-015-other.md",
                        _valid_spec_fm(id="SPEC-014"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertIn("ID_FILENAME_MISMATCH", codes)

    def test_tc053_bad_filename_version_suffix(self):
        """TC-053: embedded version suffix -v2 -> BAD_FILENAME."""
        p = self._write("docs/billing/spec/SPEC-1-policy-v2.md",
                        _valid_spec_fm(id="SPEC-1", depends_on=["REQ-2"]),
                        _SPEC_BODY_4)
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        codes, _ = self._codes(p)
        self.assertIn("BAD_FILENAME", codes)

    def test_system_singleton_skips_id_filename(self):
        """TC-051 exception: _system/glossary.md id GLOSSARY-001 -> skipped."""
        p = self._write("docs/_system/glossary.md", {
            "id": "GLOSSARY-001", "title": "g", "type": "GLOSSARY",
            "domain": "_system", "status": "current", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "用語辞書。\n")
        codes, _ = self._codes(p)
        self.assertNotIn("ID_FILENAME_MISMATCH", codes)


# ---------------------------------------------------------------------------
# type <-> location (§3.2 — TC-054..056)
# ---------------------------------------------------------------------------
class TypeLocationTest(_Base):
    def test_tc054_spec_in_spec_dir_ok(self):
        """TC-054: SPEC under billing/spec/ -> no location mismatch."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-1-x.md",
                        _valid_spec_fm(id="SPEC-1", depends_on=["REQ-2"]),
                        _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("TYPE_LOCATION_MISMATCH", codes)

    def test_tc055_spec_in_decisions_dir_mismatch(self):
        """TC-055: SPEC under billing/decisions/ -> TYPE_LOCATION_MISMATCH."""
        p = self._write("docs/billing/decisions/SPEC-1-x.md",
                        _valid_spec_fm(id="SPEC-1"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertIn("TYPE_LOCATION_MISMATCH", codes)

    def test_tc056_icd_at_domain_root_ok(self):
        """TC-056: ICD.md at billing/ -> ok; ICD elsewhere -> mismatch."""
        p = self._write("docs/billing/ICD.md", {
            "id": "ICD-1", "title": "i", "type": "ICD", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-01-01",
            "sources": [],
        }, "本文。\n")
        codes, _ = self._codes(p)
        self.assertNotIn("TYPE_LOCATION_MISMATCH", codes)

        p2 = self._write("docs/billing/spec/ICD.md", {
            "id": "ICD-1", "title": "i", "type": "ICD", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-01-01",
            "sources": [],
        }, "本文。\n")
        codes2, _ = self._codes(p2)
        self.assertIn("TYPE_LOCATION_MISMATCH", codes2)

    def test_domain_path_mismatch(self):
        """§3.4: domain:billing but path under identity/ -> DOMAIN_PATH_MISMATCH."""
        p = self._write("docs/identity/spec/SPEC-1-x.md",
                        _valid_spec_fm(id="SPEC-1", domain="billing",
                                       depends_on=["REQ-2"]),
                        _SPEC_BODY_4)
        self._write("docs/identity/REQ-2-x.md",
                    _req_fm(domain="identity"), "本文。\n")
        codes, _ = self._codes(p)
        self.assertIn("DOMAIN_PATH_MISMATCH", codes)

    def test_domain_path_mismatch_involving_system(self):
        """§3.4: _system が片側に絡む domain↔path 不一致も検出する(変異体監査)。

        L379 の `path_domain == \"_system\" and declared == \"_system\"` の
        どちらの == を != に反転しても不一致が抑止されるため、両方向を固定する。
        """
        # (1) domain:_system だが billing/ 配下 -> DOMAIN_PATH_MISMATCH
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(domain="_system"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertIn("DOMAIN_PATH_MISMATCH", codes)
        # (2) _system/ 配下だが domain:billing -> DOMAIN_PATH_MISMATCH
        p2 = self._write("docs/_system/decided-facts.md", {
            "id": "DECIDED-1", "title": "d", "type": "DECIDED",
            "domain": "billing", "status": "current", "owner": "a",
            "updated": "2026-01-01", "review_by": "2027-01-01",
            "sources": [],
        }, "事実。\n")
        codes2, _ = self._codes(p2)
        self.assertIn("DOMAIN_PATH_MISMATCH", codes2)

    def test_watch_two_locations(self):
        """TC: WATCH allowed in _system/ AND in <domain>/test/."""
        p1 = self._write("docs/_system/watchlist.md", {
            "id": "WATCH-1", "title": "w", "type": "WATCH", "domain": "_system",
            "status": "current", "owner": "a", "updated": "2026-01-01",
            "review_by": "2027-01-01", "sources": [],
        }, "本文。\n")
        c1, _ = self._codes(p1)
        self.assertNotIn("TYPE_LOCATION_MISMATCH", c1)
        # #04/#05a: watchlist.md is the spec-fixed WATCH 正本 path (§3.7); its
        # name does NOT encode the id (WATCH-1), so the id<->filename check must
        # be skipped — no false ID_FILENAME_MISMATCH.
        self.assertNotIn("ID_FILENAME_MISMATCH", c1)
        p2 = self._write("docs/billing/test/WATCH-2-x.md", {
            "id": "WATCH-2", "title": "w", "type": "WATCH", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-01-01",
            "review_by": "2027-01-01", "sources": [],
        }, "本文。\n")
        c2, _ = self._codes(p2)
        self.assertNotIn("TYPE_LOCATION_MISMATCH", c2)


# ---------------------------------------------------------------------------
# Required keys / empty keys (§3.4 — TC-047..050)
# ---------------------------------------------------------------------------
class RequiredKeysTest(_Base):
    def test_tc048_missing_owner(self):
        """TC-048: drop owner -> MISSING_KEY."""
        fm = _valid_spec_fm()
        del fm["owner"]
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)
        codes, ctx = self._codes(p)
        self.assertIn("MISSING_KEY", codes)
        self.assertIn("owner", ctx)

    def test_tc049_decided_missing_review_by(self):
        """TC-049: DECIDED missing review_by -> MISSING_KEY."""
        p = self._write("docs/_system/decided-facts.md", {
            "id": "DECIDED-1", "title": "d", "type": "DECIDED",
            "domain": "_system", "status": "current", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "事実。\n")
        codes, ctx = self._codes(p)
        self.assertIn("MISSING_KEY", codes)
        self.assertIn("review_by", ctx)

    def test_tc050_watch_missing_review_by(self):
        """TC-050: WATCH missing review_by -> MISSING_KEY."""
        p = self._write("docs/_system/watchlist.md", {
            "id": "WATCH-1", "title": "w", "type": "WATCH",
            "domain": "_system", "status": "current", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "本文。\n")
        codes, _ = self._codes(p)
        self.assertIn("MISSING_KEY", codes)

    def test_empty_owner_flagged_but_empty_sources_allowed(self):
        """§3.1: empty owner -> EMPTY_KEY; sources:[] -> NOT flagged."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(owner=None), _SPEC_BODY_4)
        codes, ctx = self._codes(p)
        self.assertIn("EMPTY_KEY", codes)
        # sources:[] must NOT produce EMPTY_KEY for sources.
        self.assertNotIn("sources", ctx.split("EMPTY_KEY")[1] if "EMPTY_KEY" in ctx else "")

    def test_missing_status_flagged_not_crashed(self):
        """status キー欠落 -> MISSING_KEY のみ。クラッシュも BAD_STATUS も出ない
        (変異体監査: _check_status の early-return ガード or->and)。"""
        fm = _valid_spec_fm()
        del fm["status"]
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)
        codes, ctx = self._codes(p)
        self.assertIn("MISSING_KEY", codes)
        self.assertIn("status", ctx)
        self.assertNotIn("BAD_STATUS", codes)
        self.assertNotIn("internal error", ctx)

    def test_missing_domain_flagged_not_crashed(self):
        """domain キー欠落 -> MISSING_KEY のみ。DOMAIN_PATH_MISMATCH 誤検出も
        クラッシュも無し(変異体監査: _check_domain_path のガード or->and)。"""
        fm = _valid_spec_fm()
        del fm["domain"]
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)
        codes, ctx = self._codes(p)
        self.assertIn("MISSING_KEY", codes)
        self.assertNotIn("DOMAIN_PATH_MISMATCH", codes)
        self.assertNotIn("internal error", ctx)

    def test_spec_with_review_by_not_required_no_flag(self):
        """§B1: review_by present on a SPEC (not required) -> not flagged missing."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(review_by="2027-01-01"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_KEY", codes)


# ---------------------------------------------------------------------------
# llm_context value (§3.5 — TC-057/058)
# ---------------------------------------------------------------------------
class LlmContextTest(_Base):
    def test_tc057_matching_default_ok(self):
        """TC-057: llm_context:task on SPEC (matches default) -> no finding."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(llm_context="task"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("BAD_LLM_CONTEXT", codes)

    def test_tc058_bogus_value_error(self):
        """TC-058: llm_context:bogus -> BAD_LLM_CONTEXT (ERROR)."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(llm_context="bogus"), _SPEC_BODY_4)
        out, _ = self._lint(p)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BAD_LLM_CONTEXT", ctx)
        self.assertIn("[ERROR]", ctx.split("BAD_LLM_CONTEXT")[0].rsplit("\n", 1)[-1]
                      + "BAD_LLM_CONTEXT")

    def test_override_default_is_warn(self):
        """§3.5: RESEARCH with llm_context:task (overrides 'never') -> WARN."""
        p = self._write("docs/billing/research/RESEARCH-1-x.md", {
            "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
            "domain": "billing", "status": "draft", "owner": "a",
            "updated": "2026-01-01", "llm_context": "task", "sources": [],
        }, "調査。\n")
        out, _ = self._lint(p)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BAD_LLM_CONTEXT", ctx)
        # the override line is WARN, not ERROR.
        for line in ctx.splitlines():
            if "BAD_LLM_CONTEXT" in line:
                self.assertIn("[WARN]", line)


class BadDateTest(_Base):
    """ADR-100: 日付の鍵が解せなければ咎める。重さは鍵で分ける。"""

    def _spec_with(self, **extra):
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        fm = _valid_spec_fm()
        fm.update(extra)
        return self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)

    def test_valid_date_is_silent(self):
        codes, _ = self._codes(self._spec_with(updated="2026-01-01"))
        self.assertNotIn("BAD_DATE", codes)

    def test_broken_updated_is_error(self):
        out, _ = self._lint(self._spec_with(updated="2026-13-45"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BAD_DATE", ctx)
        for line in ctx.splitlines():
            if "BAD_DATE" in line:
                self.assertIn("[ERROR]", line)

    def test_nonexistent_day_is_caught(self):
        """形は合っていても実在しない日付は咎める(2026-02-30)。"""
        codes, _ = self._codes(self._spec_with(updated="2026-02-30"))
        self.assertIn("BAD_DATE", codes)

    def test_trailing_garbage_is_caught(self):
        """終端の錨(ADR-099)。`2026-01-01xyz` を通さない。"""
        codes, _ = self._codes(self._spec_with(updated="2026-01-01xyz"))
        self.assertIn("BAD_DATE", codes)

    def test_created_is_only_a_warning(self):
        """created は必須キーではないので警告に留める。"""
        out, _ = self._lint(self._spec_with(created="2026-13-45"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        lines = [l for l in ctx.splitlines() if "BAD_DATE" in l]
        self.assertTrue(lines, ctx)
        for line in lines:
            self.assertIn("[WARN]", line)

    def test_absent_date_is_not_a_bad_date(self):
        """不在は必須キーの検査の領分。二重に鳴らさない。"""
        fm = _valid_spec_fm()
        fm.pop("updated", None)
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("BAD_DATE", codes)
        self.assertIn("MISSING_KEY", codes)


class PlaceholderTest(_Base):
    """ADR-098: 雛形の指示文が残ったフロントマターを咎める。"""

    def _spec_with(self, **extra):
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        fm = _valid_spec_fm()
        fm.update(extra)
        return self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)

    def test_clean_frontmatter_is_silent(self):
        codes, _ = self._codes(self._spec_with())
        self.assertNotIn("PLACEHOLDER_VALUE", codes)

    def test_owner_placeholder_is_error(self):
        out, _ = self._lint(self._spec_with(owner="<個人名>"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("PLACEHOLDER_VALUE", ctx)
        for line in ctx.splitlines():
            if "PLACEHOLDER_VALUE" in line:
                self.assertIn("[ERROR]", line)

    def test_partial_value_is_caught(self):
        """雛形は `id: SPEC-<連番>` のように値の一部へ置く。"""
        codes, _ = self._codes(self._spec_with(title="SPEC-<連番> の話"))
        self.assertIn("PLACEHOLDER_VALUE", codes)

    def test_list_element_is_caught(self):
        codes, _ = self._codes(self._spec_with(sources=["<出所URL/会話ID>"]))
        self.assertIn("PLACEHOLDER_VALUE", codes)

    def test_body_angle_brackets_are_not_reported(self):
        """本文の山括弧は咎めない(`<svg>`・置き場所の記法・id の書式が正当に出る)。"""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        body = (_SPEC_BODY_4
                + "\n置き場所は <domain>/ とし、id は <TYPE>-<NNN> の形にする。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md", _valid_spec_fm(), body)
        codes, _ = self._codes(p)
        self.assertNotIn("PLACEHOLDER_VALUE", codes)


class SubdomainTest(_Base):
    """ADR-092: ドメインの種類の語彙を検める。省略は未分類で咎めない。"""

    def _spec_with(self, **extra):
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        fm = _valid_spec_fm()
        fm.update(extra)
        return self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)

    def test_absent_is_unclassified(self):
        """省略 -> 所見なし。既存の木で所見が一件も増えないことの根拠。"""
        codes, _ = self._codes(self._spec_with())
        self.assertNotIn("BAD_SUBDOMAIN", codes)

    def test_empty_is_unclassified(self):
        """空文字 -> 省略と同じに扱う(未分類)。"""
        codes, _ = self._codes(self._spec_with(subdomain=""))
        self.assertNotIn("BAD_SUBDOMAIN", codes)

    def test_each_kind_accepted(self):
        """三語はいずれも通る。"""
        for kind in ("core", "supporting", "generic"):
            codes, _ = self._codes(self._spec_with(subdomain=kind))
            self.assertNotIn("BAD_SUBDOMAIN", codes, kind)

    def test_bogus_value_is_error(self):
        """語彙に無い値 -> BAD_SUBDOMAIN (ERROR)。門そのものが落ちることの実測。"""
        out, _ = self._lint(self._spec_with(subdomain="CORE_DOMAIN"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("BAD_SUBDOMAIN", ctx)
        for line in ctx.splitlines():
            if "BAD_SUBDOMAIN" in line:
                self.assertIn("[ERROR]", line)

    def test_non_string_value_is_unclassified(self):
        """真偽値・一覧は未分類として黙る(解析器が str 以外に解す値。判定を書けない)。

        数の見た目の値は解析器が文字列にするので(`subdomain: 3` -> '3')、
        語彙に無い値として咎める。下の試験がそれを凍らせる。
        """
        for bad in (True, ["core"]):
            codes, _ = self._codes(self._spec_with(subdomain=bad))
            self.assertNotIn("BAD_SUBDOMAIN", codes, repr(bad))

    def test_numeric_looking_value_is_reported(self):
        """`subdomain: 3` は文字列 '3' に解されるので、語彙に無い値として咎める。"""
        codes, _ = self._codes(self._spec_with(subdomain=3))
        self.assertIn("BAD_SUBDOMAIN", codes)

    def test_same_domain_may_hold_different_kinds(self):
        """ADR-092: 同じ domain の中に種類が同居してよい(一貫性の検査を入れない)。

        呼び手の木はドメインが一つで三種類を含む。検査を足せばこの試験が落ちる。
        """
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        fm1 = _valid_spec_fm()
        fm1["subdomain"] = "core"
        p1 = self._write("docs/billing/spec/SPEC-014-x.md", fm1, _SPEC_BODY_4)
        fm2 = _valid_spec_fm()
        fm2["id"] = "SPEC-015"
        fm2["subdomain"] = "generic"
        p2 = self._write("docs/billing/spec/SPEC-015-x.md", fm2, _SPEC_BODY_4)
        for p in (p1, p2):
            codes, _ = self._codes(p)
            self.assertNotIn("BAD_SUBDOMAIN", codes, p)


# ---------------------------------------------------------------------------
# RESEARCH 決定 heading (§3.6 — TC-109/110)
# ---------------------------------------------------------------------------
class ResearchDecisionTest(_Base):
    def test_tc109_research_without_decision_ok(self):
        p = self._write("docs/billing/research/RESEARCH-1-x.md", {
            "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
            "domain": "billing", "status": "draft", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "## 調査\n本文。\n")
        codes, _ = self._codes(p)
        self.assertNotIn("RESEARCH_HAS_DECISION", codes)

    def test_tc110_research_with_decision_heading_warn(self):
        p = self._write("docs/billing/research/RESEARCH-1-x.md", {
            "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
            "domain": "billing", "status": "draft", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "## 決定\nこれは決めた。\n")
        out, _ = self._lint(p)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("RESEARCH_HAS_DECISION", ctx)
        for line in ctx.splitlines():
            if "RESEARCH_HAS_DECISION" in line:
                self.assertIn("[WARN]", line)

    def test_suffix_that_makes_another_word_not_flagged(self):
        """ADR-082 / #169: 『決定的』『決定論』は『決定』ではない。見出しに『決定』を
        含むだけで咎めていたため、`## 決定的な一点：…` が決定を書いたものとして扱われた。
        2026-08-02 に実測した誤検出である。"""
        for heading in ("## 決定的な一点：検証とは証拠の提示である",
                        "## 決定論との違い"):
            p = self._write("docs/billing/research/RESEARCH-1-x.md", {
                "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
                "domain": "billing", "status": "draft", "owner": "a",
                "updated": "2026-01-01", "sources": [],
            }, "%s\n本文。\n" % heading)
            codes, _ = self._codes(p)
            self.assertNotIn("RESEARCH_HAS_DECISION", codes, heading)

    def test_decision_heading_with_qualifier_still_flagged(self):
        """除くのは語を別語にする二つの接尾だけである。『決定』を主題にした見出しは
        引き続き咎める(精度を上げただけで、検査をやめたのではない)。"""
        for heading in ("## 決定", "## 決定の背景", "## 我々の決定事項"):
            p = self._write("docs/billing/research/RESEARCH-1-x.md", {
                "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
                "domain": "billing", "status": "draft", "owner": "a",
                "updated": "2026-01-01", "sources": [],
            }, "%s\n本文。\n" % heading)
            codes, _ = self._codes(p)
            self.assertIn("RESEARCH_HAS_DECISION", codes, heading)

    def test_decision_in_prose_only_not_flagged(self):
        """§3.6: 決定 only in prose (not a heading) -> not flagged."""
        p = self._write("docs/billing/research/RESEARCH-1-x.md", {
            "id": "RESEARCH-1", "title": "r", "type": "RESEARCH",
            "domain": "billing", "status": "draft", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "## 調査\n決定はまだしていない。\n")
        codes, _ = self._codes(p)
        self.assertNotIn("RESEARCH_HAS_DECISION", codes)


# ---------------------------------------------------------------------------
# SPEC 4 sections (§3.7 — TC-059/060/061)
# ---------------------------------------------------------------------------
class SpecSectionsTest(_Base):
    def setUp(self):
        super().setUp()
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")

    def test_tc060_missing_section(self):
        """TC-060: SPEC missing エラー時挙動 -> MISSING_SECTION."""
        body = "## 入出力\nx\n## 制約\nx\n## 受入基準\nx\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        codes, ctx = self._codes(p)
        self.assertIn("MISSING_SECTION", codes)
        self.assertIn("エラー時挙動", ctx)

    def test_tc061_empty_section(self):
        """TC-061: 受入基準 heading present but empty body -> EMPTY_SECTION."""
        body = ("## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\n\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        codes, ctx = self._codes(p)
        self.assertIn("EMPTY_SECTION", codes)
        self.assertIn("受入基準", ctx)

    def test_tc059_all_four_present(self):
        """TC-059: all 4 sections non-empty -> no SPEC section findings."""
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_SECTION", codes)
        self.assertNotIn("EMPTY_SECTION", codes)


# ---------------------------------------------------------------------------
# Traceability (§3.10 — TC-040/111/112)
# ---------------------------------------------------------------------------
class TraceabilityTest(_Base):
    def test_tc112_spec_without_trace_flagged(self):
        """TC-040/112: SPEC with no [R]/REQ/depends_on -> MISSING_TRACE."""
        fm = _valid_spec_fm()
        del fm["depends_on"]
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertIn("MISSING_TRACE", codes)

    def test_tc111_spec_with_depends_on_passes(self):
        """TC-111: SPEC with depends_on to a REQ -> no MISSING_TRACE."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_TRACE", codes)

    def test_r_tag_in_body_satisfies_trace(self):
        """§3.10: a [R3] tag in the body satisfies traceability (Level-2)."""
        fm = _valid_spec_fm()
        del fm["depends_on"]
        body = _SPEC_BODY_4 + "\n本仕様は [R3] を満たす。\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, body)
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_TRACE", codes)

    def test_impl_without_trace_flagged(self):
        """Final-verify #2 / R3: an IMPL with no [R]/REQ/depends_on -> MISSING_TRACE.
        Locks IMPL in the SPEC/IMPL/TEST traceability set (docs-linter type tuple),
        not only SPEC — a regression dropping IMPL would otherwise go unnoticed."""
        fm = {"id": "IMPL-1", "title": "i", "type": "IMPL", "domain": "billing",
              "status": "current", "owner": "a", "updated": "2026-01-01",
              "sources": []}
        p = self._write("docs/billing/implementation/IMPL-1-x.md", fm, "実装本文。\n")
        codes, _ = self._codes(p)
        self.assertIn("MISSING_TRACE", codes)

    def test_test_without_trace_flagged(self):
        """Final-verify #2 / R3: a TEST with no [R]/REQ/depends_on -> MISSING_TRACE."""
        fm = {"id": "TEST-1", "title": "t", "type": "TEST", "domain": "billing",
              "status": "current", "owner": "a", "updated": "2026-01-01",
              "sources": []}
        p = self._write("docs/billing/test/TEST-1-x.md", fm, "試験本文。\n")
        codes, _ = self._codes(p)
        self.assertIn("MISSING_TRACE", codes)

    def test_impl_and_test_with_depends_on_pass(self):
        """Positive companion: IMPL and TEST WITH depends_on -> no MISSING_TRACE."""
        impl = {"id": "IMPL-1", "title": "i", "type": "IMPL", "domain": "billing",
                "status": "current", "owner": "a", "updated": "2026-01-01",
                "depends_on": ["SPEC-014"], "sources": []}
        pi = self._write("docs/billing/implementation/IMPL-1-x.md", impl, "実装本文。\n")
        self.assertNotIn("MISSING_TRACE", self._codes(pi)[0])
        test = {"id": "TEST-1", "title": "t", "type": "TEST", "domain": "billing",
                "status": "current", "owner": "a", "updated": "2026-01-01",
                "depends_on": ["SPEC-014"], "sources": []}
        pt = self._write("docs/billing/test/TEST-1-x.md", test, "試験本文。\n")
        self.assertNotIn("MISSING_TRACE", self._codes(pt)[0])


# ---------------------------------------------------------------------------
# Level-2 reduced config: L3/L4 keys absent must NOT be flagged (TC-039/120)
# ---------------------------------------------------------------------------
class LevelTwoReducedTest(_Base):
    def test_tc039_l2_missing_l3_keys_not_flagged(self):
        """TC-039/120: a Level-2 SPEC lacking depends_on/impacts/canonical_for
        draws no MISSING_KEY for those (they are not required at L2)."""
        fm = _valid_spec_fm()
        del fm["depends_on"]            # rely on a [R] tag instead
        body = _SPEC_BODY_4 + "\n要求 [R1] を満たす。\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md", fm, body)
        codes, ctx = self._codes(p)
        self.assertNotIn("MISSING_KEY", codes)
        self.assertNotIn("depends_on", ctx)
        self.assertNotIn("impacts", ctx)
        self.assertNotIn("canonical_for", ctx)


# ---------------------------------------------------------------------------
# term-check integration (advisory, no block) — TC-122/063/066
# ---------------------------------------------------------------------------
class TermCheckIntegrationTest(_Base):
    def test_tc122_calque_in_valid_spec_advisory_only(self):
        """TC-122: structurally-valid SPEC with a calque -> term-check advisory,
        no block, structural checks pass."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        body = _SPEC_BODY_4 + "\nここで針を動かす必要がある。\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        out, code = self._lint(p)
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertNotIn("decision", obj)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("CALQUE", ctx)
        # structural codes absent
        self.assertNotIn("MISSING_SECTION", ctx)
        self.assertNotIn("BAD_STATUS", ctx)

    def test_tc063_banned_synonym_surfaced(self):
        """TC-063: body uses banned synonym ドキュメント -> BANNED_SYNONYM."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        body = _SPEC_BODY_4 + "\nこのドキュメントを参照する。\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        codes, _ = self._codes(p)
        self.assertIn("BANNED_SYNONYM", codes)

    def test_mandated_io_heading_not_false_flagged(self):
        """Risk: the mandated 入出力 heading must NOT draw a 出力->投影 synonym."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("BANNED_SYNONYM", codes)


# ---------------------------------------------------------------------------
# ICD-dep post-detection (§3.9 — TC-070/071/072 advisory form)
# ---------------------------------------------------------------------------
class IcdDepTest(_Base):
    def _setup_identity_icd(self):
        self._write("docs/identity/ICD.md", {
            "id": "ICD-09", "title": "Identity ICD", "type": "ICD",
            "domain": "identity", "status": "current", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "公開境界。\n")
        self._write("docs/identity/spec/SPEC-22-internal.md", {
            "id": "SPEC-22", "title": "internal", "type": "SPEC",
            "domain": "identity", "status": "current", "owner": "a",
            "updated": "2026-01-01", "depends_on": [], "sources": [],
        }, _SPEC_BODY_4 + "\n[R9]\n")
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")

    def test_tc070_cross_domain_icd_ok(self):
        """TC-070: billing depends_on identity ICD-09 (cross-domain ICD) -> ok."""
        self._setup_identity_icd()
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(depends_on=["ICD-09", "REQ-2"]),
                        _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("ICD_DEP_VIOLATION", codes)

    def test_tc071_cross_domain_non_icd_violation(self):
        """TC-071: billing depends_on identity SPEC-22 (internal) ->
        ICD_DEP_VIOLATION advisory (ERROR), never a decision."""
        self._setup_identity_icd()
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(depends_on=["SPEC-22", "REQ-2"]),
                        _SPEC_BODY_4)
        out, code = self._lint(p)
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertNotIn("decision", obj)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ICD_DEP_VIOLATION", ctx)
        # exact guard phrasing per §4.2
        self.assertIn("SPEC-22 は identity の内部です。", ctx)

    def test_tc072_same_domain_ok(self):
        """TC-072: same-domain internal dep -> no violation."""
        self._setup_identity_icd()
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(depends_on=["REQ-2"]), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("ICD_DEP_VIOLATION", codes)

    def test_unresolvable_dep_is_unverified_warn(self):
        """§3.9: a dep the graph can't resolve -> ICD_DEP_UNVERIFIED WARN
        (linter degrades; never denies — guard/audit are authoritative)."""
        self._write("docs/billing/REQ-2-x.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(depends_on=["XYZ-99", "REQ-2"]),
                        _SPEC_BODY_4)
        out, _ = self._lint(p)
        obj = json.loads(out)
        ctx = obj["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ICD_DEP_UNVERIFIED", ctx)
        for line in ctx.splitlines():
            if "ICD_DEP_UNVERIFIED" in line:
                self.assertIn("[WARN]", line)


# ---------------------------------------------------------------------------
# Robustness (§5 / §8.C)
# ---------------------------------------------------------------------------
class RobustnessTest(_Base):
    def test_argv_fallback_when_no_stdin(self):
        """§8.C: empty stdin + argv path -> uses argv."""
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(status="accepted"), _SPEC_BODY_4)
        out, code = _util.invoke(DL, argv=[p], stdin_obj=None)
        self.assertEqual(code, 0)
        self.assertIn("BAD_STATUS", out)

    def test_malformed_frontmatter(self):
        """§8.C: 統治木の中の frontmatter 無しファイル -> MISSING_FRONTMATTER, exit 0.

        ADR-024: 統治木の外(木なし)なら無発火なので、木の印 docs/_system を置く。
        """
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        path = os.path.join(self.root, "docs", "billing", "spec", "x.md")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# no frontmatter here\n本文だけ。\n")
        out, code = self._lint(path)
        self.assertEqual(code, 0)
        self.assertIn("MISSING_FRONTMATTER", out)

    def test_non_md_path_empty(self):
        """§8.C: non-.md path -> empty output, exit 0."""
        path = os.path.join(self.root, "docs", "notes.txt")
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as fh:
            fh.write("x")
        out, code = self._lint(path)
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_deleted_file_empty(self):
        """§8.C: a path no longer on disk -> empty output, exit 0."""
        path = os.path.join(self.root, "docs", "billing", "spec", "gone.md")
        out, code = self._lint(path)
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_no_path_anywhere_empty(self):
        """No stdin path and no argv -> empty output, exit 0."""
        out, code = _util.invoke(DL, argv=[], stdin_obj="")
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_tool_response_filepath_fallback(self):
        """§5.1: path resolved from tool_response.filePath when tool_input lacks it."""
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(status="accepted"), _SPEC_BODY_4)
        stdin = _util.hook_stdin(
            "PostToolUse", tool_name="Edit", tool_input={},
            tool_response={"filePath": p})
        out, code = _util.invoke(DL, stdin_obj=stdin)
        self.assertEqual(code, 0)
        self.assertIn("BAD_STATUS", out)

    def test_typed_doc_outside_docs_tree_flagged_stray(self):
        """ADR-021/024: 登録簿の型を持つ .md が統治木のサブツリーの外 -> STRAY_DOCUMENT。

        統治木は在る(walkup が根を見つける)が、ファイルは docs/ の下でない。
        型付きなので intake 免除には入らず STRAY を出す(ADR-024 の②)。
        """
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        path = os.path.join(self.root, "notes", "SPEC-014-x.md")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_valid_spec_fm()) + _SPEC_BODY_4)
        codes, _ = self._codes(path)
        self.assertIn("STRAY_DOCUMENT", codes)

    def test_typed_doc_inside_docs_tree_not_stray(self):
        """docs/ の中の型付き文書には STRAY_DOCUMENT を出さない。"""
        self._write("docs/billing/REQ-2-refunds.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-refund-policy.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("STRAY_DOCUMENT", codes)

    def test_registered_non_document_no_schema_error(self):
        """ADR-024: intake に「非文書」と登録された型なし .md は schema 強制しない。

        統治木は在り、その _system/.md-intake に MEMO.md を非文書として登録する。
        frontmatter が無くても MISSING_FRONTMATTER も STRAY_DOCUMENT も出さない
        (用語助言のみ WARN)。監査(非文書と認める)と判定が一致する。
        """
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "_system", ".md-intake"),
                  "w", encoding="utf-8") as fh:
            fh.write("MEMO.md: 非文書\n")
        path = os.path.join(self.root, "MEMO.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# メモ\n本文。\n")
        codes, ctx = self._codes(path)
        self.assertNotIn("STRAY_DOCUMENT", codes)
        self.assertNotIn("MISSING_FRONTMATTER", codes)
        self.assertNotIn("[ERROR]", ctx)

    def test_registered_view_without_stamp_warns(self):
        """ADR-073: intake に「ビュー」と登録された型なし .md に刻印が無ければ
        VIEW_MISSING_STAMP(WARN)を助言する。schema 強制はしない。"""
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "_system", ".md-intake"),
                  "w", encoding="utf-8") as fh:
            fh.write("V.md: ビュー\n")
        path = os.path.join(self.root, "V.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# ビューの本文\n")
        codes, ctx = self._codes(path)
        self.assertIn("VIEW_MISSING_STAMP", codes)
        self.assertNotIn("MISSING_FRONTMATTER", codes)
        self.assertNotIn("[ERROR]", ctx)

    def test_registered_view_with_stamp_silent(self):
        """刻印を持つビューには VIEW_MISSING_STAMP を出さない。"""
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "_system", ".md-intake"),
                  "w", encoding="utf-8") as fh:
            fh.write("V.md: ビュー\n")
        path = os.path.join(self.root, "V.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# ビューの本文\n\n"
                     "<!-- doctrine:view src=repo as-of=1.0.0 "
                     "date=2026-07-28 refs=SPEC-1 -->\n")
        codes, _ = self._codes(path)
        self.assertNotIn("VIEW_MISSING_STAMP", codes)

    def test_unknown_string_type_flagged(self):
        """§3.2: 登録簿に無い文字列型 -> UNKNOWN_TYPE(ミューテーション監査の穴埋め)。"""
        self._write("docs/billing/REQ-2-refunds.md", _req_fm(), "本文。\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(type="BOGUS"), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertIn("UNKNOWN_TYPE", codes)

    def test_list_valued_type_flagged_not_crashed(self):
        """§8.C: `type: [SPEC]` (one-char YAML typo) must NOT abort the lint.

        Regression: this used to raise TypeError (unhashable list) inside the
        registry lookup, and the catch-all swallowed every other finding as
        'internal error'. It must now flag UNKNOWN_TYPE and keep the remaining
        checks alive (the doc below also lacks the SPEC 4 sections)."""
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        path = os.path.join(self.root, "docs", "billing", "spec",
                            "SPEC-014-x.md")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\n"
                     "id: SPEC-014\ntitle: t\ntype: [SPEC]\ndomain: billing\n"
                     "status: current\nowner: a\nupdated: 2026-01-01\n"
                     "sources: []\n---\n本文。\n")
        out, code = self._lint(path)
        self.assertEqual(code, 0)
        self.assertIn("UNKNOWN_TYPE", out)
        self.assertNotIn("internal error", out)

    def test_out_of_tree_doc_not_linted(self):
        """ADR-024: 統治木の根に到達できない体系外の .md は点検しない(無発火)。

        以前は fail-open で「木の外でも点検」していたが、ADR-024 で反転した。
        統治木が無いパスは doctrine の管轄外。ERROR も出さず、クラッシュもしない。
        """
        p = self._write("stray/REQ-9-x.md",
                        _req_fm(id="REQ-9", status="bogus"), "本文。\n")
        codes, ctx = self._codes(p)
        self.assertEqual(codes, set())
        self.assertNotIn("internal error", ctx)

    def test_list_valued_status_flagged_not_crashed(self):
        """§8.C: `status: [current]` -> BAD_STATUS, no internal error."""
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        path = os.path.join(self.root, "docs", "billing", "spec",
                            "SPEC-014-x.md")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\n"
                     "id: SPEC-014\ntitle: t\ntype: SPEC\ndomain: billing\n"
                     "status: [current]\nowner: a\nupdated: 2026-01-01\n"
                     "sources: []\n---\n" + _SPEC_BODY_4)
        out, code = self._lint(path)
        self.assertEqual(code, 0)
        self.assertIn("BAD_STATUS", out)
        self.assertNotIn("internal error", out)


if __name__ == "__main__":
    unittest.main()


# 型ごとの必須節を手で書き写した表(ADR-060 の様式。test_audit の AUDIT_CHECKS と同じ)。
# 正本は _registry.REQUIRED_SECTIONS。節を足す・消すときは**両方**を同じ変更で更新する。
# **ここを正本から生成したら凍結の意味が消える。**
#
# 一覧は実態を測って決めた(ADR-090): 統治木 203 文書で雛形と本文を突き合わせ、ある型の
# 文書が 100% ずれているなら雛形が誤りと判じた。CHANGE は六件すべてが『理由』と『要求元』を
# 一節に統合しており、RESEARCH は四件すべてが主題ごとの見出しで書かれていた。
EXPECTED_REQUIRED_SECTIONS = {
    "ADR": ("背景", "却下した選択肢", "決定", "帰結"),
    "API": ("エンドポイント", "入出力", "エラー"),
    "ARCHIVE": ("アーカイブ理由", "アーカイブ日", "後継ID"),
    "CHANGE": ("変更内容", "理由（要求元）", "影響の初期見積"),
    "DATA": ("エンティティ", "保存方針", "保持期間"),
    "DECIDED": ("確定方針", "決定日", "根拠ADR", "再点検期限"),
    "EXT": ("何に依存しているか", "期待", "動いたら何が壊れるか"),
    "ICD": ("公開する用語", "正本である事実", "データ契約", "依存してよい入口"),
    "IMPACT": ("影響する文書", "影響する実装", "影響するテスト", "工数見積"),
    "IMPL": ("実装制約", "注意点", "対象部品"),
    "NONGOAL": ("やらないこと", "理由"),
    "PROC": ("目的と発動条件", "前提", "手順", "切り戻し"),
    "REQ": ("要求文", "優先度", "受入基準参照", "出所"),
    "SPEC": ("入出力", "制約", "エラー時挙動", "受入基準"),
    "TEST": ("受入基準への対応", "退行観点", "合否基準"),
    "WATCH": ("戻してはならない事項", "撤回日", "根拠", "再点検期限"),
}


class RequiredSectionsFreezeTest(unittest.TestCase):
    """必須節の一覧を手書きの表で凍らせる(ADR-060 の様式。ADR-090)。"""

    def test_table_matches_the_transcription(self):
        reg = _util.load_core("_registry")
        self.assertEqual(
            {k: tuple(v) for k, v in reg.REQUIRED_SECTIONS.items()},
            EXPECTED_REQUIRED_SECTIONS,
            "必須節が変わった。正本(_registry.REQUIRED_SECTIONS)と手書きの表の両方を"
            "同じ変更で更新すること(片方だけ直すと、節を足しても黙って通る状態へ戻る)")

    def test_research_and_projections_are_not_charged(self):
        """形を課さない型(ADR-090)。調査は探索であり、投影は機械が描く。"""
        reg = _util.load_core("_registry")
        for t in ("RESEARCH", "OVERVIEW", "CTXMAP", "GLOSSARY"):
            self.assertEqual(reg.required_sections(t), (), t)


class GeneralSectionCheckTest(_Base):
    """ADR-090 / #154: 雛形が定める節を全型で検める。

    以前は SPEC の四節だけが検められ、他の 15 型は雛形が定めるのに誰も咎めなかった。
    実測: この検査が無いあいだに TEST-028（2026-08-02 に書かれた文書）が
    退行観点・合否基準 を欠いたまま通っていた。
    """

    def _write_typed(self, type_code, body, subdir, fname):
        return self._write("docs/billing/%s/%s" % (subdir, fname), {
            "id": fname.split("-")[0] + "-9", "title": "t", "type": type_code,
            "domain": "billing", "status": "current", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, body)

    def test_adr_missing_section_is_an_error(self):
        p = self._write_typed(
            "ADR", "## 背景\nx\n## 決定\ny\n## 帰結\nz\n", "decisions", "ADR-9-x.md")
        codes, _ = self._codes(p)
        self.assertIn("MISSING_SECTION", codes, "却下した選択肢 を欠くので咎めるはず")

    def test_adr_with_all_sections_is_clean(self):
        p = self._write_typed(
            "ADR", "## 背景\nx\n## 却下した選択肢\nw\n## 決定\ny\n## 帰結\nz\n",
            "decisions", "ADR-9-x.md")
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_SECTION", codes)
        self.assertNotIn("EMPTY_SECTION", codes)

    def test_empty_section_is_an_error(self):
        p = self._write_typed(
            "ADR", "## 背景\nx\n## 却下した選択肢\n\n## 決定\ny\n## 帰結\nz\n",
            "decisions", "ADR-9-x.md")
        codes, _ = self._codes(p)
        self.assertIn("EMPTY_SECTION", codes)

    def test_research_is_not_charged(self):
        """RESEARCH は節を課さない。何を書いても節では咎めない(ADR-090)。"""
        p = self._write_typed("RESEARCH", "## 好きな見出し\nx\n", "research",
                              "RESEARCH-9-x.md")
        codes, _ = self._codes(p)
        self.assertNotIn("MISSING_SECTION", codes)

    def test_issue197_no_deadlock_between_sections_and_glossary(self):
        """#197 / ADR-135: 節名を禁じる辞書の下でも袋小路にならない。

        『テスト→試験』を禁じる辞書で、雛形どおりの IMPACT は
        BANNED_SYNONYM も MISSING_SECTION も出ない。節を消せば
        MISSING_SECTION だけが出る(どちらを書いても ERROR の対が消える)。
        """
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        extended = tmpl.replace(
            "| 文書 | 管理対象の最小単位",
            "| 試験 | 検証の実行 | テスト |\n| 文書 | 管理対象の最小単位")
        gpath = os.path.join(self.root, "docs", "_system", "glossary.md")
        os.makedirs(os.path.dirname(gpath), exist_ok=True)
        with open(gpath, "w", encoding="utf-8") as f:
            f.write(extended)
        full = ("## 影響する文書\nx\n## 影響する実装\ny\n"
                "## 影響するテスト\nz\n## 工数見積\nw\n")
        p = self._write_typed("IMPACT", full, "decisions", "IMPACT-9-x.md")
        codes, ctx = self._codes(p)
        self.assertNotIn("BANNED_SYNONYM", codes, ctx)
        self.assertNotIn("MISSING_SECTION", codes, ctx)
        without = ("## 影響する文書\nx\n## 影響する実装\ny\n## 工数見積\nw\n")
        p2 = self._write_typed("IMPACT", without, "decisions", "IMPACT-8-y.md")
        codes2, _ = self._codes(p2)
        self.assertIn("MISSING_SECTION", codes2)
        self.assertNotIn("BANNED_SYNONYM", codes2)

    def test_message_names_the_type(self):
        """SPEC 専用だった時代の文言を残さない。型を名指す。"""
        p = self._write_typed("ADR", "## 背景\nx\n## 決定\ny\n## 帰結\nz\n",
                              "decisions", "ADR-9-x.md")
        out, _ = self._lint(p)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ADR の必須節", ctx)
