# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Packaging tests (§6 meta; 仕様 §4, §9; BRIEF2 packaging).

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
    """plugin.json is a valid, minimal Claude Code plugin manifest (仕様 §9)."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, ".claude-plugin", "plugin.json")

    def test_is_valid_json(self):
        self.assertTrue(os.path.isfile(self.path), "plugin.json must exist")
        _load_json(self.path)  # raises on invalid JSON

    def test_required_fields(self):
        data = _load_json(self.path)
        self.assertEqual(data["name"], "doctrine")
        # Version: three-component, and IDENTICAL in marketplace.json (the
        # audit found the value duplicated with no sync guarantee).
        self.assertRegex(data["version"], r"^\d+\.\d+\.\d+$")
        repo = _util.require_repo_root(self)
        mkt = _load_json(os.path.join(repo, ".claude-plugin",
                                      "marketplace.json"))
        self.assertEqual(mkt["plugins"][0]["version"], data["version"],
                         "plugin.json と marketplace.json の version が不一致")
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
    """hooks/hooks.json is the full 仕様 §4 profile."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, "hooks", "hooks.json")
        self.hooks = _load_json(self.path)

    def test_has_all_seven_events(self):
        # 4 events (SPEC-019) + UserPromptSubmit/Stop/PreCompact (ADR-028:
        # R11 生存性のハートビートと R12 会話知識の捕捉)。
        events = set(self.hooks.get("hooks", {}).keys())
        self.assertEqual(
            events,
            {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
             "Stop", "PreCompact", "SessionEnd"},
        )

    def test_coverage_matrix_has_no_empty_cell(self):
        """#94 / SPEC-025: 被覆マトリクスの R1〜R12 の全行が、発火経路・実行する
        もの・証跡・Level 2 での担保の各列を空白なく埋めていること(保証マトリクスの
        空欄を許さない原則)。表を機械で読み、空セルを凍結する。"""
        repo = _util.require_repo_root(self)
        spec = os.path.join(repo, "doctrine_docs", "packaging", "spec",
                            "SPEC-025-coverage-matrix.md")
        rows = []
        with open(spec, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if s.startswith("| R") and s.endswith("|"):
                    cells = [c.strip() for c in s.strip("|").split("|")]
                    rows.append(cells)
        # R1〜R12 の 12 行。各行はちょうど 5 列で、どのセルも空でない。
        self.assertEqual(len(rows), 12, "expected R1..R12 rows, got %d" % len(rows))
        for cells in rows:
            self.assertEqual(len(cells), 5, "row must have 5 columns: %r" % cells)
            for c in cells:
                self.assertTrue(c, "empty cell in coverage matrix row: %r" % cells)

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
        # G2: SessionEnd must run docs-audit.py AND write the summary to a
        # cache inject-contract reads, else every SessionStart shows
        # 前回監査なし. v0.4.0: the summary is PROJECT-scoped
        # (${CLAUDE_PROJECT_DIR}/.claude/.cache) so it survives plugin updates
        # and two projects sharing one plugin do not clobber each other.
        cmds = _commands_for(self.hooks, "SessionEnd")
        self.assertEqual(len(cmds), 1)
        argv = _argv(cmds[0])
        self.assertTrue(argv[0].endswith("/scripts/docs-audit.py"))
        self.assertIn("--summary-out", argv)
        self.assertEqual(argv[argv.index("--summary-out") + 1],
                         "${CLAUDE_PROJECT_DIR}/.claude/.cache/last-audit.json")
        self.assertIn("--root-from", argv)
        self.assertEqual(argv[argv.index("--root-from") + 1],
                         "${CLAUDE_PROJECT_DIR}")
        self.assertIn("--fail-on", argv)
        self.assertEqual(argv[argv.index("--fail-on") + 1], "never")
        # ADR-019: SessionEnd audit self-gates on docs/_system/.docs-level.
        self.assertIn("--respect-docs-level", argv)


class TestHooksLevel2Profile(unittest.TestCase):
    """hooks/hooks.level2.json is the trimmed Level-2 variant (仕様 §4.4)."""

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

    def test_event_set_is_the_full_profile_minus_sessionend(self):
        """縮小構成のイベント集合を凍結する(ADR-075)。

        これまでこの類は「落とすもの」だけを検めており、残すべきイベントを
        凍結していなかった。そのため ADR-028 で三イベント(UserPromptSubmit・
        Stop・PreCompact)を全構成へ足したとき、縮小構成が取り残されても
        誰も気づかなかった。SPEC-019 が定める縮小差分は「SessionEnd の監査と
        PostToolUse の policy-guard・review-nudge を外す」だけであり、
        ADR-030 決定(2)は生存性(R11)と捕捉(R12)を段差に依らず動かすと定める。
        """
        full = _load_json(os.path.join(_util.PLUGIN_ROOT, "hooks",
                                       "hooks.json"))
        expected = set(full["hooks"]) - {"SessionEnd"}
        self.assertEqual(
            expected, set(self.hooks["hooks"]),
            "縮小構成のイベント集合が『全構成 −{SessionEnd}』と違う。"
            "生存性(R11)と捕捉(R12)は段差に依らず動く(ADR-030 決定2)")

    def test_liveness_and_capture_survive_the_reduced_profile(self):
        """R11/R12 の担い手が縮小構成にも配線されている(ADR-030 決定2)。"""
        for event, program in (
                ("UserPromptSubmit", "gov-heartbeat.py"),
                ("Stop", "capture-nudge.py"),
                ("PreCompact", "precompact-dump.py")):
            with self.subTest(event=event):
                self.assertEqual(
                    ["${CLAUDE_PLUGIN_ROOT}/scripts/" + program],
                    _programs_for(self.hooks, event),
                    "%s が縮小構成に無い。手で配線した導入先で "
                    "R11/R12 が最初から存在しなくなる" % event)

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


class TestDistributionHygiene(unittest.TestCase):
    """配布物に開発機の実行時の状態を混ぜない(ADR-075)。

    marketplace の `source` がディレクトリのとき、配布は作業木の複製である
    (git archive ではない)。`.gitignore` は複製を止めないので、実行時に
    plugin/ の下へ書いた物はそのまま利用者の導入先へ配られる。実際に
    導入実体へ、別ワークスペース時代の監査要約(`root` が他所を指す
    last-audit.json)と開発機のセッション印が複製されていた。

    バイトコード(__pycache__)は無害で、しかも試験自身が生むためここでは
    見ない。配布の直前に release-check の衛生検査が見る(責務の分担)。
    """

    FORBIDDEN_DIRS = (".cache", ".claude")

    def test_no_runtime_state_under_plugin_root(self):
        found = []
        for base, dirs, _files in os.walk(_util.PLUGIN_ROOT):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in list(dirs):
                if name in self.FORBIDDEN_DIRS:
                    found.append(os.path.relpath(os.path.join(base, name),
                                                 _util.PLUGIN_ROOT))
        self.assertEqual(
            [], sorted(found),
            "plugin/ の下に実行時の状態がある: %s。ディレクトリ配布では"
            "そのまま利用者へ複製される。消したうえで、書き先を "
            "${CLAUDE_PROJECT_DIR}/.claude/.cache へ寄せること" % sorted(found))

    def test_no_test_reaches_outside_the_plugin_root(self):
        """同梱の試験が、配布されないファイルを無条件に読まない(ADR-075)。

        公式仕様は「導入したプラグインは自分のディレクトリの外を参照できない」
        と明記する。リポジトリ直下の scripts/ や doctrine_docs/ を素で開く試験は、
        利用者の導入先で必ず失敗する(実測 1 failure / 4 error)。外を要る試験は
        _util.require_repo_root か setUpModule の skip を通すこと。
        """
        import re
        tests_dir = os.path.join(_util.PLUGIN_ROOT, "tests")
        pat = re.compile(r"os\.path\.dirname\(\s*_util\.PLUGIN_ROOT\s*\)")
        offenders = []
        for name in sorted(os.listdir(tests_dir)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(tests_dir, name), encoding="utf-8") as fh:
                body = fh.read()
            if pat.search(body):
                offenders.append(name)
        self.assertEqual(
            [], offenders,
            "plugin/ の外を素で指す試験がある: %s。_util.require_repo_root を"
            "通して、導入先では skip されるようにすること" % offenders)


if __name__ == "__main__":
    unittest.main()
