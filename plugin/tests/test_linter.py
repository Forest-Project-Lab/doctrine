"""Tests for docs-linter.py (PostToolUse single-doc, advisory only).

Covers MASTER §5.1 / §3.3 / §6 and design/10-scenarios.md TCs targeting the
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
        }, "公開する用語とデータ契約。\n")
        out, code = self._lint(p)
        self.assertEqual(out, "")
        self.assertEqual(code, 0)

    def test_valid_adr_accepted_no_findings(self):
        """§8.A.2 / TC-023: ADR status:accepted under decisions/ -> clean."""
        p = self._write("docs/billing/decisions/ADR-3-refund.md", {
            "id": "ADR-3", "title": "Refund ADR", "type": "ADR",
            "domain": "billing", "status": "accepted", "owner": "a",
            "updated": "2026-01-01", "sources": [],
        }, "決定の記録。\n")
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
        """TC-060: SPEC missing エラー時挙動 -> SPEC_MISSING_SECTION."""
        body = "## 入出力\nx\n## 制約\nx\n## 受入基準\nx\n"
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        codes, ctx = self._codes(p)
        self.assertIn("SPEC_MISSING_SECTION", codes)
        self.assertIn("エラー時挙動", ctx)

    def test_tc061_empty_section(self):
        """TC-061: 受入基準 heading present but empty body -> SPEC_EMPTY_SECTION."""
        body = ("## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\n\n")
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), body)
        codes, ctx = self._codes(p)
        self.assertIn("SPEC_EMPTY_SECTION", codes)
        self.assertIn("受入基準", ctx)

    def test_tc059_all_four_present(self):
        """TC-059: all 4 sections non-empty -> no SPEC section findings."""
        p = self._write("docs/billing/spec/SPEC-014-x.md",
                        _valid_spec_fm(), _SPEC_BODY_4)
        codes, _ = self._codes(p)
        self.assertNotIn("SPEC_MISSING_SECTION", codes)
        self.assertNotIn("SPEC_EMPTY_SECTION", codes)


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
        self.assertNotIn("SPEC_MISSING_SECTION", ctx)
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
        """§8.C: a file without frontmatter -> MISSING_FRONTMATTER, exit 0."""
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


if __name__ == "__main__":
    unittest.main()
