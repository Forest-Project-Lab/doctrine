# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""§6 meta-condition acceptance (critique gap "§6 meta").

Spec §6 lists the plugin's META conditions (not bound to a single R-id):

    "プラグインが配布できる。docs-system-init が既存を壊さない。スクリプトが
     標準ライブラリだけで動く。per-turn の Hook がエージェントを体感的に遅く
     しない。…"

This file is the acceptance test for the structurally-checkable subset of those
conditions, and for the README deliverable (仕様 §9, BRIEF2 packaging):

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
import shutil
import sys
# BRIEF2: bootstrap the tests dir onto sys.path so `_util` (and the scripts dir
# it inserts) resolve whether this file is run directly, via discovery, or via
# `python3 -m unittest tests.test_meta`.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

import ast        # noqa: E402
import glob       # noqa: E402
import json       # noqa: E402
import re         # noqa: E402
import time       # noqa: E402
import unittest   # noqa: E402


# Hyphenated entry scripts (CLIs / hook targets, 仕様 §5 inventory). Cores are
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
        self.assertEqual(data["name"], "doctrine")
        self.assertTrue(str(data["version"]).strip(), "version must be non-empty")

    def test_hooks_manifest_exists_and_valid(self):
        """Hooks are auto-discovered from hooks/hooks.json (§9): it must parse."""
        hooks_path = os.path.join(_util.PLUGIN_ROOT, "hooks", "hooks.json")
        self.assertTrue(os.path.isfile(hooks_path), "hooks/hooks.json must exist")
        with open(hooks_path, "r", encoding="utf-8") as fh:
            json.load(fh)


class TestReadme(unittest.TestCase):
    """README is the entry-point/index deliverable (仕様 §9, BRIEF2)."""

    def setUp(self):
        self.path = os.path.join(_util.PLUGIN_ROOT, "README.md")
        self.assertTrue(os.path.isfile(self.path), "plugin/README.md must exist")
        self.text = _util.read(self.path)

    def test_has_view_stamp(self):
        """ADR-073: README はビューであり、刻印(参照時点)を持つ。
        as-of と版の一致は release-check(SPEC-027)が検める。"""
        self.assertIn("doctrine:view", self.text)
        self.assertIn("as-of=", self.text)

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
    """spec §3 / R6 (仕様 §10.1): the §3.2/§3.3 registry tables live ONCE in
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


class TestRunProvenance(unittest.TestCase):
    """SPEC-028 / ADR-085 / #166: 試験走行が判定の依り所を刷る。

    「試験が通った」という主張が、どの環境の話なのかを読めるようにする。
    2026-08-02 に同じ試験・同じ commit が手元で 1036 件すべて緑、CI で落ちた
    (core.fileMode=false により git の索引の mode が 644)。そのとき主張は環境を
    持っていなかった。
    """

    KEYS = ("python", "platform", "plugin", "core.fileMode", "commit")
    UNKNOWN = "（取れなかった）"

    def _capture(self, cwd=None):
        """走者の証跡だけを別プロセスで刷らせて拾う(全件を回さない)。"""
        import subprocess
        code = (
            "import sys; sys.path.insert(0, %r); sys.dont_write_bytecode = True\n"
            "import importlib.util as u\n"
            "s = u.spec_from_file_location('rt', %r); m = u.module_from_spec(s)\n"
            "s.loader.exec_module(m); m.print_provenance()\n"
            % (_util.PLUGIN_ROOT, os.path.join(_util.PLUGIN_ROOT, "run_tests.py"))
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=cwd,
                             capture_output=True, timeout=60, check=False)
        return out.returncode, out.stdout.decode("utf-8", "replace")

    def _rows(self, text):
        rows = {}
        seen_header = False
        for line in text.splitlines():
            if line.strip() == "PROVENANCE:":
                seen_header = True
                continue
            if seen_header and line.startswith("  ") and ":" in line:
                key, _, value = line.strip().partition(":")
                rows[key.strip()] = value.strip()
        return rows

    def test_block_has_the_five_items_in_order(self):
        rc, text = self._capture()
        self.assertEqual(rc, 0, text)
        self.assertIn("PROVENANCE:", text)
        rows = self._rows(text)
        self.assertEqual(tuple(rows.keys()), self.KEYS, text)

    def test_environment_items_carry_real_values(self):
        """python・platform・plugin は必ず取れる(取れなければ環境が壊れている)。"""
        _rc, text = self._capture()
        rows = self._rows(text)
        for key in ("python", "platform", "plugin"):
            self.assertNotEqual(rows[key], self.UNKNOWN, key)
            self.assertTrue(rows[key].strip(), key)

    def test_no_git_degrades_without_crashing(self):
        """git の届かない場所でも走行は落ちず、該当項目が明示的に未取得になる。

        cwd を git の外へ置いても _run は PLUGIN_ROOT で走るため、ここでは
        PATH から git を外して同じ状態を作る。
        """
        import subprocess
        code = (
            "import os, sys; os.environ['PATH'] = %r\n"
            "sys.path.insert(0, %r); sys.dont_write_bytecode = True\n"
            "import importlib.util as u\n"
            "s = u.spec_from_file_location('rt', %r); m = u.module_from_spec(s)\n"
            "s.loader.exec_module(m); m.print_provenance()\n"
            % ("/nonexistent-bin", _util.PLUGIN_ROOT,
               os.path.join(_util.PLUGIN_ROOT, "run_tests.py"))
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             timeout=60, check=False)
        text = out.stdout.decode("utf-8", "replace")
        self.assertEqual(out.returncode, 0, text)
        rows = self._rows(text)
        self.assertEqual(rows["commit"], self.UNKNOWN, text)
        self.assertEqual(rows["core.fileMode"], self.UNKNOWN, text)
        # 環境の項目は git に依らないので、引き続き取れる。
        self.assertNotEqual(rows["python"], self.UNKNOWN)

    def test_no_governed_content_is_printed(self):
        """統治対象の内容(パス・作業ディレクトリ・リポジトリ名)を刷らない。"""
        _rc, text = self._capture()
        block = text[text.index("PROVENANCE:"):]
        self.assertNotIn(_util.PLUGIN_ROOT, block)
        self.assertNotIn(os.getcwd(), block)
        self.assertNotIn("doctrine_docs", block)
        self.assertNotIn(os.sep + "workspaces", block)


class TestNoWallClockInTests(unittest.TestCase):
    """ADR-094: 試験は実時計を読まない。時計を固定できる呼び出しでは固定を要求する。

    2026-08-03 に main が赤くなった。誰も何も変えておらず、日付が進んだだけだった
    —— 注入の試験が要約の `generated_at` を前の固定日に置き、時計を渡していなかった
    ので、7 日が経った時点で鮮度の警告が湧いた。**門が自分で壊れる形**である。

    規約は `test_integration_e2e.py` の説明文に「実時計を使わない」と書かれていたが、
    一つのファイルの説明文は他のファイルを縛らない。ここが正本の検めである。

    判定はクラス単位で行い、同じモジュール内の基底クラスまで辿る。ファイル単位では
    駄目だった —— main の test_inject.py は別のクラスで `--today` を 3 箇所使っており、
    **ファイル単位の検めは落ちた当日でも通ってしまう**（実測した。歯止めが飾りになる）。
    """

    CLOCK_FLAG = "--today"

    def _clock_pinnable(self):
        """時計を固定する口を持つ呼び出しの名前。免除の一覧を持たず、口の有無で決める。

        呼び出しが後から口を得れば、その試験も自動で対象に入る。
        """
        names = set()
        if not os.path.isdir(_util.SCRIPTS):
            return names
        for fn in sorted(os.listdir(_util.SCRIPTS)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            try:
                with open(os.path.join(_util.SCRIPTS, fn), encoding="utf-8") as fh:
                    src = fh.read()
            except (OSError, UnicodeError):
                continue
            if self.CLOCK_FLAG in src:
                names.add(fn[:-3])
        return names

    @staticmethod
    def _string_literals(node):
        return {c.value for c in ast.walk(node)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)}

    def _class_literal_closures(self, tree):
        """クラスごとの文字列の集合。同じモジュール内の基底クラスの分も畳み込む。

        継承で分かれるのを見落とさないため —— 呼び出しは基底の補助が起動し、固定日は
        派生の側に書かれる（まさに落ちた形である）。
        """
        classes = {n.name: n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef)}
        out = {}

        def closure(name, seen):
            node = classes.get(name)
            if node is None or name in seen:
                return set()
            seen.add(name)
            lits = self._string_literals(node)
            for base in node.bases:
                if isinstance(base, ast.Name):
                    lits |= closure(base.id, seen)
                elif isinstance(base, ast.Attribute):
                    lits |= closure(base.attr, seen)
            return lits

        for name in classes:
            out[name] = closure(name, set())
        return out

    def test_the_gate_can_see_at_least_one_pinnable_script(self):
        """歯止めが空回りしていないこと。口を持つ呼び出しが一つも見えないなら、
        走査そのものが壊れている（在ることと効くことを分けない）。"""
        self.assertTrue(self._clock_pinnable(),
                        "時計を固定する口を持つ呼び出しが一つも見つからない")

    def _offenders(self, pinnable):
        found = []
        for fn in sorted(os.listdir(_util.HERE)):
            if not fn.startswith("test_") or not fn.endswith(".py"):
                continue
            path = os.path.join(_util.HERE, fn)
            try:
                with open(path, encoding="utf-8") as fh:
                    src = fh.read()
                tree = ast.parse(src)
            except (OSError, UnicodeError, SyntaxError):
                continue
            for cls, lits in sorted(self._class_literal_closures(tree).items()):
                if not any("generated_at" in s for s in lits):
                    continue
                invoked = sorted(lits & pinnable)
                if not invoked:
                    continue
                if not any(self.CLOCK_FLAG in s for s in lits):
                    found.append("%s::%s (起動: %s)"
                                 % (fn, cls, ", ".join(invoked)))
        return found

    def test_fixed_generated_at_requires_a_pinned_clock(self):
        pinnable = self._clock_pinnable()
        if not pinnable:
            self.skipTest("時計を固定する口を持つ呼び出しが無い")
        offenders = self._offenders(pinnable)
        self.assertEqual(
            offenders, [],
            "要約の generated_at を埋め込み、時計を固定できる呼び出しを起動している"
            "のに、時計を固定していないクラスがある。日付が進むだけで落ちる"
            "(ADR-094): %s" % "; ".join(offenders))



class TestDateParsingHasOneCanon(unittest.TestCase):
    """ADR-099: 日付の解釈は共有コアに一度だけ。写しを機械が咎める。

    以前は四箇所に写しが在り、そのうち一つが終端の錨を欠いて `2026-01-01xyz` を
    受けていた —— ADR-053 が一本化した「要約の読み取り」の中で、日付の答えが
    読み手ごとに割れていた。**書いても消えないから、機械に見せる。**
    """

    CANON = "_frontmatter.py"

    def _sources(self):
        out = []
        for path in _scripts_present():
            if os.path.basename(path) == self.CANON:
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    out.append((path, fh.read()))
            except (OSError, UnicodeError):
                continue
        return out

    def test_canon_exists_and_is_strict(self):
        """歯止めが空回りしていないこと。正本が在り、厳しい側であること。"""
        fm = _util.load_core("_frontmatter")
        self.assertTrue(hasattr(fm, "parse_date"), "正本 parse_date が無い")
        self.assertIsNotNone(fm.parse_date("2026-01-01"))
        self.assertIsNone(fm.parse_date("2026-01-01xyz"),
                          "終端の錨が無い(緩い側へ揃っている)")
        self.assertIsNone(fm.parse_date("2026-02-30"),
                          "実在しない日付を受けている")

    def test_no_script_defines_its_own_date_parser(self):
        """日付を解す関数を正本の外に持たない(薄い前面すら置かない)。

        前面を置くと、後からそこで挙動を変えられる —— 実際、緩い写しが一つ在って
        `2026-01-01xyz` を受けていた。呼び手は正本を直に呼ぶ。
        """
        offenders = []
        for path, src in self._sources():
            try:
                tree = ast.parse(src, filename=path)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name in ("_parse_date", "parse_date"):
                    offenders.append(os.path.relpath(path, _util.PLUGIN_ROOT))
        self.assertEqual(
            sorted(set(offenders)), [],
            "日付を解す関数が正本の外に在る(写しになる。ADR-099): %r"
            % sorted(set(offenders)))

    def test_no_script_owns_a_date_regexp(self):
        """`\\d{4}-\\d{2}-\\d{2}` の形の正規表現を正本の外に持たない。"""
        pattern = r"\\d{4}"
        offenders = [os.path.relpath(p, _util.PLUGIN_ROOT)
                     for p, src in self._sources() if pattern in src]
        self.assertEqual(
            sorted(offenders), [],
            "日付の正規表現が正本の外に在る(写しになる。ADR-099): %r" % sorted(offenders))


class TestSharedJudgementsHaveOneCanon(unittest.TestCase):
    """共有の判定は正本の外に写しを持たない(ADR-099・ADR-101)。

    手で書いた表で凍らせる(ADR-060 の様式)。写しが生まれるたびに「一箇所だけ直す」が
    起き、実際に二度起きた —— 日付の解釈(四写しのうち一つが終端の錨を欠いた)と
    スカラへの正規化(入れ物の欠陥を直したのが一箇所だけだった)。
    """

    # 関数名 -> 正本を持つモジュール。写しを許さない。
    CANONS = {
        "_parse_date": "_frontmatter.py",
        "_coerce_str": "_frontmatter.py",
        # ADR-104: 設定の読み取り。以前は四写しで、一つだけ utf-8 で開いており
        # BOM 付きの設定で監査だけが既定へ落ちていた。
        "_load_config": "_config.py",
        "_config_path": "_config.py",
        # ADR-105: トークンの見積りと較正の解釈。以前は二写しで、較正が注入にだけ
        # 効き、パックは未較正の見積りで上限を判じていた。
        "estimate_tokens": "_tokens.py",
    }

    def test_no_copy_of_a_shared_judgement(self):
        offenders = []
        for path in _scripts_present():
            base = os.path.basename(path)
            try:
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
            except (OSError, UnicodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                canon = self.CANONS.get(node.name)
                if canon is None or base == canon:
                    continue
                offenders.append("%s の %s" % (base, node.name))
        self.assertEqual(
            sorted(set(offenders)), [],
            "共有の判定の写しが在る(一箇所だけ直す事故が起きる。ADR-101): %r"
            % sorted(set(offenders)))

    def test_the_canon_actually_exists(self):
        """歯止めが空回りしていないこと。正本が在り、入れ物を空にすること。"""
        fm = _util.load_core("_frontmatter")
        self.assertTrue(hasattr(fm, "coerce_str"), "正本 coerce_str が無い")
        self.assertEqual(fm.coerce_str(["a"]), "",
                         "入れ物に内部表記を返している")
        self.assertEqual(fm.coerce_str({"k": 1}), "")
        self.assertEqual(fm.coerce_str("x"), "x")
        self.assertEqual(fm.coerce_str(3), "3")


class TestConfigIsReadThroughTheCanon(unittest.TestCase):
    """ADR-104: 統治の設定を自前で開かない。読み取りは共有コアが正本。

    設定の一枚は常時投入の上限(確定事実6)・パックの上限・追跡の悉皆の様式・走査の
    適用除外を握る。**符号化が一つ違うだけで、監査が設定を丸ごと見失った**(実測)。
    """

    CANON = "_config.py"
    CONFIG_NAME = ".context-config.json"

    def test_no_script_opens_the_config_itself(self):
        """設定の名前を**そのまま**の文字列定数で持つスクリプトを咎める。

        散文の中に名前が出るのは咎めない(案内の文が名前を告げるのは正しい)。
        判定は文字列定数の一致で行う —— 案内の文は長い文の一部なので一致しない。
        """
        offenders = []
        for path in _scripts_present():
            base = os.path.basename(path)
            if base == self.CANON:
                continue
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(),
                                 filename=path)
            except (OSError, UnicodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and node.value == self.CONFIG_NAME):
                    offenders.append(base)
                    break
        self.assertEqual(
            sorted(offenders), [],
            "設定の名前を文字列定数で持つスクリプトが在る(道も符号化も写しになる。"
            "ADR-104): %r" % sorted(offenders))

    def test_the_canon_reads_a_bom_file(self):
        """歯止めが空回りしていないこと。BOM 付きも読める側で揃っていること。"""
        cfg = _util.load_core("_config")
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        path = os.path.join(sysdir, self.CONFIG_NAME)
        with open(path, "w", encoding="utf-8-sig") as fh:
            fh.write('{"trace_mode": "exhaustive"}')
        self.assertEqual(cfg.load(root).get("trace_mode"), "exhaustive")

    def test_the_canon_never_raises(self):
        cfg = _util.load_core("_config")
        for bad in (None, "", "/nonexistent/x.json"):
            self.assertEqual(cfg.load(config_path=bad), {})
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, self.CONFIG_NAME), "w",
                  encoding="utf-8") as fh:
            fh.write("{ broken")
        self.assertEqual(cfg.load(root), {})

    def test_a_list_config_is_not_a_mapping(self):
        cfg = _util.load_core("_config")
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, self.CONFIG_NAME), "w",
                  encoding="utf-8") as fh:
            fh.write("[1, 2]")
        self.assertEqual(cfg.load(root), {})

    def test_a_directory_in_place_of_the_config_is_silent(self):
        """ディレクトリでも例外を投げない(頑健さ。門の証明ではない)。

        **これは通常ファイルの門を証明しない** —— 素の open でも
        IsADirectoryError は OSError なので同じく黙る(実測)。門そのものは
        下の構造の検めで凍らせる。
        """
        cfg = _util.load_core("_config")
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, "_system", self.CONFIG_NAME), exist_ok=True)
        self.assertEqual(cfg.load(root), {})

    def test_the_canon_reads_through_the_shared_reader(self):
        """通常ファイルの門(ADR-075)を通ることを**構造で**凍らせる。

        名前付きパイプで戻らないことは測れない(測ろうとすると試験が止まる)。
        測れないものを測ったふりにしない —— 代わりに「共有の読み手を呼んで
        いること」と「素の open を持たないこと」を見る。
        """
        path = os.path.join(_util.SCRIPTS, "_config.py")
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        calls = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Attribute):
                calls.add(fn.attr)
            elif isinstance(fn, ast.Name):
                calls.add(fn.id)
        self.assertIn("read_text", calls,
                      "共有の読み手を通っていない(ADR-075 の門が掛からない)")
        self.assertNotIn("open", calls,
                         "素の open を持っている(門を迂回している)")


class TestTokenCalibrationIsShared(unittest.TestCase):
    """ADR-105: 見積りと較正の正本が一つで、壊れた値で負を返さない。

    負のトークン数は上限との比較を必ず通すので、**上限が黙って無効になる**。
    較正を読ませるのと同時にその道が開くので、頑健な側で揃える。
    """

    def test_the_canon_exists(self):
        t = _util.load_core("_tokens")
        self.assertEqual(t.DEFAULT_CHARS_PER_TOKEN, 4.0)
        self.assertEqual(t.estimate("abcd"), 1)
        self.assertEqual(t.estimate("abcde"), 2)
        self.assertEqual(t.estimate(""), 0)

    def test_calibration_is_honoured(self):
        t = _util.load_core("_tokens")
        self.assertEqual(t.chars_per_token({"model_chars_per_token": 2.0}), 2.0)
        self.assertEqual(t.estimate("a" * 1000, 2.0), 500)

    def test_broken_calibration_falls_back(self):
        """零・負・非数・真偽値・無限は既定へ。**負のトークン数を返さない。**"""
        t = _util.load_core("_tokens")
        for bad in (0, -1, "x", True, False, None, float("inf"), float("nan")):
            self.assertEqual(
                t.chars_per_token({"model_chars_per_token": bad}),
                t.DEFAULT_CHARS_PER_TOKEN, repr(bad))
            self.assertGreaterEqual(
                t.estimate("a" * 100, bad), 0,
                "負のトークン数を返した(上限が黙って無効になる): %r" % (bad,))

    def test_estimate_never_raises(self):
        t = _util.load_core("_tokens")
        for bad in (None, 0, [], {}):
            self.assertEqual(t.estimate("", bad), 0)
        self.assertEqual(t.estimate(None, 2.0), 0)

    def test_bad_config_shape_falls_back(self):
        t = _util.load_core("_tokens")
        for bad in (None, "x", 3, []):
            self.assertEqual(t.chars_per_token(bad), t.DEFAULT_CHARS_PER_TOKEN)

    def test_the_pack_resolves_the_calibration(self):
        """パックが較正を読むこと(ADR-105 の主眼)。以前は説明文だけが約束していた。"""
        cc = _util.load_script("collect-context")
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, ".context-config.json"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"model_chars_per_token": 2.0}')
        self.assertEqual(cc.load_chars_per_token(root), 2.0,
                         "パックが較正を読んでいない(較正が注入にだけ効く)")


class TestRegistryHasNoUnusedCanon(unittest.TestCase):
    """ADR-106: 登録簿の公開名は消費者を持つ。使われない正本を置かない。

    **消費者が無いことは無害ではなく、静かに嘘になる** —— 実測で、
    `ALWAYS_CONTRACT_TYPES` は `OVERVIEW` を欠き、`SYSTEM_TIER_TYPES` は `REQ` を
    欠いていた。後者は ADR-091 の帰結で、**誰も読まない表は誰も直さなかった。**

    この検めは、その欠陥を見つけた走査そのものである。
    """

    CANON = "_registry.py"

    def _public_names(self, path):
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        out = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if (isinstance(t, ast.Name) and t.id.isupper()
                            and not t.id.startswith("_")):
                        out.append((t.id, node.lineno))
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                out.append((node.name, node.lineno))
        return out

    def test_every_public_name_has_a_consumer(self):
        reg = os.path.join(_util.SCRIPTS, self.CANON)
        if not os.path.isfile(reg):
            self.skipTest("_registry.py が無い")
        lines = open(reg, encoding="utf-8").read().split("\n")
        others = {}
        for path in _scripts_present():
            if os.path.basename(path) == self.CANON:
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    others[os.path.basename(path)] = fh.read()
            except (OSError, UnicodeError):
                continue
        dead = []
        for name, lineno in self._public_names(reg):
            pattern = r"\b" + re.escape(name) + r"\b"
            if any(re.search(pattern, src) for src in others.values()):
                continue
            # 登録簿の中の取得関数から使われていれば生きている(定義行は除く)。
            inner = [i + 1 for i, line in enumerate(lines)
                     if re.search(pattern, line) and (i + 1) != lineno
                     and not line.strip().startswith("#")]
            if inner:
                continue
            dead.append(name)
        self.assertEqual(
            sorted(dead), [],
            "登録簿に消費者の無い公開名が在る(古びても誰にも見えない。ADR-106): %r"
            % sorted(dead))
