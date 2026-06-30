"""Tests for render-projection.py (deterministic projection renderer).

Covers MASTER §5.6 and slice-06 §3 (render-projection). The TC matrix only
specified DRIFT DETECTION on the audit side (TC-042/098/099/100); this file
encodes the CRITIQUE GAP the synthesis flagged: the RENDERER itself had no
cases. Per BRIEF2 "render-projection determinism/idempotency/--check/headers/
type:OVERVIEW" we assert:

- determinism: two renders are byte-identical (§3.6 R1).
- idempotency: render then re-render produces no change (§3.6).
- --check: nonzero exit on drift, zero when in sync; missing projection = drift
  (the basis docs-audit's projection_drift TC-098/099/100/042 compares against).
- header line `描画される。手で編集しない。` present (§3.9 / 付録B).
- icd-index frontmatter `type: OVERVIEW`, `id: OVERVIEW-<n>` (C8).
- context-map BEGIN/END markers; prose OUTSIDE the markers preserved on
  re-render; only the marked region diffed by --check (§3.5).
- overview covers exactly the current docs; deprecated/archived excluded;
  projections excluded from their own listing (R1 "Overview投影が現行文書を網羅").

All temp trees are made via _util.make_repo / write_doc and cleaned up by the
caller (BRIEF2 / _util cleanup convention).
"""
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


HEADER_LINE = "描画される。手で編集しない。"
CTXMAP_BEGIN = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
CTXMAP_END = "<!-- END PROJECTION:context-map-skeleton -->"


def _fm(doc_id, type_code, domain, status="current", updated="2026-01-01",
        title=None, **extra):
    """Registry-shaped frontmatter dict for a doc."""
    fm = {
        "id": doc_id,
        "title": title if title is not None else (doc_id + "の題"),
        "type": type_code,
        "domain": domain,
        "status": status,
        "owner": "t",
        "updated": updated,
        "sources": [],
    }
    fm.update(extra)
    return fm


class RenderProjectionBase(unittest.TestCase):
    """Shared fixture: a small docs tree with current + deprecated + ICD docs."""

    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.docs = os.path.join(self.root, "docs")
        # _system canonical (current)
        _util.write_doc(self.docs, "_system/decided-facts.md",
                        _fm("DECIDED-001", "DECIDED", "_system",
                            updated="2026-02-01", review_by="2026-09-01"),
                        body="本文。\n")
        # two domains, each with an ICD (current)
        _util.write_doc(self.docs, "billing/ICD.md",
                        _fm("ICD-01", "ICD", "billing", updated="2026-03-10",
                            canonical_for=["refund", "invoice"]),
                        body="本文。\n")
        _util.write_doc(self.docs, "orders/ICD.md",
                        _fm("ICD-02", "ICD", "orders", updated="2026-01-05"),
                        body="本文。\n")
        # a current SPEC that depends cross-domain on the orders ICD (legal edge)
        _util.write_doc(self.docs, "billing/spec/SPEC-014.md",
                        _fm("SPEC-014", "SPEC", "billing", updated="2026-03-15",
                            depends_on=["ICD-02"]),
                        body="本文。\n")
        # a deprecated SPEC — MUST be excluded from Overview
        _util.write_doc(self.docs, "orders/spec/SPEC-020.md",
                        _fm("SPEC-020", "SPEC", "orders", status="deprecated",
                            updated="2026-01-20"),
                        body="本文。\n")

    def render(self, mode, extra=None):
        """Render `mode` to stdout (--out -) and return (text, exit_code)."""
        argv = [mode, "--docs-root", self.docs, "--out", "-"]
        if extra:
            argv += extra
        return _util.invoke("render-projection", argv)


# ---------------------------------------------------------------------------
# Determinism + idempotency (§3.6 R1)
# ---------------------------------------------------------------------------
class TestDeterminism(RenderProjectionBase):
    """Critique gap: renderer determinism/idempotency (slice-06 T-RP-2/T-RP-6)."""

    def test_two_renders_byte_identical(self):
        """Two stdout renders of the same inputs are byte-identical (R1)."""
        for mode in ("overview", "icd-index"):
            a, ca = self.render(mode)
            b, cb = self.render(mode)
            self.assertEqual(ca, 0)
            self.assertEqual(cb, 0)
            self.assertEqual(a, b, "%s not deterministic" % mode)

    def test_no_wall_clock_updated_is_max_source(self):
        """`updated` is the max source `updated`, not today (§3.6 no wall-clock).

        Overview's max current `updated` is SPEC-014's 2026-03-15; ICD-index's
        max ICD `updated` is ICD-01's 2026-03-10. A wall-clock date (2026-06-29)
        must NOT appear.
        """
        ov, _ = self.render("overview")
        self.assertIn("updated: 2026-03-15", ov)
        self.assertNotIn("2026-06-29", ov)
        ix, _ = self.render("icd-index")
        self.assertIn("updated: 2026-03-10", ix)

    def test_render_then_rerender_no_change(self):
        """Write to canonical paths, render again: files unchanged (idempotent)."""
        out, code = _util.invoke("render-projection",
                                 ["all", "--docs-root", self.docs])
        self.assertEqual(code, 0, out)
        sysdir = os.path.join(self.docs, "_system")
        first = {n: _util.read(os.path.join(sysdir, n))
                 for n in ("overview.md", "icd-index.md", "context-map.md")}
        _util.invoke("render-projection", ["all", "--docs-root", self.docs])
        for name, before in first.items():
            after = _util.read(os.path.join(sysdir, name))
            self.assertEqual(before, after, "%s changed on re-render" % name)


# ---------------------------------------------------------------------------
# --check drift mode (basis for audit TC-042/098/099/100)
# ---------------------------------------------------------------------------
class TestCheckMode(RenderProjectionBase):
    """--check exits nonzero on drift, zero when synced (slice-06 T-RP-3)."""

    def _render_all(self):
        _util.invoke("render-projection", ["all", "--docs-root", self.docs])

    def test_check_zero_when_synced(self):
        """After `all`, --check on every projection exits 0 (TC-098 pass side)."""
        self._render_all()
        for mode in ("overview", "icd-index", "context-map-skeleton"):
            out, code = _util.invoke(
                "render-projection",
                [mode, "--docs-root", self.docs, "--check"])
            self.assertEqual(code, 0, "%s: expected sync, got drift: %s"
                             % (mode, out))
        out, code = _util.invoke("render-projection",
                                 ["all", "--docs-root", self.docs, "--check"])
        self.assertEqual(code, 0, out)

    def test_check_nonzero_on_missing_projection(self):
        """--check against a never-rendered projection = drift (投影未生成)."""
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", self.docs, "--check"])
        self.assertNotEqual(code, 0)
        self.assertIn("投影未生成", out)

    def test_check_nonzero_on_hand_edit(self):
        """Hand-edit a rendered Overview row -> --check exits nonzero (TC-042/099/100).

        This is the renderer side of the audit's projection_drift: the renderer
        is the source of truth the audit compares the on-disk projection to.
        """
        self._render_all()
        ov_path = os.path.join(self.docs, "_system/overview.md")
        text = _util.read(ov_path)
        with open(ov_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text + "| HAND-1 | X | y | 手編集 |\n")
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", self.docs, "--check"])
        self.assertNotEqual(code, 0)
        self.assertIn("投影ドリフト", out)

    def test_check_drift_when_current_doc_added(self):
        """Add a current doc after render -> Overview --check drifts (TC-099)."""
        self._render_all()
        _util.write_doc(self.docs, "orders/spec/SPEC-030.md",
                        _fm("SPEC-030", "SPEC", "orders", updated="2026-04-01"))
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", self.docs, "--check"])
        self.assertNotEqual(code, 0, "adding a current doc must drift Overview")


# ---------------------------------------------------------------------------
# Header line + projection frontmatter (§3.9 / C8)
# ---------------------------------------------------------------------------
class TestHeadersAndType(RenderProjectionBase):
    """Header line present; icd-index type OVERVIEW / id OVERVIEW-<n> (C8)."""

    def test_header_line_present(self):
        """First body line is `描画される。手で編集しない。` (both projections)."""
        for mode in ("overview", "icd-index"):
            text, _ = self.render(mode)
            self.assertIn(HEADER_LINE, text, "%s missing header" % mode)
            # the header is the first non-empty BODY line (after frontmatter)
            body = text.split("---\n", 2)[-1]
            first_nonempty = next(l for l in body.splitlines() if l.strip())
            self.assertEqual(first_nonempty, HEADER_LINE)

    def test_icd_index_type_is_overview(self):
        """ICD-index frontmatter carries type: OVERVIEW and id: OVERVIEW-<n> (C8)."""
        text, _ = self.render("icd-index")
        self.assertIn("type: OVERVIEW", text)
        self.assertRegex(text, r"id: OVERVIEW-\d+")
        self.assertNotIn("type: ICDINDEX", text)
        self.assertNotIn("type: INDEX", text)

    def test_overview_type_is_overview(self):
        """Overview frontmatter carries type: OVERVIEW and llm_context: always."""
        text, _ = self.render("overview")
        self.assertIn("type: OVERVIEW", text)
        self.assertIn("llm_context: always", text)


# ---------------------------------------------------------------------------
# Overview coverage of current docs (R1) + projection self-exclusion
# ---------------------------------------------------------------------------
class TestOverviewCoverage(RenderProjectionBase):
    """Overview covers exactly current docs; excludes deprecated + projections."""

    def test_overview_lists_each_current_doc_once(self):
        """Every current source doc appears exactly once (TC-098 / R1)."""
        text, _ = self.render("overview")
        for doc_id in ("DECIDED-001", "ICD-01", "ICD-02", "SPEC-014"):
            self.assertEqual(text.count("| %s |" % doc_id), 1,
                             "%s not listed exactly once" % doc_id)

    def test_overview_excludes_deprecated(self):
        """A deprecated doc is absent from Overview (TC-100 source side)."""
        text, _ = self.render("overview")
        self.assertNotIn("SPEC-020", text)

    def test_overview_excludes_its_own_projections(self):
        """After `all`, the projection docs are NOT listed in Overview.

        A projection is a rendered view, not a catalogued source. Excluding them
        keeps `all` self-consistent: re-running --check stays in sync (no
        self-referential drift). We assert no OVERVIEW-/CTXMAP- TABLE ROW.
        """
        _util.invoke("render-projection", ["all", "--docs-root", self.docs])
        ov = _util.read(os.path.join(self.docs, "_system/overview.md"))
        # table rows start with "| <id> |"; the frontmatter id: line is not a row
        self.assertNotIn("| OVERVIEW-", ov)
        self.assertNotIn("| CTXMAP-", ov)

    def test_overview_deterministic_ordering(self):
        """Domain order (_system first) then registry type order then id."""
        text, _ = self.render("overview")
        i_decided = text.index("DECIDED-001")   # _system first
        i_icd01 = text.index("ICD-01")           # billing
        i_spec = text.index("SPEC-014")          # billing, after ICD in type order
        i_icd02 = text.index("ICD-02")           # orders, last domain
        self.assertLess(i_decided, i_icd01)
        self.assertLess(i_icd01, i_spec)
        self.assertLess(i_spec, i_icd02)


# ---------------------------------------------------------------------------
# ICD-index from frontmatter (slice-06 T-RP-4)
# ---------------------------------------------------------------------------
class TestIcdIndex(RenderProjectionBase):
    """ICD-index lists all ICDs from frontmatter; bodies not inlined."""

    def test_lists_all_icds(self):
        """Both ICDs appear; their canonical_for comes from frontmatter."""
        text, _ = self.render("icd-index")
        self.assertIn("ICD-01", text)
        self.assertIn("ICD-02", text)
        self.assertIn("refund", text)   # ICD-01 canonical_for
        self.assertIn("invoice", text)

    def test_bodies_not_inlined(self):
        """The ICD body text (本文。) is NOT pulled into the index."""
        text, _ = self.render("icd-index")
        self.assertNotIn("本文", text)

    def test_zero_icds_is_valid(self):
        """A tree with no ICDs renders a valid index with a '現行 ICD なし' note."""
        empty = _util.make_repo({
            "docs/_system/decided-facts.md": _util.fm_block(
                _fm("DECIDED-001", "DECIDED", "_system")) + "本文。\n",
        })
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        text, code = _util.invoke(
            "render-projection",
            ["icd-index", "--docs-root", os.path.join(empty, "docs"),
             "--out", "-"])
        self.assertEqual(code, 0)
        self.assertIn("現行 ICD なし", text)
        self.assertIn("type: OVERVIEW", text)


# ---------------------------------------------------------------------------
# Context-map skeleton: markers + outside-prose preservation (§3.5)
# ---------------------------------------------------------------------------
class TestContextMapSkeleton(RenderProjectionBase):
    """Skeleton region between markers; prose outside preserved (T-RP-5)."""

    def test_markers_present(self):
        """Rendered context-map carries BEGIN/END skeleton markers."""
        _util.invoke("render-projection",
                     ["context-map-skeleton", "--docs-root", self.docs])
        cm = _util.read(os.path.join(self.docs, "_system/context-map.md"))
        self.assertIn(CTXMAP_BEGIN, cm)
        self.assertIn(CTXMAP_END, cm)
        # the legal cross-domain edge SPEC-014 -> ICD-02 is in the skeleton
        self.assertIn("SPEC-014 --depends_on--> ICD-02", cm)

    def test_outside_prose_preserved_on_rerender(self):
        """Hand-written prose OUTSIDE the markers survives a re-render (§3.5)."""
        path = os.path.join(self.docs, "_system/context-map.md")
        _util.invoke("render-projection",
                     ["context-map-skeleton", "--docs-root", self.docs])
        text = _util.read(path)
        marker_text = "## 結合の要点\n返金は注文の境界に依存する。手書き。\n"
        text = text.replace(CTXMAP_END, CTXMAP_END + "\n\n" + marker_text)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        # re-render
        _util.invoke("render-projection",
                     ["context-map-skeleton", "--docs-root", self.docs])
        after = _util.read(path)
        self.assertIn("手書き", after, "outside prose was lost on re-render")
        self.assertIn(CTXMAP_BEGIN, after)
        self.assertIn(CTXMAP_END, after)

    def test_check_only_diffs_marked_region(self):
        """--check ignores prose OUTSIDE markers; flags edits INSIDE them.

        Editing outside the markers is NOT drift; editing inside IS drift (§3.5).
        """
        path = os.path.join(self.docs, "_system/context-map.md")
        _util.invoke("render-projection",
                     ["context-map-skeleton", "--docs-root", self.docs])
        text = _util.read(path)
        # 1) outside edit -> still in sync
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.replace(CTXMAP_END,
                                  CTXMAP_END + "\n\n勝手な散文。\n"))
        out, code = _util.invoke(
            "render-projection",
            ["context-map-skeleton", "--docs-root", self.docs, "--check"])
        self.assertEqual(code, 0, "outside-marker prose must not be drift: %s" % out)
        # 2) inside edit -> drift
        text2 = _util.read(path)
        text2 = text2.replace("SPEC-014 --depends_on--> ICD-02",
                              "SPEC-014 --depends_on--> ICD-99")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text2)
        out, code = _util.invoke(
            "render-projection",
            ["context-map-skeleton", "--docs-root", self.docs, "--check"])
        self.assertNotEqual(code, 0, "edit inside markers must drift")
        self.assertIn("骨組み", out)

    def test_violation_edge_marked(self):
        """An illegal cross-domain dep (-> non-ICD) is rendered with (境界違反)."""
        # billing SPEC depends on an orders internal SPEC (not its ICD) -> violation
        _util.write_doc(self.docs, "billing/spec/SPEC-099.md",
                        _fm("SPEC-099", "SPEC", "billing", updated="2026-03-01",
                            depends_on=["SPEC-020"]))
        out, code = _util.invoke(
            "render-projection",
            ["context-map-skeleton", "--docs-root", self.docs, "--out", "-"])
        self.assertEqual(code, 0)
        self.assertIn("(境界違反)", out)
        self.assertIn("SPEC-099 --depends_on--> SPEC-020", out)


# ---------------------------------------------------------------------------
# CLI surface + robustness
# ---------------------------------------------------------------------------
class TestCli(RenderProjectionBase):
    """CLI exit codes and arg validation."""

    def test_missing_root_exits_3(self):
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", os.path.join(self.root, "nope"),
             "--out", "-"])
        self.assertEqual(code, 3)

    def test_bad_mode_usage_error(self):
        out, code = _util.invoke("render-projection",
                                 ["bogus", "--docs-root", self.docs])
        self.assertEqual(code, 2)

    def test_no_mode_usage_error(self):
        out, code = _util.invoke("render-projection",
                                 ["--docs-root", self.docs])
        self.assertEqual(code, 2)

    def test_check_and_out_conflict(self):
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", self.docs, "--check", "--out", "-"])
        self.assertEqual(code, 2)

    def test_out_writes_named_path(self):
        target = os.path.join(self.root, "myoverview.md")
        out, code = _util.invoke(
            "render-projection",
            ["overview", "--docs-root", self.docs, "--out", target])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(target))
        self.assertIn(HEADER_LINE, _util.read(target))

    def test_malformed_doc_skipped(self):
        """A file with no frontmatter is skipped; render still succeeds."""
        bad = os.path.join(self.docs, "billing", "notes.md")
        with open(bad, "w", encoding="utf-8", newline="") as fh:
            fh.write("# just prose, no frontmatter\n")
        text, code = self.render("overview")
        self.assertEqual(code, 0)
        # the bad file contributes nothing; the good docs are still present
        self.assertIn("ICD-01", text)


class TestProjectionFrontmatterValid(RenderProjectionBase):
    """Every rendered projection carries the §3.4 required frontmatter keys, so
    the renderer's output passes the linter. Regression: `owner` was omitted from
    overview/icd-index and `owner`+`updated` from the context-map skeleton —
    surfaced by dogfooding the plugin on its own design docs (the renderer
    produced projections that failed the plugin's own required-key check)."""

    def test_rendered_projections_have_required_keys(self):
        reg = _util.load_core("_registry")
        fmmod = _util.load_core("_frontmatter")
        _out, code = _util.invoke(
            "render-projection", ["all", "--docs-root", self.docs])
        self.assertEqual(code, 0)
        for rel in ("_system/overview.md", "_system/icd-index.md",
                    "_system/context-map.md"):
            path = os.path.join(self.docs, rel)
            self.assertTrue(os.path.isfile(path), rel)
            fm, _body, _err = fmmod.parse(_util.read(path))
            for key in reg.REQUIRED_KEYS_L2:
                self.assertIn(key, fm, "%s missing required key %s" % (rel, key))
                if key != "sources":          # empty sources [] is allowed
                    self.assertNotIn(fm[key], (None, "", []),
                                     "%s has empty %s" % (rel, key))


if __name__ == "__main__":
    unittest.main()
