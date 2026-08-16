# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""外部読み口の封筒の試験(ADR-152〜ADR-159 / #294 の受け)。

- 三鍵(source_revision・source_dirty・generator)が宣言済みの読み口すべてに載る。
- 値は git の三態(clean・dirty・git 無し)で決定的に変わる。実時計は読まない。
- dep-graph の --find-root、scaffold の --list-sections、map-draft-check の
  複数リポジトリ受け(--repo 接頭=経路)を凍らせる。
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

sys.path.insert(0, _util.SCRIPTS if hasattr(_util, "SCRIPTS") else
                os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "scripts"))
import _registry  # noqa: E402
import _revinfo  # noqa: E402

GIT = shutil.which("git")
TODAY = "2026-08-13"


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, "-c", "user.email=t@example.com",
         "-c", "user.name=t"] + list(args),
        capture_output=True, text=True, timeout=30)


def _make_git_repo(files):
    root = _util.make_repo(files)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


class RevinfoTest(unittest.TestCase):
    def test_non_git_dir_is_null_null(self):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        got = _revinfo.revision_of(root)
        self.assertIsNone(got["source_revision"])
        self.assertIsNone(got["source_dirty"])

    def test_missing_dir_is_null_null(self):
        got = _revinfo.revision_of("/no/such/dir")
        self.assertIsNone(got["source_revision"])
        self.assertIsNone(got["source_dirty"])

    @unittest.skipUnless(GIT, "git が無い環境では三態を検められない")
    def test_clean_then_dirty(self):
        root = _make_git_repo({"a.txt": "hello\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        got = _revinfo.revision_of(root)
        self.assertRegex(got["source_revision"], r"^[0-9a-f]{40}$")
        self.assertFalse(got["source_dirty"])
        with open(os.path.join(root, "b.txt"), "w", encoding="utf-8") as fh:
            fh.write("dirty\n")
        got2 = _revinfo.revision_of(root)
        # dirty でも SHA は書く(嘘をつかず、印を添える。ADR-155)。
        self.assertEqual(got2["source_revision"], got["source_revision"])
        self.assertTrue(got2["source_dirty"])

    def test_generator_info_shape(self):
        gen = _revinfo.generator_info("x.py")
        self.assertEqual(gen["name"], "x.py")
        self.assertTrue(gen["version"] is None or
                        isinstance(gen["version"], str))


def _docs_tree():
    fm = ("---\nid: SPEC-01\ntitle: t\ntype: SPEC\ndomain: billing\n"
          "status: current\nowner: o\nupdated: 2026-08-01\nsources: []\n---\n\n# t\n")
    root = _util.make_repo({"docs/_system/glossary.md": "# 用語\n",
                            "docs/billing/spec/SPEC-01-t.md": fm})
    return root


class DepGraphEnvelopeTest(unittest.TestCase):
    def test_json_envelope_keys_and_result_duplication(self):
        root = _docs_tree()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "dep-graph", argv=["--root", os.path.join(root, "docs"),
                               "--classify-edges", "--json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["schema"], "dep-graph/1")
        self.assertEqual(d["root"], "docs")
        self.assertNotIn(os.sep, d["root"])
        # 非 git の木では null/null(「分からない」を欄の省略にしない)。
        self.assertIsNone(d["source_revision"])
        self.assertIsNone(d["source_dirty"])
        self.assertEqual(d["generator"]["name"], "dep-graph.py")
        self.assertEqual(d["mode"], "classify-edges")
        # result は edges と同じ内容の重複(互換のため残す。ADR-153)。
        self.assertEqual(d["result"], d["edges"])

    def test_usage_error_keeps_stdout_clean(self):
        out, code = _util.invoke("dep-graph", argv=["--bogus"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")  # 診断は標準エラーへ(ADR-153)

    def test_root_not_found_keeps_stdout_clean(self):
        out, code = _util.invoke(
            "dep-graph", argv=["--root", "/no/such/docs", "--classify-edges",
                               "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(out, "")

    def test_find_root_found(self):
        root = _util.make_repo({"doctrine_docs/_system/glossary.md": "# 用語\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        start = os.path.join(root, "sub", "dir")
        os.makedirs(start)
        out, code = _util.invoke(
            "dep-graph", argv=["--find-root", start, "--json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["mode"], "find-root")
        self.assertTrue(os.path.isabs(d["result"]))
        self.assertEqual(os.path.basename(d["result"]), "doctrine_docs")
        self.assertEqual(d["root"], "doctrine_docs")
        self.assertEqual(d["nodes"], [])
        self.assertEqual(d["edges"], [])

    def test_find_root_not_found_exit_3_result_null(self):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "dep-graph", argv=["--find-root", root, "--json"])
        self.assertEqual(code, 3)
        d = json.loads(out)
        self.assertIsNone(d["result"])
        self.assertIsNone(d["root"])

    def test_find_root_text_mode_prints_path_only(self):
        root = _util.make_repo({"doctrine_docs/_system/glossary.md": "# 用語\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke("dep-graph", argv=["--find-root", root])
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().endswith("doctrine_docs"))


class TraceIndexEnvelopeTest(unittest.TestCase):
    def test_json_envelope_keys(self):
        root = _docs_tree()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "trace-index", argv=["--root", root, "--docs-root",
                                 os.path.join(root, "docs"),
                                 "--format", "json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["schema"], "trace-index/1")
        self.assertIn("source_revision", d)
        self.assertIn("source_dirty", d)
        self.assertEqual(d["generator"]["name"], "trace-index.py")
        self.assertIsNone(d["source_revision"])

    def test_coverage_envelope_keys(self):
        root = _docs_tree()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "trace-index", argv=["--root", root, "--docs-root",
                                 os.path.join(root, "docs"),
                                 "--coverage", "--format", "json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertIn("source_revision", d)
        self.assertIn("source_dirty", d)
        self.assertIn("generator", d)
        self.assertIn("coverage", d)

    @unittest.skipUnless(GIT, "git が無い環境では版を検められない")
    def test_git_tree_names_revision(self):
        root = _make_git_repo({"docs/_system/glossary.md": "# 用語\n",
                               "src/x.py": "pass\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "trace-index", argv=["--root", root, "--docs-root",
                                 os.path.join(root, "docs"),
                                 "--format", "json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertRegex(d["source_revision"], r"^[0-9a-f]{40}$")
        self.assertFalse(d["source_dirty"])


class AuditEnvelopeTest(unittest.TestCase):
    def test_summary_envelope_keys(self):
        root = _docs_tree()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        out, code = _util.invoke(
            "docs-audit", argv=["--root", os.path.join(root, "docs"),
                                "--today", TODAY, "--json"])
        d = json.loads(out)
        self.assertEqual(d["schema"], "docs-audit/1")
        self.assertIn("source_revision", d)
        self.assertIn("source_dirty", d)
        self.assertEqual(d["generator"]["name"], "docs-audit.py")
        self.assertIsNone(d["source_revision"])
        self.assertTrue(os.path.isabs(d["root"]))


class ScaffoldListSectionsTest(unittest.TestCase):
    def test_json_matches_registry(self):
        out, code = _util.invoke("scaffold", argv=["--list-sections", "--json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["schema"], "scaffold-sections/1")
        want = {t: list(_registry.required_sections(t))
                for t in _registry.REQUIRED_SECTIONS}
        self.assertEqual(d["sections"], want)  # 写しではなく参照(ドリフト零)
        self.assertEqual(d["generator"]["name"], "scaffold.py")

    def test_single_type(self):
        out, code = _util.invoke(
            "scaffold", argv=["--list-sections", "--type", "ADR", "--json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(list(d["sections"].keys()), ["ADR"])
        self.assertEqual(d["sections"]["ADR"],
                         list(_registry.required_sections("ADR")))

    def test_lowercase_type_accepted(self):
        out, code = _util.invoke(
            "scaffold", argv=["--list-sections", "--type", "adr", "--json"])
        self.assertEqual(code, 0)

    def test_unknown_type_exit_2(self):
        out, code = _util.invoke(
            "scaffold", argv=["--list-sections", "--type", "ZZZ"])
        self.assertEqual(code, 2)

    def test_type_without_list_sections_exit_2(self):
        out, code = _util.invoke("scaffold", argv=["--type", "ADR"])
        self.assertEqual(code, 2)

    def test_text_mode(self):
        out, code = _util.invoke("scaffold", argv=["--list-sections"])
        self.assertEqual(code, 0)
        self.assertIn("ADR:", out)


def _ms(prefix, path, locator, verdict="present"):
    return {"source": "%s: %s" % (prefix, path), "locator": locator,
            "checked_at": "2026-08-10", "verdict": verdict}


def _multi_model(src_a, src_b, anchors=None):
    return {
        "schema": "system-map/gold-model/0.2",
        "target": "fixture",
        "system": {"purpose": "p", "boundary": "b",
                   "provenance": [src_a], "review_status": "proposed"},
        "elements": [
            {"id": "e1", "name": "要素", "kind": "system", "purpose": "p",
             "responsibilities": ["r"], "owner": "o", "parent": None,
             "provenance": [src_b], "review_status": "proposed"},
        ],
        "flows": [],
        "contracts": [],
        "scenarios": [],
        "anchors": anchors or [],
    }


class MapDraftMultiRepoTest(unittest.TestCase):
    def _two_repos(self):
        repo_a = _util.make_repo({
            "doctrine_docs/_system/non-goals.md":
                "# やらないこと\n第1項 これはしない\n三行目\n"})
        self.addCleanup(shutil.rmtree, repo_a, ignore_errors=True)
        repo_b = _util.make_repo({"src/lib.py": "line-one here\nline2\n"})
        self.addCleanup(shutil.rmtree, repo_b, ignore_errors=True)
        return repo_a, repo_b

    def _write(self, obj, name="model.json"):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        return path

    def _run(self, argv):
        out, code = _util.invoke("map-draft-check", argv=argv)
        return (json.loads(out) if out.strip().startswith("{") else out), code

    def test_legacy_single_repo_sends_other_prefix_to_unverifiable(self):
        repo_a, _repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/lib.py", "「line-one」")))
        d, code = self._run(["--model", model, "--repo", repo_a,
                             "--repo-prefix", "docA", "--today", TODAY,
                             "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(d["totals"]["findings"], 0)
        self.assertEqual(d["totals"]["unverifiable"], 1)
        self.assertIn("docB", d["unverifiable"][0]["reason"])

    def test_multi_repo_resolves_both_prefixes(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/lib.py", "「line-one」")))
        d, code = self._run(["--model", model,
                             "--repo", "docA=%s" % repo_a,
                             "--repo", "docB=%s" % repo_b,
                             "--today", TODAY, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(d["totals"]["findings"], 0)
        # 二リポジトリの模型で「原理的に検証不能」が消える(ADR-158)。
        self.assertEqual(d["totals"]["unverifiable"], 0)

    def test_multi_repo_unknown_prefix_goes_to_unverifiable(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docC", "src/lib.py", "「line-one」")))
        d, code = self._run(["--model", model,
                             "--repo", "docA=%s" % repo_a,
                             "--repo", "docB=%s" % repo_b,
                             "--today", TODAY, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(d["totals"]["unverifiable"], 1)
        self.assertIn("docC", d["unverifiable"][0]["reason"])

    def test_multi_repo_missing_file_is_finding(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/nothing.py", "「line-one」")))
        d, code = self._run(["--model", model,
                             "--repo", "docA=%s" % repo_a,
                             "--repo", "docB=%s" % repo_b,
                             "--today", TODAY, "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(d["totals"]["by_code"].get("D2_SOURCE_UNRESOLVED"), 1)

    def test_duplicate_prefix_exit_2(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」")))
        _d, code = self._run(["--model", model,
                              "--repo", "docA=%s" % repo_a,
                              "--repo", "docA=%s" % repo_b, "--json"])
        self.assertEqual(code, 2)

    def test_mixed_forms_exit_2(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/lib.py", "「line-one」")))
        _d, code = self._run(["--model", model, "--repo", repo_a,
                              "--repo", "docB=%s" % repo_b, "--json"])
        self.assertEqual(code, 2)

    def test_legacy_repo_twice_exit_2(self):
        repo_a, repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/lib.py", "「line-one」")))
        _d, code = self._run(["--model", model, "--repo", repo_a,
                              "--repo", repo_b, "--json"])
        self.assertEqual(code, 2)

    def test_repo_prefix_with_new_form_exit_2(self):
        repo_a, _repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」")))
        _d, code = self._run(["--model", model,
                              "--repo", "docA=%s" % repo_a,
                              "--repo-prefix", "docA", "--json"])
        self.assertEqual(code, 2)

    def test_trace_json_prefix_requires_new_form_exit_2(self):
        repo_a, _repo_b = self._two_repos()
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」")))
        _d, code = self._run(["--model", model, "--repo", repo_a,
                              "--trace-json", "docA=/tmp/x.json", "--json"])
        self.assertEqual(code, 2)

    def test_d4_anchor_matches_per_prefix_index(self):
        repo_a, repo_b = self._two_repos()
        trace_b = self._write({
            "schema": "trace-index/1", "root": "b",
            "ranges": [{"id": "SPEC-01", "path": "src/lib.py",
                        "begin_line": 1, "end_line": 2,
                        "fingerprint": "sha256:" + "0" * 64}],
            "findings": []}, name="trace-b.json")
        anchors = [
            {"target_kind": "code_range", "authority": "doctrine",
             "target": "docB: src/lib.py", "review_status": "proposed"},
            {"target_kind": "code_range", "authority": "doctrine",
             "target": "docC: src/other.py", "review_status": "proposed"},
        ]
        model = self._write(_multi_model(
            _ms("docA", "doctrine_docs/_system/non-goals.md", "「これはしない」"),
            _ms("docB", "src/lib.py", "「line-one」"), anchors=anchors))
        d, code = self._run(["--model", model,
                             "--repo", "docA=%s" % repo_a,
                             "--repo", "docB=%s" % repo_b,
                             "--trace-json", "docB=%s" % trace_b,
                             "--trace-json", "docA=%s" % trace_b,
                             "--today", TODAY, "--json"])
        # docB のアンカーは注入した索引に合い、docC のアンカーは検証不能へ。
        self.assertEqual(code, 0)
        self.assertEqual(d["totals"]["by_code"].get("D4_ANCHOR_UNMATCHED"),
                         None)
        reasons = " / ".join(u["reason"] for u in d["unverifiable"])
        self.assertIn("接頭", reasons)


if __name__ == "__main__":
    unittest.main()
