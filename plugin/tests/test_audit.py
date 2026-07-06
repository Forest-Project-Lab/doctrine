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

    def test_review_by_due_today_not_overrun(self):
        """review_by == today(期限当日)はまだ超過ではない(< の境界)。"""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by=TODAY), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "review_by_overrun"), [])


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

    def test_draft_with_broken_updated_is_stale(self):
        """updated が解せない draft は古び扱い(不明は安全側 = stale)。"""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="not-a-date", llm_context="never"), "x"),
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

    def test_orphan_review_by_boundary(self):
        """review_by 超過は陳腐化(orphan 成立)、当日はまだ非陳腐化(< の境界)。

        updated は最近(180 日閾値未満)にして updated 経由の陳腐化を切り、
        review_by 経由の陳腐化分岐だけを検証する。
        """
        # 過去の review_by + 最近の updated -> review_by 経由で orphan。
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", review_by="2026-06-28",
                 llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "RESEARCH-1")
        # review_by == today -> まだ陳腐化ではない -> not orphan。
        root2 = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", review_by=TODAY,
                 llm_context="never"), "x"),
        ])
        data2, _ = self.audit_json(root2)
        self.assertEqual(self.checks_for(data2, "orphan"), [])


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


class IcdIndexDriftTest(AuditBase):
    """icd-index.md の投影ドリフト検査(ICD-005)。overview とは別経路。

    Regression: 既存の ProjectionDriftTest は overview.md のみで、icd-index の
    検査ブロックが丸ごと未実行だった(ミューテーション監査で発見)。"""

    def _repo(self, index_body):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/shipping/ICD.md":
                _util.fm_block(_fm("ICD-2", "ICD", "shipping")) + "x",
            "docs/_system/icd-index.md": _util.fm_block(
                _fm("OVERVIEW-2", "OVERVIEW", "_system"))
                + "描画される。手で編集しない。\n\n" + index_body,
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def test_complete_icd_index_no_drift(self):
        """現行 ICD を全て列挙した icd-index はドリフト無し。"""
        data, _ = self.audit_json(self._repo("- ICD-1\n- ICD-2\n"))
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_missing_icd_in_index_is_drift_error(self):
        """icd-index に現行 ICD が欠けている -> projection_drift error。"""
        data, _ = self.audit_json(self._repo("- ICD-1\n"))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("ICD-2" in (f.get("refs") or []) for f in pd),
                        "missing ICD-2 must be reported: %r" % pd)
        self.assertTrue(all(f["severity"] == "error" for f in pd))


class CtxmapDriftTest(AuditBase):
    """Context Map の投影ドリフト(ICD-005: 構造差 error / ラベル差 warn)。

    Regression: 監査は overview / icd-index しか見ておらず、docstring と
    ICD-005 が約束する Context Map 被覆が未実装だった(全体監査の major 所見)。"""

    _B = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
    _E = "<!-- END PROJECTION:context-map-skeleton -->"

    def _repo(self, region):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/shipping/spec/SPEC-2.md":
                _util.fm_block(_fm("SPEC-2", "SPEC", "shipping",
                                   depends_on=["ICD-1"])) + "x",
            "docs/_system/context-map.md": _util.fm_block(
                _fm("CTXMAP-1", "CTXMAP", "_system"))
                + "描画される。手で編集しない。\n\n%s\n%s\n%s\n" % (self._B, region, self._E),
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def _matching_region(self):
        return ("## ドメインとICD\n\n"
                "- _system: (ICD 未公開)\n"
                "- billing: ICD-1\n"
                "- shipping: (ICD 未公開)\n\n"
                "## ドメイン越えの依存(ICD境界)\n\n"
                "- SPEC-2 --depends_on--> ICD-1\n")

    def test_matching_ctxmap_no_drift(self):
        data, _ = self.audit_json(self._repo(self._matching_region()))
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_missing_domain_is_error(self):
        region = self._matching_region().replace("- shipping: (ICD 未公開)\n", "")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("shipping" in f["message"] and
                            f["severity"] == "error" for f in pd), pd)

    def test_missing_cross_edge_is_error(self):
        region = self._matching_region().replace(
            "- SPEC-2 --depends_on--> ICD-1\n", "")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(sorted(f["refs"]) == ["ICD-1", "SPEC-2"] and
                            f["severity"] == "error" for f in pd), pd)

    def test_icd_label_difference_is_warn(self):
        region = self._matching_region().replace("- billing: ICD-1",
                                                 "- billing: (ICD 未公開)")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("ラベル差" in f["message"] and
                            f["severity"] == "warn" for f in pd), pd)
        self.assertFalse(any(f["severity"] == "error" for f in pd), pd)

    def test_unrendered_region_is_error(self):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/_system/context-map.md": _util.fm_block(
                _fm("CTXMAP-1", "CTXMAP", "_system")) + "印なし本文。\n",
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("未描画" in f["message"] and
                            f["severity"] == "error" for f in pd), pd)


class StrayDocumentTest(AuditBase):
    """体系外 .md(stray_document, ADR-021): docs/ の外の .md を分類の記録
    (docs/_system/.md-intake)と突き合わせる。"""

    def _proj(self, ledger=None):
        root = self.build([(_fm("SPEC-1", "SPEC", "billing"), "x")])
        proj = os.path.dirname(root)
        if ledger is not None:
            os.makedirs(os.path.join(root, "_system"), exist_ok=True)
            with open(os.path.join(root, "_system", ".md-intake"), "w",
                      encoding="utf-8") as fh:
                fh.write(ledger)
        return root, proj

    def _write(self, proj, rel, text):
        path = os.path.join(proj, rel)
        os.makedirs(os.path.dirname(path) or proj, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_typed_stray_is_warn(self):
        root, proj = self._proj()
        self._write(proj, "notes/SPEC-9-draft.md",
                    _util.fm_block(_fm("SPEC-9", "SPEC", "billing")) + "x")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "warn" and
                            "SPEC" in f["message"] for f in sd), sd)

    def test_unledgered_untyped_is_advisory(self):
        root, proj = self._proj()
        self._write(proj, "MEMO.md", "# メモ\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "advisory" and
                            f["path"] == "MEMO.md" for f in sd), sd)

    def test_ledgered_files_are_silent(self):
        """記録された非文書(完全一致)と配下指定(末尾 /)は挙がらない。"""
        root, proj = self._proj(
            ledger="README.md: 非文書\nvendor/: 非文書\n")
        self._write(proj, "README.md", "# r\n")
        self._write(proj, "vendor/a/b.md", "# b\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stray_document"), [])

    def test_hold_expiry(self):
        """保留は期限まで沈黙し、期限を過ぎると warn で再浮上する。"""
        root, proj = self._proj(
            ledger="old.md: 保留 2026-01-01\nnew.md: 保留 2027-01-01\n")
        self._write(proj, "old.md", "# o\n")
        self._write(proj, "new.md", "# n\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "warn" and f["path"] == "old.md"
                            for f in sd), sd)
        self.assertFalse(any(f["path"] == "new.md" for f in sd), sd)

    def test_dead_ledger_entry_is_advisory(self):
        root, _proj = self._proj(ledger="gone.md: 非文書\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any("gone.md" in f["message"] and
                            f["severity"] == "advisory" for f in sd), sd)

    def test_dot_dirs_not_scanned(self):
        root, proj = self._proj()
        self._write(proj, ".hidden/x.md", "# x\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stray_document"), [])


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

    def test_scale_gate_skips_pass_and_emits_advisory(self):
        """Current-doc count over near_dup_max_docs -> O(n^2) pass skipped,
        exactly one near_duplicate advisory announcing the skip (no silent
        truncation, severity stays advisory)."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        docs = []
        for k in range(3):
            docs.append((_fm("SPEC-%d" % k, "SPEC", "billing"), shared + " w%d" % k))
        root = self.build(docs)
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"near_dup_max_docs": 1}, fh)
        data, _ = self.audit_json(root, ["--config", cfg])
        nd = self.checks_for(data, "near_duplicate")
        self.assertEqual(len(nd), 1)
        self.assertEqual(nd[0]["severity"], "advisory")
        self.assertIn("省いた", nd[0]["message"])
        # the skip advisory is corpus-wide, not a per-pair finding
        self.assertEqual(nd[0]["refs"], [])

    def test_scale_gate_not_tripped_runs_pass(self):
        """At/under near_dup_max_docs the normal pairwise pass still runs and
        reports the overlapping pair (not the skip advisory)."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), shared + " alpha"),
            (_fm("SPEC-2", "SPEC", "billing"), shared + " beta"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"near_dup_max_docs": 2}, fh)
        data, _ = self.audit_json(root, ["--config", cfg])
        nd = self.checks_for(data, "near_duplicate")
        self.assertTrue(len(nd) >= 1)
        self.assertTrue(all(f["severity"] == "advisory" for f in nd))
        self.assertTrue(all("省いた" not in f["message"] for f in nd))


# --- summary schema + handshake (critique gap C3) -------------------------

class SummaryHandshakeTest(AuditBase):
    def _docs(self):
        return [
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "x"),
        ]

    def test_respect_docs_level_skips_at_level2_without_summary(self):
        """ADR-019: --respect-docs-level 付きで level: 2 の体系 -> 監査を飛ばし
        exit 0、要約も書かない。フラグ無し(CI)なら Level に依らず監査する。"""
        root = self.build(self._docs())
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, ".docs-level"), "w",
                  encoding="utf-8") as fh:
            fh.write("level: 2\n")
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, "last-audit.json")
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--summary-out", out_path,
             "--fail-on", "never", "--today", TODAY, "--respect-docs-level"])
        self.assertEqual(code, 0)
        self.assertIn("Level 3", out)
        self.assertFalse(os.path.exists(out_path),
                         "level-2 skip must not write a summary")
        # フラグ無し(CI 経路)は Level 2 でも全件監査する。
        data, code2 = self.audit_json(root)
        self.assertEqual(code2, 0)
        self.assertIn("findings", data)

    def test_respect_docs_level_runs_at_level4(self):
        """level: 4(または marker 無し)なら --respect-docs-level 付きでも監査する。"""
        root = self.build(self._docs())
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, ".docs-level"), "w",
                  encoding="utf-8") as fh:
            fh.write("level: 4\n")
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--today", TODAY,
             "--respect-docs-level"])
        self.assertEqual(code, 0)
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["schema"], "docs-audit/1")

    def test_summary_out_into_existing_dir_and_overwrite(self):
        """出力先ディレクトリ・ファイルが既存でも summary は書かれる。

        Regression guard: SessionEnd は毎回同じ .cache/last-audit.json に書く
        ので、「2回目以降(既存)で書けない」退行は握手を恒久停止させる。"""
        root = self.build(self._docs())
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", out_path,
                "--fail-on", "never", "--today", TODAY]
        _util.invoke("docs-audit", argv)
        out, code = _util.invoke("docs-audit", argv)  # 2回目: 全部既存
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schema"], "docs-audit/1")

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


# --- registration completeness (unregistered / shadowed, R1/R8) -----------

class UnregisteredTest(AuditBase):
    def test_frontmatterless_file_is_unregistered(self):
        """docs/ 内の frontmatter/id 無し .md -> unregistered_document error。

        他の検査は g.nodes 上の述語なので、この検査だけが「亡霊」を拾える。
        """
        root = _util.make_repo({
            "docs/notes/scratch.md": "ただの散文。フロントマターも id も無い。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        u = self.checks_for(data, "unregistered_document")
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["severity"], "error")
        self.assertEqual(u[0]["path"], "notes/scratch.md")
        self.assertEqual(u[0]["doc_id"], "")  # 登録簿に id が無い → 空文字（整列安全）

    def test_duplicate_id_shadow_is_flagged(self):
        """同じ id の別ファイル -> 影のパスだけ shadowed_document error。"""
        a = _util.fm_block(_fm("DUP-1", "RESEARCH", "a", llm_context="never")) + "A"
        b = _util.fm_block(_fm("DUP-1", "RESEARCH", "b", llm_context="never")) + "B"
        root = _util.make_repo({
            "docs/a/research/DUP-1.md": a,
            "docs/b/research/DUP-1.md": b,
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        s = self.checks_for(data, "shadowed_document")
        self.assertEqual(len(s), 1)  # 2 ファイル中 1 つが影
        self.assertEqual(s[0]["severity"], "error")
        self.assertEqual(s[0]["doc_id"], "DUP-1")
        self.assertEqual(s[0]["path"], "a/research/DUP-1.md")  # 後勝ちで b を採用

    def test_clean_corpus_has_neither(self):
        """全ファイルが一意 id で登録済み -> unregistered/shadowed ゼロ。"""
        root = _util.make_repo({
            "docs/billing/spec/SPEC-1.md":
                _util.fm_block(_fm("SPEC-1", "SPEC", "billing")) + "x",
            "docs/billing/REQ-1.md":
                _util.fm_block(_fm("REQ-1", "REQ", "billing")) + "x",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(self.checks_for(data, "unregistered_document"), [])
        self.assertEqual(self.checks_for(data, "shadowed_document"), [])


if __name__ == "__main__":
    unittest.main()
