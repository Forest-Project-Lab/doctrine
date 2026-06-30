"""Tests for docs-audit.py (full-corpus audit, SessionEnd/CI) — MASTER §5.5, slice 05 PART B.

Covers every §4.2 audit finding plus the audit↔inject handshake (critique gap C3):
- dead_link (R4): TC-082 pass, TC-083 fail.
- review_by overrun incl. DECIDED/WATCH (R2): TC-084 pass, TC-085/086 fail,
  missing review_by on DECIDED/WATCH = error.
- stale_draft (R8/R2): TC-088 pass, TC-089 fail.
- orphan conjunction 逆参照ゼロ∧stale∧reproducible (R1/R8): TC-090/092 pass,
  TC-091 fail, TC-121 依存-not-参照 distinction.
- reverse_orphan req_no_spec + spec_no_test (R3/R8): TC-093 pass, TC-094/095 fail.
- canonical_conflict (R8): TC-096 pass, TC-097 fail, TC-125 superseded carrier.
- icd_dependency_violation (R7): pseudo-spec message.
- projection_drift (R1/R8): TC-098 pass, TC-099/100 fail.
- near_duplicate advisory Jaccard (R8): TC-126 advisory not error.
- SessionEnd handshake: --json --summary-out --fail-on never non-blocking,
  atomic write, exit 0; --fail-on error gates CI.
- audit summary schema docs-audit/1 round-trips as valid JSON (critique gap).

All dates controlled via --today. Stdlib unittest only.
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

TODAY = "2026-06-29"


def _fm(doc_id, type_code, domain, status="current", **extra):
    fm = {
        "id": doc_id,
        "title": doc_id,
        "type": type_code,
        "domain": domain,
        "status": status,
        "owner": "t",
        "updated": "2026-06-01",
        "sources": [],
    }
    fm.update(extra)
    return fm


def _loc(domain, type_code, doc_id):
    if type_code == "ICD":
        return "docs/%s/ICD.md" % domain
    if type_code in ("OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH"):
        # _system singletons; filename derives from a stable map
        names = {
            "OVERVIEW": "overview.md", "GLOSSARY": "glossary.md",
            "CTXMAP": "context-map.md", "DECIDED": "decided-facts.md",
            "NONGOAL": "non-goals.md", "WATCH": "watch.md",
        }
        return "docs/_system/%s" % names[type_code]
    sub = {
        "REQ": "", "SPEC": "spec/", "TEST": "test/", "IMPL": "implementation/",
        "ADR": "decisions/", "DATA": "spec/", "API": "spec/",
        "RESEARCH": "research/",
    }.get(type_code, "")
    return "docs/%s/%s%s.md" % (domain, sub, doc_id)


class AuditBase(unittest.TestCase):
    def build(self, docs, projection_bodies=None):
        """docs: list of (fm_dict, body). Writes each at its §3.2 location.

        projection_bodies lets a caller override the body for projection docs.
        Returns docs root (the 'docs' dir under the temp tree).
        """
        files = {}
        for fm, body in docs:
            relpath = _loc(fm["domain"], fm["type"], fm["id"])
            files[relpath] = _util.fm_block(fm) + (body or "")
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def audit_json(self, docs_root, extra_argv=None):
        argv = ["--root", docs_root, "--json", "--today", TODAY]
        if extra_argv:
            argv += extra_argv
        out, code = _util.invoke("docs-audit", argv)
        data = json.loads(out.strip().splitlines()[-1])
        return data, code

    def checks_for(self, data, check):
        return [f for f in data["findings"] if f["check"] == check]


# --- dead_link (TC-082/083, R4) -------------------------------------------

class DeadLinkTest(AuditBase):
    def test_all_resolve_pass(self):
        """TC-082: all depends_on/links resolve -> no dead_link."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "本文"),
            (_fm("REQ-1", "REQ", "billing"), "本文"),
        ])
        data, code = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "dead_link"), [])

    def test_dangling_dep_fail(self):
        """TC-083: depends_on a non-existent id -> dead_link error."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "本文"),
        ])
        data, code = self.audit_json(root)
        dl = self.checks_for(data, "dead_link")
        self.assertTrue(any(f["refs"] == ["SPEC-99"] for f in dl))
        self.assertTrue(all(f["severity"] == "error" for f in dl))


# --- review_by overrun (TC-084/085/086, R2) -------------------------------

class ReviewByTest(AuditBase):
    def test_future_review_by_pass(self):
        """TC-084: DECIDED review_by in the future -> no overrun."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2027-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "review_by_overrun"), [])

    def test_past_review_by_decided_fail(self):
        """TC-085: DECIDED review_by past -> warn overrun."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        rb = self.checks_for(data, "review_by_overrun")
        self.assertEqual(len(rb), 1)
        self.assertEqual(rb[0]["severity"], "warn")

    def test_past_review_by_watch_fail(self):
        """TC-086: WATCH review_by past -> warn overrun (DECIDED/WATCH included)."""
        root = self.build([
            (_fm("WATCH-1", "WATCH", "billing", review_by="2026-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(len(self.checks_for(data, "review_by_overrun")), 1)

    def test_missing_review_by_on_decided_is_error(self):
        """MASTER §5.5: missing review_by on DECIDED/WATCH = error severity."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        rb = self.checks_for(data, "review_by_overrun")
        self.assertEqual(len(rb), 1)
        self.assertEqual(rb[0]["severity"], "error")


# --- stale_draft (TC-088/089, R8/R2) --------------------------------------

class StaleDraftTest(AuditBase):
    def test_recent_draft_pass(self):
        """TC-088: RESEARCH draft recently updated -> not stale."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stale_draft"), [])

    def test_old_draft_fail(self):
        """TC-089: RESEARCH draft updated long past -> stale_draft warn."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stale_draft")
        self.assertEqual(len(sd), 1)
        self.assertEqual(sd[0]["severity"], "warn")


# --- orphan conjunction (TC-090/091/092/121, R1/R8) -----------------------

class OrphanTest(AuditBase):
    def test_depended_on_pass(self):
        """TC-090: doc depended on by a current doc -> not orphan."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["RESEARCH-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_conjunction_fail(self):
        """TC-091: zero reverse-deps ∧ stale ∧ reproducible -> orphan error."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "RESEARCH-1")
        self.assertEqual(orph[0]["severity"], "error")

    def test_not_stale_no_orphan(self):
        """TC-092: zero reverse-deps but recently updated -> NOT orphan."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_reference_not_dependency_still_orphan(self):
        """TC-121: a mere body 参照 (link) does NOT save from orphan; only 依存 does."""
        # SPEC-2 mentions RESEARCH-1 in its BODY (参照) but does not depends_on it.
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
            (_fm("SPEC-2", "SPEC", "billing"), "see RESEARCH-1 for context"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertTrue(any(f["doc_id"] == "RESEARCH-1" for f in orph))

    def test_icd_never_orphan(self):
        """Orphan excludes ICD (entry point) even with zero reverse-refs."""
        root = self.build([
            (_fm("ICD-1", "ICD", "billing", updated="2025-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_task_spec_stale_zero_dep_without_reproducible_not_orphan(self):
        """TC #12(1): current SPEC, llm_context:task, stale, zero-dep, NO reproducible
        => NOT orphan. The 'reproducible' conjunct must guard this false positive.

        A normal task-context SPEC that is merely stale and undepended-on is NOT
        reproducible (no reproducible:true, not RESEARCH, not llm_context:never),
        so the third conjunct (再現可能) fails and it is not flagged.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="task", updated="2025-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_task_spec_stale_zero_dep_with_reproducible_is_orphan(self):
        """TC #12(2): same current SPEC but reproducible:true => orphan (error).

        The third branch of _is_reproducible fires only because build_graph now
        copies the 'reproducible' field into the node dict (defect #06). Without
        that field the node.get('reproducible') would be None and this would
        silently NOT be flagged.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="task", updated="2025-01-01", reproducible=True), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "SPEC-1")
        self.assertEqual(orph[0]["severity"], "error")

    def test_stale_zero_dep_projection_not_orphan(self):
        """TC #13(a): a stale, zero-dep OVERVIEW projection is NOT orphan.

        Projections are excluded from the orphan check per MASTER §5.5
        (entry points / always-injected), regardless of staleness.
        """
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system", updated="2025-01-01"),
             "描画される。手で編集しない。\n"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_stale_zero_dep_always_doc_not_orphan(self):
        """TC #13(b): a stale, zero-dep llm_context:always doc is NOT orphan.

        llm_context:always is excluded from the orphan check per MASTER §5.5,
        even when stale and undepended-on. Use reproducible:true to show the
        exclusion fires BEFORE the reproducible conjunct could.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="always", updated="2025-01-01",
                 reproducible=True), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])


# --- reverse_orphan (TC-093/094/095, R3/R8) -------------------------------

class ReverseOrphanTest(AuditBase):
    def test_complete_chain_pass(self):
        """TC-093: every REQ has SPEC, every SPEC has TEST -> no reverse-orphan."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
            (_fm("TEST-1", "TEST", "billing", depends_on=["SPEC-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "reverse_orphan_req_no_spec"), [])
        self.assertEqual(self.checks_for(data, "reverse_orphan_spec_no_test"), [])

    def test_req_without_spec_fail(self):
        """TC-094: REQ with no SPEC pointing to it -> reverse_orphan error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        f = self.checks_for(data, "reverse_orphan_req_no_spec")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["doc_id"], "REQ-1")
        self.assertEqual(f[0]["severity"], "error")

    def test_spec_without_test_fail(self):
        """TC-095: SPEC (acceptance carrier) with no TEST -> reverse_orphan error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        f = self.checks_for(data, "reverse_orphan_spec_no_test")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["doc_id"], "SPEC-1")


# --- canonical_conflict (TC-096/097/125, R8) ------------------------------

class CanonicalConflictTest(AuditBase):
    def test_single_canonical_pass(self):
        """TC-096: single doc declares canonical_for [refund] -> no conflict."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "canonical_conflict"), [])

    def test_two_canonicals_fail(self):
        """TC-097: two current docs both canonical_for [refund] -> conflict error."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", canonical_for=["refund"]), "x"),
            (_fm("SPEC-2", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        cc = self.checks_for(data, "canonical_conflict")
        self.assertEqual(len(cc), 2)   # one per carrier
        self.assertTrue(all(f["severity"] == "error" for f in cc))

    def test_superseded_carrier_conflict(self):
        """TC-125: superseded doc still carrying canonical_for + current one -> conflict."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="superseded",
                 canonical_for=["refund"], superseded_by="SPEC-2"), "x"),
            (_fm("SPEC-2", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        cc = self.checks_for(data, "canonical_conflict")
        self.assertTrue(len(cc) >= 2)
        ids = {f["doc_id"] for f in cc}
        self.assertIn("SPEC-1", ids)
        self.assertIn("SPEC-2", ids)


# --- icd_dependency_violation (R7) ----------------------------------------

class IcdViolationTest(AuditBase):
    def test_cross_domain_non_icd_violation(self):
        """ICD violation: billing depends_on identity-internal SPEC -> error with pseudo-spec msg."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-22"]), "x"),
            (_fm("SPEC-22", "SPEC", "identity"), "x"),
        ])
        data, _ = self.audit_json(root)
        v = self.checks_for(data, "icd_dependency_violation")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["severity"], "error")
        self.assertIn("identity の内部です", v[0]["message"])
        self.assertIn("identity の ICD 宛", v[0]["message"])

    def test_cross_domain_icd_allowed(self):
        """Cross-domain dep to an ICD is allowed -> no violation."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["ICD-9"]), "x"),
            (_fm("ICD-9", "ICD", "identity"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "icd_dependency_violation"), [])


# --- projection_drift (TC-098/099/100, R1/R8) -----------------------------

class ProjectionDriftTest(AuditBase):
    def test_overview_matches_pass(self):
        """TC-098: OVERVIEW lists exactly the current source set -> no drift."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n- REQ-1\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_overview_missing_entry_fail(self):
        """TC-099: current doc added but OVERVIEW missing it -> projection drift error."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(f["refs"] == ["REQ-1"] for f in pd))
        self.assertTrue(all(f["severity"] == "error" for f in pd))

    def test_overview_extra_stale_entry_fail(self):
        """TC-100: OVERVIEW lists a removed/non-current doc -> projection drift error."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n- SPEC-9\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(f["refs"] == ["SPEC-9"] for f in pd))


# --- near_duplicate advisory (TC-126, R8) ---------------------------------

class NearDuplicateTest(AuditBase):
    def test_near_dup_is_advisory_not_error(self):
        """TC-126: highly overlapping SPEC bodies -> advisory, never error."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), shared + " alpha"),
            (_fm("SPEC-2", "SPEC", "billing"), shared + " beta"),
        ])
        data, _ = self.audit_json(root)
        nd = self.checks_for(data, "near_duplicate")
        self.assertTrue(len(nd) >= 1)
        self.assertTrue(all(f["severity"] == "advisory" for f in nd))

    def test_distinct_bodies_no_dup(self):
        """Distinct bodies -> no near_duplicate finding."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), "alpha unique words only here"),
            (_fm("SPEC-2", "SPEC", "billing"), "completely different unrelated text"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "near_duplicate"), [])


# --- summary schema + handshake (critique gap C3) -------------------------

class SummaryHandshakeTest(AuditBase):
    def _docs(self):
        return [
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "x"),
        ]

    def test_schema_shape_and_json_valid(self):
        """docs-audit/1 schema has exactly the frozen keys and round-trips as JSON."""
        root = self.build(self._docs())
        data, _ = self.audit_json(root)
        self.assertEqual(data["schema"], "docs-audit/1")
        for key in ("schema", "generated_at", "today", "root", "totals",
                    "counts_by_check", "top_findings", "findings"):
            self.assertIn(key, data)
        self.assertEqual(set(data["totals"].keys()),
                         {"error", "warn", "advisory"})
        self.assertEqual(data["today"], TODAY)
        # generated_at is deterministic-injectable from --today.
        self.assertTrue(data["generated_at"].startswith(TODAY))
        # top_findings errors-first and capped.
        self.assertLessEqual(len(data["top_findings"]), 20)
        if data["top_findings"]:
            sevs = [f["severity"] for f in data["top_findings"]]
            # all errors come before any warn/advisory
            seen_non_error = False
            for s in sevs:
                if s != "error":
                    seen_non_error = True
                elif seen_non_error:
                    self.fail("errors not first in top_findings")

    def test_summary_out_round_trip(self):
        """SessionEnd handshake: write summary to a path; it is valid docs-audit/1 JSON."""
        root = self.build(self._docs())
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, ".cache", "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", out_path,
                "--fail-on", "never", "--today", TODAY]
        out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as fh:
            persisted = json.load(fh)        # must be valid JSON
        self.assertEqual(persisted["schema"], "docs-audit/1")
        # The persisted file and stdout describe the same audit.
        stdout_data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(persisted["totals"], stdout_data["totals"])
        self.assertEqual(persisted["counts_by_check"],
                         stdout_data["counts_by_check"])

    def test_session_end_non_blocking_exit_zero(self):
        """SessionEnd: --fail-on never returns 0 even with error findings."""
        root = self.build(self._docs())   # has a dead_link error
        argv = ["--root", root, "--json", "--fail-on", "never", "--today", TODAY]
        _out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)

    def test_session_end_does_not_read_stdin(self):
        """SessionEnd contract: audit does NOT read its stdin and exits 0 regardless.

        main() never consults stdin (it depends only on argv/config). A hook
        envelope on stdin must neither change the result nor cause a hang/error:
        running with the SessionEnd envelope and with empty stdin yields the
        same stdout and exit 0. A closed/unconsumed stdin does not block.
        """
        root = self.build(self._docs())
        stdin_obj = _util.hook_stdin("SessionEnd", reason="clear")
        out_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, out_dir, ignore_errors=True)
        argv = ["--root", root, "--json", "--summary-out",
                os.path.join(out_dir, "a.json"),
                "--fail-on", "never", "--today", TODAY]
        # With the SessionEnd envelope on stdin.
        out_with, code_with = _util.invoke("docs-audit", argv, stdin_obj=stdin_obj)
        # With empty stdin (closed/unconsumed) — must be identical, no hang.
        out_empty, code_empty = _util.invoke("docs-audit", argv, stdin_obj=None)
        self.assertEqual(code_with, 0)
        self.assertEqual(code_empty, 0)
        # Stdin content does not influence the audit: byte-identical stdout.
        self.assertEqual(out_with, out_empty)

    def test_ci_fail_on_error_gates(self):
        """CI: --fail-on error exits 1 when any error finding exists."""
        root = self.build(self._docs())   # dead_link error present
        argv = ["--root", root, "--json", "--fail-on", "error", "--today", TODAY]
        _out, code = self.audit_json(root, extra_argv=["--fail-on", "error"])
        # use direct invoke to read code precisely
        out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 1)

    def test_ci_clean_corpus_exits_zero(self):
        """CI: clean corpus with no errors exits 0 under --fail-on error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
            (_fm("TEST-1", "TEST", "billing", depends_on=["SPEC-1"]), "x"),
        ])
        argv = ["--root", root, "--json", "--fail-on", "error", "--today", TODAY]
        out, code = _util.invoke("docs-audit", argv)
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["totals"]["error"], 0)
        self.assertEqual(code, 0)

    def test_atomic_write_failure_still_exit_zero(self):
        """Write fail (summary-out under a path that is a file) -> exit 0 anyway."""
        root = self.build(self._docs())
        # Point summary-out into a path whose parent is a regular file.
        blocker = os.path.join(_util.mkdtemp(), "blocker")
        with open(blocker, "w") as fh:
            fh.write("x")
        bad_out = os.path.join(blocker, "sub", "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", bad_out,
                "--fail-on", "never", "--today", TODAY]
        _out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)


# --- determinism + config knobs -------------------------------------------

class DeterminismTest(AuditBase):
    def test_deterministic_output(self):
        """Same corpus + same --today -> byte-identical JSON (sorted keys)."""
        docs = [
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "x"),
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-01-01"), "y"),
        ]
        root = self.build(docs)
        out1, _ = _util.invoke("docs-audit",
                               ["--root", root, "--json", "--today", TODAY])
        out2, _ = _util.invoke("docs-audit",
                               ["--root", root, "--json", "--today", TODAY])
        self.assertEqual(out1, out2)

    def test_config_today_overrides(self):
        """--config today is honored when --today absent (review_by overrun keys on it)."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-06-15"), "x"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"today": "2026-06-29"}, fh)
        out, _ = _util.invoke("docs-audit",
                              ["--root", root, "--json", "--config", cfg])
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["today"], "2026-06-29")
        self.assertEqual(len(self.checks_for(data, "review_by_overrun")), 1)

    def test_bad_today_is_usage_error(self):
        """A supplied but unparseable --today is a usage error (exit 2), NOT a
        silent wall-clock fallback. Guards the 'no uncontrolled wall-clock' promise.
        """
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--today", "not-a-date"])
        self.assertEqual(code, 2)
        self.assertIn("usage error", out)

    def test_bad_config_today_is_usage_error(self):
        """A supplied but unparseable config.today (no --today) is also exit 2."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"today": "2026-13-99"}, fh)
        _out, code = _util.invoke(
            "docs-audit", ["--root", root, "--json", "--config", cfg])
        self.assertEqual(code, 2)


# --- §7 detected-fallback: guard misses, audit catches (TC-130) ------------

class DetectedFallbackTest(AuditBase):
    def test_icd_violation_audit_fallback_when_guard_not_fired(self):
        """TC-130 (§7): the guard is preventive but not total; the audit is the
        detective backstop. A cross-domain non-ICD depends_on can reach disk via
        a tool path the guard's matcher does not cover. On such a NON-matched
        event the guard quietly allows (does not fire), yet docs-audit later
        surfaces the same violation as an icd_dependency_violation error.
        """
        # Cross-domain non-ICD dependency written straight to disk (simulating a
        # tool path the PreToolUse Edit|Write|MultiEdit / Bash matcher misses).
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-22"]), "x"),
            (_fm("SPEC-22", "SPEC", "identity"), "x"),
        ])
        offending = os.path.join(root, "billing", "spec", "SPEC-1.md")
        self.assertTrue(os.path.isfile(offending))

        # 1) policy-guard on a NON-matched event (PreToolUse + a tool the guard
        # does not route, e.g. Read) → quiet allow, the guard does not fire.
        stdin_obj = _util.hook_stdin(
            "PreToolUse", tool_name="Read",
            tool_input={"file_path": offending})
        out, code = _util.invoke("policy-guard", stdin_obj=stdin_obj)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        hso = resp.get("hookSpecificOutput", {})
        # allow / quiet: no deny, no block — the guard did not fire.
        self.assertNotEqual(hso.get("permissionDecision"), "deny")
        self.assertNotEqual(resp.get("decision"), "block")
        self.assertEqual(hso.get("permissionDecision"), "allow")

        # 2) docs-audit catches the same violation (reverse-ref/edge fallback).
        data, _ = self.audit_json(root)
        v = self.checks_for(data, "icd_dependency_violation")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["doc_id"], "SPEC-1")
        self.assertEqual(v[0]["severity"], "error")
        self.assertEqual(v[0]["refs"], ["SPEC-22"])
        self.assertIn("identity の内部です", v[0]["message"])


if __name__ == "__main__":
    unittest.main()
