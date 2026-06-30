"""Permanent end-to-end regression test: the REAL scripts run as Claude Code hooks.

Unlike the per-script unit tests (which import each script in-process via
`tests/_util.invoke`), this suite shells out to the actual entry scripts with
`python3 <script>`, feeds them a hook-JSON envelope on stdin, sets the runtime
env (`CLAUDE_PLUGIN_ROOT`), and runs from a temp working directory — exactly the
way Claude Code drives them at runtime (MASTER §3 hook protocol, §4 hooks.json,
§5 script contracts). It exercises the full lifecycle:

    scaffold (SessionStart-of-life) -> guards (PreToolUse) -> linter (PostToolUse)
    -> audit (SessionEnd) -> inject-contract (next SessionStart) -> term-check dogfood

and asserts concrete outputs, not just exit codes.

Determinism: `--today 2026-06-29` is passed everywhere a date matters, so audit
`generated_at`/`today` and any review_by math are fixed. No wall clock, no
network, stdlib only.

Cleanup convention follows tests/_util (the CALLER removes temp trees).
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

# Reuse the frozen harness constants/helpers (do NOT redefine them here).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402  (path set just above)


TODAY = "2026-06-29"


# ---------------------------------------------------------------------------
# Subprocess driver — the one place that shells out to a real entry script.
# ---------------------------------------------------------------------------
def run_script(script_name, argv=None, stdin_obj=None, cwd=None, plugin_root=None):
    """Run an entry script as a real subprocess and return a CompletedProcess.

    - script_name: e.g. "policy-guard.py" (resolved under plugin/scripts).
    - argv: list of CLI args after the script path.
    - stdin_obj: dict (JSON-encoded onto stdin), str (verbatim), or None (empty).
    - cwd: working directory for the child (the temp repo, per the brief).
    - plugin_root: value for CLAUDE_PLUGIN_ROOT (defaults to the real plugin).

    The child gets a clean-ish env that always carries CLAUDE_PLUGIN_ROOT, the
    way the live runtime injects it. `text=True` decodes stdout/stderr as UTF-8.
    """
    script_path = os.path.join(_util.SCRIPTS, script_name)
    cmd = [sys.executable, script_path] + list(argv or [])

    if isinstance(stdin_obj, dict):
        stdin_text = json.dumps(stdin_obj)
    elif stdin_obj is None:
        stdin_text = ""
    else:
        stdin_text = stdin_obj

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root or _util.PLUGIN_ROOT
    # Force a deterministic, ASCII-safe locale for the child's stdio so the
    # Japanese guard/linter strings round-trip regardless of host locale.
    env.setdefault("PYTHONIOENCODING", "utf-8")

    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def parse_json_stdout(proc):
    """Parse a child's stdout as JSON, with a helpful failure message."""
    out = proc.stdout.strip()
    if not out:
        raise AssertionError(
            "expected JSON on stdout, got empty (stderr=%r)" % proc.stderr)
    try:
        return json.loads(out)
    except ValueError as exc:
        raise AssertionError(
            "stdout was not JSON (%r): %r (stderr=%r)"
            % (exc, proc.stdout, proc.stderr))


def pre_decision(obj):
    """Pull permissionDecision out of a PreToolUse response."""
    return obj.get("hookSpecificOutput", {}).get("permissionDecision")


def pre_reason(obj):
    """Pull permissionDecisionReason out of a PreToolUse response."""
    return obj.get("hookSpecificOutput", {}).get("permissionDecisionReason")


# ---------------------------------------------------------------------------
# Shared corpus builders (a REAL docs/ tree under a temp root).
# ---------------------------------------------------------------------------
def build_identity_billing_corpus():
    """Create a temp repo with an identity ICD + identity internal SPEC.

    Returns the repo root (caller cleans up). The corpus is the minimal graph
    the ICD-dependency guard needs to resolve domains:
      docs/identity/ICD.md        -> ICD-100, domain=identity (cross-domain OK)
      docs/identity/spec/SPEC-200  -> SPEC-200, domain=identity (internal; a
                                       cross-domain depends_on target -> DENY)
    """
    root = _util.mkdtemp()
    _util.write_doc(
        root, "docs/identity/ICD.md",
        {
            "id": "ICD-100", "title": "identity ICD", "type": "ICD",
            "domain": "identity", "status": "current", "owner": "alice",
            "updated": "2026-06-01", "sources": [],
            "canonical_for": ["identity-boundary"],
        },
        "## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n",
    )
    _util.write_doc(
        root, "docs/identity/spec/SPEC-200-internal.md",
        {
            "id": "SPEC-200", "title": "identity internal spec", "type": "SPEC",
            "domain": "identity", "status": "current", "owner": "alice",
            "updated": "2026-06-01", "depends_on": ["REQ-1"], "sources": [],
        },
        "## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n",
    )
    return root


def write_billing_doc(domain, depends_on, doc_id="SPEC-300"):
    """Render a billing-side SPEC's full file text (Write tool_input.content)."""
    fm = {
        "id": doc_id, "title": "billing spec", "type": "SPEC",
        "domain": domain, "status": "current", "owner": "bob",
        "updated": "2026-06-01", "depends_on": depends_on, "sources": [],
    }
    body = "## 入出力\nx\n## 制約\nx\n## エラー時挙動\nx\n## 受入基準\nx\n"
    return _util.fm_block(fm) + body


# ===========================================================================
# 1. scaffold.py lifecycle (docs-system-init)
# ===========================================================================
class TestScaffoldLifecycle(unittest.TestCase):
    """scaffold.py --root TMP --level 2 — exact output set + idempotent re-run."""

    EXPECTED = {
        "docs/_system/glossary.md",
        "docs/_system/decided-facts.md",
        "docs/_system/non-goals.md",
        "docs/_system/overview.md",
        "docs/_system/.docs-level",
        "AGENTS.md",
        "CLAUDE.md",
    }

    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _all_files(self):
        found = set()
        for dirpath, _dirs, files in os.walk(self.root):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), self.root)
                found.add(rel.replace(os.sep, "/"))
        return found

    def test_creates_exactly_the_minimal_set(self):
        proc = run_script(
            "scaffold.py",
            ["--root", self.root, "--level", "2", "--today", TODAY],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        found = self._all_files()
        self.assertEqual(
            found, self.EXPECTED,
            "scaffold wrote an unexpected set: extra=%s missing=%s"
            % (found - self.EXPECTED, self.EXPECTED - found))

    def test_does_not_create_domain_or_projection_extras(self):
        run_script(
            "scaffold.py",
            ["--root", self.root, "--level", "2", "--today", TODAY],
            cwd=self.root,
        )
        # No domain folders (only _system lives under docs/).
        docs_children = set(os.listdir(os.path.join(self.root, "docs")))
        self.assertEqual(docs_children, {"_system"},
                         "scaffold created non-_system entries under docs/")
        # None of the deferred artifacts (§5.8: NOT created by scaffold).
        for forbidden in ("docs/_system/watchlist.md",
                          "docs/_system/context-map.md",
                          "docs/_system/icd-index.md",
                          "hooks/hooks.json"):
            self.assertFalse(
                os.path.exists(os.path.join(self.root, forbidden)),
                "scaffold must not create %s" % forbidden)

    def test_docs_level_marker_content(self):
        run_script(
            "scaffold.py",
            ["--root", self.root, "--level", "2", "--today", TODAY],
            cwd=self.root,
        )
        marker = _util.read(os.path.join(self.root, "docs/_system/.docs-level"))
        self.assertEqual(marker.strip(), "level: 2")

    def test_rerun_is_all_skip_and_nondestructive(self):
        # First run.
        run_script(
            "scaffold.py",
            ["--root", self.root, "--level", "2", "--today", TODAY],
            cwd=self.root,
        )
        # Tamper with one seeded file to prove it is NOT overwritten.
        glossary = os.path.join(self.root, "docs/_system/glossary.md")
        sentinel = "SENTINEL-DO-NOT-OVERWRITE\n"
        with open(glossary, "w", encoding="utf-8") as fh:
            fh.write(sentinel)
        before = self._all_files()

        # Second run: must skip everything, write nothing.
        proc = run_script(
            "scaffold.py",
            ["--root", self.root, "--level", "2", "--today", TODAY],
            cwd=self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("作成 0", proc.stdout, "re-run should create nothing")
        self.assertEqual(self._all_files(), before,
                         "re-run changed the file set")
        self.assertEqual(_util.read(glossary), sentinel,
                         "re-run overwrote a pre-existing file (destructive!)")


# ===========================================================================
# 2. policy-guard.py — ICD-dependency boundary guard (R7, PreToolUse Write)
# ===========================================================================
class TestPolicyGuardICDBoundary(unittest.TestCase):
    """PreToolUse Write cross-domain dependency decisions (MASTER §5.3 Guard2)."""

    def setUp(self):
        self.root = build_identity_billing_corpus()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _guard_write(self, content, file_relpath):
        file_path = os.path.join(self.root, file_relpath)
        stdin = _util.hook_stdin(
            "PreToolUse", tool_name="Write",
            tool_input={"file_path": file_path, "content": content},
        )
        # The hook envelope's cwd drives docs-root discovery in the child.
        stdin["cwd"] = self.root
        proc = run_script("policy-guard.py", stdin_obj=stdin, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return parse_json_stdout(proc)

    def test_cross_domain_non_icd_dep_is_denied_with_exact_message(self):
        # billing SPEC-300 depends_on the identity-internal SPEC-200 -> DENY.
        content = write_billing_doc("billing", ["SPEC-200"])
        obj = self._guard_write(
            content, "docs/billing/spec/SPEC-300-x.md")
        self.assertEqual(pre_decision(obj), "deny",
                         "cross-domain non-ICD dependency must be denied")
        self.assertEqual(
            pre_reason(obj),
            "SPEC-200 は identity の内部です。identity の ICD 宛にしてください。",
            "deny message must be the EXACT pseudo-spec string")

    def test_cross_domain_icd_dep_is_allowed(self):
        # billing SPEC-301 depends_on identity's ICD-100 -> ALLOW.
        content = write_billing_doc("billing", ["ICD-100"], doc_id="SPEC-301")
        obj = self._guard_write(
            content, "docs/billing/spec/SPEC-301-x.md")
        self.assertEqual(pre_decision(obj), "allow",
                         "a cross-domain dep on an ICD must be allowed")

    def test_intra_domain_dep_is_allowed(self):
        # identity SPEC-302 depends_on identity's own SPEC-200 -> ALLOW.
        content = write_billing_doc("identity", ["SPEC-200"], doc_id="SPEC-302")
        obj = self._guard_write(
            content, "docs/identity/spec/SPEC-302-x.md")
        self.assertEqual(pre_decision(obj), "allow",
                         "an intra-domain dependency must be allowed")


# ===========================================================================
# 3. docs-linter.py — advisory only, never a 'decision' (PostToolUse)
# ===========================================================================
class TestLinterSpecMissingSections(unittest.TestCase):
    """A SPEC missing the 4 mandatory sections -> additionalContext, no decision."""

    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # A SPEC with valid frontmatter but a body lacking 入出力/制約/エラー時挙動/受入基準.
        self.spec_path = _util.write_doc(
            self.root, "docs/billing/spec/SPEC-400-nosections.md",
            {
                "id": "SPEC-400", "title": "spec missing sections", "type": "SPEC",
                "domain": "billing", "status": "current", "owner": "bob",
                "updated": "2026-06-01", "depends_on": ["REQ-9"], "sources": [],
            },
            "本文に必須の節が一つも無い。\n",
        )

    def test_missing_sections_advisory_has_no_decision(self):
        stdin = _util.hook_stdin(
            "PostToolUse", tool_name="Write",
            tool_input={"file_path": self.spec_path},
            tool_response={"filePath": self.spec_path},
        )
        stdin["cwd"] = self.root
        proc = run_script("docs-linter.py", stdin_obj=stdin, cwd=self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        obj = parse_json_stdout(proc)

        # MASTER §3.3 / C4: the linter is pure-advisory. NEVER a decision key.
        self.assertNotIn("decision", obj,
                         "docs-linter must never emit a 'decision' key")
        hso = obj.get("hookSpecificOutput", {})
        self.assertEqual(hso.get("hookEventName"), "PostToolUse")
        ac = hso.get("additionalContext", "")
        self.assertTrue(ac, "expected a non-empty additionalContext")
        # Each of the four mandatory section names must be named as missing.
        for section in ("入出力", "制約", "エラー時挙動", "受入基準"):
            self.assertIn(
                section, ac,
                "additionalContext must mention missing section %r" % section)
        self.assertIn("SPEC_MISSING_SECTION", ac)


# ===========================================================================
# 4. docs-audit.py -> inject-contract.py handshake (C3 summary round-trip)
# ===========================================================================
class TestAuditInjectHandshake(unittest.TestCase):
    """SessionEnd audit writes docs-audit/1; next SessionStart inject reads it."""

    def setUp(self):
        self.root = build_identity_billing_corpus()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # A standalone plugin root whose .cache holds the audit summary (C3).
        self.plugin_root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.plugin_root, ignore_errors=True)
        self.cache = os.path.join(self.plugin_root, ".cache", "last-audit.json")

    def _run_audit(self):
        proc = run_script(
            "docs-audit.py",
            ["--root", "docs", "--json", "--summary-out", self.cache,
             "--fail-on", "never", "--today", TODAY],
            cwd=self.root,
            plugin_root=self.plugin_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def test_audit_writes_valid_docs_audit_1_summary(self):
        proc = self._run_audit()
        # stdout JSON and the persisted cache must both be docs-audit/1.
        stdout_summary = parse_json_stdout(proc)
        self.assertEqual(stdout_summary.get("schema"), "docs-audit/1")

        self.assertTrue(os.path.isfile(self.cache),
                        "audit must persist the summary to --summary-out")
        with open(self.cache, "r", encoding="utf-8") as fh:
            cached = json.load(fh)
        self.assertEqual(cached.get("schema"), "docs-audit/1")
        # Frozen §5.5 schema keys.
        for key in ("schema", "generated_at", "today", "root", "totals",
                    "counts_by_check", "top_findings", "findings"):
            self.assertIn(key, cached, "summary missing key %r" % key)
        self.assertEqual(cached["today"], TODAY)
        self.assertEqual(cached["generated_at"], TODAY + "T00:00:00Z",
                         "generated_at must be deterministic from --today")
        for sev in ("error", "warn", "advisory"):
            self.assertIn(sev, cached["totals"])
        # This corpus has at least one real finding (SPEC-200's dangling REQ-1).
        self.assertGreater(cached["totals"]["error"], 0,
                           "expected the seeded corpus to surface error findings")

    def test_inject_contract_includes_audit_summary_when_cache_present(self):
        self._run_audit()
        with open(self.cache, "r", encoding="utf-8") as fh:
            cached = json.load(fh)
        proc = run_script(
            "inject-contract.py",
            ["--docs-root", "docs", "--format", "text", "--today", TODAY],
            stdin_obj=_util.hook_stdin("SessionStart", source="startup"),
            cwd=self.root,
            plugin_root=self.plugin_root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout
        self.assertIn("前回監査の要約", out,
                      "inject-contract must render the previous-audit section")
        self.assertNotIn("前回監査なし", out,
                         "with a cache present it must NOT say 'no prior audit'")
        # The rendered summary must reflect the audit's real error total.
        self.assertIn("error %d" % cached["totals"]["error"], out)

    def test_inject_contract_says_no_audit_when_cache_absent(self):
        # A fresh plugin root with NO .cache/last-audit.json.
        empty_plugin = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, empty_plugin, ignore_errors=True)
        proc = run_script(
            "inject-contract.py",
            ["--docs-root", "docs", "--format", "text", "--today", TODAY],
            stdin_obj=_util.hook_stdin("SessionStart", source="startup"),
            cwd=self.root,
            plugin_root=empty_plugin,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("前回監査なし", proc.stdout,
                      "with no cache, inject-contract must say '前回監査なし'")


# ===========================================================================
# 5. term-check.py — dogfood the plugin's own prose (zero ERROR findings)
# ===========================================================================
class TestTermCheckDogfood(unittest.TestCase):
    """The plugin's own README + every SKILL.md must pass its own term checker."""

    def _target_files(self):
        files = [os.path.join(_util.PLUGIN_ROOT, "README.md")]
        skills_dir = os.path.join(_util.PLUGIN_ROOT, "skills")
        for name in sorted(os.listdir(skills_dir)):
            skill_md = os.path.join(skills_dir, name, "SKILL.md")
            if os.path.isfile(skill_md):
                files.append(skill_md)
        return files

    def test_no_error_severity_findings_in_own_docs(self):
        targets = self._target_files()
        # Sanity: we must actually be checking the README and several skills.
        self.assertTrue(any(f.endswith("README.md") for f in targets))
        self.assertGreaterEqual(
            sum(1 for f in targets if f.endswith("SKILL.md")), 5,
            "expected to dogfood several SKILL.md files")

        for path in targets:
            proc = run_script(
                "term-check.py", [path],
                cwd=_util.PLUGIN_ROOT,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # render_findings prints '  [ERROR] ...' / '  [WARN] ...' per finding.
            # ERROR-severity = BANNED_SYNONYM / CALQUE (R6/R10). WARN is allowed.
            error_lines = [ln for ln in proc.stdout.splitlines()
                           if "[ERROR]" in ln]
            self.assertEqual(
                error_lines, [],
                "term-check found ERROR-severity issue(s) in %s:\n%s"
                % (os.path.relpath(path, _util.PLUGIN_ROOT),
                   "\n".join(error_lines)))


if __name__ == "__main__":
    unittest.main()
