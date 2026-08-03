#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for scaffold.py (docs-system-init engine, non-destructive).

Covers 仕様 §5.8 + slice 07 §A and the critique gaps assigned to this
component:
  - non-destructive / idempotent re-run (second run all-skip, zero diff)
  - existing files untouched (sentinel glossary survives)
  - --dry-run writes nothing
  - creates EXACTLY the minimal set and NOT domain folders / watchlist /
    context-map / icd-index (§3.7 / A.2)
  - .docs-level marker written (C9)
  - Level-2 default selection
  - --fallback places under .claude/ (仕様 §9 / spec §5)
  - seeded DECIDED carries a non-empty review_by (created + 90d)
  - seeded GLOSSARY carries the §1 approved-term + calque tables
"""
import json
import os
import sys
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

TODAY = "2026-06-29"


class ScaffoldBase(unittest.TestCase):
    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def run_scaffold(self, *extra):
        argv = ["--root", self.root, "--today", TODAY] + list(extra)
        return _util.invoke("scaffold", argv=argv)

    def sysfile(self, name, prefix=""):
        return os.path.join(self.root, prefix, "doctrine_docs", "_system", name)

    def listing(self):
        out = []
        for dp, dn, fn in os.walk(self.root):
            for f in fn:
                out.append(os.path.relpath(os.path.join(dp, f), self.root))
        return sorted(out)


class TestCreatesMinimalSet(ScaffoldBase):
    """A1/A.6-1: fresh repo -> exactly the 4 _system docs + 2 pointers + marker."""

    def test_creates_exactly_the_minimal_set(self):
        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        expected = sorted([
            os.path.join("doctrine_docs", "_system", "glossary.md"),
            os.path.join("doctrine_docs", "_system", "decided-facts.md"),
            os.path.join("doctrine_docs", "_system", "non-goals.md"),
            os.path.join("doctrine_docs", "_system", "overview.md"),
            os.path.join("doctrine_docs", "_system", ".docs-level"),
            os.path.join("doctrine_docs", "_system", ".governance-state"),
            ".gitignore",
            "AGENTS.md",
            "CLAUDE.md",
        ])
        self.assertEqual(self.listing(), expected)

    def test_seeded_docs_have_required_frontmatter(self):
        """Each seeded _system doc parses with the §3.4 required keys present."""
        self.run_scaffold()
        import _frontmatter
        import _registry
        for name, type_code in (
            ("glossary.md", "GLOSSARY"),
            ("decided-facts.md", "DECIDED"),
            ("non-goals.md", "NONGOAL"),
            ("overview.md", "OVERVIEW"),
        ):
            meta, body, errs = _frontmatter.parse_file(self.sysfile(name))
            for key in _registry.REQUIRED_KEYS_L2:
                self.assertIn(key, meta, "%s missing %s" % (name, key))
            self.assertEqual(meta.get("type"), type_code)

    def test_decided_review_by_is_created_plus_90d_and_nonempty(self):
        """DECIDED requires a non-empty review_by; seed = created + 90 days."""
        self.run_scaffold()
        import _frontmatter
        meta, _b, _e = _frontmatter.parse_file(self.sysfile("decided-facts.md"))
        self.assertEqual(meta.get("review_by"), "2026-09-27")

    def test_glossary_carries_section1_tables(self):
        """Seeded glossary holds the §1 approved-term + calque tables (term-check
        reads this as the operational dictionary; no 二重定義)."""
        self.run_scaffold()
        text = _util.read(self.sysfile("glossary.md"))
        self.assertIn("承認語", text)
        self.assertIn("禁止する同義語", text)
        self.assertIn("使わない（カルク）", text)
        # A representative approved term and a representative calque row.
        self.assertIn("ドメイン", text)
        self.assertIn("針を動かす", text)

    def test_overview_is_projection_stub(self):
        """OVERVIEW seed carries the 「描画される。手で編集しない」 header."""
        self.run_scaffold()
        text = _util.read(self.sysfile("overview.md"))
        self.assertIn("描画される。手で編集しない。", text)

    def test_overview_is_derived_and_fresh_tree_reports_only_placeholders(self):
        """初期化直後のコーパスは、**人が埋める箇所だけ**を名指しして赤い(ADR-098)。

        以前は「素通しで緑」を凍結していた。**その緑は偽りだった** —— 用語辞書の
        正本が `owner: <記入>` のまま緑で通り、呼び手の木では初期化から今日まで
        誰も気づかなかった(doctrine#182)。埋まっていない正本を健全と呼ばない。

        いま凍結するのは「緑」ではなく「**指示文以外の所見が出ないこと**」である
        —— 投影ドリフト・孤児・逆孤児のような、道具の側の不備は一件も出ない。

        Regression(元の観点は残す): scaffold used to leave the overview stub with
        an empty table, so a brand-new user's very first SessionEnd audit
        reported projection_drift error×3. The seeded overview must list the
        seeded canonical docs and match render-projection's own derivation."""
        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        text = _util.read(self.sysfile("overview.md"))
        for doc_id in ("GLOSSARY-001", "DECIDED-001", "NONGOAL-001"):
            self.assertIn(doc_id, text,
                          "seeded overview must list %s" % doc_id)
        docs_root = os.path.join(self.root, "doctrine_docs")
        audit_out, _audit_code = _util.invoke(
            "docs-audit", argv=["--root", docs_root, "--today", TODAY,
                                "--json", "--fail-on", "never"])
        data = json.loads(audit_out)
        others = sorted(set(data["counts_by_check"]) - {"template_placeholder"})
        self.assertEqual(
            others, [],
            "初期化したての木に、人が埋める箇所以外の所見が出ている: %s" % others)
        self.assertTrue(
            data["counts_by_check"].get("template_placeholder"),
            "指示文の所見が一件も出ない。埋めるべき箇所を名指ししていない(ADR-098)")
        for finding in data["findings"]:
            self.assertTrue(
                finding["path"].startswith("_system/"),
                "埋める箇所は _system の正本に限るはず: %s" % finding["path"])
        check_out, check_code = _util.invoke(
            "render-projection",
            argv=["overview", "--docs-root", docs_root, "--check"])
        self.assertEqual(check_code, 0,
                         "scaffolded overview drifts from render-projection: %s"
                         % check_out)

    def test_pre_existing_overview_is_never_rerendered(self):
        """非破壊: 既存の overview には導出でも触れない(再実行で保存)."""
        self.run_scaffold()
        sentinel = "SENTINEL-OVERVIEW\n"
        with open(self.sysfile("overview.md"), "w", encoding="utf-8") as fh:
            fh.write(sentinel)
        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        self.assertEqual(_util.read(self.sysfile("overview.md")), sentinel)

    def test_root_pointing_at_docs_warns(self):
        """--root に docs/ 自体を渡す取り違えには注意書きを出す(処理は続行)."""
        docsy = os.path.join(self.root, "docs")
        os.makedirs(docsy, exist_ok=True)
        out, code = _util.invoke(
            "scaffold", argv=["--root", docsy, "--today", TODAY, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("プロジェクトの根", out)

    def test_root_pointers_point_at_system_and_hold_no_facts(self):
        """A.5: CLAUDE.md/AGENTS.md are projection pointers (entry only)."""
        self.run_scaffold()
        for name in ("AGENTS.md", "CLAUDE.md"):
            text = _util.read(os.path.join(self.root, name))
            self.assertIn("投影", text)
            self.assertIn("doctrine_docs/_system/overview.md", text)
            self.assertIn("doctrine_docs/_system/glossary.md", text)


class TestNoFullTree(ScaffoldBase):
    """A.6-2 / §3.7: scaffold creates no domain folders or deferred projections."""

    def test_no_domain_or_layer_dirs_and_no_deferred_projections(self):
        self.run_scaffold()
        files = self.listing()
        # No domain folder layers.
        for layer in ("spec", "decisions", "implementation", "test",
                      "research", "archive"):
            self.assertFalse(
                any(("/%s/" % layer) in ("/" + f) for f in files),
                "unexpected %s/ layer present: %s" % (layer, files))
        # No deferred _system projections / indices.
        for deferred in ("watchlist.md", "context-map.md", "icd-index.md"):
            self.assertNotIn(
                os.path.join("doctrine_docs", "_system", deferred), files,
                "scaffold must not create %s" % deferred)
        # No hooks/ or skills/ written into the target repo.
        self.assertFalse(any(f.startswith("hooks" + os.sep) for f in files))
        self.assertFalse(any(f.startswith("skills" + os.sep) for f in files))

    def test_only_system_subdir_exists_under_docs(self):
        self.run_scaffold()
        docs_dir = os.path.join(self.root, "doctrine_docs")
        subdirs = sorted(d for d in os.listdir(docs_dir)
                         if os.path.isdir(os.path.join(docs_dir, d)))
        self.assertEqual(subdirs, ["_system"])


class TestIdempotentReRun(ScaffoldBase):
    """A.6-3 (critique gap): second run all-skip, byte-for-byte identical."""

    def _snapshot(self):
        snap = {}
        for rel in self.listing():
            snap[rel] = _util.read(os.path.join(self.root, rel))
        return snap

    def test_second_run_all_skip_zero_diff(self):
        out1, code1 = self.run_scaffold()
        self.assertEqual(code1, 0)
        before = self._snapshot()

        out2, code2 = self.run_scaffold()
        self.assertEqual(code2, 0)
        # Every line of the second run is a SKIP (8 plan items: 4 docs +
        # .docs-level + .governance-state + 2 pointers).
        self.assertIn("飛ばし 8", out2)
        self.assertNotIn("CREATE ", out2)
        after = self._snapshot()
        self.assertEqual(before, after, "re-run changed files")


class TestExistingFilesUntouched(ScaffoldBase):
    """A.6-4 (critique gap): a pre-existing file is never overwritten."""

    def test_sentinel_glossary_survives_and_siblings_created(self):
        # Pre-write a custom glossary with sentinel content.
        sentinel = "SENTINEL-GLOSSARY-DO-NOT-OVERWRITE\n"
        gpath = self.sysfile("glossary.md")
        os.makedirs(os.path.dirname(gpath), exist_ok=True)
        with open(gpath, "w", encoding="utf-8") as fh:
            fh.write(sentinel)

        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        # Sentinel untouched (既存を壊さない).
        self.assertEqual(_util.read(gpath), sentinel)
        self.assertIn("SKIP (exists) doctrine_docs/_system/glossary.md", out)
        # Missing siblings still created.
        self.assertTrue(os.path.isfile(self.sysfile("non-goals.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "AGENTS.md")))

    def test_partial_state_recreates_only_the_missing_one(self):
        # Full run, then delete one seed and re-run.
        self.run_scaffold()
        ng = self.sysfile("non-goals.md")
        glossary_before = _util.read(self.sysfile("glossary.md"))
        os.remove(ng)
        out, code = self.run_scaffold()
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(ng), "deleted seed not recreated")
        # Other seeds untouched.
        self.assertEqual(_util.read(self.sysfile("glossary.md")),
                         glossary_before)


class TestDryRun(ScaffoldBase):
    """A.6-7: --dry-run prints a plan but writes nothing (no dirs, no files)."""

    def test_dry_run_writes_nothing(self):
        out, code = self.run_scaffold("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertIn("doctrine_docs/_system/glossary.md", out)
        # Nothing on disk.
        self.assertEqual(self.listing(), [])
        self.assertFalse(os.path.isdir(os.path.join(self.root, "docs")))

    def test_dry_run_then_real_run_matches_plan(self):
        out_dry, _ = self.run_scaffold("--dry-run")
        out_real, code = self.run_scaffold()
        self.assertEqual(code, 0)
        # 8 plan entries + .gitignore post-step = 9 files on disk.
        self.assertEqual(len(self.listing()), 9)
        # dry-run advertised the .gitignore append too (honest preview).
        self.assertIn(".gitignore", out_dry)


class TestDocsLevelMarker(ScaffoldBase):
    """A.6-10 / C9: .docs-level is a single 'level: N' line; idempotent."""

    def test_marker_default_level_2(self):
        self.run_scaffold()
        text = _util.read(self.sysfile(".docs-level"))
        self.assertEqual(text, "level: 2\n")

    def test_marker_level_3(self):
        self.run_scaffold("--level", "3")
        self.assertEqual(_util.read(self.sysfile(".docs-level")), "level: 3\n")

    def test_marker_same_level_rerun_idempotent(self):
        self.run_scaffold("--level", "3")
        first = _util.read(self.sysfile(".docs-level"))
        # Re-run with the SAME level: marker unchanged.
        self.run_scaffold("--level", "3")
        self.assertEqual(_util.read(self.sysfile(".docs-level")), first)

    def test_marker_upgrade_on_different_level(self):
        # #90: re-run with a DIFFERENT --level UPDATES the marker (explicit
        # user intent; the marker is a control input, not a content seed).
        self.run_scaffold("--level", "2")
        out, code = self.run_scaffold("--level", "4")
        self.assertEqual(code, 0)
        self.assertEqual(_util.read(self.sysfile(".docs-level")), "level: 4\n")
        self.assertIn("UPGRADE", out)


class TestLevel2Selection(ScaffoldBase):
    """A.6-6: Level-2 (default) produces exactly the minimal core (no L3/4
    extra artifacts at init — the core is already minimal for every level)."""

    def test_level2_is_the_minimal_core(self):
        self.run_scaffold("--level", "2")
        # 8 plan files + .gitignore = 9.
        self.assertEqual(len(self.listing()), 9)
        self.assertEqual(_util.read(self.sysfile(".docs-level")), "level: 2\n")

    def test_level4_writes_same_minimal_core(self):
        # Higher level only records the marker; the created file SET is identical.
        self.run_scaffold("--level", "4")
        names = set(os.path.basename(f) for f in self.listing())
        self.assertEqual(
            names,
            {"glossary.md", "decided-facts.md", "non-goals.md",
             "overview.md", ".docs-level", ".governance-state",
             ".gitignore", "AGENTS.md", "CLAUDE.md"})


class TestFallback(ScaffoldBase):
    """A.3 / critique gap: --fallback places the layout under .claude/."""

    def test_fallback_uses_claude_dir(self):
        out, code = self.run_scaffold("--fallback")
        self.assertEqual(code, 0)
        files = self.listing()
        self.assertIn(os.path.join(".claude", "AGENTS.md"), files)
        self.assertIn(os.path.join(".claude", "CLAUDE.md"), files)
        self.assertIn(
            os.path.join(".claude", "doctrine_docs", "_system", "glossary.md"),
            files)
        # Nothing leaked to the repo root.
        self.assertFalse(os.path.isfile(os.path.join(self.root, "AGENTS.md")))
        self.assertFalse(
            os.path.isdir(os.path.join(self.root, "doctrine_docs")))


class TestTreeChoice(ScaffoldBase):
    """ADR-022: 既定は doctrine_docs。docs/_system が在れば docs を使い続ける。
    素の docs/ には入植しない。"""

    def test_legacy_docs_system_continues_in_docs(self):
        os.makedirs(os.path.join(self.root, "docs", "_system"), exist_ok=True)
        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.isdir(os.path.join(self.root, "doctrine_docs")),
                         "既存の docs/_system があるのに doctrine_docs を新設した")
        self.assertTrue(os.path.isfile(os.path.join(
            self.root, "docs", "_system", "glossary.md")))

    def test_plain_foreign_docs_not_colonized(self):
        os.makedirs(os.path.join(self.root, "docs", "guides"), exist_ok=True)
        out, code = self.run_scaffold()
        self.assertEqual(code, 0, out)
        self.assertFalse(
            os.path.exists(os.path.join(self.root, "docs", "_system")),
            "素の docs/ に _system を入植してはならない(ADR-022)")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "doctrine_docs")))


class TestArgErrors(ScaffoldBase):
    """Usage errors exit 2; success exits 0 on all-skip."""

    def test_bad_level_exits_2(self):
        out, code = self.run_scaffold("--level", "9")
        self.assertEqual(code, 2)

    def test_unknown_flag_exits_2(self):
        out, code = self.run_scaffold("--nope")
        self.assertEqual(code, 2)


class TestStdlibOnly(unittest.TestCase):
    """A.6-9 / §6 meta: scaffold imports nothing third-party."""

    def test_no_third_party_imports(self):
        path = os.path.join(_util.SCRIPTS, "scaffold.py")
        src = _util.read(path)
        for banned in ("import numpy", "import yaml", "import requests",
                       "import sklearn", "import janome", "import mecab"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
