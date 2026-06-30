#!/usr/bin/env python3
"""Unit tests for scripts/_registry.py — the single in-code copy of §3.2/§3.3/§3.4.

Covers the synthesis gap "_registry.py itself has no test cases" (MASTER §10.1):
registry parity (the 18 types with correct default status & llm_context),
status_allowed per type (ADR exact set, RESEARCH draft carve-out, non-ADR excludes
'accepted'), type_of prefix parsing, is_projection, effective_llm_context override,
required_keys gating, is_current. Asserts against the MASTER §2 tables as the
authoritative source.
"""
import os
import sys
import unittest

# Import the underscore core directly via sys.path (NOT via tests/_util) so this
# slice has no dependency on the test harness (per slice instruction).
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import _registry as R  # noqa: E402


# Expected tables transcribed independently from MASTER §2 / spec §3.2 so the
# test is a true parity check, not a re-read of the module's own literals.
EXPECTED_TYPES = (
    "ICD", "OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH",
    "REQ", "SPEC", "DATA", "API", "ADR", "CHANGE", "IMPACT", "IMPL", "TEST",
    "RESEARCH", "ARCHIVE",
)

EXPECTED_DEFAULT_STATUS = {
    "ICD": "current", "OVERVIEW": "current", "GLOSSARY": "current",
    "CTXMAP": "current", "DECIDED": "current", "NONGOAL": "current",
    "WATCH": "current", "REQ": "current", "SPEC": "current", "DATA": "current",
    "API": "current", "ADR": "accepted", "CHANGE": "proposed",
    "IMPACT": "current", "IMPL": "current", "TEST": "current",
    "RESEARCH": "draft", "ARCHIVE": "archived",
}

EXPECTED_DEFAULT_LLM_CONTEXT = {
    "ICD": "task", "OVERVIEW": "always", "GLOSSARY": "always", "CTXMAP": "task",
    "DECIDED": "always", "NONGOAL": "always", "WATCH": "always", "REQ": "task",
    "SPEC": "task", "DATA": "task", "API": "task", "ADR": "task",
    "CHANGE": "task", "IMPACT": "task", "IMPL": "task", "TEST": "task",
    "RESEARCH": "never", "ARCHIVE": "never",
}


class TestTypeRegistryParity(unittest.TestCase):
    """All 18 types present, in registry order, with correct default tables (MASTER §2.1)."""

    def test_18_types_in_order(self):
        self.assertEqual(R.TYPES, EXPECTED_TYPES)
        self.assertEqual(len(R.TYPES), 18)
        self.assertEqual(len(set(R.TYPES)), 18, "no duplicate type codes")

    def test_default_status_per_type(self):
        self.assertEqual(set(R.TYPE_DEFAULT_STATUS), set(EXPECTED_TYPES))
        for t in EXPECTED_TYPES:
            self.assertEqual(R.TYPE_DEFAULT_STATUS[t], EXPECTED_DEFAULT_STATUS[t], t)
            self.assertEqual(R.default_status(t), EXPECTED_DEFAULT_STATUS[t], t)

    def test_default_llm_context_per_type(self):
        self.assertEqual(set(R.TYPE_DEFAULT_LLM_CONTEXT), set(EXPECTED_TYPES))
        for t in EXPECTED_TYPES:
            self.assertEqual(R.TYPE_DEFAULT_LLM_CONTEXT[t], EXPECTED_DEFAULT_LLM_CONTEXT[t], t)
            self.assertEqual(R.default_llm_context(t), EXPECTED_DEFAULT_LLM_CONTEXT[t], t)

    def test_every_default_status_is_in_its_own_allow_list(self):
        # Invariant 2 (01-registry §9): default_status in status_allowed(type).
        for t in EXPECTED_TYPES:
            self.assertIn(R.default_status(t), R.status_allowed(t), t)

    def test_every_default_status_is_a_known_status(self):
        for t in EXPECTED_TYPES:
            self.assertIn(R.default_status(t), R.ALL_STATUSES, t)

    def test_every_default_llm_context_is_legal(self):
        for t in EXPECTED_TYPES:
            self.assertIn(R.default_llm_context(t), R.LLM_CONTEXT_VALUES, t)

    def test_unknown_type_defaults_are_none(self):
        self.assertIsNone(R.default_status("XYZ"))
        self.assertIsNone(R.default_llm_context("XYZ"))


class TestTypeLocation(unittest.TestCase):
    """置き場所 table (MASTER §2.1) — allowed_locations + WATCH dual location."""

    def test_all_types_have_a_location(self):
        self.assertEqual(set(R.TYPE_LOCATION), set(EXPECTED_TYPES))

    def test_watch_has_two_locations(self):
        locs = R.allowed_locations("WATCH")
        self.assertEqual(set(locs), {"_system/", "<domain>/test/"})

    def test_single_location_types(self):
        self.assertEqual(R.allowed_locations("SPEC"), ["<domain>/spec/"])
        self.assertEqual(R.allowed_locations("ADR"), ["<domain>/decisions/"])
        self.assertEqual(R.allowed_locations("OVERVIEW"), ["_system/"])

    def test_allowed_locations_returns_fresh_list(self):
        a = R.allowed_locations("SPEC")
        a.append("MUTATED")
        self.assertEqual(R.allowed_locations("SPEC"), ["<domain>/spec/"])

    def test_unknown_type_has_no_location(self):
        self.assertEqual(R.allowed_locations("XYZ"), [])


class TestStatusAllowed(unittest.TestCase):
    """Per-type status allow-lists (§3.3 + C5)."""

    def test_adr_exact_set(self):
        self.assertEqual(
            R.status_allowed("ADR"),
            {"proposed", "accepted", "superseded", "deprecated"},
        )

    def test_non_adr_excludes_accepted(self):
        # The "6値" base = accepted を除く. 'accepted' legal ONLY for ADR (R2).
        for t in EXPECTED_TYPES:
            if t == "ADR":
                continue
            self.assertNotIn("accepted", R.status_allowed(t), t)

    def test_only_adr_allows_accepted(self):
        allowing = [t for t in EXPECTED_TYPES if "accepted" in R.status_allowed(t)]
        self.assertEqual(allowing, ["ADR"])

    def test_non_adr_base_six_values(self):
        base = {"proposed", "current", "deprecated", "superseded", "archived", "open"}
        for t in EXPECTED_TYPES:
            if t in ("ADR", "RESEARCH"):
                continue
            self.assertEqual(R.status_allowed(t), base, t)

    def test_research_draft_carveout(self):
        base = {"proposed", "current", "deprecated", "superseded", "archived", "open"}
        self.assertEqual(R.status_allowed("RESEARCH"), base | {"draft"})
        self.assertIn("draft", R.status_allowed("RESEARCH"))

    def test_draft_legal_only_for_research(self):
        allowing = [t for t in EXPECTED_TYPES if "draft" in R.status_allowed(t)]
        self.assertEqual(allowing, ["RESEARCH"])

    def test_status_allowed_subset_of_all_statuses(self):
        for t in EXPECTED_TYPES:
            self.assertTrue(set(R.status_allowed(t)) <= set(R.ALL_STATUSES), t)

    def test_status_allowed_returns_fresh_set(self):
        s = R.status_allowed("SPEC")
        s.add("MUTATED")
        self.assertNotIn("MUTATED", R.status_allowed("SPEC"))

    def test_unknown_type_status_allowed_empty(self):
        self.assertEqual(R.status_allowed("XYZ"), set())


class TestTypeOf(unittest.TestCase):
    """type_of prefix parsing (MASTER §2.5): returns str|None, never raises."""

    def test_known_prefix(self):
        self.assertEqual(R.type_of("SPEC-014"), "SPEC")
        self.assertEqual(R.type_of("ADR-1"), "ADR")
        self.assertEqual(R.type_of("ICD-0"), "ICD")
        self.assertEqual(R.type_of("RESEARCH-99999"), "RESEARCH")

    def test_unknown_prefix_is_none(self):
        self.assertIsNone(R.type_of("XYZ-1"))

    def test_malformed_is_none(self):
        for bad in ("SPEC", "SPEC-", "-014", "spec-014", "SPEC_014",
                    "SPEC-01a", "SPEC 014", "", "SPEC-014-refund"):
            self.assertIsNone(R.type_of(bad), bad)

    def test_non_str_is_none(self):
        for bad in (None, 14, ["SPEC-1"], {}):
            self.assertIsNone(R.type_of(bad))

    def test_every_known_type_round_trips(self):
        for t in EXPECTED_TYPES:
            self.assertEqual(R.type_of(t + "-7"), t, t)


class TestIsKnownType(unittest.TestCase):
    def test_known(self):
        for t in EXPECTED_TYPES:
            self.assertTrue(R.is_known_type(t), t)

    def test_unknown(self):
        for bad in ("XYZ", "spec", "ICDINDEX", "", None):
            self.assertFalse(R.is_known_type(bad))


class TestIsProjection(unittest.TestCase):
    """is_projection True for exactly {OVERVIEW, CTXMAP} (C8 / invariant 8)."""

    def test_projection_types(self):
        self.assertTrue(R.is_projection("OVERVIEW"))
        self.assertTrue(R.is_projection("CTXMAP"))

    def test_non_projection_types(self):
        for t in EXPECTED_TYPES:
            if t in ("OVERVIEW", "CTXMAP"):
                continue
            self.assertFalse(R.is_projection(t), t)

    def test_projection_types_constant(self):
        self.assertEqual(R.PROJECTION_TYPES, ("OVERVIEW", "CTXMAP"))

    def test_unknown_not_projection(self):
        self.assertFalse(R.is_projection("ICDINDEX"))


class TestEffectiveLlmContext(unittest.TestCase):
    """Frontmatter override wins, else per-type default (MASTER §2.5)."""

    def test_override_wins(self):
        # SPEC default is 'task'; an explicit 'never' override must win.
        self.assertEqual(
            R.effective_llm_context({"type": "SPEC", "llm_context": "never"}),
            "never",
        )
        # OVERVIEW default is 'always'; explicit 'task' override wins.
        self.assertEqual(
            R.effective_llm_context({"type": "OVERVIEW", "llm_context": "task"}),
            "task",
        )

    def test_default_when_no_override(self):
        self.assertEqual(R.effective_llm_context({"type": "SPEC"}), "task")
        self.assertEqual(R.effective_llm_context({"type": "RESEARCH"}), "never")
        self.assertEqual(R.effective_llm_context({"type": "OVERVIEW"}), "always")

    def test_empty_override_falls_back_to_default(self):
        # An empty-string override must not shadow the default.
        self.assertEqual(
            R.effective_llm_context({"type": "SPEC", "llm_context": ""}),
            "task",
        )

    def test_none_override_falls_back_to_default(self):
        self.assertEqual(
            R.effective_llm_context({"type": "ICD", "llm_context": None}),
            "task",
        )

    def test_unknown_type_no_override_is_none(self):
        self.assertIsNone(R.effective_llm_context({"type": "XYZ"}))
        self.assertIsNone(R.effective_llm_context({}))

    def test_robust_to_non_dict(self):
        self.assertIsNone(R.effective_llm_context(None))
        self.assertIsNone(R.effective_llm_context("notadict"))


class TestRequiredKeys(unittest.TestCase):
    """required_keys gating (MASTER §2.4 / C11): base 8, +review_by for DECIDED/WATCH."""

    def test_base_eight_no_created(self):
        self.assertEqual(
            R.REQUIRED_KEYS_L2,
            ("id", "title", "type", "domain", "status", "owner", "updated", "sources"),
        )
        self.assertEqual(len(R.REQUIRED_KEYS_L2), 8)
        self.assertNotIn("created", R.REQUIRED_KEYS_L2)

    def test_non_review_type_returns_base_eight(self):
        for lvl in (2, 3, 4):
            self.assertEqual(R.required_keys(lvl, "SPEC"), R.REQUIRED_KEYS_L2, lvl)

    def test_decided_and_watch_add_review_by(self):
        for t in ("DECIDED", "WATCH"):
            for lvl in (2, 3, 4):
                keys = R.required_keys(lvl, t)
                self.assertEqual(keys, R.REQUIRED_KEYS_L2 + ("review_by",), (t, lvl))

    def test_required_set_does_not_grow_with_level_except_review_by(self):
        # depends_on / impacts / canonical_for are NEVER required.
        for t in EXPECTED_TYPES:
            for lvl in (2, 3, 4):
                keys = set(R.required_keys(lvl, t))
                self.assertNotIn("depends_on", keys, (t, lvl))
                self.assertNotIn("impacts", keys, (t, lvl))
                self.assertNotIn("canonical_for", keys, (t, lvl))

    def test_bad_level_raises(self):
        for bad in (1, 5, 0, "2", None):
            with self.assertRaises(ValueError):
                R.required_keys(bad, "SPEC")

    def test_review_by_types_constant(self):
        self.assertEqual(R.REQUIRED_REVIEW_BY_TYPES, ("DECIDED", "WATCH"))

    def test_level_key_ladder_constants(self):
        self.assertEqual(R.LEVEL3_KEYS, ("depends_on", "impacts", "review_by"))
        self.assertEqual(R.LEVEL4_KEYS, ("canonical_for",))


class TestIsCurrent(unittest.TestCase):
    """is_current: current/accepted -> True, others -> False (§1 glossary)."""

    def test_current_and_accepted_true(self):
        self.assertTrue(R.is_current("current"))
        self.assertTrue(R.is_current("accepted"))

    def test_others_false(self):
        for s in ("proposed", "deprecated", "superseded", "archived", "open", "draft"):
            self.assertFalse(R.is_current(s), s)

    def test_current_statuses_constant(self):
        self.assertEqual(R.CURRENT_STATUSES, frozenset({"current", "accepted"}))

    def test_garbage_false(self):
        self.assertFalse(R.is_current("Current"))
        self.assertFalse(R.is_current(""))
        self.assertFalse(R.is_current(None))


class TestFixedSystemFiles(unittest.TestCase):
    """Fixed _system filenames (01-registry §5.3, consistent with MASTER C8/§5.8)."""

    def test_projection_files(self):
        self.assertEqual(
            R.PROJECTION_FILES,
            frozenset({"overview.md", "icd-index.md", "context-map.md"}),
        )

    def test_system_canonical_files(self):
        self.assertEqual(
            R.SYSTEM_CANONICAL_FILES,
            frozenset({"glossary.md", "decided-facts.md", "non-goals.md",
                       "overview.md", "watchlist.md"}),
        )

    def test_watchlist_is_system_canonical(self):
        """#04: the WATCH 正本 at the spec-fixed path docs/_system/watchlist.md
        (§3.7) must be recognized so the linter skips id<->filename matching."""
        self.assertIn("watchlist.md", R.SYSTEM_CANONICAL_FILES)


class TestConstants(unittest.TestCase):
    """Top-level constant sanity (the cross-slice contract surface)."""

    def test_all_statuses(self):
        self.assertEqual(
            R.ALL_STATUSES,
            ("proposed", "accepted", "current", "deprecated",
             "superseded", "archived", "open", "draft"),
        )

    def test_llm_context_values(self):
        self.assertEqual(R.LLM_CONTEXT_VALUES, ("always", "task", "never"))

    def test_system_tier_types(self):
        self.assertEqual(
            R.SYSTEM_TIER_TYPES,
            ("OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH"),
        )

    def test_always_contract_types(self):
        self.assertEqual(
            R.ALWAYS_CONTRACT_TYPES,
            ("DECIDED", "NONGOAL", "WATCH", "GLOSSARY"),
        )

    def test_domain_of_not_present(self):
        # domain_of lives in _depgraph.resolve, NOT in the registry (MASTER §2.5).
        self.assertFalse(hasattr(R, "domain_of"))


if __name__ == "__main__":
    unittest.main()
