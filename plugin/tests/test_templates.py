"""Template validation suite (slice 09 / MASTER §8).

Validates ALL 19 shipped templates under plugin/templates/:
the 17 single-type templates (icd, overview, ctxmap, decided, nongoal, watch,
req, spec, data, api, adr, change, impact, impl, test, research, archive) plus
the glossary template (owned by the termcore agent, validated here by path) and
the icd-index projection seed (type OVERVIEW, C8).

Every template is parsed through the FROZEN _frontmatter parser and checked
against the FROZEN _registry tables (no rule is duplicated here — the registry
is the single source of truth, §3 "コードに規則を二重定義しない").

TC coverage (design/10-scenarios.md):
- TC-001/003/005/007/009/011/013/015/017/019/021/023/027/029/031/033/035/037:
  each type's TEMPLATE DEFAULT status is inside status_allowed(type) — the
  allow side of the 18-type status matrix, asserted at the seed level so a
  scaffolded doc starts legal.
- TC-035: RESEARCH default `draft` is legal (C5 carve-out) — template seeds it.
- TC-037: ARCHIVE default `archived` is legal — template seeds it.
- TC-023: ADR default `accepted` legal only for ADR — template seeds it.
- TC-099/100/042: projection seeds (overview, ctxmap, icd-index) carry the
  「描画される。手で編集しない。」 first body line so render-projection drift
  checks have a stable header and hand-edit deterrent.
- Critique gap (placeholder convention): every template uses the same
  angle-bracket placeholder vocabulary so scaffold.py / doc-author fill
  consistently; no 入れない comment text leaks above the body (advisory) — it
  must not survive into a projection.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

_registry = _util.load_core("_registry")
_frontmatter = _util.load_core("_frontmatter")


# --- The shipped template inventory ----------------------------------------
# Maps template filename -> the type code its frontmatter MUST carry.
# 17 single-type templates + glossary (sibling-owned) = 18 type templates;
# icd-index is the +1 projection seed (type OVERVIEW, C8).
TYPE_TEMPLATES = {
    "icd.md.tmpl": "ICD",
    "overview.md.tmpl": "OVERVIEW",
    "glossary.md.tmpl": "GLOSSARY",
    "ctxmap.md.tmpl": "CTXMAP",
    "decided.md.tmpl": "DECIDED",
    "nongoal.md.tmpl": "NONGOAL",
    "watch.md.tmpl": "WATCH",
    "req.md.tmpl": "REQ",
    "spec.md.tmpl": "SPEC",
    "data.md.tmpl": "DATA",
    "api.md.tmpl": "API",
    "adr.md.tmpl": "ADR",
    "change.md.tmpl": "CHANGE",
    "impact.md.tmpl": "IMPACT",
    "impl.md.tmpl": "IMPL",
    "test.md.tmpl": "TEST",
    "research.md.tmpl": "RESEARCH",
    "archive.md.tmpl": "ARCHIVE",
}

# Projection seed outside the 18 (type OVERVIEW reused, C8).
PROJECTION_SEED = {"icd-index.md.tmpl": "OVERVIEW"}

# All 19 shipped templates (18 type + 1 projection seed).
ALL_TEMPLATES = dict(TYPE_TEMPLATES)
ALL_TEMPLATES.update(PROJECTION_SEED)

PROJECTION_FIRST_LINE = "描画される。手で編集しない。"

# Files whose body must begin with the projection deterrent line (§3.9 / 付録B).
PROJECTION_TEMPLATES = ("overview.md.tmpl", "ctxmap.md.tmpl", "icd-index.md.tmpl")


def _path(name):
    return os.path.join(_util.TEMPLATES, name)


def _parse(name):
    """Read + parse a template by filename. Returns (fm, body, errors)."""
    text = _util.read(_path(name))
    return _frontmatter.parse(text)


class TemplatesExistTest(unittest.TestCase):
    """The 19 templates are present on disk (glossary by path, sibling-owned)."""

    def test_all_nineteen_present(self):
        missing = [n for n in ALL_TEMPLATES if not os.path.isfile(_path(n))]
        self.assertEqual(missing, [], "missing templates: %s" % missing)

    def test_exactly_nineteen_md_tmpl(self):
        """No stray *.md.tmpl beyond the 19 documented ones."""
        on_disk = sorted(
            f for f in os.listdir(_util.TEMPLATES) if f.endswith(".md.tmpl")
        )
        self.assertEqual(
            on_disk, sorted(ALL_TEMPLATES.keys()),
            "templates/ must hold exactly the 19 documented *.md.tmpl files",
        )


class FrontmatterParsesTest(unittest.TestCase):
    """Every template parses cleanly via the FROZEN _frontmatter parser.

    TC R3-row: a seeded doc has valid §3.4 frontmatter from the start.
    """

    def test_every_template_parses_without_errors(self):
        for name in ALL_TEMPLATES:
            with self.subTest(template=name):
                fm, body, errors = _parse(name)
                self.assertEqual(
                    errors, [],
                    "%s produced parser errors: %s" % (name, errors),
                )
                self.assertTrue(fm, "%s has no frontmatter" % name)
                self.assertTrue(body.strip(), "%s has empty body" % name)

    def test_required_keys_present(self):
        """All 8 REQUIRED_KEYS_L2 present in every template (§3.4)."""
        for name in ALL_TEMPLATES:
            fm, _body, _errs = _parse(name)
            for key in _registry.REQUIRED_KEYS_L2:
                with self.subTest(template=name, key=key):
                    self.assertIn(
                        key, fm,
                        "%s missing required key %r" % (name, key),
                    )

    def test_created_present_recommended(self):
        """`created` is recommended (C11: allowed, not required) — every
        template includes it for a clean scaffold."""
        for name in ALL_TEMPLATES:
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertIn("created", fm, "%s lacks created" % name)


class TypeAndIdTest(unittest.TestCase):
    """type field matches the expected registry type; id prefix matches type.

    TC R2-row family: the template seed is type-consistent so the linter's
    id<->type and type-validity checks pass on a fresh doc.
    """

    def test_type_field_matches_expected(self):
        for name, expected_type in ALL_TEMPLATES.items():
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertEqual(
                    fm.get("type"), expected_type,
                    "%s: type=%r, expected %r"
                    % (name, fm.get("type"), expected_type),
                )

    def test_type_is_known_registry_type(self):
        for name in ALL_TEMPLATES:
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertTrue(
                    _registry.is_known_type(fm.get("type")),
                    "%s: type %r not a registry type"
                    % (name, fm.get("type")),
                )

    def test_id_prefix_matches_type(self):
        """id is <TYPE>-<...>; the prefix's registry type == the template type.

        icd-index uses id OVERVIEW-<連番> (C8): the id prefix is OVERVIEW even
        though the file is the ICD index — asserted via the expected type.
        """
        for name, expected_type in ALL_TEMPLATES.items():
            fm, _b, _e = _parse(name)
            doc_id = fm.get("id", "")
            with self.subTest(template=name, id=doc_id):
                prefix = doc_id.split("-", 1)[0]
                self.assertEqual(
                    prefix, expected_type,
                    "%s: id %r prefix != type %r"
                    % (name, doc_id, expected_type),
                )


class DefaultStatusTest(unittest.TestCase):
    """Template default status == registry default AND is in status_allowed.

    TC-001/003/005/007/009/011/013/015/017/019/021/023/027/029/031/033/035/037
    (the ALLOW side of the 18-type status matrix, at the template-seed level):
    a scaffolded doc starts with a legal status for its type.
    TC-023: ADR seed=accepted (the only type where accepted is legal).
    TC-035: RESEARCH seed=draft (C5 carve-out).
    TC-037: ARCHIVE seed=archived.
    """

    def test_default_status_matches_registry(self):
        for name, type_code in ALL_TEMPLATES.items():
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertEqual(
                    fm.get("status"), _registry.default_status(type_code),
                    "%s: status=%r, registry default=%r"
                    % (name, fm.get("status"),
                       _registry.default_status(type_code)),
                )

    def test_default_status_is_allowed(self):
        for name, type_code in ALL_TEMPLATES.items():
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertIn(
                    fm.get("status"), _registry.status_allowed(type_code),
                    "%s: status %r not in status_allowed(%s)=%s"
                    % (name, fm.get("status"), type_code,
                       sorted(_registry.status_allowed(type_code))),
                )

    def test_adr_seed_accepted(self):
        """TC-023: ADR is the only type seeded `accepted`."""
        fm, _b, _e = _parse("adr.md.tmpl")
        self.assertEqual(fm.get("status"), "accepted")

    def test_research_seed_draft(self):
        """TC-035: RESEARCH seed status is `draft` (C5 carve-out)."""
        fm, _b, _e = _parse("research.md.tmpl")
        self.assertEqual(fm.get("status"), "draft")
        self.assertIn("draft", _registry.status_allowed("RESEARCH"))

    def test_archive_seed_archived_with_superseded_by(self):
        """TC-037: ARCHIVE seed=archived and carries superseded_by (§3.8)."""
        fm, _b, _e = _parse("archive.md.tmpl")
        self.assertEqual(fm.get("status"), "archived")
        self.assertIn("superseded_by", fm)


class LlmContextTest(unittest.TestCase):
    """Template llm_context default matches the registry default (§3.2).

    ICD is the deliberate exception: 付録A ships NO llm_context line, so the
    registry default `task` applies implicitly.
    """

    def test_llm_context_matches_registry(self):
        for name, type_code in ALL_TEMPLATES.items():
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                if name == "icd.md.tmpl":
                    # 付録A verbatim: no llm_context line; default task applies.
                    self.assertNotIn("llm_context", fm)
                    self.assertEqual(
                        _registry.effective_llm_context(fm), "task")
                    continue
                expected = _registry.default_llm_context(type_code)
                self.assertEqual(
                    fm.get("llm_context"), expected,
                    "%s: llm_context=%r, registry default=%r"
                    % (name, fm.get("llm_context"), expected),
                )

    def test_llm_context_value_legal(self):
        for name in ALL_TEMPLATES:
            fm, _b, _e = _parse(name)
            if "llm_context" not in fm:
                continue
            with self.subTest(template=name):
                self.assertIn(
                    fm["llm_context"], _registry.LLM_CONTEXT_VALUES,
                    "%s: llm_context %r not legal" % (name, fm["llm_context"]),
                )

    def test_research_and_archive_are_never(self):
        """RESEARCH/ARCHIVE seed llm_context: never (R5 hard-exclude source)."""
        for name in ("research.md.tmpl", "archive.md.tmpl"):
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertEqual(fm.get("llm_context"), "never")


class IcdTemplateTest(unittest.TestCase):
    """icd.md.tmpl == 付録A verbatim structure: 4 sections + canonical_for,
    status current, NO llm_context line."""

    ICD_SECTIONS = ("公開する用語", "正本である事実", "データ契約", "依存してよい入口")

    def test_icd_has_four_sections(self):
        _fm, body, _e = _parse("icd.md.tmpl")
        for heading in self.ICD_SECTIONS:
            with self.subTest(section=heading):
                self.assertIn(
                    "## " + heading, body,
                    "icd template missing ## %s" % heading,
                )

    def test_icd_status_current_and_canonical_for(self):
        fm, _b, _e = _parse("icd.md.tmpl")
        self.assertEqual(fm.get("status"), "current")
        self.assertIn("canonical_for", fm)

    def test_icd_has_no_llm_context_line(self):
        fm, _b, _e = _parse("icd.md.tmpl")
        self.assertNotIn("llm_context", fm)


class SpecTemplateTest(unittest.TestCase):
    """spec.md.tmpl has all 4 mandatory headings non-trivially + depends_on.

    Slice §2.9 / MASTER §8: 入出力・制約・エラー時挙動・受入基準 as headings,
    each with non-empty guidance text under it.
    """

    SPEC_SECTIONS = ("入出力", "制約", "エラー時挙動", "受入基準")

    def test_spec_has_four_sections_nontrivial(self):
        _fm, body, _e = _parse("spec.md.tmpl")
        # Split body on level-2 headings; map heading text -> following content.
        sections = self._sections(body)
        for heading in self.SPEC_SECTIONS:
            with self.subTest(section=heading):
                self.assertIn(
                    heading, sections,
                    "spec template missing ## %s" % heading,
                )
                content = sections[heading].strip()
                self.assertTrue(
                    content,
                    "spec ## %s section is empty (must be non-trivial)"
                    % heading,
                )

    def test_spec_has_depends_on(self):
        fm, _b, _e = _parse("spec.md.tmpl")
        self.assertIn("depends_on", fm, "spec template lacks depends_on")

    @staticmethod
    def _sections(body):
        """Return {heading_text: section_body} for level-2 (## ) headings."""
        out = {}
        current = None
        buf = []
        for line in body.splitlines():
            m = re.match(r"^##\s+(.+?)\s*$", line)
            if m:
                if current is not None:
                    out[current] = "\n".join(buf)
                current = m.group(1)
                buf = []
            elif current is not None:
                buf.append(line)
        if current is not None:
            out[current] = "\n".join(buf)
        return out


class ReviewByTest(unittest.TestCase):
    """DECIDED & WATCH templates carry review_by as a filled mandatory field.

    TC-009/TC-013: a DECIDED/WATCH doc must present review_by for the linter's
    MISSING_KEY-on-review_by check to pass and for the audit review_by-overrun
    signal to have a value to key on.
    """

    def test_decided_and_watch_have_review_by(self):
        for name in ("decided.md.tmpl", "watch.md.tmpl"):
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertIn(
                    "review_by", fm, "%s lacks review_by" % name)
                # Filled field — a placeholder date, not blank/None.
                self.assertTrue(
                    fm["review_by"], "%s review_by is blank" % name)

    def test_review_by_required_types_parity(self):
        """The two review_by-required types match the registry list."""
        self.assertEqual(
            set(_registry.REQUIRED_REVIEW_BY_TYPES), {"DECIDED", "WATCH"})


class ProjectionTest(unittest.TestCase):
    """overview/ctxmap/icd-index bodies begin with the deterrent line.

    TC-042/099/100: rendered projections must carry 「描画される。手で編集しない。」
    as the first body line so a hand-edit is visibly off-contract and the
    render-projection drift check has a stable header anchor.
    """

    def test_projection_first_body_line(self):
        for name in PROJECTION_TEMPLATES:
            _fm, body, _e = _parse(name)
            with self.subTest(template=name):
                first = body.lstrip("\n").splitlines()[0]
                self.assertEqual(
                    first, PROJECTION_FIRST_LINE,
                    "%s first body line is %r, expected %r"
                    % (name, first, PROJECTION_FIRST_LINE),
                )

    def test_icd_index_is_type_overview(self):
        """C8: icd-index reuses type OVERVIEW (no new ICDINDEX type)."""
        fm, _b, _e = _parse("icd-index.md.tmpl")
        self.assertEqual(fm.get("type"), "OVERVIEW")
        self.assertTrue(fm.get("id", "").startswith("OVERVIEW-"))

    def test_no_new_icdindex_type(self):
        """Defensive: ICDINDEX must NOT be a registry type (C8)."""
        self.assertNotIn("ICDINDEX", _registry.TYPES)


class NotInCommentTest(unittest.TestCase):
    """Every type template ends with a trailing `<!-- 入れない: ... -->` comment
    that sits AFTER the body content (so it never leaks into a projection).

    Critique gap (advisory): the 入れない guidance is an HTML comment placed at
    the very end; no 入れない comment text appears above the first body heading,
    so a projection that copies body sections cannot surface it.
    """

    def test_type_templates_have_trailing_notin_comment(self):
        # 17 single-type templates carry an explicit 入れない comment
        # (glossary's 入れない is folded into its prose, projection seeds use
        # 仕様本文/索引 notes — both checked for placement, not presence).
        for name in TYPE_TEMPLATES:
            if name == "glossary.md.tmpl":
                continue
            _fm, body, _e = _parse(name)
            with self.subTest(template=name):
                self.assertIn(
                    "<!-- 入れない:", body,
                    "%s lacks a trailing 入れない comment" % name,
                )

    def test_notin_comment_is_last_nonblank_line(self):
        """The 入れない comment is the final non-blank body line — nothing real
        follows it, so projections that read above it never include it."""
        for name in TYPE_TEMPLATES:
            if name == "glossary.md.tmpl":
                continue
            _fm, body, _e = _parse(name)
            nonblank = [ln for ln in body.splitlines() if ln.strip()]
            with self.subTest(template=name):
                self.assertTrue(nonblank, "%s empty body" % name)
                self.assertTrue(
                    nonblank[-1].strip().startswith("<!-- 入れない:"),
                    "%s: last non-blank line is %r, expected the 入れない comment"
                    % (name, nonblank[-1]),
                )

    def test_projection_seeds_have_no_notin_above_table(self):
        """Projection seeds must not carry 入れない text in their leading prose
        (it would render into the projection). Any 入れない note is an HTML
        comment at the file end, after the table skeleton."""
        for name in PROJECTION_TEMPLATES:
            _fm, body, _e = _parse(name)
            # Take everything before the first HTML comment; assert no 入れない.
            head = body.split("<!--", 1)[0]
            with self.subTest(template=name):
                self.assertNotIn(
                    "入れない", head,
                    "%s leaks 入れない into rendered prose" % name,
                )


class PlaceholderConventionTest(unittest.TestCase):
    """Placeholder convention is consistent across templates (critique risk).

    scaffold.py / doc-author rely on a single placeholder vocabulary:
    angle-bracket tokens like <連番>, <個人名>, <YYYY-MM-DD>, <ドメイン名>.
    Every template uses <YYYY-MM-DD> for both created and updated, and the id
    placeholder is <型>-<連番>; _system templates use the literal domain
    `_system`, domain templates use the <ドメイン名> placeholder.
    """

    DATE_PLACEHOLDER = "<YYYY-MM-DD>"

    def test_dates_use_canonical_placeholder(self):
        for name in ALL_TEMPLATES:
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertEqual(
                    fm.get("created"), self.DATE_PLACEHOLDER,
                    "%s created placeholder drift" % name)
                self.assertEqual(
                    fm.get("updated"), self.DATE_PLACEHOLDER,
                    "%s updated placeholder drift" % name)

    def test_id_uses_renban_placeholder(self):
        """Non-glossary templates seed id as <TYPE>-<連番> (a placeholder).

        glossary ships a concrete GLOSSARY-001 (singleton正本), so it is
        exempt from the <連番> placeholder rule.
        """
        for name, type_code in ALL_TEMPLATES.items():
            if name == "glossary.md.tmpl":
                continue
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                self.assertEqual(
                    fm.get("id"), "%s-<連番>" % type_code,
                    "%s id placeholder drift: %r" % (name, fm.get("id")),
                )

    def test_system_templates_use_literal_system_domain(self):
        """_system-tier templates carry the literal domain `_system`; domain
        templates carry the <ドメイン名> placeholder (§3.4 / D0-7)."""
        system_files = {
            "overview.md.tmpl", "glossary.md.tmpl", "ctxmap.md.tmpl",
            "decided.md.tmpl", "nongoal.md.tmpl", "watch.md.tmpl",
            "icd-index.md.tmpl",
        }
        for name in ALL_TEMPLATES:
            fm, _b, _e = _parse(name)
            with self.subTest(template=name):
                if name in system_files:
                    self.assertEqual(
                        fm.get("domain"), "_system",
                        "%s should be domain _system" % name)
                else:
                    self.assertEqual(
                        fm.get("domain"), "<ドメイン名>",
                        "%s should use <ドメイン名> placeholder" % name)


class GlossaryTemplateTest(unittest.TestCase):
    """glossary.md.tmpl (sibling-owned, validated by path).

    Structural assertions only — the 22-term table CONTENT is the termcore
    agent's contract; here we confirm it parses, is type GLOSSARY current
    always, declares canonical_for [glossary], and ships both control tables.
    """

    def test_glossary_frontmatter(self):
        fm, _b, _e = _parse("glossary.md.tmpl")
        self.assertEqual(_e, [])
        self.assertEqual(fm.get("type"), "GLOSSARY")
        self.assertEqual(fm.get("status"), "current")
        self.assertEqual(fm.get("llm_context"), "always")
        self.assertEqual(
            _frontmatter.as_list(fm.get("canonical_for")), ["glossary"])

    def test_glossary_ships_both_control_tables(self):
        _fm, body, _e = _parse("glossary.md.tmpl")
        self.assertIn("承認語", body, "glossary lacks the approved-term header")
        self.assertIn("唯一の意味", body)
        self.assertIn("禁止する同義語", body)
        self.assertIn("使わない（カルク）", body,
                      "glossary lacks the calque table header")


class TermDisciplineTest(unittest.TestCase):
    """The templates' own prose obeys §1: no banned synonym leaks into a
    template body (the deliverable must pass its own term-check).

    This is a static guard against the concrete banned-synonym tokens from the
    glossary's 禁止する同義語 column, plus the calque word-traps. The authoritative
    checker is term-check.py (sibling-owned); this is a belt-and-suspenders
    static screen so a template never seeds off-vocabulary prose.

    NOTE: '現在形' (grammatical "present tense", verbatim spec §3.2 API row) is
    NOT the banned synonym '現在' (=現行); it is allowed and excluded here.
    """

    # Concrete banned-synonym tokens (rows with literal synonyms in §1).
    BANNED = (
        "ドキュメント", "資料", "領域", "サブシステム",
        "つなぎ目", "接合部", "マスター", "原本", "オリジナル",
        "経緯", "来歴", "廃案", "ボツ", "退役", "保管",
        "要件", "ニーズ", "迷子",
        # calque expressions / word-traps
        "することができる", "を行う", "を可能にする",
        "掘り下げる", "ロールアップ",
    )

    def test_no_banned_synonym_in_template_prose(self):
        for name in ALL_TEMPLATES:
            if name == "glossary.md.tmpl":
                # The glossary正本 lists banned synonyms BY DESIGN (定義表).
                continue
            text = _util.read(_path(name))
            for token in self.BANNED:
                with self.subTest(template=name, token=token):
                    self.assertNotIn(
                        token, text,
                        "%s contains banned token %r" % (name, token),
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
