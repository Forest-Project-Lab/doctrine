"""Tests for the dependency-graph core (_depgraph) and CLI (dep-graph.py).

Covers MASTER §5.2 frozen API and slice-05 PART A:
- forward transitive impacts (R4): TC-115, TC-116, and TC-113/TC-114 (the
  latter two re-annotated from R3: they walk IMPACTS, so they prove R4, #26).
- depends_on traceability closure (R3): test_r3_depends_on_upstream_closure_full
  + broken-link variant (reverse_dependents over depends_on, transitive).
- reverse_dependents / reverse_current_dependents excludes non-current (R4
  delete-safety reverse-ref): TC-078 input shape, TC-090.
- edge classification intra/cross_domain_icd/cross_domain_violation/
  cross_domain_impact/dangling (R7 + C13 dangling): TC-070..072, TC-117, TC-123
  input shape, TC-082/083 dangling.
- reverse_orphans REQ-without-SPEC and SPEC-without-TEST (R3/R8): TC-093..095.
- resolve() returns {path, domain, type, status} — the de-facto domain_of/
  type_of/status_of for guard/linter/audit (critique-gap: confirm return keys).
- CLI exit codes (0 with findings / 2 usage / 3 root missing) and --reverse-refs
  current-only-by-default: slice 05 A.6, the exact delete-safety guard call.
"""
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


def _node(doc_id, type_code, domain, status="current",
          depends_on=None, impacts=None, canonical_for=None):
    """Build a frontmatter dict with the registry-required shape."""
    fm = {
        "id": doc_id,
        "title": doc_id,
        "type": type_code,
        "domain": domain,
        "status": status,
        "owner": "t",
        "updated": "2026-01-01",
        "sources": [],
    }
    if depends_on is not None:
        fm["depends_on"] = depends_on
    if impacts is not None:
        fm["impacts"] = impacts
    if canonical_for is not None:
        fm["canonical_for"] = canonical_for
    return fm


def _path_for(domain, type_code, doc_id):
    """Place a doc at a plausible §3.2 location under docs/."""
    if type_code == "ICD":
        return "docs/%s/ICD.md" % domain
    sub = {
        "REQ": "", "SPEC": "spec/", "TEST": "test/", "IMPL": "implementation/",
        "ADR": "decisions/", "DATA": "spec/", "API": "spec/",
    }.get(type_code, "")
    return "docs/%s/%s%s.md" % (domain, sub, doc_id)


class DepGraphCoreTest(unittest.TestCase):
    def _build(self, nodes):
        """nodes: list of frontmatter dicts. Returns (graph, root)."""
        _depgraph = _util.load_core("_depgraph")
        files = {}
        for fm in nodes:
            rel = _path_for(fm["domain"], fm["type"], fm["id"])
            files[rel] = _util.fm_block(fm)
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return _depgraph.build_graph(os.path.join(root, "docs")), root

    # -- forward impacts (R4) --------------------------------------------

    def test_forward_impacts_transitive_TC115(self):
        """TC-115: edit ICD; forward impact set is the transitive closure."""
        g, _ = self._build([
            _node("ICD-09", "ICD", "identity", impacts=["SPEC-01"]),
            _node("SPEC-01", "SPEC", "billing", impacts=["IMPL-01"]),
            _node("IMPL-01", "IMPL", "billing", impacts=["TEST-01"]),
            _node("TEST-01", "TEST", "billing"),
        ])
        self.assertEqual(
            g.forward_impacts("ICD-09"),
            {"SPEC-01", "IMPL-01", "TEST-01"},
        )

    def test_forward_impacts_leaf_empty_TC116(self):
        """TC-116: a leaf doc with no impacts yields an empty set (no over-report)."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", impacts=["TEST-01"]),
            _node("TEST-01", "TEST", "billing"),
        ])
        self.assertEqual(g.forward_impacts("TEST-01"), set())

    def test_forward_impacts_cycle_safe(self):
        """A cycle in impacts must not infinite-loop (slice 05 A.3.5)."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", impacts=["SPEC-02"]),
            _node("SPEC-02", "SPEC", "billing", impacts=["SPEC-01"]),
        ])
        # Closure excludes the start itself even when reachable via the cycle.
        self.assertEqual(g.forward_impacts("SPEC-01"), {"SPEC-02"})

    # -- forward IMPACTS propagation (R4) — TC-113/114 re-annotated ----------
    # NOTE (#26): TC-113/114 assert forward_impacts over IMPACTS edges. That is
    # R4 (change-propagation closure), NOT R3 (depends_on traceability). They are
    # re-annotated here as R4 forward-impact tests; the genuine R3 depends_on
    # traceability assertions live below in test_r3_*.

    def test_forward_impacts_chain_full_TC113(self):
        """TC-113 (R4): a REQ->SPEC->IMPL->TEST chain wired with IMPACTS edges
        propagates the full transitive forward-impact closure. (depends_on is
        present too but forward_impacts walks impacts only — proves R4.)"""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing", impacts=["SPEC-01"]),
            _node("SPEC-01", "SPEC", "billing", impacts=["IMPL-01"],
                  depends_on=["REQ-01"]),
            _node("IMPL-01", "IMPL", "billing", impacts=["TEST-01"],
                  depends_on=["SPEC-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["SPEC-01"]),
        ])
        self.assertEqual(
            g.forward_impacts("REQ-01"),
            {"SPEC-01", "IMPL-01", "TEST-01"},
        )

    def test_forward_impacts_chain_broken_TC114(self):
        """TC-114 (R4): a broken IMPACTS link (SPEC has no onward impacts) shrinks
        the forward-impact reachable set."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing", impacts=["SPEC-01"]),
            _node("SPEC-01", "SPEC", "billing"),   # no impacts onward — chain breaks
            _node("IMPL-01", "IMPL", "billing", impacts=["TEST-01"]),
            _node("TEST-01", "TEST", "billing"),
        ])
        self.assertEqual(g.forward_impacts("REQ-01"), {"SPEC-01"})

    # -- depends_on traceability closure (R3) — the genuine R3 test ----------

    def test_r3_depends_on_upstream_closure_full(self):
        """R3: over depends_on (downstream depends_on upstream), the reverse
        transitive closure of a REQ is the whole REQ<-SPEC<-IMPL<-TEST<-ADR
        traceability chain. This is depends_on traceability, not impacts.
        reverse_dependents(REQ, current_only=False, transitive=True)."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("IMPL-01", "IMPL", "billing", depends_on=["SPEC-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["IMPL-01"]),
            _node("ADR-01", "ADR", "billing", status="accepted",
                  depends_on=["TEST-01"]),
        ])
        self.assertEqual(
            g.reverse_dependents("REQ-01", current_only=False, transitive=True),
            {"SPEC-01", "IMPL-01", "TEST-01", "ADR-01"},
        )

    def test_r3_depends_on_broken_link_shrinks_closure(self):
        """R3 broken-link variant: dropping one depends_on (IMPL no longer
        depends_on SPEC) severs the chain, so the upstream closure of REQ shrinks
        to just {SPEC} — IMPL/TEST/ADR fall out of REQ's traceability."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("IMPL-01", "IMPL", "billing"),  # depends_on SPEC-01 dropped
            _node("TEST-01", "TEST", "billing", depends_on=["IMPL-01"]),
            _node("ADR-01", "ADR", "billing", status="accepted",
                  depends_on=["TEST-01"]),
        ])
        self.assertEqual(
            g.reverse_dependents("REQ-01", current_only=False, transitive=True),
            {"SPEC-01"},
        )

    # -- reverse dependents / current-only (R4 delete-safety) ------------

    def test_reverse_current_dependents_excludes_non_current_TC078(self):
        """TC-078/090: only CURRENT docs count as reverse dependents.

        A deprecated dependent must not keep a doc from being demotable; a
        current dependent must (delete-safety guard reads exactly this).
        """
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing"),
            _node("IMPL-01", "IMPL", "billing", status="current",
                  depends_on=["SPEC-01"]),
            _node("IMPL-02", "IMPL", "billing", status="deprecated",
                  depends_on=["SPEC-01"]),
        ])
        self.assertEqual(g.reverse_dependents("SPEC-01"),
                         {"IMPL-01", "IMPL-02"})
        self.assertEqual(g.reverse_current_dependents("SPEC-01"),
                         {"IMPL-01"})
        self.assertEqual(
            g.reverse_dependents("SPEC-01", current_only=True),
            {"IMPL-01"},
        )

    def test_reverse_dependents_zero_when_only_links_TC090(self):
        """TC-090: a doc with zero depends_on dependents has empty reverse set."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing"),
            _node("IMPL-01", "IMPL", "billing"),   # no depends_on
        ])
        self.assertEqual(g.reverse_current_dependents("SPEC-01"), set())

    def test_reverse_dependents_transitive(self):
        """transitive=True returns the upstream closure (traceability)."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["SPEC-01"]),
        ])
        self.assertEqual(
            g.reverse_dependents("REQ-01", transitive=True),
            {"SPEC-01", "TEST-01"},
        )

    # -- edge classification (R7 + C13 dangling) -------------------------

    def test_classify_intra_domain_TC069(self):
        """Same-domain depends_on is intra_domain (allowed, §3.6)."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("REQ-01", "REQ", "billing"),
        ])
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "REQ-01")], "intra_domain")

    def test_classify_cross_domain_icd_allowed_TC070(self):
        """TC-070: cross-domain depends_on targeting an ICD is cross_domain_icd."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["ICD-09"]),
            _node("ICD-09", "ICD", "identity"),
        ])
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "ICD-09")], "cross_domain_icd")

    def test_classify_cross_domain_violation_TC071(self):
        """Cross-domain depends_on to a NON-ICD internal doc is a violation (R7)."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-09"]),
            _node("SPEC-09", "SPEC", "identity"),
        ])
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "SPEC-09")],
                         "cross_domain_violation")

    def test_classify_cross_domain_icd_status_blind_TC117(self):
        """TC-117: a cross-domain dep to a DEPRECATED ICD is still cross_domain_icd.

        Edge classification is purely structural (domain + type==ICD); the ICD's
        status is not a classification concern (it is audit/currency).
        """
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["ICD-09"]),
            _node("ICD-09", "ICD", "identity", status="deprecated"),
        ])
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "ICD-09")], "cross_domain_icd")

    def test_classify_cross_domain_impact_advisory(self):
        """Cross-domain IMPACTS edge is cross_domain_impact (advisory, not R7)."""
        g, _ = self._build([
            _node("ICD-09", "ICD", "identity", impacts=["SPEC-01"]),
            _node("SPEC-01", "SPEC", "billing"),
        ])
        edges = {(e["src"], e["dst"], e["field"]): e["kind"]
                 for e in g.classify_edges()}
        self.assertEqual(edges[("ICD-09", "SPEC-01", "impacts")],
                         "cross_domain_impact")

    def test_classify_dangling_TC083(self):
        """TC-083/C13: a depends_on to an absent id classifies as dangling.

        dangling is the structural input the guard reads to ALLOW (dead-link is
        audit's job), distinct from an unclassifiable target.
        """
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-99"]),
        ])
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "SPEC-99")], "dangling")

    def test_classify_unclassifiable_id_resolve_none_TC123(self):
        """TC-123: an id absent from the graph resolves to None; type_of/domain_of
        report UNKNOWN. The guard reads this to deny fail-closed (C13). dep-graph
        only reports the fact (dangling edge + UNKNOWN resolution)."""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["XYZ-01"]),
        ])
        self.assertIsNone(g.resolve("XYZ-01"))
        self.assertEqual(g.domain_of("XYZ-01"), "UNKNOWN")
        self.assertEqual(g.type_of("XYZ-01"), "UNKNOWN")
        kinds = {(e["src"], e["dst"]): e["kind"] for e in g.classify_edges()}
        self.assertEqual(kinds[("SPEC-01", "XYZ-01")], "dangling")

    # -- reverse orphans (R3/R8) -----------------------------------------

    def test_reverse_orphans_all_satisfied_TC093(self):
        """TC-093: every REQ has a SPEC and every SPEC has a TEST -> no orphans."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["SPEC-01"]),
        ])
        self.assertEqual(
            g.reverse_orphans(),
            {"req_without_spec": [], "spec_without_test": []},
        )

    def test_reverse_orphan_req_without_spec_TC094(self):
        """TC-094: a REQ with no SPEC depending on it is a reverse-orphan."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing"),   # depends_on absent
        ])
        r = g.reverse_orphans()
        self.assertIn("REQ-01", r["req_without_spec"])

    def test_reverse_orphan_spec_without_test_TC095(self):
        """TC-095: a SPEC with no TEST depending on it is a reverse-orphan."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            # no TEST
        ])
        r = g.reverse_orphans()
        self.assertIn("SPEC-01", r["spec_without_test"])
        self.assertEqual(r["req_without_spec"], [])   # REQ-01 has SPEC-01

    def test_reverse_orphans_current_only(self):
        """Deprecated REQ/SPEC are excluded from reverse-orphan (current only)."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing", status="deprecated"),
            _node("SPEC-01", "SPEC", "billing", status="deprecated",
                  depends_on=["REQ-01"]),
        ])
        self.assertEqual(
            g.reverse_orphans(),
            {"req_without_spec": [], "spec_without_test": []},
        )

    def test_reverse_orphan_link_is_depends_on_not_impacts(self):
        """A SPEC reaching a REQ only via impacts (not depends_on) does NOT
        clear the REQ's reverse-orphan status (link is strict depends_on)."""
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", impacts=["REQ-01"]),
        ])
        self.assertIn("REQ-01", g.reverse_orphans()["req_without_spec"])

    # -- resolve (de-facto domain_of/type_of/status_of) ------------------

    def test_resolve_return_keys(self):
        """resolve() returns exactly {path, domain, type, status} for a known id.

        This is the contract guard/linter/audit rely on (risk-to-report).
        """
        g, _ = self._build([
            _node("ICD-09", "ICD", "identity", status="current"),
        ])
        r = g.resolve("ICD-09")
        self.assertEqual(set(r.keys()), {"path", "domain", "type", "status"})
        self.assertEqual(r["domain"], "identity")
        self.assertEqual(r["type"], "ICD")
        self.assertEqual(r["status"], "current")
        self.assertTrue(r["path"].endswith("ICD.md"))

    def test_resolve_unknown_is_none(self):
        """resolve() of an id absent from the corpus is None."""
        g, _ = self._build([_node("SPEC-01", "SPEC", "billing")])
        self.assertIsNone(g.resolve("SPEC-99"))

    def test_to_json_shape_deterministic(self):
        """to_json() yields sorted node ids and serializable edges."""
        g, _ = self._build([
            _node("SPEC-02", "SPEC", "billing", depends_on=["ICD-09"]),
            _node("SPEC-01", "SPEC", "billing"),
            _node("ICD-09", "ICD", "identity"),
        ])
        j = g.to_json()
        ids = [n["id"] for n in j["nodes"]]
        self.assertEqual(ids, sorted(ids))
        self.assertIn("edges", j)
        # JSON round-trip must not raise.
        import json
        json.loads(json.dumps(j, ensure_ascii=False))

    def test_no_frontmatter_file_not_a_node(self):
        """A .md without frontmatter is a parse_warning, never a graph node."""
        _depgraph = _util.load_core("_depgraph")
        root = _util.make_repo({"docs/readme.md": "# plain markdown, no fm\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = _depgraph.build_graph(os.path.join(root, "docs"))
        self.assertEqual(g.nodes, {})
        self.assertTrue(g.parse_warnings)


class DepGraphCLITest(unittest.TestCase):
    def _repo(self, nodes):
        files = {}
        for fm in nodes:
            rel = _path_for(fm["domain"], fm["type"], fm["id"])
            files[rel] = _util.fm_block(fm)
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def test_cli_root_missing_exit_3(self):
        """Missing root -> exit 3 (slice 05 A.6)."""
        out, code = _util.invoke(
            "dep-graph", argv=["--root", "/no/such/docs", "--classify-edges"])
        self.assertEqual(code, 3)

    def test_cli_usage_error_exit_2(self):
        """No mode -> usage error exit 2."""
        root = self._repo([_node("SPEC-01", "SPEC", "billing")])
        out, code = _util.invoke("dep-graph", argv=["--root", root])
        self.assertEqual(code, 2)

    def test_cli_unknown_arg_exit_2(self):
        out, code = _util.invoke("dep-graph", argv=["--bogus"])
        self.assertEqual(code, 2)

    def test_cli_impacts_exit_0_with_findings(self):
        """Findings present but exit stays 0 (query tool, not a gate)."""
        root = self._repo([
            _node("ICD-09", "ICD", "identity", impacts=["SPEC-01"]),
            _node("SPEC-01", "SPEC", "billing"),
        ])
        out, code = _util.invoke(
            "dep-graph", argv=["--root", root, "--impacts", "ICD-09"])
        self.assertEqual(code, 0)
        self.assertIn("SPEC-01", out)

    def test_cli_reverse_refs_current_only_default_TC078(self):
        """--reverse-refs is the delete-safety call: current-only by default.

        A deprecated dependent must NOT appear; a current one must. Exit 0.
        """
        root = self._repo([
            _node("SPEC-01", "SPEC", "billing"),
            _node("IMPL-01", "IMPL", "billing", status="current",
                  depends_on=["SPEC-01"]),
            _node("IMPL-02", "IMPL", "billing", status="deprecated",
                  depends_on=["SPEC-01"]),
        ])
        out, code = _util.invoke(
            "dep-graph", argv=["--root", root, "--reverse-refs", "SPEC-01"])
        self.assertEqual(code, 0)
        self.assertIn("IMPL-01", out)
        self.assertNotIn("IMPL-02", out)
        self.assertIn("count: 1", out)

    def test_cli_reverse_refs_zero_count(self):
        root = self._repo([
            _node("SPEC-01", "SPEC", "billing"),
            _node("IMPL-01", "IMPL", "billing"),
        ])
        out, code = _util.invoke(
            "dep-graph", argv=["--root", root, "--reverse-refs", "SPEC-01"])
        self.assertEqual(code, 0)
        self.assertIn("count: 0", out)

    def test_cli_classify_edges_json(self):
        """--classify-edges --json emits parseable edges with kinds."""
        import json
        root = self._repo([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-09"]),
            _node("SPEC-09", "SPEC", "identity"),
        ])
        out, code = _util.invoke(
            "dep-graph",
            argv=["--root", root, "--classify-edges", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        kinds = {(e["src"], e["dst"]): e["kind"] for e in data["edges"]}
        self.assertEqual(kinds[("SPEC-01", "SPEC-09")],
                         "cross_domain_violation")

    def test_cli_reverse_orphans(self):
        root = self._repo([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing"),   # no depends_on -> REQ orphaned
        ])
        out, code = _util.invoke(
            "dep-graph", argv=["--root", root, "--reverse-orphans"])
        self.assertEqual(code, 0)
        self.assertIn("REQ-01", out)


if __name__ == "__main__":
    unittest.main()
