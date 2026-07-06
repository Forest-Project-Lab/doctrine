"""Packaging tests (§6 meta; MASTER §4, §9; BRIEF2 packaging).

Covers the critique gaps "Level-2 trimmed hooks.json", "§6 meta (stdlib-only,
plugin.json valid, hook-snapshot note)". These assert the shipped manifest +
hook profiles are valid and structurally correct, and that any scripts already
on disk import nothing outside the standard library (plus their sibling
underscore cores).
"""

import ast
import glob
import json
import os
import shlex
import sys
import unittest

import _util


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _commands(hooks_obj):
    """Yield (event, matcher_or_None, command) for every command in a profile."""
    for event, groups in hooks_obj.get("hooks", {}).items():
        for group in groups:
            matcher = group.get("matcher")
            for entry in group.get("hooks", []):
                yield event, matcher, entry.get("command", "")


def _commands_for(hooks_obj, event, matcher=None):
    """Ordered list of command strings for a given event (and optional matcher)."""
    out = []
    for group in hooks_obj.get("hooks", {}).get(event, []):
        if matcher is not None and group.get("matcher") != matcher:
            continue
        for entry in group.get("hooks", []):
            out.append(entry.get("command", ""))
    return out


def _argv(command):
    """Shell-token view of a hook command (quotes resolved, ${VAR} kept)."""
    return shlex.split(command)


def _programs_for(hooks_obj, event, matcher=None):
    """Ordered list of program paths (first shell token) for an event."""
    return [_argv(c)[0] for c in _commands_for(hooks_obj, event, matcher)]


class TestPluginJson(unittest.TestCase):
    """plugin.json is a valid, minimal Claude Code plugin manifest (MASTER §9)."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, ".claude-plugin", "plugin.json")

    def test_is_valid_json(self):
        self.assertTrue(os.path.isfile(self.path), "plugin.json must exist")
        _load_json(self.path)  # raises on invalid JSON

    def test_required_fields(self):
        data = _load_json(self.path)
        self.assertEqual(data["name"], "doctrine")
        self.assertEqual(data["version"], "0.1.0")
        self.assertEqual(data["license"], "MIT")
        # description: a non-empty one-sentence Japanese string.
        self.assertIsInstance(data["description"], str)
        self.assertTrue(data["description"].strip(), "description must be non-empty")
        # author is an object carrying a name.
        self.assertIsInstance(data["author"], dict)
        self.assertTrue(data["author"].get("name"))

    def test_no_unexpected_top_level_keys(self):
        """Manifest stays minimal: only known plugin.json fields."""
        data = _load_json(self.path)
        allowed = {"name", "version", "description", "author", "license",
                   "homepage", "repository", "keywords"}
        self.assertTrue(set(data.keys()) <= allowed,
                        "unexpected keys: %s" % (set(data.keys()) - allowed))


class TestAllJsonValid(unittest.TestCase):
    """Every *.json shipped under plugin/ parses (§6 meta)."""

    def test_all_json_parses(self):
        pattern = os.path.join(_util.PLUGIN_ROOT, "**", "*.json")
        files = glob.glob(pattern, recursive=True)
        self.assertTrue(files, "expected at least one JSON file under plugin/")
        for path in files:
            with self.subTest(path=path):
                _load_json(path)


class TestHooksFullProfile(unittest.TestCase):
    """hooks/hooks.json is the full MASTER §4 profile."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, "hooks", "hooks.json")
        self.hooks = _load_json(self.path)

    def test_has_all_four_events(self):
        events = set(self.hooks.get("hooks", {}).keys())
        self.assertEqual(
            events,
            {"SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"},
        )

    def test_every_command_is_a_plugin_script(self):
        for event, matcher, command in _commands(self.hooks):
            with self.subTest(event=event, matcher=matcher, command=command):
                # A command may carry arguments after the script path
                # (e.g. SessionEnd's docs-audit.py --summary-out ...). Validate
                # the program token: the first shell token, quotes resolved.
                program = _argv(command)[0]
                self.assertTrue(
                    program.startswith("${CLAUDE_PLUGIN_ROOT}/scripts/"),
                    "command must live under ${CLAUDE_PLUGIN_ROOT}/scripts/: %r" % command,
                )
                self.assertTrue(program.endswith(".py"),
                                "command must be a .py script: %r" % command)

    def test_commands_survive_paths_with_spaces(self):
        """Every ${VAR} in a command must sit inside double quotes: hook
        commands run through the shell, and an unquoted expansion word-splits
        on paths with spaces (breaking every hook, or silently mis-pointing
        docs-audit's --root). Substituting a spacey path must not change the
        token count."""
        for event, matcher, command in _commands(self.hooks):
            with self.subTest(event=event, matcher=matcher, command=command):
                spacey = command.replace(
                    "${CLAUDE_PLUGIN_ROOT}", "/tmp/pa th/plugin"
                ).replace("${CLAUDE_PROJECT_DIR}", "/tmp/pa th/proj")
                self.assertEqual(
                    len(_argv(spacey)), len(_argv(command)),
                    "unquoted ${VAR} word-splits on spacey paths: %r" % command,
                )

    def test_sessionstart_injects_contract(self):
        progs = _programs_for(self.hooks, "SessionStart")
        self.assertEqual(progs, ["${CLAUDE_PLUGIN_ROOT}/scripts/inject-contract.py"])

    def test_pretooluse_edit_and_bash_route_to_guard(self):
        edit = _programs_for(self.hooks, "PreToolUse", "Edit|Write|MultiEdit")
        bash = _programs_for(self.hooks, "PreToolUse", "Bash")
        self.assertEqual(edit, ["${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py"])
        self.assertEqual(bash, ["${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py"])

    def test_posttooluse_guard_then_linter_in_order(self):
        """C4: PostToolUse runs policy-guard FIRST, then docs-linter, then the
        advisory doc-review nudge (review-nudge.py) last."""
        progs = _programs_for(self.hooks, "PostToolUse", "Edit|Write|MultiEdit")
        self.assertEqual(
            progs,
            [
                "${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py",
                "${CLAUDE_PLUGIN_ROOT}/scripts/docs-linter.py",
                "${CLAUDE_PLUGIN_ROOT}/scripts/review-nudge.py",
            ],
        )

    def test_sessionend_runs_audit_and_writes_the_inject_cache(self):
        # G2: SessionEnd must run docs-audit.py AND write the summary to the
        # exact cache inject-contract reads, else every SessionStart shows
        # 前回監査なし. The command carries the SessionEnd contract
        # (--summary-out <plugin-root>/.cache/last-audit.json, --fail-on never).
        cmds = _commands_for(self.hooks, "SessionEnd")
        self.assertEqual(len(cmds), 1)
        argv = _argv(cmds[0])
        self.assertTrue(argv[0].endswith("/scripts/docs-audit.py"))
        self.assertIn("--summary-out", argv)
        self.assertEqual(argv[argv.index("--summary-out") + 1],
                         "${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json")
        self.assertIn("--root", argv)
        self.assertEqual(argv[argv.index("--root") + 1],
                         "${CLAUDE_PROJECT_DIR}/docs")
        self.assertIn("--fail-on", argv)
        self.assertEqual(argv[argv.index("--fail-on") + 1], "never")


class TestHooksLevel2Profile(unittest.TestCase):
    """hooks/hooks.level2.json is the trimmed Level-2 variant (MASTER §4.4)."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, "hooks", "hooks.level2.json")
        self.hooks = _load_json(self.path)

    def test_valid_json_and_paths(self):
        for event, matcher, command in _commands(self.hooks):
            with self.subTest(event=event, command=command):
                program = _argv(command)[0]
                self.assertTrue(program.startswith("${CLAUDE_PLUGIN_ROOT}/scripts/"))
                self.assertTrue(program.endswith(".py"))

    def test_commands_survive_paths_with_spaces(self):
        """Same quoting invariant as the full profile (see TestHooksFullProfile)."""
        for event, matcher, command in _commands(self.hooks):
            with self.subTest(event=event, command=command):
                spacey = command.replace(
                    "${CLAUDE_PLUGIN_ROOT}", "/tmp/pa th/plugin"
                ).replace("${CLAUDE_PROJECT_DIR}", "/tmp/pa th/proj")
                self.assertEqual(len(_argv(spacey)), len(_argv(command)))

    def test_omits_sessionend_audit(self):
        self.assertNotIn("SessionEnd", self.hooks.get("hooks", {}))

    def test_omits_posttooluse_policy_guard(self):
        """Level-2 PostToolUse keeps only the advisory linter (no post-apply guard)."""
        progs = _programs_for(self.hooks, "PostToolUse", "Edit|Write|MultiEdit")
        self.assertEqual(progs, ["${CLAUDE_PLUGIN_ROOT}/scripts/docs-linter.py"])
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py", progs)

    def test_keeps_sessionstart_and_pretooluse(self):
        self.assertEqual(
            _programs_for(self.hooks, "SessionStart"),
            ["${CLAUDE_PLUGIN_ROOT}/scripts/inject-contract.py"],
        )
        self.assertEqual(
            _programs_for(self.hooks, "PreToolUse", "Edit|Write|MultiEdit"),
            ["${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py"],
        )
        self.assertEqual(
            _programs_for(self.hooks, "PreToolUse", "Bash"),
            ["${CLAUDE_PLUGIN_ROOT}/scripts/policy-guard.py"],
        )


class TestScriptsExecutable(unittest.TestCase):
    """Every plugin/scripts/*.py carries the executable bit.

    hooks.json runs the scripts directly (no `python3` prefix), so a fresh
    checkout/install must receive mode 100755 from the git index. With
    core.filemode=false a working-tree chmod is never recorded, which is
    exactly the failure this guards against: all hooks dying with exit 126
    (fail-open, silent) on a new install.
    """

    def test_all_scripts_have_exec_bit(self):
        py_files = sorted(glob.glob(os.path.join(_util.SCRIPTS, "*.py")))
        self.assertTrue(py_files, "expected .py files under plugin/scripts/")
        for path in py_files:
            with self.subTest(path=path):
                self.assertTrue(
                    os.access(path, os.X_OK),
                    "%s is not executable; run: git update-index --chmod=+x %s"
                    % (path, path),
                )

    def test_all_scripts_have_python3_shebang(self):
        """The exec bit is useless without a shebang line."""
        py_files = sorted(glob.glob(os.path.join(_util.SCRIPTS, "*.py")))
        for path in py_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as fh:
                    first = fh.readline()
                self.assertTrue(
                    first.startswith("#!") and "python3" in first,
                    "%s must start with a python3 shebang" % path,
                )


class TestScriptsStdlibOnly(unittest.TestCase):
    """Every plugin/scripts/*.py imports only stdlib + sibling underscore cores.

    Scoped to files that exist: if scripts/ is empty (early phase) the test
    skips gracefully so packaging can pass before the scripts are authored.
    """

    def _stdlib_names(self):
        return set(sys.stdlib_module_names)

    def _sibling_cores(self, scripts_dir):
        """Underscore-named sibling modules are allowed imports (DRY cores)."""
        names = set()
        for path in glob.glob(os.path.join(scripts_dir, "*.py")):
            base = os.path.basename(path)[:-3]
            if base.startswith("_"):
                names.add(base)
        return names

    def test_no_forbidden_third_party_imports(self):
        scripts_dir = _util.SCRIPTS
        py_files = sorted(glob.glob(os.path.join(scripts_dir, "*.py"))) \
            if os.path.isdir(scripts_dir) else []
        if not py_files:
            self.skipTest("plugin/scripts has no .py files yet")

        stdlib = self._stdlib_names()
        cores = self._sibling_cores(scripts_dir)
        allowed = stdlib | cores

        for path in py_files:
            with self.subTest(path=path):
                with open(path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                # Compile to catch syntax errors early.
                tree = ast.parse(source, filename=path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            top = alias.name.split(".")[0]
                            self.assertIn(
                                top, allowed,
                                "%s imports non-stdlib module %r" % (path, top),
                            )
                    elif isinstance(node, ast.ImportFrom):
                        if node.level and node.level > 0:
                            # Relative import (rare); treat as sibling — allowed.
                            continue
                        if node.module is None:
                            continue
                        top = node.module.split(".")[0]
                        self.assertIn(
                            top, allowed,
                            "%s imports non-stdlib module %r" % (path, top),
                        )


if __name__ == "__main__":
    unittest.main()
