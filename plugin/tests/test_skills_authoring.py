"""Content-contract tests for the four authoring/flow skills this component owns.

`test_skills.py` (owned by the other skills agent) is the cross-cutting gate for
ALL 7 skills: existence, verbatim §7 description, third-person, <500 lines,
`## 保証限界` + three tiers, and term-check no-ERROR. This file does NOT repeat
those; it asserts the per-skill PROCEDURAL contract that MASTER §7 / spec
§4.1/§3.7/§3.8 / design/08-skills.md assign specifically to:

    docs-system-init · doc-author · doc-review · change-impact

Each test cites the spec section and, where applicable, the BRIEF2 critique gap
this component must close:

  - doc-author lazy domain-folder gen + correct placement (§3.7)
  - change-impact 14-step order ADR->SPEC->impl->test->LLM-context->deprecation (§3.8)
  - per-artifact 保証限界 wording (R9) — the prevent/detect/defer *content*, not
    just the heading (the heading is covered by test_skills.py).

It also confirms each owned skill ships its `references/*.md` detail set
(design/08-skills.md "SKILL.md vs references/"), and that those reference files
also pass term-check with no ERROR (dogfooding, §1/R6).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

fm = _util.load_core("_frontmatter")
tc = _util.load_core("_termcheck")

SKILLS_DIR = os.path.join(_util.PLUGIN_ROOT, "skills")

# Only the four skills THIS component authors.
OWNED = ("docs-system-init", "doc-author", "doc-review", "change-impact")

# The reference files each owned skill must ship (design/08-skills.md
# "SKILL.md vs references/").
EXPECTED_REFERENCES = {
    "docs-system-init": ("levels.md", "fallback.md", "hook-snapshot.md"),
    "doc-author": (
        "type-registry.md", "icd-authoring.md", "frontmatter.md",
        "lazy-domain-gen.md", "dependency-rules.md",
    ),
    "doc-review": (
        "back-translation-tell.md", "writing-rules.md",
        "cadence-review.md", "term-addition.md",
    ),
    "change-impact": (
        "change-flow.md", "dep-graph-usage.md", "deprecation.md", "icd-change.md",
    ),
}


def _skill_path(name):
    return os.path.join(SKILLS_DIR, name, "SKILL.md")


def _load(name):
    text = _util.read(_skill_path(name))
    meta, body, _errs = fm.parse(text)
    return text, meta, body


def _assurance_section(body):
    idx = body.find("## 保証限界")
    return body[idx:] if idx >= 0 else ""


class DocsSystemInitContentTest(unittest.TestCase):
    """docs-system-init: §4.1 role + §3.7 (no domain trees) + R1,R8.

    Targets the non-destructive invariant and the init/doc-author hand-off that
    the design contract (08-skills §1) makes load-bearing.
    """

    def test_names_scaffold_script(self):
        """Delegates determinism to scaffold.py (design 08 §1 Invokes)."""
        _t, _m, body = _load("docs-system-init")
        self.assertIn("scaffold.py", body)

    def test_states_non_destructive_invariant(self):
        """Meta acceptance '既存を壊さない' — must be stated, not just implied."""
        _t, _m, body = _load("docs-system-init")
        self.assertIn("既存", body)
        self.assertTrue(
            ("壊さない" in body) or ("上書き" in body),
            "must state it does not overwrite / break existing files",
        )

    def test_does_not_build_domain_trees(self):
        """§3.7: init never builds domain folders — doc-author does, lazily."""
        _t, _m, body = _load("docs-system-init")
        self.assertIn("doc-author", body,
                      "must hand domain creation off to doc-author")
        self.assertTrue(
            ("ドメインのフォルダ" in body) or ("ドメイン" in body and "作らない" in body),
            "must state it does not create domain folders/layers",
        )

    def test_default_is_reduced_level_2(self):
        """§4.4: default configuration is the reduced Level 2."""
        _t, _m, body = _load("docs-system-init")
        self.assertIn("Level 2", body)

    def test_ships_expected_references(self):
        for ref in EXPECTED_REFERENCES["docs-system-init"]:
            with self.subTest(ref=ref):
                p = os.path.join(SKILLS_DIR, "docs-system-init", "references", ref)
                self.assertTrue(os.path.isfile(p), "missing reference: %s" % ref)

    def test_assurance_prevent_is_honest(self):
        """R9: a skill must not claim to prevent what only a guard can enforce.
        docs-system-init installs the guards; by itself it prevents nothing."""
        section = _assurance_section(_load("docs-system-init")[2])
        self.assertIn("予防", section)
        # It says it installs the guards that prevent later (defers prevention).
        self.assertIn("ガード", section)


class DocAuthorContentTest(unittest.TestCase):
    """doc-author: §3.7 lazy gen + §3.5 ICD + §3.6 deps + SPEC 4 sections.

    Closes the critique gap 'doc-author lazy domain-folder gen + correct
    placement' and asserts the registry-single-source discipline (§3).
    """

    def test_lazy_domain_folder_generation(self):
        """Critique gap + §3.7: generate docs/<domain>/ and only the needed
        layer subfolder on the FIRST doc of that type ('空の足場を先に作らない')."""
        _t, _m, body = _load("doc-author")
        self.assertIn("3.7", body)
        self.assertTrue(
            ("遅延生成" in body) or ("最初" in body),
            "must describe lazy (first-doc) folder generation",
        )
        self.assertIn("空の足場を先に作らない", body)

    def test_lazy_gen_reference_lists_layer_mapping(self):
        """The lazy-domain-gen reference maps each type to its layer subfolder."""
        p = os.path.join(SKILLS_DIR, "doc-author", "references", "lazy-domain-gen.md")
        ref = _util.read(p)
        for layer in ("spec/", "decisions/", "implementation/", "test/",
                      "research/", "archive/"):
            with self.subTest(layer=layer):
                self.assertIn(layer, ref)

    def test_prefers_write_over_edit(self):
        """§3.8/§7: route to Write so the ICD guard can deny pre-execution."""
        _t, _m, body = _load("doc-author")
        self.assertIn("Write", body)
        self.assertIn("Edit", body)

    def test_icd_three_declarations(self):
        """§3.5: ICD declares exactly three things; doc-author authors ICDs."""
        _t, _m, body = _load("doc-author")
        self.assertIn("ICD", body)
        self.assertTrue(
            ("公開する用語" in body) and ("データ契約" in body),
            "must list ICD's public-terms and data-contract declarations",
        )

    def test_spec_four_mandatory_sections_named(self):
        """§3.2/§4.2: SPEC must carry the 4 mandatory sections."""
        _t, _m, body = _load("doc-author")
        for sec in ("入出力", "制約", "エラー時挙動", "受入基準"):
            with self.subTest(section=sec):
                self.assertIn(sec, body)

    def test_calls_linter_for_self_correction(self):
        """§4.2: doc-author self-corrects on docs-linter PostToolUse findings."""
        _t, _m, body = _load("doc-author")
        self.assertIn("docs-linter.py", body)

    def test_does_not_duplicate_registry_in_text(self):
        """§3: rules live once in §3.2/_registry — the skill references, not copies.
        Asserts the skill explicitly says it does not re-define the registry."""
        _t, _m, body = _load("doc-author")
        self.assertIn("二重定義しない", body)

    def test_ships_expected_references(self):
        for ref in EXPECTED_REFERENCES["doc-author"]:
            with self.subTest(ref=ref):
                p = os.path.join(SKILLS_DIR, "doc-author", "references", ref)
                self.assertTrue(os.path.isfile(p), "missing reference: %s" % ref)


class DocReviewContentTest(unittest.TestCase):
    """doc-review: §1 逆翻訳テル + term-check alongside + cadence checks (R6,R10)."""

    def test_runs_term_check_alongside(self):
        """§4.1: 用語チェッカーを併走 — names term-check.py and 併走."""
        _t, _m, body = _load("doc-review")
        self.assertIn("term-check.py", body)
        self.assertIn("併走", body)

    def test_back_translation_tell(self):
        """§1: calque the linter cannot catch is judged by the 逆翻訳テル."""
        _t, _m, body = _load("doc-review")
        self.assertIn("逆翻訳テル", body)

    def test_cadence_only_checks(self):
        """§7 operational contract: canonical_for / translationese / semantic dup
        close only on a defined cadence (定例)."""
        _t, _m, body = _load("doc-review")
        self.assertIn("canonical_for", body)
        self.assertIn("意味的重複", body)
        self.assertIn("定例", body)

    def test_new_term_requires_adr(self):
        """§1: adding an approved term requires an ADR + glossary update; the
        skill never self-approves vocabulary."""
        _t, _m, body = _load("doc-review")
        self.assertIn("ADR", body)
        self.assertIn("用語辞書", body)

    def test_advisory_not_blocking(self):
        """R9: review is advisory; prevention is owned by guards/linter."""
        section = _assurance_section(_load("doc-review")[2])
        self.assertIn("予防", section)
        self.assertIn("助言", section)

    def test_ships_expected_references(self):
        for ref in EXPECTED_REFERENCES["doc-review"]:
            with self.subTest(ref=ref):
                p = os.path.join(SKILLS_DIR, "doc-review", "references", ref)
                self.assertTrue(os.path.isfile(p), "missing reference: %s" % ref)


class ChangeImpactContentTest(unittest.TestCase):
    """change-impact: §3.8 14-step flow + mandated order (R3,R4).

    Closes the critique gap 'change-impact 14-step order' and the CHANGE/ADR
    separation requirement.
    """

    def test_mandated_order_appears_in_sequence(self):
        """§3.8: ADR -> SPEC -> 実装 -> テスト -> LLM context -> 廃止整理, in order.

        Asserts the six stage anchors appear left-to-right WITHIN the dedicated
        '## 更新の順序' declaration line (not first-occurrence across the whole
        doc, where role/links mention ADR/SPEC out of flow order)."""
        _t, _m, body = _load("change-impact")
        marker = "## 更新の順序"
        start = body.find(marker)
        self.assertNotEqual(start, -1, "missing '## 更新の順序' section")
        # The order is stated on the lines immediately following the heading,
        # before the next '## ' heading.
        rest = body[start + len(marker):]
        nxt = rest.find("\n## ")
        order_section = rest if nxt < 0 else rest[:nxt]

        anchors = ["ADR", "SPEC", "実装", "テスト", "LLM", "廃止整理"]
        positions = []
        for a in anchors:
            i = order_section.find(a)
            self.assertNotEqual(i, -1,
                                "order anchor missing in 更新の順序: %s" % a)
            positions.append(i)
        self.assertEqual(
            positions, sorted(positions),
            "mandated order not preserved in '## 更新の順序': %s" % anchors,
        )

    def test_has_fourteen_numbered_steps(self):
        """The 14-step flow is enumerated 1..14."""
        _t, _m, body = _load("change-impact")
        for n in (1, 6, 7, 11, 13, 14):
            with self.subTest(step=n):
                self.assertTrue(
                    ("\n%d. " % n) in body or ("\n%d." % n) in body,
                    "missing change-flow step %d" % n,
                )

    def test_change_vs_adr_separation(self):
        """§3.8: '何を変えたか'(CHANGE/git) separate from 'なぜ決めたか'(ADR)."""
        _t, _m, body = _load("change-impact")
        self.assertIn("何を変えたか", body)
        self.assertIn("なぜ", body)
        self.assertIn("CHANGE", body)

    def test_names_dep_graph_for_impact_set(self):
        """R4: impact set comes from dep-graph.py (forward + reverse)."""
        _t, _m, body = _load("change-impact")
        self.assertIn("dep-graph.py", body)

    def test_demotion_invariant_reverse_ref_zero(self):
        """§3.8: do not demote while a current dependency remains (逆参照ゼロ);
        the delete-safety guard enforces it — the skill orders work to respect it."""
        _t, _m, body = _load("change-impact")
        self.assertIn("不変条件", body)
        self.assertTrue(
            ("削除安全ガード" in body),
            "must attribute enforcement to the delete-safety guard (R9 honesty)",
        )

    def test_ships_expected_references(self):
        for ref in EXPECTED_REFERENCES["change-impact"]:
            with self.subTest(ref=ref):
                p = os.path.join(SKILLS_DIR, "change-impact", "references", ref)
                self.assertTrue(os.path.isfile(p), "missing reference: %s" % ref)


class OwnedReferencesTermCheckTest(unittest.TestCase):
    """Dogfooding (§1/R6): the references/*.md of the owned skills also pass
    term-check with NO ERROR-severity finding. WARN (undefined Latin acronym such
    as a type code) is allowed. SKILL.md bodies are covered by test_skills.py.
    """

    def setUp(self):
        self.g = tc.load_glossary(None)  # the shipped §1 seed

    def test_no_error_in_owned_reference_files(self):
        for name in OWNED:
            refs_dir = os.path.join(SKILLS_DIR, name, "references")
            if not os.path.isdir(refs_dir):
                continue
            for fn in sorted(os.listdir(refs_dir)):
                if not fn.endswith(".md"):
                    continue
                with self.subTest(ref="%s/%s" % (name, fn)):
                    text = _util.read(os.path.join(refs_dir, fn))
                    meta, body, _errs = fm.parse(text)
                    findings = tc.check(body, meta, self.g)
                    errors = [f for f in findings if f.severity == tc.ERROR]
                    self.assertEqual(
                        errors, [],
                        "%s/%s trips term-check (ERROR): %s" % (
                            name, fn, "; ".join(f.message for f in errors)),
                    )


if __name__ == "__main__":
    unittest.main()
