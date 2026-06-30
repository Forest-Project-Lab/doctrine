"""Tests for collect-context.py — task-scoped minimal context pack (R5).

Component: collect-context.py (llm-context-pack task min-set), MASTER §5.4, C10.
Slice 06 §2 (collect-context parts) + critique two-cap gap.

Covers:
- TC-101 (B21): context pack excludes RESEARCH/ARCHIVE (`llm_context: never`) —
  never-group not present in the pack. (R5 "never群が渡らない")
- TC-102 (B21, fail/regression): a `never` doc that WOULD cover a REQ is still
  excluded BEFORE any covering computation, and the REQ is reported uncovered if
  nothing else covers it. Hard-exclude-never precedes set-cover (MASTER §5.4, R5).
- Minimum covering set (greedy + reverse-prune): no superfluous doc; a doc fully
  subsumed by others is dropped (slice 06 §2.4, T-CC-3).
- Provenance present per fact: `〔出所: <id> · <relpath>〕` in md, `source_id`/
  `source_path` per fact in json (slice 06 §2.5, T-CC-4).
- ICD dependency closure: a cross-domain ICD reached via depends_on is pulled in
  as a `dependency` member; a `never` doc is NEVER pulled by closure (T-CC-7).
- task_pack_token_cap distinct from injection_token_cap (C10, critique two-cap
  gap): the cap is read from a SEPARATE key; injection_token_cap is ignored here.
- uncovered REQs reported, exit 0 (T-CC-5); determinism (T-CC-6); stdlib-only.

Uses make_repo with REQ/SPEC/ICD/RESEARCH docs (per assignment).
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


# --- fixture builders -------------------------------------------------------

def _fm(doc_id, type_code, domain, status="current", **extra):
    base = {
        "id": doc_id,
        "title": doc_id + " title",
        "type": type_code,
        "domain": domain,
        "status": status,
        "owner": "t",
        "updated": "2026-01-01",
        "sources": [],
    }
    base.update(extra)
    return base


def _loc(domain, type_code, doc_id):
    if type_code == "ICD":
        return "docs/%s/ICD.md" % domain
    sub = {
        "REQ": "", "SPEC": "spec/", "TEST": "test/", "IMPL": "implementation/",
        "ADR": "decisions/", "RESEARCH": "research/", "ARCHIVE": "archive/",
        "DATA": "spec/", "API": "spec/",
    }.get(type_code, "")
    return "docs/%s/%s%s.md" % (domain, sub, doc_id)


def _before_uncovered(md_out):
    """Return the md region before the「覆えなかった要求」header (fact/doc bullets
    only). Those uncovered bullets and the trimmed note are provenance-free by
    design (finding #19), so provenance assertions must scope to this region."""
    marker = "## 覆えなかった要求"
    idx = md_out.find(marker)
    return md_out if idx < 0 else md_out[:idx]


class CollectBase(unittest.TestCase):
    def make(self, docs):
        """docs: list of (fm_dict, body). Returns (root, docs_root)."""
        root = _util.make_repo({})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for fm, body in docs:
            rel = _loc(fm["domain"], fm["type"], fm["id"])
            _util.write_doc(root, rel, fm, body)
        return root, os.path.join(root, "docs")

    def run_json(self, docs_root, argv):
        out, code = _util.invoke(
            "collect-context",
            ["--docs-root", docs_root, "--format", "json"] + argv)
        self.assertEqual(code, 0, "exit must be 0; got %d\n%s" % (code, out))
        return json.loads(out), out

    def run_md(self, docs_root, argv):
        out, code = _util.invoke(
            "collect-context",
            ["--docs-root", docs_root, "--format", "md"] + argv)
        self.assertEqual(code, 0, "exit must be 0; got %d\n%s" % (code, out))
        return out


# --- TC-101 / TC-102: hard-exclude never BEFORE covering --------------------

class NeverExclusionTest(CollectBase):
    """TC-101/TC-102, R5: never group excluded before any covering computation."""

    def test_tc101_never_doc_body_absent_from_pack(self):
        """TC-101: a RESEARCH (`never`) doc body is not present in the pack."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- refund window\n"),
            (_fm("SPEC-001", "SPEC", "billing", depends_on=["REQ-001"]),
             "## 入出力\nrefund flow\n"),
            (_fm("RESEARCH-001", "RESEARCH", "billing", status="draft",
                 depends_on=["REQ-001"]),
             "SECRET-RESEARCH-MARKER body of research\n"),
        ])
        pack, raw = self.run_json(docs_root, ["--task", "refund",
                                              "--require", "REQ-001"])
        ids = [d["id"] for d in pack["docs"]]
        self.assertNotIn("RESEARCH-001", ids)
        self.assertNotIn("SECRET-RESEARCH-MARKER", raw)

    def test_tc102_never_doc_that_would_cover_is_still_excluded(self):
        """TC-102 (regression): the ONLY doc tracing to a required REQ is a
        `never` doc, AND the REQ itself is absent as a current doc. The never doc
        must be hard-excluded BEFORE the set-cover, so the REQ ends up uncovered
        and the never doc is never in the pack (finding #27).

        This proves hard-exclude-never PRECEDES covering: were the never doc a
        covering candidate it would cover REQ-009 and the REQ would not be
        uncovered. Earlier this asserted assertIn('REQ-009', ids + uncovered),
        which was tautological (REQ-009 was a current doc covering itself).
        """
        _, docs_root = self.make([
            # No REQ-009 current doc exists; only a RESEARCH (never) traces to it.
            (_fm("RESEARCH-009", "RESEARCH", "billing", status="draft",
                 depends_on=["REQ-009"]),
             "research that traces to REQ-009\n"),
        ])
        pack, raw = self.run_json(docs_root, ["--task", "audit",
                                              "--require", "REQ-009"])
        ids = [d["id"] for d in pack["docs"]]
        # The never doc is excluded (not a covering candidate).
        self.assertNotIn("RESEARCH-009", ids)
        self.assertNotIn("research that traces to REQ-009", raw)
        # The REQ is reported uncovered (nothing current covers it).
        self.assertIn("REQ-009", pack["uncovered"])

    def test_tc102_req_only_in_never_is_uncovered(self):
        """TC-102 strict: a REQ that exists ONLY inside a never doc (not as its
        own current doc) is reported uncovered, never pulled from the never doc.
        """
        _, docs_root = self.make([
            # No REQ-077 doc exists; only an ARCHIVE (never) mentions/traces it.
            (_fm("ARCHIVE-077", "ARCHIVE", "billing", status="archived",
                 depends_on=["REQ-077"]),
             "archived approach covering REQ-077\n"),
        ])
        pack, raw = self.run_json(docs_root, ["--task", "x",
                                              "--require", "REQ-077"])
        ids = [d["id"] for d in pack["docs"]]
        self.assertNotIn("ARCHIVE-077", ids)
        self.assertIn("REQ-077", pack["uncovered"])

    def test_archive_never_excluded(self):
        """R5: ARCHIVE (`never` by default) excluded same as RESEARCH."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("ARCHIVE-001", "ARCHIVE", "billing", status="archived",
                 depends_on=["REQ-001"]), "old archived body\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "need",
                                            "--require", "REQ-001"])
        self.assertNotIn("ARCHIVE-001", [d["id"] for d in pack["docs"]])

    def test_explicit_never_override_excluded(self):
        """R5: a normally-`task` type with frontmatter llm_context: never is
        excluded too (effective_llm_context honors the override)."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("SPEC-050", "SPEC", "billing", depends_on=["REQ-001"],
                 llm_context="never"), "spec hidden by override\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "need",
                                            "--require", "REQ-001"])
        self.assertNotIn("SPEC-050", [d["id"] for d in pack["docs"]])
        # REQ-001 still covers itself, so it is covered (not uncovered).
        self.assertNotIn("REQ-001", pack["uncovered"])


# --- minimum covering set ---------------------------------------------------

class MinimumCoverTest(CollectBase):
    """Greedy set-cover + reverse-prune: no superfluous docs (slice 06 §2.4)."""

    def test_covering_set_covers_required(self):
        """T-CC-2: all coverable required REQs appear covered."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("REQ-002", "REQ", "billing"), "- b\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "REQ-002"]), "covers both\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t",
                                            "--require", "REQ-001", "REQ-002"])
        covered = set()
        for d in pack["docs"]:
            covered.update(d["covers"])
        self.assertEqual({"REQ-001", "REQ-002"}, covered & {"REQ-001", "REQ-002"})
        self.assertEqual([], pack["uncovered"])

    def test_no_superfluous_doc_single_spec_covers_both(self):
        """Minimality: one SPEC covering both REQs is chosen over two SPECs each
        covering one — the redundant single-REQ SPECs are NOT selected."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("REQ-002", "REQ", "billing"), "- b\n"),
            (_fm("SPEC-100", "SPEC", "billing",
                 depends_on=["REQ-001", "REQ-002"]), "covers both\n"),
            (_fm("SPEC-101", "SPEC", "billing", depends_on=["REQ-001"]),
             "covers only one\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t",
                                            "--require", "REQ-001", "REQ-002"])
        primary_ids = {d["id"] for d in pack["docs"] if d["role"] == "primary"}
        self.assertIn("SPEC-100", primary_ids)
        self.assertNotIn("SPEC-101", primary_ids)

    def test_reverse_prune_drops_subsumed_doc(self):
        """T-CC-3: reverse-prune drops a doc the GREEDY pass actually selected but
        whose coverage is fully subsumed by the UNION of LATER picks.

        Fixture (4 reqs, no single superset doc, so greedy makes 3 picks):
          SPEC-A = {R1,R2}, SPEC-B = {R2,R3}, SPEC-C = {R1,R4}.
        Greedy (gain, then substantive, then -token, then id-ascending first-wins)
        picks A (gain 2) → remaining {R3,R4}; then B (gain 1, id-first) → {R4};
        then C (gain 1). Selected = [A,B,C].
        Reverse-prune (from the end) keeps C (uniquely covers R4) and B (uniquely
        covers R3), then finds A's reqs {R1,R2} ⊆ (B∪C = {R1,R2,R3,R4}) and DROPS
        A. Coverage of {R1..R4} stays complete via B∪C. Equal-length bodies keep
        the only tie-break id-ascending, so A (not B/C) is the greedy first pick.
        """
        body = "yyyyy\n"  # identical length so the only step-1 tie-break is id.
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("REQ-002", "REQ", "billing"), "- b\n"),
            (_fm("REQ-003", "REQ", "billing"), "- c\n"),
            (_fm("REQ-004", "REQ", "billing"), "- d\n"),
            (_fm("SPEC-A", "SPEC", "billing",
                 depends_on=["REQ-001", "REQ-002"]), body),
            (_fm("SPEC-B", "SPEC", "billing",
                 depends_on=["REQ-002", "REQ-003"]), body),
            (_fm("SPEC-C", "SPEC", "billing",
                 depends_on=["REQ-001", "REQ-004"]), body),
        ])
        pack, _ = self.run_json(
            docs_root, ["--task", "t", "--require",
                        "REQ-001", "REQ-002", "REQ-003", "REQ-004"])
        primary_ids = {d["id"] for d in pack["docs"] if d["role"] == "primary"}
        # A was selected by greedy but reverse-prune drops it as redundant.
        self.assertNotIn("SPEC-A", primary_ids,
                         "reverse-prune must drop the subsumed primary SPEC-A")
        self.assertIn("SPEC-B", primary_ids)
        self.assertIn("SPEC-C", primary_ids)
        # Coverage stays complete despite the prune.
        covered = set()
        for d in pack["docs"]:
            covered.update(d["covers"])
        self.assertEqual({"REQ-001", "REQ-002", "REQ-003", "REQ-004"},
                         covered & {"REQ-001", "REQ-002", "REQ-003", "REQ-004"})
        self.assertEqual([], pack["uncovered"])

    def test_unrelated_doc_not_added(self):
        """Spec §3.9 "関係しない文書を足さない": an unrelated SPEC is not in pack."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("SPEC-001", "SPEC", "billing", depends_on=["REQ-001"]), "x\n"),
            (_fm("SPEC-999", "SPEC", "shipping", depends_on=["REQ-999"]),
             "unrelated\n"),
            (_fm("REQ-999", "REQ", "shipping"), "- unrelated need\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t",
                                            "--require", "REQ-001"])
        ids = {d["id"] for d in pack["docs"]}
        self.assertNotIn("SPEC-999", ids)
        self.assertNotIn("REQ-999", ids)


# --- provenance per fact ----------------------------------------------------

class ProvenanceTest(CollectBase):
    """T-CC-4: provenance present per fact (md 〔出所〕 / json source_id)."""

    def test_md_provenance_marker_per_fact(self):
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- refund within 30 days\n"),
            (_fm("SPEC-001", "SPEC", "billing", depends_on=["REQ-001"]),
             "## 入出力\nthe refund flow\n"),
        ])
        out = self.run_md(docs_root, ["--task", "refund", "--require", "REQ-001"])
        # Provenance applies to fact/document bullets only — scope to the region
        # BEFORE the「覆えなかった要求」header (those bullets are intentionally
        # provenance-free, finding #19).
        fact_region = _before_uncovered(out)
        bullets = [l for l in fact_region.splitlines() if l.startswith("- ")]
        self.assertTrue(bullets, "expected at least one fact bullet")
        for line in bullets:
            self.assertIn("〔出所:", line, "fact missing provenance: %r" % line)
        # SPEC-001 (the substantive coverer of REQ-001) supplies the facts; its
        # relpath appears as the source. The bare REQ is de-duplicated since
        # SPEC-001 already covers it.
        self.assertIn("billing/spec/SPEC-001.md", out)

    def test_uncovered_bullets_are_provenance_free(self):
        """Finding #19: the「覆えなかった要求」bullets legitimately carry NO
        provenance. Fact bullets (before the header) all do; uncovered bullets
        (after) do not. This pins the scoping so the provenance assertion can
        never silently demand provenance on uncovered bullets."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- refund within 30 days\n"),
            (_fm("SPEC-001", "SPEC", "billing", depends_on=["REQ-001"]),
             "## 入出力\nthe refund flow\n"),
        ])
        # REQ-404 has no covering current doc → it appears under 覆えなかった要求.
        out = self.run_md(docs_root, ["--task", "refund",
                                      "--require", "REQ-001", "REQ-404"])
        self.assertIn("## 覆えなかった要求", out)
        before, after = out.split("## 覆えなかった要求", 1)
        # Every fact bullet BEFORE the header carries provenance.
        before_bullets = [l for l in before.splitlines() if l.startswith("- ")]
        self.assertTrue(before_bullets)
        for line in before_bullets:
            self.assertIn("〔出所:", line, "fact missing provenance: %r" % line)
        # The uncovered REQ bullet AFTER the header is provenance-free.
        after_bullets = [l for l in after.splitlines() if l.startswith("- ")]
        self.assertTrue(after_bullets, "expected an uncovered bullet")
        self.assertTrue(any("REQ-404" in l for l in after_bullets))
        for line in after_bullets:
            self.assertNotIn("〔出所:", line,
                             "uncovered bullet must be provenance-free: %r" % line)

    def test_json_provenance_per_fact(self):
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need one\n- need two\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        req = [d for d in pack["docs"] if d["id"] == "REQ-001"][0]
        self.assertTrue(req["facts"])
        for fact in req["facts"]:
            self.assertEqual(fact["source_id"], "REQ-001")
            self.assertEqual(fact["source_path"], "billing/REQ-001.md")
            self.assertIn("text", fact)


# --- ICD dependency closure -------------------------------------------------

class DependencyClosureTest(CollectBase):
    """T-CC-7: ICD pulled via closure; never docs never pulled by closure."""

    def test_icd_pulled_as_dependency(self):
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "ICD-09"]), "spec\n"),
            (_fm("ICD-09", "ICD", "identity", canonical_for=["identity"]),
             "- identity public contract\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        by_id = {d["id"]: d for d in pack["docs"]}
        self.assertIn("ICD-09", by_id)
        self.assertEqual(by_id["ICD-09"]["role"], "dependency")

    def test_transitive_closure_pulls_second_hop_icd(self):
        """Finding #17: the depends_on closure is TRANSITIVE. SPEC→ICD-A→ICD-B
        pulls BOTH ICD-A and ICD-B; a `never` doc anywhere in the chain is NOT
        pulled and its onward edges are not followed (R5 holds at every hop)."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "ICD-A"]), "spec\n"),
            # ICD-A depends on ICD-B (second hop) and on a never RESEARCH doc.
            (_fm("ICD-A", "ICD", "identity", canonical_for=["identity"],
                 depends_on=["ICD-B", "RESEARCH-900"]),
             "- identity contract A\n"),
            (_fm("ICD-B", "ICD", "shipping", canonical_for=["shipping"]),
             "- shipping contract B\n"),
            (_fm("RESEARCH-900", "RESEARCH", "identity", status="draft",
                 depends_on=["ICD-B"]),
             "NEVER-CHAIN-MARKER research never body\n"),
        ])
        pack, raw = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        by_id = {d["id"]: d for d in pack["docs"]}
        # First hop ICD pulled.
        self.assertIn("ICD-A", by_id)
        # Second hop ICD pulled transitively.
        self.assertIn("ICD-B", by_id)
        self.assertEqual(by_id["ICD-B"]["role"], "dependency")
        # The never doc in the chain is NOT pulled and its body does not leak.
        self.assertNotIn("RESEARCH-900", by_id)
        self.assertNotIn("NEVER-CHAIN-MARKER", raw)

    def test_never_doc_never_pulled_by_closure(self):
        """A selected doc depends_on a RESEARCH (never) doc; closure must NOT
        pull the never doc (R5 hard guarantee even through dependency closure)."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "RESEARCH-001"]), "spec\n"),
            (_fm("RESEARCH-001", "RESEARCH", "billing", status="draft"),
             "never body must not leak\n"),
        ])
        pack, raw = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        self.assertNotIn("RESEARCH-001", [d["id"] for d in pack["docs"]])
        self.assertNotIn("never body must not leak", raw)

    def test_cross_domain_internal_dep_flagged(self):
        """T-CC-8: a cross-domain depends_on that targets a NON-ICD internal doc
        is flagged (境界違反); the guard/audit owns enforcement, pack just flags."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            # SPEC in billing depends on an internal SPEC in another domain.
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "SPEC-200"]), "spec\n"),
            (_fm("SPEC-200", "SPEC", "identity"), "internal cross-domain\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        self.assertIn("SPEC-200", pack["boundary_violations"])


# --- two-cap separation (C10, critique gap) ---------------------------------

class TwoCapTest(CollectBase):
    """C10 / critique: task_pack_token_cap is a SEPARATE key from
    injection_token_cap. collect-context reads ONLY task_pack_token_cap."""

    def _big_corpus(self):
        # One REQ uniquely covered by SPEC-001 (a non-droppable unique keeper),
        # plus a fat dependency ICD that is droppable (it covers no required REQ
        # uniquely — it is dependency-closure substance). A small cap drops the
        # ICD while preserving the unique coverer (slice 06 §2.2 / §2.4).
        body = "x" * 800 + "\n"   # ~200 tokens each
        return [
            (_fm("REQ-001", "REQ", "billing"), "- need one\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "ICD-09"]), "spec one " + body),
            (_fm("ICD-09", "ICD", "identity", canonical_for=["identity"]),
             "icd body " + body),
        ]

    def test_max_tokens_cli_trims(self):
        """--max-tokens enforces the task-pack cap; trimmed flag set. The fat
        dependency ICD is dropped; the unique coverer SPEC-001 survives."""
        _, docs_root = self.make(self._big_corpus())
        pack, _ = self.run_json(
            docs_root,
            ["--task", "t", "--require", "REQ-001", "--max-tokens", "60"])
        self.assertTrue(pack["trimmed"])
        # The unique coverer must survive; coverage preserved.
        covered = set()
        for d in pack["docs"]:
            covered.update(d["covers"])
        self.assertIn("REQ-001", covered)

    def test_config_task_pack_cap_distinct_from_injection_cap(self):
        """The critique two-cap gap: a config setting ONLY injection_token_cap
        (and NOT task_pack_token_cap) must NOT cap the task pack; setting
        task_pack_token_cap DOES. They are independent keys (C10).
        """
        docs = self._big_corpus()
        # Case A: only injection_token_cap set (small) — must be IGNORED here.
        rootA, docs_rootA = self.make(docs)
        cfgA = os.path.join(docs_rootA, "_system", ".context-config.json")
        os.makedirs(os.path.dirname(cfgA), exist_ok=True)
        with open(cfgA, "w", encoding="utf-8") as fh:
            json.dump({"injection_token_cap": 1}, fh)
        packA, _ = self.run_json(
            docs_rootA, ["--task", "t", "--require", "REQ-001"])
        self.assertFalse(packA["trimmed"],
                         "injection_token_cap must NOT affect the task pack (C10)")

        # Case B: task_pack_token_cap set small — MUST trim.
        rootB, docs_rootB = self.make(docs)
        cfgB = os.path.join(docs_rootB, "_system", ".context-config.json")
        os.makedirs(os.path.dirname(cfgB), exist_ok=True)
        with open(cfgB, "w", encoding="utf-8") as fh:
            json.dump({"task_pack_token_cap": 60}, fh)
        packB, _ = self.run_json(
            docs_rootB, ["--task", "t", "--require", "REQ-001"])
        self.assertTrue(packB["trimmed"],
                        "task_pack_token_cap must cap the task pack (C10)")

    def test_cap_never_drops_unique_coverer(self):
        """A doc that uniquely covers a required REQ is never dropped by the cap
        (slice 06 §2.2 --max-tokens decision)."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
            (_fm("SPEC-001", "SPEC", "billing", depends_on=["REQ-001"]),
             "x" * 2000 + "\n"),   # huge, but uniquely covers REQ-001
        ])
        pack, _ = self.run_json(
            docs_root, ["--task", "t", "--require", "REQ-001", "--max-tokens", "5"])
        ids = {d["id"] for d in pack["docs"]}
        # SPEC-001 (or REQ-001) must still cover REQ-001 — coverage preserved.
        covered = set()
        for d in pack["docs"]:
            covered.update(d["covers"])
        self.assertIn("REQ-001", covered)


# --- uncovered reporting + exit codes + determinism -------------------------

class UncoveredAndExitTest(CollectBase):
    """T-CC-5/6: uncovered reported with exit 0; determinism; usage errors."""

    def test_uncovered_required_reported_exit0(self):
        """A required REQ with no covering current doc is in `uncovered`, exit 0."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- need\n"),
        ])
        out, code = _util.invoke(
            "collect-context",
            ["--docs-root", docs_root, "--format", "json",
             "--task", "t", "--require", "REQ-001", "REQ-404"])
        self.assertEqual(code, 0)
        pack = json.loads(out)
        self.assertIn("REQ-404", pack["uncovered"])
        # REQ-001 covers itself → not uncovered.
        self.assertNotIn("REQ-001", pack["uncovered"])

    def test_uncovered_reason_never_only(self):
        """A REQ coverable only via a never doc gets the never-only reason."""
        _, docs_root = self.make([
            (_fm("RESEARCH-050", "RESEARCH", "billing", status="draft",
                 depends_on=["REQ-050"]), "research only\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t", "--require", "REQ-050"])
        self.assertIn("REQ-050", pack["uncovered"])
        self.assertIn("never", pack["uncovered_reasons"]["REQ-050"])

    def test_deterministic_output(self):
        """T-CC-6: same inputs → byte-identical output across runs."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("REQ-002", "REQ", "billing"), "- b\n"),
            (_fm("SPEC-001", "SPEC", "billing",
                 depends_on=["REQ-001", "REQ-002"]), "x\n"),
        ])
        out1, _ = _util.invoke(
            "collect-context",
            ["--docs-root", docs_root, "--format", "json",
             "--task", "t", "--require", "REQ-001", "REQ-002"])
        out2, _ = _util.invoke(
            "collect-context",
            ["--docs-root", docs_root, "--format", "json",
             "--task", "t", "--require", "REQ-001", "REQ-002"])
        self.assertEqual(out1, out2)

    def test_missing_task_is_usage_error(self):
        """--task is required; its absence is a usage error (exit 2)."""
        out, code = _util.invoke("collect-context", ["--format", "json"])
        self.assertEqual(code, 2)

    def test_missing_docs_root_returns_valid_empty(self):
        """A non-existent docs root yields a valid empty pack at exit 0 (never
        crash the skill)."""
        out, code = _util.invoke(
            "collect-context",
            ["--docs-root", "/nonexistent/docs/root", "--format", "json",
             "--task", "t", "--require", "REQ-001"])
        self.assertEqual(code, 0)
        pack = json.loads(out)
        self.assertEqual(pack["docs"], [])
        self.assertIn("REQ-001", pack["uncovered"])

    def test_non_current_spec_not_selected(self):
        """A deprecated SPEC is not pack-eligible (R2 currency); its REQ is then
        uncovered unless the REQ itself covers it."""
        _, docs_root = self.make([
            (_fm("REQ-001", "REQ", "billing"), "- a\n"),
            (_fm("SPEC-001", "SPEC", "billing", status="deprecated",
                 depends_on=["REQ-001"]), "old\n"),
        ])
        pack, _ = self.run_json(docs_root, ["--task", "t", "--require", "REQ-001"])
        self.assertNotIn("SPEC-001", [d["id"] for d in pack["docs"]])
        # REQ-001 is current and covers itself.
        self.assertNotIn("REQ-001", pack["uncovered"])


# --- stdlib-only (shared meta) ----------------------------------------------

class StdlibOnlyTest(unittest.TestCase):
    """T-SH-1: collect-context imports only stdlib + the shared cores."""

    def test_no_third_party_imports(self):
        path = os.path.join(_util.SCRIPTS, "collect-context.py")
        src = _util.read(path)
        for bad in ("import requests", "import yaml", "import numpy",
                    "from yaml", "import pandas", "pip install"):
            self.assertNotIn(bad, src)
        # The only non-stdlib imports allowed are the underscore cores.
        self.assertIn("import _depgraph", src)
        self.assertIn("import _frontmatter", src)
        self.assertIn("import _registry", src)


if __name__ == "__main__":
    unittest.main()
