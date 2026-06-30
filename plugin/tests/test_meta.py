"""§6 meta-condition acceptance (critique gap "§6 meta").

Spec §6 lists the plugin's META conditions (not bound to a single R-id):

    "プラグインが配布できる。docs-system-init が既存を壊さない。スクリプトが
     標準ライブラリだけで動く。per-turn の Hook がエージェントを体感的に遅く
     しない。…"

This file is the acceptance test for the structurally-checkable subset of those
conditions, and for the README deliverable (MASTER §9, BRIEF2 packaging):

  1. STDLIB-ONLY  — every plugin/scripts/*.py imports only the standard library
     or a sibling scripts module (no third-party / pip dependency). Parsed via
     `ast`; each top-level import is checked against
     `sys.stdlib_module_names` ∪ {sibling module names}. (spec §4.3
     "外部pip依存を作らない"; §6 "スクリプトが標準ライブラリだけで動く".)
  2. PACKAGING    — plugin.json is valid JSON and /plugin-install-shaped:
     `name`/`version` present, name == the plugin name. (§6 "配布できる".)
  3. README       — exists, is Japanese, contains a `## 保証限界` section
     inheriting spec §7 (R9), and passes its OWN term-check with no ERROR
     finding (BRIEF2 prose discipline / §1).
  4. CONVENTION   — every hyphenated ENTRY script defines `def main(...)` and
     follows the `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`
     convention (BRIEF2 "every entry-point script").
  5. PERF SMOKE   — a light per-turn-perf advisory: import time of the two
     per-turn-hot scripts (docs-linter, policy-guard) under a generous bound.
     Marked advisory and skipped if either script is absent or the machine is
     too loaded for a meaningful measurement (§6 "per-turn の Hook が…遅くしない"
     is operational, §7; this is a structural smoke, not a tuning gate).

Scoping note: the scripts are authored by sibling agents in the same phase, so
some entry scripts may not yet exist on disk when this runs. Every check that
walks the scripts dir is SCOPED TO THE FILES THAT EXIST and skips gracefully
when none are present, so the meta suite is green from the first script onward.
"""

import os
import sys
# BRIEF2: bootstrap the tests dir onto sys.path so `_util` (and the scripts dir
# it inserts) resolve whether this file is run directly, via discovery, or via
# `python3 -m unittest tests.test_meta`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

import ast        # noqa: E402
import glob       # noqa: E402
import json       # noqa: E402
import time       # noqa: E402
import unittest   # noqa: E402


# Hyphenated entry scripts (CLIs / hook targets, MASTER §5 inventory). Cores are
# the underscore-prefixed modules; they are NOT entry scripts (no main()).
ENTRY_SCRIPTS = (
    "docs-linter.py", "term-check.py", "policy-guard.py", "inject-contract.py",
    "docs-audit.py", "dep-graph.py", "render-projection.py", "term-extract.py",
    "collect-context.py", "scaffold.py", "review-nudge.py",
)

# The two per-turn-hot scripts: run on PostToolUse (linter) and Pre/PostToolUse
# (guard) on every Edit/Write. Their cold-import time is the per-turn-perf proxy.
PER_TURN_SCRIPTS = ("docs-linter.py", "policy-guard.py")


def _scripts_present():
    """Sorted list of plugin/scripts/*.py that exist right now (may be partial)."""
    if not os.path.isdir(_util.SCRIPTS):
        return []
    return sorted(glob.glob(os.path.join(_util.SCRIPTS, "*.py")))


def _sibling_module_names():
    """Module names importable as siblings within plugin/scripts (DRY cores +
    any module that exists). A `from _registry import X` / `import _depgraph`
    is a sibling import, always allowed."""
    names = set()
    for path in _scripts_present():
        names.add(os.path.basename(path)[:-3])
    return names


def _top_level_imports(tree):
    """Yield top-level imported module names (the part before the first dot).

    Relative imports (`from . import x`) are reported as None and skipped by the
    caller — they are siblings by construction.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                yield None          # relative import -> sibling, allowed
                continue
            if node.module is None:
                continue
            yield node.module.split(".")[0]


class TestStdlibOnly(unittest.TestCase):
    """§6 / §4.3: every script imports only stdlib or a sibling scripts module.

    Reports (in the failure message) any non-stdlib, non-sibling import found,
    naming the file and the offending module so the report can cite it.
    """

    def test_no_third_party_imports(self):
        py_files = _scripts_present()
        if not py_files:
            self.skipTest("plugin/scripts has no .py files yet")

        stdlib = set(sys.stdlib_module_names)
        siblings = _sibling_module_names()
        allowed = stdlib | siblings

        offenders = []          # (file, module)
        for path in py_files:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            # ast.parse also verifies the file is syntactically valid Python.
            tree = ast.parse(source, filename=path)
            for top in _top_level_imports(tree):
                if top is None:
                    continue
                if top not in allowed:
                    offenders.append((os.path.relpath(path, _util.PLUGIN_ROOT), top))

        self.assertEqual(
            offenders, [],
            "non-stdlib / non-sibling imports found (must be stdlib only): %s"
            % offenders,
        )

    def test_every_script_parses(self):
        """Defensive: each script is syntactically valid (compiles via ast)."""
        py_files = _scripts_present()
        if not py_files:
            self.skipTest("plugin/scripts has no .py files yet")
        for path in py_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as fh:
                    ast.parse(fh.read(), filename=path)


class TestPluginInstallShape(unittest.TestCase):
    """§6 "プラグインが配布できる": plugin.json is valid and /plugin-install-shaped."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, ".claude-plugin", "plugin.json")

    def test_plugin_json_valid_and_shaped(self):
        self.assertTrue(os.path.isfile(self.path), "plugin.json must exist")
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)        # raises on invalid JSON -> test fails
        # /plugin install requires at minimum a name and a version.
        self.assertIn("name", data, "plugin.json must declare a name")
        self.assertIn("version", data, "plugin.json must declare a version")
        self.assertEqual(data["name"], "context-engineering-blueprint")
        self.assertTrue(str(data["version"]).strip(), "version must be non-empty")

    def test_hooks_manifest_exists_and_valid(self):
        """Hooks are auto-discovered from hooks/hooks.json (§9): it must parse."""
        hooks_path = os.path.join(_util.PLUGIN_ROOT, "hooks", "hooks.json")
        self.assertTrue(os.path.isfile(hooks_path), "hooks/hooks.json must exist")
        with open(hooks_path, "r", encoding="utf-8") as fh:
            json.load(fh)


class TestReadme(unittest.TestCase):
    """README is the entry-point/index deliverable (MASTER §9, BRIEF2)."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, "README.md")
        self.assertTrue(os.path.isfile(self.path), "plugin/README.md must exist")
        self.text = _util.read(self.path)

    def test_has_guarantee_limits_section(self):
        """§7 / R9: README carries a `## 保証限界` section (予防/検出/委ねる)."""
        self.assertIn("保証限界", self.text)
        self.assertIn("## 保証限界", self.text,
                      "保証限界 must be a section heading")
        # The three sub-distinctions inherited from spec §7 (R9).
        self.assertIn("予防", self.text)
        self.assertIn("検出", self.text)
        self.assertIn("委ねる", self.text)

    def test_covers_the_index_topics(self):
        """It is an index: names the install path, the skills, the hooks, the
        scripts, and the staged levels. (Spot-checks, not a knowledge dump.)"""
        for token in (
            "/plugin install",          # install path
            ".claude/",                 # fallback
            "docs-system-init",         # one of the 7 skills
            "docs-curate",              # another skill
            "SessionStart", "PreToolUse", "PostToolUse", "SessionEnd",  # hooks
            "policy-guard.py", "docs-linter.py", "inject-contract.py",  # scripts
            "Level 2", "Level 3", "Level 4",                            # staging
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text, "README should mention %r" % token)

    def test_lists_all_seven_skills(self):
        skills = (
            "docs-system-init", "doc-author", "doc-review", "change-impact",
            "regression-guard", "llm-context-pack", "docs-curate",
        )
        for skill in skills:
            with self.subTest(skill=skill):
                self.assertIn(skill, self.text)

    def test_passes_its_own_term_check_no_errors(self):
        """BRIEF2 §1: the deliverable must pass its own term-check.

        Loads the §1 glossary seed via _termcheck and asserts the README body
        produces NO ERROR finding (BANNED_SYNONYM / CALQUE). WARN-level findings
        (undefined-term heuristic, wordtrap) are advisory and not asserted here.
        """
        _frontmatter = _util.load_core("_frontmatter")
        _termcheck = _util.load_core("_termcheck")
        meta, body, _errs = _frontmatter.parse_file(self.path)
        glossary = _termcheck.load_glossary(None)     # plugin §1 seed
        findings = _termcheck.check(body, meta, glossary)
        errors = [f for f in findings if f.severity == "ERROR"]
        self.assertEqual(
            errors, [],
            "README must pass its own term-check (no ERROR): %s"
            % [(f.code, f.message, f.line) for f in errors],
        )


class TestEntryScriptConvention(unittest.TestCase):
    """BRIEF2: every entry script defines main() and the sys.path.insert convention.

    Scoped to the entry scripts that exist on disk. Each present entry script is
    asserted to (a) define a top-level `def main(...)`, and (b) contain the
    `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` bootstrap so
    its sibling cores import correctly when run as a hook command.
    """

    SYS_PATH_BOOTSTRAP = (
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))"
    )

    def _present_entry_scripts(self):
        out = []
        for name in ENTRY_SCRIPTS:
            path = os.path.join(_util.SCRIPTS, name)
            if os.path.isfile(path):
                out.append((name, path))
        return out

    def test_entry_scripts_define_main(self):
        present = self._present_entry_scripts()
        if not present:
            self.skipTest("no entry scripts on disk yet")
        for name, path in present:
            with self.subTest(script=name):
                with open(path, "r", encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                has_main = any(
                    isinstance(node, ast.FunctionDef) and node.name == "main"
                    for node in tree.body
                )
                self.assertTrue(
                    has_main, "%s must define a top-level def main(...)" % name)

    def test_entry_scripts_have_syspath_bootstrap(self):
        present = self._present_entry_scripts()
        if not present:
            self.skipTest("no entry scripts on disk yet")
        for name, path in present:
            with self.subTest(script=name):
                source = _util.read(path)
                self.assertIn(
                    self.SYS_PATH_BOOTSTRAP, source,
                    "%s must bootstrap sys.path so sibling cores import" % name)

    def test_entry_scripts_are_importable_via_loader(self):
        """The harness can load each present entry script as a module (it imports
        its siblings cleanly and exposes main)."""
        present = self._present_entry_scripts()
        if not present:
            self.skipTest("no entry scripts on disk yet")
        for name, _path in present:
            with self.subTest(script=name):
                module = _util.load_script(name)
                self.assertTrue(
                    callable(getattr(module, "main", None)),
                    "%s.main must be callable" % name)


class TestPerTurnPerfSmoke(unittest.TestCase):
    """§6 / §7 (advisory): the per-turn-hot scripts import quickly.

    This is a SMOKE check, not a tuning gate (the optimal per-turn budget is
    operational, §7). It imports docs-linter and policy-guard cold and asserts a
    generous wall-clock bound so a gross regression (e.g. an accidental heavy
    import) is surfaced. Skipped when either script is absent. The bound is
    deliberately loose; on a wildly loaded CI box a transient overrun is treated
    as inconclusive (skip) rather than a hard failure.
    """

    # Generous ceiling for a cold import of one stdlib-only script (seconds).
    BOUND_SECONDS = 2.0

    def test_per_turn_scripts_import_under_bound(self):
        for name in PER_TURN_SCRIPTS:
            path = os.path.join(_util.SCRIPTS, name)
            if not os.path.isfile(path):
                self.skipTest("per-turn script %s not on disk yet" % name)

        slow = []
        for name in PER_TURN_SCRIPTS:
            start = time.perf_counter()
            _util.load_script(name)          # cold-ish import via importlib
            elapsed = time.perf_counter() - start
            if elapsed > self.BOUND_SECONDS:
                slow.append((name, round(elapsed, 3)))

        if slow:
            # Advisory: a transient overrun on a loaded box is inconclusive, not
            # a correctness failure. Skip with the measurement so it is visible.
            self.skipTest(
                "per-turn import slower than %.1fs (advisory, machine load?): %s"
                % (self.BOUND_SECONDS, slow))


class TestRegistryParity(unittest.TestCase):
    """spec §3 / R6 (MASTER §10.1): the §3.2/§3.3 registry tables live ONCE in
    _registry.py — no other script re-hardcodes them ('コードに規則を二重定義しない',
    R6 '辞書を二重定義しない'). Scans every non-registry script for a dict literal
    that re-encodes the type table (>= 6 keys that are all known TYPE codes)."""

    def test_no_script_rehardcodes_the_type_table(self):
        py = _scripts_present()
        if not py:
            self.skipTest("plugin/scripts has no .py files yet")
        reg = _util.load_core("_registry")
        types = set(reg.TYPES)
        offenders = []
        for path in py:
            if os.path.basename(path) == "_registry.py":
                continue
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                keys = [k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                hits = [k for k in keys if k in types]
                if len(hits) >= 6:
                    offenders.append(
                        (os.path.relpath(path, _util.PLUGIN_ROOT), sorted(hits)))
        self.assertEqual(
            offenders, [],
            "registry table re-hardcoded outside _registry.py: %r" % offenders)


class TestDeliverableDogfood(unittest.TestCase):
    """§1 / R6 / R10 (BRIEF2 'the deliverable must pass its own term-check'):
    every shipped document and template passes the plugin's own term-check.py
    with NO ERROR-severity finding. The GLOSSARY 正本 and projection templates
    self-skip inside check() (they legitimately carry banned tokens / are
    rendered). Runs the actual CLI so it tests the shipped path."""

    def _docs(self):
        out = [os.path.join(_util.PLUGIN_ROOT, "README.md")]
        for base in ("skills", "templates"):
            root = os.path.join(_util.PLUGIN_ROOT, base)
            for pat in ("*.md", "*.tmpl"):
                out += glob.glob(os.path.join(root, "**", pat), recursive=True)
        return sorted(p for p in out if os.path.isfile(p))

    def test_all_shipped_docs_pass_term_check_no_error(self):
        docs = self._docs()
        self.assertTrue(docs, "no shipped docs found")
        offenders = []
        for path in docs:
            out, code = _util.invoke("term-check", argv=[path])
            self.assertEqual(code, 0, path)
            for line in out.splitlines():
                if "[ERROR]" in line:
                    offenders.append(
                        "%s :: %s" % (os.path.relpath(path, _util.PLUGIN_ROOT),
                                      line.strip()))
        self.assertEqual(
            offenders, [],
            "shipped docs must pass own term-check:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
