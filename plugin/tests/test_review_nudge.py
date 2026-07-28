# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for review-nudge.py (PostToolUse doc-review nudge).

§4.1/§4.2: doc-review runs on authoring via doc-author, and on manual edits via
this advisory PostToolUse nudge. It nudges (additionalContext) only for typed
governance documents, emits nothing for non-docs, never a decision, exit 0.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402
import shutil  # noqa: E402
import unittest  # noqa: E402

import _util  # noqa: E402

NUDGE = "review-nudge"


class ReviewNudgeBase(unittest.TestCase):
    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def _nudge(self, file_path):
        stdin = _util.hook_stdin(
            "PostToolUse", tool_name="Edit",
            tool_input={"file_path": file_path})
        return _util.invoke("review-nudge", stdin_obj=stdin)


class TestCodeTraceNudge(ReviewNudgeBase):
    """印の無いコードへの紐づけ促し(ADR-063)。追跡を使う体系でだけ、一度だけ。"""

    def setUp(self):
        super().setUp()
        for k in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT"):
            old = os.environ.get(k)
            self.addCleanup(
                (lambda key, val: (lambda: (
                    os.environ.__setitem__(key, val) if val is not None
                    else os.environ.pop(key, None))))(k, old))
        os.environ["CLAUDE_PROJECT_DIR"] = self.root
        os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
        os.makedirs(os.path.join(self.root, "doctrine_docs", "_system"),
                    exist_ok=True)

    def _put_summary(self, with_coverage=True):
        payload = {
            "schema": "docs-audit/1", "today": "2026-07-27",
            "generated_at": "2026-07-27T00:00:00Z",
            "root": os.path.join(self.root, "doctrine_docs"),
            "totals": {"error": 0, "warn": 0, "advisory": 0},
            "counts_by_check": {}, "checks_run": [], "top_findings": [],
            "findings": [],
        }
        if with_coverage:
            payload["trace_coverage"] = {"reached_files": 1}
        cache = os.path.join(self.root, ".claude", ".cache")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "last-audit.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _code(self, rel="src/app.py", body="print(1)\n"):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        return p

    def _nudge_sid(self, file_path, sid):
        stdin = _util.hook_stdin(
            "PostToolUse", tool_name="Edit",
            tool_input={"file_path": file_path})
        stdin["session_id"] = sid
        return _util.invoke("review-nudge", stdin_obj=stdin)

    def test_unmarked_code_gets_the_nudge_when_tracing_is_active(self):
        self._put_summary(with_coverage=True)
        p = self._code()
        out, code = self._nudge_sid(p, "sid-a1")
        self.assertEqual(code, 0)
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("追跡の印が無い", ctx)
        self.assertIn("コード対応なし", ctx, "宣言の道(ADR-061)も示す")

    def test_silent_when_summary_has_no_trace_coverage(self):
        self._put_summary(with_coverage=False)
        p = self._code()
        out, code = self._nudge_sid(p, "sid-a2")
        self.assertEqual((out.strip(), code), ("", 0))

    def test_silent_without_any_summary(self):
        p = self._code()
        out, code = self._nudge_sid(p, "sid-a3")
        self.assertEqual((out.strip(), code), ("", 0))

    def test_only_once_per_session(self):
        self._put_summary(with_coverage=True)
        p = self._code()
        first, _ = self._nudge_sid(p, "sid-once")
        second, _ = self._nudge_sid(p, "sid-once")
        self.assertTrue(first.strip())
        self.assertEqual(second.strip(), "")

    def test_marked_code_is_silent(self):
        self._put_summary(with_coverage=True)
        body = ("# doctrine:" + "begin SPEC-900\nx=1\n"
                "# doctrine:" + "end SPEC-900\n")
        p = self._code(body=body)
        out, code = self._nudge_sid(p, "sid-a4")
        self.assertEqual((out.strip(), code), ("", 0))

    def test_md_and_docs_tree_files_are_out_of_scope(self):
        self._put_summary(with_coverage=True)
        md = self._code(rel="README2.md")
        out, _ = self._nudge_sid(md, "sid-a5")
        self.assertEqual(out.strip(), "")
        inner = self._code(rel="doctrine_docs/app/notes.txt")
        out, _ = self._nudge_sid(inner, "sid-a6")
        self.assertEqual(out.strip(), "")


class TestNudgesTypedDoc(ReviewNudgeBase):
    def test_typed_doc_gets_nudge(self):
        """A typed governance doc -> additionalContext nudge mentioning doc-review."""
        p = _util.write_doc(self.root, "doctrine_docs/billing/spec/SPEC-001-x.md", {
            "id": "SPEC-001", "title": "x", "type": "SPEC", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "## 入出力\n本文。\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(
            resp["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("doc-review", resp["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("decision", resp)  # advisory only, never a decision

    def test_each_known_type_nudges(self):
        reg = _util.load_core("_registry")
        for tc in ("REQ", "ADR", "ICD", "TEST", "DECIDED"):
            p = _util.write_doc(self.root, "doctrine_docs/billing/%s-9-x.md" % tc, {
                "id": "%s-9" % tc, "title": "x", "type": tc, "domain": "billing",
                "status": reg.default_status(tc) or "current", "owner": "a",
                "updated": "2026-06-30", "sources": [],
            }, "本文。\n")
            out, code = self._nudge(p)
            self.assertEqual(code, 0)
            self.assertTrue(out.strip(), tc)


class TestLevelGate(ReviewNudgeBase):
    """ADR-019 段差ゲート: Level 2 の体系ではナッジを出さない(縮小構成)。"""

    def _typed_doc_in_docs_tree(self, marker):
        p = _util.write_doc(self.root, "docs/billing/spec/SPEC-001-x.md", {
            "id": "SPEC-001", "title": "x", "type": "SPEC", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "## 入出力\n本文。\n")
        if marker is not None:
            sysdir = os.path.join(self.root, "docs", "_system")
            os.makedirs(sysdir, exist_ok=True)
            with open(os.path.join(sysdir, ".docs-level"), "w",
                      encoding="utf-8") as fh:
                fh.write(marker)
        return p

    def test_level2_no_nudge(self):
        p = self._typed_doc_in_docs_tree("level: 2\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_level4_and_missing_marker_nudge(self):
        p = self._typed_doc_in_docs_tree("level: 4\n")
        out, _ = self._nudge(p)
        self.assertIn("doc-review", out)
        p2 = self._typed_doc_in_docs_tree(None)
        out2, _ = self._nudge(p2)
        self.assertIn("doc-review", out2)


class TestSilentForNonDocs(ReviewNudgeBase):
    def test_non_md_file_no_nudge(self):
        """A non-.md path (e.g. a script) -> empty stdout."""
        p = os.path.join(self.root, "code.py")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("print('x')\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_md_without_frontmatter_no_nudge(self):
        """A .md with no frontmatter (not a governance doc) -> empty stdout."""
        p = os.path.join(self.root, "notes.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# just prose\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_unknown_type_no_nudge(self):
        """A .md whose type is not a known registry type -> empty stdout."""
        p = _util.write_doc(self.root, "x.md", {
            "id": "XYZ-1", "title": "x", "type": "XYZ", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "本文。\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_missing_path_no_crash(self):
        out, code = _util.invoke("review-nudge", stdin_obj="")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


class TestSilentWithoutTree(ReviewNudgeBase):
    """ADR-036 境界: 統治木の無いプロジェクトでは、type を持つ他体系の .md を
    編集しても、印も助言も出さない(#68。存在しない _system への書き戻し指示や
    無関係セッションの Stop 差し止めを防ぐ)。"""

    def test_typed_doc_outside_any_tree_is_silent(self):
        # doctrine_docs も docs/_system も無い、素の .md(Obsidian 等を模す)。
        p = _util.write_doc(self.root, "vault/SPEC-001-x.md", {
            "id": "SPEC-001", "title": "x", "type": "SPEC", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "## 入出力\n本文。\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_typed_doc_in_doctrine_tree_still_nudges(self):
        # 対照: 同じ型付き文書でも doctrine_docs/ の木の中なら従来どおり助言する。
        p = _util.write_doc(self.root, "doctrine_docs/billing/SPEC-003-x.md", {
            "id": "SPEC-003", "title": "x", "type": "SPEC", "domain": "billing",
            "status": "current", "owner": "a", "updated": "2026-06-30",
            "sources": [],
        }, "## 入出力\n本文。\n")
        out, code = self._nudge(p)
        self.assertEqual(code, 0)
        self.assertIn("doc-review", out)


if __name__ == "__main__":
    unittest.main()
