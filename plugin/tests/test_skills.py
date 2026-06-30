"""Validate all 7 skills against the §4.1 / MASTER §7 contract.

Reads every plugin/skills/<name>/SKILL.md from disk at suite time and checks the
frozen properties that hold for ALL skills (not just the three this component
authors — the suite is the single gate for the skill set):

  - the 7 required skill directories exist, each with a SKILL.md;
  - each SKILL.md has a non-empty, third-person `description` in frontmatter;
  - the description matches the MASTER §7 verbatim trigger string — asserted by
    requiring the distinctive trigger phrases of that skill to be present;
  - SKILL.md body is < 500 lines (§4.1 / slice 08 §0.1);
  - the body contains a `## 保証限界` section (critique R9 per-artifact gap);
  - the body uses approved vocabulary: running `_termcheck.check` over it yields
    NO ERROR-severity findings (skills must pass their own term-check, §1/R6).

Maps to: spec §4.1, MASTER §7, design/08-skills.md §0 (cross-cutting rules),
and the critique gap "per-artifact 保証限界 (`## 保証限界` present in each
SKILL.md)". The term-check assertion is the dogfooding requirement: the system
obeys the rules it enforces.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

fm = _util.load_core("_frontmatter")
tc = _util.load_core("_termcheck")

SKILLS_DIR = os.path.join(_util.PLUGIN_ROOT, "skills")

# The 7 skills are fixed (§4.1: "Skillは7つに限る").
SKILL_NAMES = (
    "docs-system-init",
    "doc-author",
    "doc-review",
    "change-impact",
    "regression-guard",
    "llm-context-pack",
    "docs-curate",
)

# Distinctive verbatim fragments from the MASTER §7 frozen description strings.
# The on-disk description must contain every fragment for its skill: this both
# proves the description is the verbatim §7 trigger and that the literal user
# phrases ("起動を促す表現と実際に使う語句", §4.1) are present.
TRIGGER_FRAGMENTS = {
    "docs-system-init": [
        "Sets up the document governance system in a repository",
        "creates the minimal _system layer",
        "without overwriting anything that already exists",
        '"initialize docs"',
        '"set up the documentation system"',
        '"bootstrap docs governance"',
        '"scaffold _system"',
    ],
    "doc-author": [
        "Creates and updates typed governance documents",
        "placing each in the correct location with correct frontmatter",
        "generating the domain folder and its layer subfolders",
        '"write a spec"',
        '"add an ADR"',
        '"create an ICD"',
        '"author a requirement"',
    ],
    "doc-review": [
        "Reviews a document's prose and positioning against the writing norms",
        "runs the term checker alongside",
        "back-translation tell",
        "missing canonical_for",
        '"review this doc"',
        '"check for calque',
        "定例レビュー",
    ],
    "change-impact": [
        "Runs the 14-step change flow for a proposed change",
        "traces dependencies to enumerate every document",
        "decision (ADR) first",
        'keeping "what changed" (CHANGE/git) separate from "why decided" (ADR)',
        '"assess the impact of a change"',
        '"plan a change"',
        '"trace impact"',
    ],
    "regression-guard": [
        "Guards against regressions",
        "prevents reviving deprecated approaches",
        "cross-checking the proposed change against Decided Facts (DECIDED)",
        "Regression Watchlist (WATCH)",
        '"check for regressions"',
        '"check the watchlist"',
        '"guard against backsliding"',
    ],
    "llm-context-pack": [
        "Builds the minimal context for a specific task",
        "gathers only the fewest documents whose coverage satisfies",
        "excludes everything marked llm_context: never",
        "shows the provenance",
        '"build context for this task"',
        '"pack the minimal context"',
        '"assemble LLM context"',
    ],
    "docs-curate": [
        "Curates the document set one item at a time",
        "merges duplicate facts / demotes one step / or deletes",
        "always checking reverse references first",
        "re-rendering the projections",
        "shrinking the always-injected set",
        '"clean up the docs"',
        '"shrink the always-set"',
        "定例整理",
    ],
}


def _skill_path(name):
    return os.path.join(SKILLS_DIR, name, "SKILL.md")


def _load(name):
    """Return (raw_text, meta, body) for a skill, reading from disk fresh."""
    path = _skill_path(name)
    text = _util.read(path)
    meta, body, _errs = fm.parse(text)
    return text, meta, body


class SkillExistenceTest(unittest.TestCase):
    """7 skill dirs exist, each with a SKILL.md (§4.1, MASTER §9 inventory)."""

    def test_skills_dir_exists(self):
        self.assertTrue(os.path.isdir(SKILLS_DIR), "plugin/skills/ must exist")

    def test_exactly_the_seven_skills_present(self):
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                d = os.path.join(SKILLS_DIR, name)
                self.assertTrue(os.path.isdir(d), "missing skill dir: %s" % name)
                self.assertTrue(os.path.isfile(_skill_path(name)),
                                "missing SKILL.md for: %s" % name)

    def test_no_unexpected_skill_dirs(self):
        """The set is fixed at 7 — no extra (e.g. a separate ICD) skill."""
        if not os.path.isdir(SKILLS_DIR):
            self.skipTest("skills/ not present yet")
        present = {
            n for n in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, n)) and not n.startswith(".")
        }
        self.assertEqual(present, set(SKILL_NAMES),
                         "skill set must be exactly the 7 (§4.1)")


class SkillFrontmatterTest(unittest.TestCase):
    """Each SKILL.md frontmatter carries a non-empty third-person description
    that is the verbatim MASTER §7 trigger string (§4.1)."""

    def test_description_non_empty(self):
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, meta, _body = _load(name)
                desc = meta.get("description")
                self.assertIsInstance(desc, str, "%s: description must be a string" % name)
                self.assertTrue(desc.strip(), "%s: description must be non-empty" % name)

    def test_description_is_third_person(self):
        """§4.1: descriptionは三人称で書く. The §7 strings open with a third-person
        present-tense verb (Sets/Creates/Reviews/Runs/Guards/Builds/Curates)."""
        openers = ("Sets ", "Creates ", "Reviews ", "Runs ", "Guards ",
                   "Builds ", "Curates ")
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, meta, _body = _load(name)
                desc = meta.get("description", "").lstrip()
                self.assertTrue(
                    desc.startswith(openers),
                    "%s: description must open third-person (got %r)" % (name, desc[:24]),
                )

    def test_description_matches_master_triggers(self):
        """The description contains every distinctive §7 trigger phrase, including
        the literal user phrases (§4.1 起動を促す表現と実際に使う語句)."""
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, meta, _body = _load(name)
                desc = meta.get("description", "")
                for fragment in TRIGGER_FRAGMENTS[name]:
                    self.assertIn(fragment, desc,
                                  "%s: description missing §7 trigger %r" % (name, fragment))


class SkillBodyTest(unittest.TestCase):
    """Body-level invariants: length, the 保証限界 section, vocabulary."""

    def test_under_500_lines(self):
        """§4.1 / slice 08 §0.1: SKILL.md body < 500 lines."""
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                text, _meta, _body = _load(name)
                n = len(text.splitlines())
                self.assertLess(n, 500, "%s: SKILL.md has %d lines (>= 500)" % (name, n))

    def test_has_assurance_limit_section(self):
        """Critique R9 per-artifact gap: each SKILL.md declares `## 保証限界`."""
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, _meta, body = _load(name)
                self.assertIn("## 保証限界", body,
                              "%s: missing `## 保証限界` (R9 prevent/detect/defer)" % name)

    def test_assurance_limit_declares_the_three_tiers(self):
        """The 保証限界 section names all three tiers (予防 / 検出 / 委ねる, R9)."""
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, _meta, body = _load(name)
                idx = body.find("## 保証限界")
                section = body[idx:] if idx >= 0 else ""
                for tier in ("予防", "検出", "委ねる"):
                    self.assertIn(tier, section,
                                  "%s: 保証限界 must state %s" % (name, tier))


class SkillTermCheckTest(unittest.TestCase):
    """Dogfooding (§1/R6): each SKILL.md body passes its own term-check —
    no ERROR-severity findings (banned synonym / banned calque). WARN-level
    findings (e.g. an undefined Latin acronym such as ADR) are allowed.

    The body is checked, not the frontmatter: the English §7 description lives in
    frontmatter and is not subject to the Japanese vocabulary rules.
    """

    def setUp(self):
        # Seed glossary from the shipped template (docs_root=None -> template):
        # the single §1 encoding the whole system enforces.
        self.g = tc.load_glossary(None)

    def test_no_error_findings_in_any_skill_body(self):
        for name in SKILL_NAMES:
            with self.subTest(skill=name):
                _text, meta, body = _load(name)
                findings = tc.check(body, meta, self.g)
                errors = [f for f in findings if f.severity == tc.ERROR]
                self.assertEqual(
                    errors, [],
                    "%s: SKILL.md body trips term-check (ERROR): %s" % (
                        name, "; ".join(f.message for f in errors)),
                )


class AllSkillReferencesTermCheckTest(unittest.TestCase):
    """Dogfooding (§1/R6), full coverage: the references/*.md of ALL 7 skills
    pass term-check with NO ERROR-severity finding.

    test_skills_authoring.py only dogfoods the 4 'owned' skills' reference
    files; the remaining three (regression-guard, llm-context-pack, docs-curate)
    were never term-checked. This loop closes that gap so a banned synonym /
    banned calque sneaking into ANY skill's reference detail can never return
    silently. WARN (e.g. an undefined Latin acronym such as ADR) is allowed.
    """

    def setUp(self):
        # The shipped §1 seed (docs_root=None -> template glossary).
        self.g = tc.load_glossary(None)

    def test_some_reference_file_was_checked(self):
        """Guard the loop itself: at least one references/*.md exists, so a
        future refactor that empties references/ cannot make the dogfood a
        vacuous pass."""
        seen = 0
        for name in SKILL_NAMES:
            refs_dir = os.path.join(SKILLS_DIR, name, "references")
            if os.path.isdir(refs_dir):
                seen += sum(1 for fn in os.listdir(refs_dir) if fn.endswith(".md"))
        self.assertGreater(seen, 0, "no references/*.md found across the 7 skills")

    def test_no_error_in_any_skill_reference_file(self):
        for name in SKILL_NAMES:
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


class RevivalRulesLadderTest(unittest.TestCase):
    """§3.8 has exactly 5 demotion rungs: 現行 → 廃止 → アーカイブ → git だけ
    → 抹消. 置換 is a STATUS (§3.3), never a rung. Lock regression-guard's
    revival-rules.md to that ladder so finding #24 (a 6-rung ladder with 置換
    inserted) can never silently return."""

    def _revival_rules(self):
        p = os.path.join(
            SKILLS_DIR, "regression-guard", "references", "revival-rules.md")
        return _util.read(p)

    def test_ladder_line_has_exactly_five_rungs(self):
        body = self._revival_rules()
        # Find the demotion-ladder line (the one containing the arrows).
        line = next(
            (ln for ln in body.splitlines() if "現行" in ln and "→" in ln),
            None,
        )
        self.assertIsNotNone(line, "no demotion-ladder line found")
        # The last arrow segment carries trailing prose after the final rung
        # (".. 抹消。一段ずつ降ろす。.."); keep only the rung token: cut at the
        # first sentence stop, then take the first whitespace-delimited piece.
        rungs = []
        for seg in line.split("→"):
            seg = seg.strip().split("。")[0].strip()
            rungs.append(seg.split()[0] if seg.split() else seg)
        self.assertEqual(
            rungs,
            ["現行", "廃止", "アーカイブ", "git", "抹消"],
            "revival-rules.md ladder must be the 5 §3.8 rungs (no 置換 rung)",
        )

    def test_placement_status_not_a_rung(self):
        """置換 must appear as a STATUS, not on the demotion-ladder line."""
        body = self._revival_rules()
        ladder_line = next(
            (ln for ln in body.splitlines() if "現行" in ln and "→" in ln), "")
        self.assertNotIn("置換", ladder_line,
                         "置換 must not sit on the demotion ladder (§3.3 status)")
        self.assertIn("置換は段ではなく状態", body,
                      "置換 must be presented as a state, not a rung")


if __name__ == "__main__":
    unittest.main()
