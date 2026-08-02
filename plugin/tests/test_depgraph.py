# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for the dependency-graph core (_depgraph) and CLI (dep-graph.py).

Covers 仕様 §5.2 frozen API and slice-05 PART A:
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

    def test_reverse_dependents_default_is_direct_not_transitive(self):
        """既定は直接依存のみ: 廃止済み中間ノード越しにしか届かない current 文書は
        逆参照に数えない(削除安全ガード/孤児判定 R8 の前提)。"""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing"),
            _node("IMPL-01", "IMPL", "billing", status="deprecated",
                  depends_on=["SPEC-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["IMPL-01"]),
        ])
        self.assertEqual(g.reverse_dependents("SPEC-01"), {"IMPL-01"})
        self.assertEqual(g.reverse_current_dependents("SPEC-01"), set())

    def test_status_of_convenience(self):
        """status_of: 既知 id は frontmatter の status、未知 id は UNKNOWN(例外なし)。"""
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", status="current"),
        ])
        self.assertEqual(g.status_of("SPEC-01"), "current")
        self.assertEqual(g.status_of("NOPE-99"), "UNKNOWN")

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

    # -- find_cycles (ADR-038 / #89) ---------------------------------------

    def test_no_cycles_in_acyclic_chain(self):
        g, _ = self._build([
            _node("REQ-01", "REQ", "billing"),
            _node("SPEC-01", "SPEC", "billing", depends_on=["REQ-01"]),
            _node("TEST-01", "TEST", "billing", depends_on=["SPEC-01"]),
        ])
        self.assertEqual(g.find_cycles(), [])

    def test_self_dependency_is_a_cycle(self):
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-01"]),
        ])
        self.assertEqual(g.find_cycles(), [["SPEC-01"]])

    def test_multi_node_cycle_detected(self):
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-02"]),
            _node("SPEC-02", "SPEC", "billing", depends_on=["SPEC-03"]),
            _node("SPEC-03", "SPEC", "billing", depends_on=["SPEC-01"]),
        ])
        cycles = g.find_cycles()
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0], ["SPEC-01", "SPEC-02", "SPEC-03"])

    def test_dangling_edge_is_not_a_cycle(self):
        # 索引に無い依存先はたどらない(実在ノード間の循環だけ)。
        g, _ = self._build([
            _node("SPEC-01", "SPEC", "billing", depends_on=["SPEC-99"]),
        ])
        self.assertEqual(g.find_cycles(), [])

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

    def test_duplicate_id_path_sorted_first_wins(self):
        """同じ id の別ファイルはパス整列の最初が先勝ちでノードになる(ADR-049)。

        docs-audit の shadowed_document が報告する採用先と、resolve() の答え
        (guard/linter が読む domain/type/status)と、inject-contract が契約へ
        運ぶ文書は、一致しなければならない。採用規則の正本は登録簿の
        resolve_duplicate_id ただ一つで、ここは自前の整列規則を持たない。"""
        _depgraph = _util.load_core("_depgraph")
        _registry = _util.load_core("_registry")
        fa = _node("DUP-1", "RESEARCH", "alpha")
        fz = _node("DUP-1", "RESEARCH", "zulu")
        root = _util.make_repo({
            "docs/alpha/research/DUP-1.md": _util.fm_block(fa),
            "docs/zulu/research/DUP-1.md": _util.fm_block(fz),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        g = _depgraph.build_graph(os.path.join(root, "docs"))
        self.assertEqual(g.nodes["DUP-1"]["path"], "alpha/research/DUP-1.md")
        self.assertEqual(g.resolve("DUP-1")["domain"], "alpha")
        self.assertEqual(sorted(g.dup_ids["DUP-1"]),
                         ["alpha/research/DUP-1.md", "zulu/research/DUP-1.md"])
        # 採用先はグラフが独自に決めず、登録簿の規則と同じ答えになる。
        self.assertEqual(g.nodes["DUP-1"]["path"],
                         _registry.resolve_duplicate_id(g.dup_ids["DUP-1"]))

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


class JsonNodeShapeTest(unittest.TestCase):
    """ADR-087 / #149: 問い合わせの節点は隠さない。

    以前は直列化が八項の白名簿で絞っており、正本がどこにも無いまま組み立てと別々に
    手で保つ形になっていた。そして実際にずれた —— 組み立てが四項を足した後も白名簿は
    八項のままで、**必須項の題名は最初から集められてさえいなかった**。
    """

    def _graph(self):
        root = _util.make_repo({
            "docs/_system/glossary.md": _util.fm_block({
                "id": "GLOSSARY-001", "title": "用語", "type": "GLOSSARY",
                "domain": "_system", "status": "current", "owner": "o",
                "updated": "2026-06-01", "sources": []}) + "本文。\n",
            "docs/billing/spec/SPEC-1-x.md": _util.fm_block({
                "id": "SPEC-1", "title": "請求の仕様", "type": "SPEC",
                "domain": "billing", "status": "current", "owner": "o",
                "updated": "2026-06-01", "sources": [], "review_by": "2026-12-01",
                "llm_context": "task"}) + "本文。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return _util.load_core("_depgraph").build_graph(os.path.join(root, "docs"))

    def test_title_is_returned(self):
        """題名は必須項なので、必ず返る(取れないのではなく返していなかった)。"""
        data = self._graph().to_json()
        by_id = {n["id"]: n for n in data["nodes"]}
        self.assertEqual(by_id["SPEC-1"]["title"], "請求の仕様")

    def test_lifecycle_fields_are_returned(self):
        """鮮度と後継の項も返る。読み手が自分で判じられる。"""
        by_id = {n["id"]: n for n in self._graph().to_json()["nodes"]}
        node = by_id["SPEC-1"]
        self.assertEqual(node["updated"], "2026-06-01")
        self.assertEqual(node["review_by"], "2026-12-01")
        self.assertEqual(node["llm_context"], "task")
        self.assertIn("superseded_by", node)

    def test_json_node_hides_nothing_from_the_builder(self):
        """**これが本当の歯止めである。** 組み立てが節点へ入れた項と、直列化が返す項が
        一致すること。正本を書いても、一致を機械が見ていなければまたずれる(ADR-087)。"""
        g = self._graph()
        data = g.to_json()
        for node in data["nodes"]:
            built = set(g.nodes[node["id"]].keys()) | {"id"}
            self.assertEqual(
                set(node.keys()), built,
                "組み立てと直列化の項がずれた: %s(白名簿を復活させていないか。ADR-087)"
                % node["id"])

    def test_indexed_fields_carry_resolved_edges(self):
        """唯一の例外。depends_on/impacts は生の値ではなく索引の値を返す。"""
        g = self._graph()
        by_id = {n["id"]: n for n in g.to_json()["nodes"]}
        for field in ("depends_on", "impacts"):
            self.assertIsInstance(by_id["SPEC-1"][field], list, field)


class SubdomainNodeTest(unittest.TestCase):
    """ADR-092 / #152: 節点がドメインの種類を運ぶ。未分類は空文字で、値が化けない。

    呼び手はこの値をそのまま出すだけにする。語彙を自分の実装に持たない。
    """

    def _graph(self, docs):
        base = {
            "docs/_system/glossary.md": _util.fm_block({
                "id": "GLOSSARY-001", "title": "用語", "type": "GLOSSARY",
                "domain": "_system", "status": "current", "owner": "o",
                "updated": "2026-06-01", "sources": []}) + "本文。\n",
        }
        base.update(docs)
        root = _util.make_repo(base)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return _util.load_core("_depgraph").build_graph(os.path.join(root, "docs"))

    def _spec(self, num, extra=None):
        fm = {
            "id": "SPEC-%d" % num, "title": "s%d" % num, "type": "SPEC",
            "domain": "billing", "status": "current", "owner": "o",
            "updated": "2026-06-01", "sources": [],
        }
        if extra:
            fm.update(extra)
        return {"docs/billing/spec/SPEC-%d-x.md" % num: _util.fm_block(fm) + "本文。\n"}

    def test_declared_kind_is_carried(self):
        docs = {}
        for num, kind in ((1, "core"), (2, "supporting"), (3, "generic")):
            docs.update(self._spec(num, {"subdomain": kind}))
        by_id = {n["id"]: n for n in self._graph(docs).to_json()["nodes"]}
        self.assertEqual(by_id["SPEC-1"]["subdomain"], "core")
        self.assertEqual(by_id["SPEC-2"]["subdomain"], "supporting")
        self.assertEqual(by_id["SPEC-3"]["subdomain"], "generic")

    def test_absent_is_empty_string_not_missing(self):
        """未分類は空文字。項が消えると読み手が「取れなかった」と見分けられない。"""
        by_id = {n["id"]: n for n in self._graph(self._spec(1)).to_json()["nodes"]}
        self.assertIn("subdomain", by_id["SPEC-1"])
        self.assertEqual(by_id["SPEC-1"]["subdomain"], "")
        self.assertEqual(by_id["GLOSSARY-001"]["subdomain"], "")

    def test_non_string_does_not_leak_a_python_repr(self):
        """真偽値・一覧が来ても、節点には空文字が載る(値が化けない)。"""
        docs = {}
        docs.update(self._spec(1, {"subdomain": True}))
        docs.update(self._spec(2, {"subdomain": ["core"]}))
        by_id = {n["id"]: n for n in self._graph(docs).to_json()["nodes"]}
        self.assertEqual(by_id["SPEC-1"]["subdomain"], "")
        self.assertEqual(by_id["SPEC-2"]["subdomain"], "")

    def test_no_field_leaks_a_container_repr(self):
        """一項だけ塞がない。同じ補助を通る全てのスカラ項で内部表記が漏れないこと。

        `_coerce_str` は「スカラ値を str に」と宣言していたのに、一覧に str() を当てて
        "['x']" を返していた。題名でも llm_context でも起きる欠陥だった。
        """
        docs = self._spec(1, {"title": ["t"], "llm_context": ["task"],
                              "status": ["current"], "superseded_by": ["SPEC-9"]})
        by_id = {n["id"]: n for n in self._graph(docs).to_json()["nodes"]}
        node = by_id["SPEC-1"]
        self.assertEqual(node["title"], "")
        self.assertEqual(node["llm_context"], "")
        self.assertEqual(node["superseded_by"], "")
        # status は空なら型の既定に落ちる(既存の挙動)。内部表記は載らない。
        self.assertEqual(node["status"], "current")
        for key, value in node.items():
            if isinstance(value, str):
                self.assertNotIn("['", value, key)

    def test_graph_does_not_check_the_vocabulary(self):
        """語彙の当否はリンタが検める。グラフは運ぶだけで、黙って捨てない。"""
        by_id = {n["id"]: n for n in
                 self._graph(self._spec(1, {"subdomain": "CORE_DOMAIN"}))
                 .to_json()["nodes"]}
        self.assertEqual(by_id["SPEC-1"]["subdomain"], "CORE_DOMAIN")


class MirroredEdgeTest(unittest.TestCase):
    """ADR-088 / #151: 両端から書かれた同じ事実に印を付ける。

    `A impacts B` と `B depends_on A` は同じ一つの事実を両端から書いたものだが、
    印が無いため読み手が図に描くと**循環に見えた**。利用者の実際の指摘 ——
    「依存しあっているものは異常？」。本当の循環は 0 件だった。
    画面が作った嘘を、利用者が正しく読んだ。
    """

    def _graph(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return _util.load_core("_depgraph").build_graph(os.path.join(root, "docs"))

    def _doc(self, doc_id, type_code, extra=None):
        meta = {"id": doc_id, "title": "t", "type": type_code, "domain": "billing",
                "status": "current", "owner": "o", "updated": "2026-06-01",
                "sources": []}
        if extra:
            meta.update(extra)
        return _util.fm_block(meta) + "本文。\n"

    def _both_ends(self):
        """SPEC-1 impacts IMPL-1 と IMPL-1 depends_on SPEC-1 の両方が書かれた木。"""
        return self._graph({
            "docs/billing/spec/SPEC-1-x.md": self._doc(
                "SPEC-1", "SPEC", {"impacts": ["IMPL-1"]}),
            "docs/billing/implementation/IMPL-1-x.md": self._doc(
                "IMPL-1", "IMPL", {"depends_on": ["SPEC-1"]}),
        })

    def test_both_ends_written_are_marked(self):
        edges = self._both_ends().classify_edges()
        self.assertEqual(len(edges), 2, edges)
        self.assertTrue(all(e["mirrored"] for e in edges), edges)

    def test_one_end_only_is_not_marked(self):
        """片方だけの宣言は正当である。印は事実の報告に留め、咎めない。"""
        g = self._graph({
            "docs/billing/spec/SPEC-1-x.md": self._doc("SPEC-1", "SPEC"),
            "docs/billing/implementation/IMPL-1-x.md": self._doc(
                "IMPL-1", "IMPL", {"depends_on": ["SPEC-1"]}),
        })
        edges = g.classify_edges()
        self.assertEqual(len(edges), 1, edges)
        self.assertFalse(edges[0]["mirrored"])

    def test_marker_does_not_replace_kind(self):
        """軸を混ぜない。kind は越境と dangling の分類のままである。"""
        edges = self._both_ends().classify_edges()
        for e in edges:
            self.assertEqual(e["kind"], "intra_domain", e)
            self.assertIn("mirrored", e)

    def test_marker_is_not_a_cycle(self):
        """**印は循環ではない。** 両端書きの木に循環は無い(強連結成分は空)。"""
        g = self._both_ends()
        self.assertTrue(all(e["mirrored"] for e in g.classify_edges()))
        self.assertEqual(g.find_cycles(), [],
                         "両端書きを循環として返してはならない(ADR-088)")

    def test_real_cycle_is_still_found(self):
        """本当の循環は引き続き find_cycles が返す。二つを混同しない。"""
        g = self._graph({
            "docs/billing/spec/SPEC-1-x.md": self._doc(
                "SPEC-1", "SPEC", {"depends_on": ["SPEC-2"]}),
            "docs/billing/spec/SPEC-2-x.md": self._doc(
                "SPEC-2", "SPEC", {"depends_on": ["SPEC-1"]}),
        })
        self.assertTrue(g.find_cycles(), "本当の循環は返るはず")
        # depends_on だけの往復なので、両端書きの印は付かない。
        self.assertFalse(any(e["mirrored"] for e in g.classify_edges()))

    def test_marker_agrees_with_the_readers_own_folding(self):
        """読み手が自前の鍵(src/dst を昇順)で畳んだ結果と、上流の印が一致すること。

        実物で確かめてある(2026-08-02): 呼び手の木で 10 対 = 20 本（辺の 28%）が
        印を持ち、自前の鍵で数えた結果と完全に一致した。
        """
        edges = self._both_ends().classify_edges()
        key = lambda e: "|".join(sorted([e["src"], e["dst"]]))
        dep = {key(e) for e in edges if e["field"] == "depends_on"}
        imp = {key(e) for e in edges if e["field"] == "impacts"}
        marked = [e for e in edges if e["mirrored"]]
        self.assertEqual(len(marked), len(dep & imp) * 2)


class SystemShelfRequirementTest(unittest.TestCase):
    """ADR-091 / #153: 横断の棚(_system/)に在る要求は逆孤児の対象にしない。

    実装して分かった事実に合わせた設計である。当初は「要求は要求が実現してよい」と
    して判定を広げようとしたが、**ドメインの文書が _system の文書を depends_on で
    指すことは、この体系ではできない** —— 越境依存のガードが「_system の ICD 宛に
    してください」と拒み、_system に ICD は無い。実測でも、_system の正本
    (DECIDED・NONGOAL・WATCH)を frontmatter で指している文書は一件も無かった。
    横断の正本は本文で参照され、辺では指されない。
    """

    def _graph(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return _util.load_core("_depgraph").build_graph(os.path.join(root, "docs"))

    def _doc(self, doc_id, type_code, domain="billing", extra=None):
        meta = {"id": doc_id, "title": "t", "type": type_code, "domain": domain,
                "status": "current", "owner": "o", "updated": "2026-06-01",
                "sources": []}
        if extra:
            meta.update(extra)
        return _util.fm_block(meta) + "本文。\n"

    def test_system_shelf_req_is_not_a_reverse_orphan(self):
        g = self._graph({
            "docs/_system/REQ-0-x.md": self._doc("REQ-0", "REQ", "_system"),
        })
        self.assertNotIn("REQ-0", g.reverse_orphans()["req_without_spec"],
                         "横断の棚に在る要求は辺で指されないので、逆孤児にしない")

    def test_domain_req_without_spec_is_still_a_reverse_orphan(self):
        """広げただけで緩めていない。ドメインの要求は引き続き立つ。"""
        g = self._graph({
            "docs/billing/REQ-1-x.md": self._doc("REQ-1", "REQ"),
        })
        self.assertIn("REQ-1", g.reverse_orphans()["req_without_spec"])

    def test_domain_req_with_a_spec_is_clean(self):
        g = self._graph({
            "docs/billing/REQ-1-x.md": self._doc("REQ-1", "REQ"),
            "docs/billing/spec/SPEC-1-x.md": self._doc(
                "SPEC-1", "SPEC", extra={"depends_on": ["REQ-1"]}),
        })
        self.assertNotIn("REQ-1", g.reverse_orphans()["req_without_spec"])

    def test_spec_without_test_is_unchanged(self):
        """仕様→試験の側は触っていない。"""
        g = self._graph({
            "docs/billing/spec/SPEC-1-x.md": self._doc("SPEC-1", "SPEC"),
        })
        self.assertIn("SPEC-1", g.reverse_orphans()["spec_without_test"])
