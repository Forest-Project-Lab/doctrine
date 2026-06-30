#!/usr/bin/env python3
"""Unit tests for scripts/inject-contract.py — SessionStart minimal contract (R5).

Encodes the slice-06 / MASTER §5.4 obligations and the 10-scenarios cases that
target inject-contract:
  - TC-101/TC-102 (R5): never-group (RESEARCH/ARCHIVE, llm_context:never) is NOT
    injected; no full bodies of any doc leak.
  - TC-043/TC-124 (R5): a deprecated doc's body is excluded; its paired DECIDED
    fact (current) is retained.
  - TC-103/TC-104/TC-105 (R5): injection cap is a hard ceiling; over-cap emits the
    docs-curate prompt; trimmed size respects the cap.
  - TC-106/TC-107/TC-108 (R5): recap (要点復唱) present at head; important docs
    at HEAD and TAIL both.
  - TC-135 (R5, limit): cap is enforced but the optimal value is operational.
Plus the MASTER §10.5 critique gap: the audit-summary handshake — inject-contract
reads ${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json (docs-audit/1 schema) and
summarizes it; missing -> 「前回監査なし」.

Top-of-file harness import per BRIEF2.
"""
import json
import math
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402


# --- shared frontmatter builders ------------------------------------------

def _decided(doc_id, title, updated="2026-06-01", review_by="2026-12-01",
             superseded_by=None, status="current", llm_context=None, body=""):
    fm = {
        "id": doc_id, "title": title, "type": "DECIDED", "domain": "_system",
        "status": status, "owner": "team", "updated": updated,
        "review_by": review_by, "sources": [],
    }
    if superseded_by:
        fm["superseded_by"] = superseded_by
    if llm_context:
        fm["llm_context"] = llm_context
    return _util.fm_block(fm) + (body or ("本文: %s の詳細。" % title))


def _nongoal(doc_id, title, body=""):
    fm = {
        "id": doc_id, "title": title, "type": "NONGOAL", "domain": "_system",
        "status": "current", "owner": "team", "updated": "2026-05-01",
        "sources": [],
    }
    return _util.fm_block(fm) + (body or ("本文: %s をしない理由。" % title))


def _watch(doc_id, title, review_by="2026-03-01", body=""):
    fm = {
        "id": doc_id, "title": title, "type": "WATCH", "domain": "_system",
        "status": "current", "owner": "team", "updated": "2026-04-01",
        "review_by": review_by, "sources": [],
    }
    return _util.fm_block(fm) + (body or ("本文: %s を戻さない根拠。" % title))


def _glossary(doc_id="GLOSSARY-001", body="承認語の意味の一行。"):
    fm = {
        "id": doc_id, "title": "用語集", "type": "GLOSSARY", "domain": "_system",
        "status": "current", "owner": "team", "updated": "2026-01-01",
        "sources": [],
    }
    return _util.fm_block(fm) + body


def _research(doc_id="RESEARCH-001", marker="SECRET_RESEARCH_BODY"):
    fm = {
        "id": doc_id, "title": "調査メモ", "type": "RESEARCH", "domain": "billing",
        "status": "draft", "owner": "team", "updated": "2026-02-01",
        "sources": [],
    }
    return _util.fm_block(fm) + ("%s この本文は never 群なので注入禁止。" % marker)


def _archive(doc_id="ARCHIVE-001", marker="SECRET_ARCHIVE_BODY"):
    fm = {
        "id": doc_id, "title": "旧資料", "type": "ARCHIVE", "domain": "billing",
        "status": "archived", "owner": "team", "updated": "2025-01-01",
        "sources": [],
    }
    return _util.fm_block(fm) + ("%s この本文は never 群なので注入禁止。" % marker)


def _deprecated_spec(doc_id="SPEC-900", marker="SECRET_DEPRECATED_SPEC_BODY"):
    fm = {
        "id": doc_id, "title": "旧仕様", "type": "SPEC", "domain": "billing",
        "status": "deprecated", "owner": "team", "updated": "2025-06-01",
        "superseded_by": "SPEC-901", "sources": [],
    }
    return _util.fm_block(fm) + ("%s 旧仕様の本文。注入禁止。" % marker)


class InjectBase(unittest.TestCase):
    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _run_json(self, docs_root, extra=None):
        argv = ["--docs-root", docs_root]
        if extra:
            argv += extra
        out, code = _util.invoke(
            "inject-contract", argv,
            stdin_obj=_util.hook_stdin("SessionStart", source="startup"))
        self.assertEqual(code, 0, "exit must be 0 (must not abort session)")
        data = json.loads(out)
        return data

    def _ctx(self, data):
        hso = data["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "SessionStart")
        return hso["additionalContext"]


class TestSessionStartShape(InjectBase):
    """TC-101 baseline: output is a valid SessionStart additionalContext JSON,
    exit 0 always."""

    def test_valid_session_start_json(self):
        root = self._repo({"docs/_system/decided-facts.md":
                           _decided("DECIDED-001", "返金は当日のみ")})
        docs_root = os.path.join(root, "docs")
        data = self._run_json(docs_root)
        self.assertIn("hookSpecificOutput", data)
        self.assertIsInstance(self._ctx(data), str)

    def test_stdin_ignored_and_exit_zero(self):
        root = self._repo({"docs/_system/decided-facts.md":
                           _decided("DECIDED-001", "確定A")})
        docs_root = os.path.join(root, "docs")
        # Garbage stdin must still yield exit 0 / valid JSON.
        out, code = _util.invoke("inject-contract", ["--docs-root", docs_root],
                                 stdin_obj="not json at all {{{")
        self.assertEqual(code, 0)
        json.loads(out)  # parses


class TestNeverGroupExcluded(InjectBase):
    """TC-101 / TC-102 (R5): never群 (RESEARCH/ARCHIVE, llm_context:never) and
    full bodies of any doc are never injected."""

    def test_research_archive_bodies_absent(self):
        root = self._repo({
            "docs/_system/decided-facts.md": _decided("DECIDED-001", "確定A"),
            "docs/billing/research/RESEARCH-001-foo.md": _research(),
            "docs/billing/archive/ARCHIVE-001-bar.md": _archive(),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        self.assertNotIn("SECRET_RESEARCH_BODY", ctx, "RESEARCH body leaked (R5)")
        self.assertNotIn("SECRET_ARCHIVE_BODY", ctx, "ARCHIVE body leaked (R5)")
        # The never-group ids themselves must not appear as injected facts.
        self.assertNotIn("RESEARCH-001", ctx)
        self.assertNotIn("ARCHIVE-001", ctx)

    def test_explicit_never_override_excluded(self):
        # A DECIDED forced to llm_context:never must not be injected.
        root = self._repo({
            "docs/_system/decided-facts.md":
                _decided("DECIDED-077", "隠す確定", llm_context="never",
                         body="HIDE_THIS_DECIDED_BODY"),
            "docs/_system/d2.md": _decided("DECIDED-002", "出す確定"),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        self.assertNotIn("HIDE_THIS_DECIDED_BODY", ctx)
        self.assertNotIn("DECIDED-077", ctx)
        self.assertIn("DECIDED-002", ctx)

    def test_no_full_bodies_only_headlines(self):
        # A DECIDED with a long multi-line body: only headline/fact lines appear,
        # never the full body text.
        long_body = ("# 見出し\n"
                     "本文の一行目は事実。\n"
                     "BODY_LINE_TWO_MUST_NOT_APPEAR\n"
                     "BODY_LINE_THREE_MUST_NOT_APPEAR\n")
        root = self._repo({
            "docs/_system/decided-facts.md":
                _decided("DECIDED-001", "返金は当日のみ", body=long_body),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        self.assertNotIn("BODY_LINE_TWO_MUST_NOT_APPEAR", ctx)
        self.assertNotIn("BODY_LINE_THREE_MUST_NOT_APPEAR", ctx)
        # The title/headline is present.
        self.assertIn("返金は当日のみ", ctx)


class TestDeprecatedFacts(InjectBase):
    """TC-043 / TC-124 (R5): a deprecated doc's body is excluded; its paired
    DECIDED fact (current, carrying superseded_by) is retained as fact-only."""

    def test_deprecated_body_excluded_decided_fact_kept(self):
        root = self._repo({
            # paired DECIDED fact recording the supersession (current).
            "docs/_system/decided-facts.md":
                _decided("DECIDED-050", "旧方式は撤回し新方式へ統合",
                         superseded_by="SPEC-901"),
            # the deprecated SPEC whose body must NOT be injected.
            "docs/billing/spec/SPEC-900-old.md": _deprecated_spec(),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        self.assertNotIn("SECRET_DEPRECATED_SPEC_BODY", ctx,
                         "deprecated SPEC body leaked (§3.8 step2 violated)")
        # The paired DECIDED fact is present (fact-only residue).
        self.assertIn("DECIDED-050", ctx)
        self.assertIn("旧方式は撤回し新方式へ統合", ctx)
        # It appears under the deprecated-facts section marker.
        self.assertIn("廃止事実", ctx)

    def test_superseded_decided_rendered_exactly_once(self):
        # Finding #18: a current DECIDED carrying superseded_by must be rendered
        # ONCE across the whole contract — only under 廃止事実, never duplicated in
        # the plain DECIDED section (nor double-counted against the cap).
        root = self._repo({
            "docs/_system/decided-facts.md":
                _decided("DECIDED-050", "旧方式は撤回し新方式へ統合",
                         superseded_by="SPEC-901"),
            "docs/_system/d2.md": _decided("DECIDED-002", "現行の確定事実"),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        # The superseded DECIDED's id headline appears exactly once.
        self.assertEqual(ctx.count("〔DECIDED-050〕"), 1,
                         "superseded DECIDED duplicated across the contract (#18)")
        # It lives under 廃止事実, not the plain 確定事実（現行 DECIDED） section.
        dep_pos = ctx.index("廃止事実")
        self.assertGreater(ctx.index("〔DECIDED-050〕"), dep_pos,
                           "superseded DECIDED must render under 廃止事実 only")
        # The non-superseded DECIDED still shows in the plain DECIDED section.
        self.assertIn("DECIDED-002", ctx)


class TestRecapPresence(InjectBase):
    """TC-106 / TC-107 (R5): injection begins with a recap (要点復唱) block."""

    def test_recap_at_head(self):
        root = self._repo({
            "docs/_system/decided-facts.md": _decided("DECIDED-001", "確定A"),
            "docs/_system/non-goals.md": _nongoal("NONGOAL-001", "やらないB"),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        # Recap must be at the very head, before any other section.
        self.assertTrue(ctx.lstrip().startswith("## セッション開始（要点復唱）"),
                        "recap must lead the injection (§3.9)")
        self.assertIn("復唱", ctx)
        # Recap precedes the audit summary section.
        self.assertLess(ctx.index("要点復唱"), ctx.index("前回監査"))


class TestHeadTailPlacement(InjectBase):
    """TC-108 (R5): important (pinned) docs appear at BOTH head and tail, around
    the audit-summary block."""

    def test_pinned_doc_head_and_tail(self):
        cfg = json.dumps({"head_tail_priority": ["DECIDED-001"]})
        root = self._repo({
            "docs/_system/.context-config.json": cfg,
            "docs/_system/decided-facts.md":
                _decided("DECIDED-001", "最重要の確定事実XYZ"),
            "docs/_system/d2.md": _decided("DECIDED-002", "別の確定"),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        audit_pos = ctx.index("前回監査")
        head_region = ctx[:audit_pos]
        tail_region = ctx[audit_pos:]
        # DECIDED-001 headline appears both before and after the audit block.
        self.assertIn("DECIDED-001", head_region, "pinned doc missing at HEAD")
        self.assertIn("DECIDED-001", tail_region, "pinned doc missing at TAIL")
        self.assertIn("末尾", tail_region)


class TestCapEnforcement(InjectBase):
    """TC-103 / TC-104 / TC-105 (R5): cap is a hard ceiling; over-cap (measured on
    the untrimmed render) emits the docs-curate prompt; trimmed result fits cap."""

    def _many_decided(self):
        files = {}
        for i in range(40):
            did = "DECIDED-%03d" % (i + 1)
            files["docs/_system/d%03d.md" % i] = _decided(
                did, "長い確定事実の見出し番号%02dで上限を押し上げる用の文章" % i,
                updated="2026-%02d-01" % ((i % 12) + 1))
        return files

    def test_under_cap_no_prompt(self):
        # TC-103: small corpus under cap -> no overflow notice.
        root = self._repo({
            "docs/_system/decided-facts.md": _decided("DECIDED-001", "確定A"),
        })
        ctx = self._ctx(self._run_json(os.path.join(root, "docs"),
                                       extra=["--cap", "12000"]))
        self.assertNotIn("docs-curate を起動", ctx)
        self.assertNotIn("注入上限", ctx)

    def test_over_cap_emits_curate_prompt(self):
        # TC-104: untrimmed render over a tiny cap -> overflow notice + curate.
        root = self._repo(self._many_decided())
        ctx = self._ctx(self._run_json(os.path.join(root, "docs"),
                                       extra=["--cap", "50"]))
        self.assertIn("docs-curate", ctx, "overflow must prompt docs-curate")
        self.assertIn("注入上限", ctx)
        self.assertIn("50", ctx)

    def test_cap_is_hard_ceiling_after_trim(self):
        # TC-105: even when source is far over cap, the FINAL injected size fits.
        root = self._repo(self._many_decided())
        cap = 120
        ctx = self._ctx(self._run_json(os.path.join(root, "docs"),
                                       extra=["--cap", str(cap)]))
        # estimate_tokens of the FINAL string (incl. the overflow notice) <= cap.
        mod = _util.load_script("inject-contract")
        est = mod.estimate_tokens(ctx)
        self.assertLessEqual(est, cap,
                             "final injected size (%d) exceeds cap (%d)" % (est, cap))
        # The overflow notice itself is always kept.
        self.assertIn("docs-curate", ctx)

    def test_cap_from_config(self):
        # injection_token_cap in .context-config.json drives the cap (C10).
        cfg = json.dumps({"injection_token_cap": 40})
        files = self._many_decided()
        files["docs/_system/.context-config.json"] = cfg
        root = self._repo(files)
        ctx = self._ctx(self._run_json(os.path.join(root, "docs")))
        self.assertIn("docs-curate", ctx)
        self.assertIn("40", ctx)

    def test_cli_cap_overrides_config(self):
        # --cap overrides config injection_token_cap.
        cfg = json.dumps({"injection_token_cap": 40})
        files = {"docs/_system/decided-facts.md": _decided("DECIDED-001", "確定A"),
                 "docs/_system/.context-config.json": cfg}
        root = self._repo(files)
        # A huge --cap must suppress overflow even though config says 40.
        ctx = self._ctx(self._run_json(os.path.join(root, "docs"),
                                       extra=["--cap", "99999"]))
        self.assertNotIn("docs-curate を起動", ctx)


class TestTokenEstimator(unittest.TestCase):
    """TC-135 (R5, limit): the cap is enforced via a deterministic estimator;
    the optimal value is operational, but the estimator itself is pure."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        self.mod = _util.load_script("inject-contract")

    def test_estimate_deterministic_ceil(self):
        f = self.mod.estimate_tokens
        self.assertEqual(f(""), 0)
        self.assertEqual(f("abcd"), 1)            # 4/4 = 1
        self.assertEqual(f("abcde"), 2)           # ceil(5/4) = 2
        self.assertEqual(f("a" * 4000), math.ceil(4000 / 4.0))
        # Pure: same input -> same output.
        self.assertEqual(f("同じ入力"), f("同じ入力"))


class TestAuditHandshake(InjectBase):
    """MASTER §10.5 / C3 gap: inject-contract reads the previous-audit summary at
    ${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json (docs-audit/1) and summarizes it;
    missing -> 「前回監査なし」. Round-trip with a docs-audit/1 artifact."""

    def _audit_obj(self):
        return {
            "schema": "docs-audit/1",
            "generated_at": "2026-06-28T00:00:00Z",
            "today": "2026-06-28",
            "root": "docs",
            "totals": {"error": 2, "warn": 3, "advisory": 1},
            "counts_by_check": {"dead_link": 2, "stale_draft": 3},
            "top_findings": [
                {"check": "dead_link", "severity": "error", "doc_id": "SPEC-014",
                 "path": "billing/spec/SPEC-014.md",
                 "message": "depends_on SPEC-99 が解決しない", "refs": ["SPEC-99"]},
                {"check": "review_by_overrun", "severity": "warn",
                 "doc_id": "DECIDED-003", "path": "_system/decided-facts.md",
                 "message": "review_by 超過", "refs": []},
            ],
            "findings": [],
        }

    def test_summary_from_plugin_root_cache(self):
        # Write the audit artifact at ${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json
        # and assert inject-contract summarizes it.
        plugin_root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, plugin_root, ignore_errors=True)
        cache_dir = os.path.join(plugin_root, ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "last-audit.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(self._audit_obj(), fh, ensure_ascii=False)

        root = self._repo({"docs/_system/decided-facts.md":
                           _decided("DECIDED-001", "確定A")})
        docs_root = os.path.join(root, "docs")

        old = os.environ.get("CLAUDE_PLUGIN_ROOT")
        os.environ["CLAUDE_PLUGIN_ROOT"] = plugin_root
        try:
            data = self._run_json(docs_root)
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old

        ctx = self._ctx(data)
        # Totals are summarized.
        self.assertIn("error 2", ctx)
        self.assertIn("warn 3", ctx)
        # A top finding's check/doc surfaces, but NOT a full body.
        self.assertIn("dead_link", ctx)
        self.assertIn("SPEC-014", ctx)
        self.assertNotIn("前回監査なし", ctx)

    def test_summary_fallback_claude_cache(self):
        # No CLAUDE_PLUGIN_ROOT -> fallback to <proj>/.claude/.cache/last-audit.json.
        proj = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, proj, ignore_errors=True)
        cache_dir = os.path.join(proj, ".claude", ".cache")
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, "last-audit.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(self._audit_obj(), fh, ensure_ascii=False)

        os.makedirs(os.path.join(proj, "docs", "_system"), exist_ok=True)
        with open(os.path.join(proj, "docs", "_system", "decided-facts.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(_decided("DECIDED-001", "確定A"))
        docs_root = os.path.join(proj, "docs")

        old_pr = os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        old_pd = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        try:
            data = self._run_json(docs_root)
        finally:
            if old_pr is not None:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old_pr
            if old_pd is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_pd

        ctx = self._ctx(data)
        self.assertIn("error 2", ctx)
        self.assertNotIn("前回監査なし", ctx)

    def test_missing_audit_says_none(self):
        # No artifact anywhere -> 「前回監査なし」, never an error.
        root = self._repo({"docs/_system/decided-facts.md":
                           _decided("DECIDED-001", "確定A")})
        docs_root = os.path.join(root, "docs")
        old_pr = os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        old_pd = os.environ.pop("CLAUDE_PROJECT_DIR", None)
        # Point cwd-based fallback somewhere empty.
        old_cwd = os.getcwd()
        empty = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        os.chdir(empty)
        try:
            data = self._run_json(docs_root)
        finally:
            os.chdir(old_cwd)
            if old_pr is not None:
                os.environ["CLAUDE_PLUGIN_ROOT"] = old_pr
            if old_pd is not None:
                os.environ["CLAUDE_PROJECT_DIR"] = old_pd
        ctx = self._ctx(data)
        self.assertIn("前回監査なし", ctx)


class TestResilience(InjectBase):
    """T-IC-9 / §1.10: a malformed doc is skipped; exit 0 with valid JSON. No
    _system at all -> bootstrap notice (never empty)."""

    def test_malformed_doc_skipped(self):
        root = self._repo({
            "docs/_system/decided-facts.md": _decided("DECIDED-001", "良い確定"),
            # frontmatter never closes — parser returns body="" + error; no id.
            "docs/_system/broken.md": "---\nid: DECIDED-009\ntitle: 壊れ\n",
        })
        data = self._run_json(os.path.join(root, "docs"))
        ctx = self._ctx(data)
        self.assertIn("DECIDED-001", ctx)

    def test_no_system_bootstrap_notice(self):
        root = self._repo({"README.md": "no docs here"})
        docs_root = os.path.join(root, "docs")  # does not exist
        data = self._run_json(docs_root)
        ctx = self._ctx(data)
        self.assertNotEqual(ctx.strip(), "")
        self.assertIn("docs-system-init", ctx)


class TestStdlibOnly(unittest.TestCase):
    """T-SH-1: the script imports only stdlib + the underscore cores."""

    def test_no_third_party_imports(self):
        path = os.path.join(_util.SCRIPTS, "inject-contract.py")
        src = _util.read(path)
        for bad in ("import yaml", "import requests", "from yaml",
                    "import numpy", "import pytest"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
