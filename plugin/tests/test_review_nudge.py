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


class TestNudgesTypedDoc(ReviewNudgeBase):
    def test_typed_doc_gets_nudge(self):
        """A typed governance doc -> additionalContext nudge mentioning doc-review."""
        p = _util.write_doc(self.root, "billing/spec/SPEC-001-x.md", {
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
            p = _util.write_doc(self.root, "billing/%s-9-x.md" % tc, {
                "id": "%s-9" % tc, "title": "x", "type": tc, "domain": "billing",
                "status": reg.default_status(tc) or "current", "owner": "a",
                "updated": "2026-06-30", "sources": [],
            }, "本文。\n")
            out, code = self._nudge(p)
            self.assertEqual(code, 0)
            self.assertTrue(out.strip(), tc)


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


if __name__ == "__main__":
    unittest.main()
