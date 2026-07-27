#!/usr/bin/env python3
"""_tracescan — コード注釈の走査(SPEC-026 / TEST-026)の単体試験。

凍らせる不変条件:

1. 言語で手段を分けない。六通りの注釈記号で同じ印が同じように読める。判定に
   言語ごとの分岐を入れない(ADR-054。ADR-049・ADR-053 と同じ欠陥類型を作らない)。
2. 指紋が環境で割れない。改行コードの違いと行末の空白で古びと誤判定しない。
   同じリポジトリを Windows と Linux の両方で扱うと、正規化しなければ割れる。
3. 対応付けの誤り(入れ子・両端の id の不一致・閉じ忘れ・開いていない end)を
   四種に分けて挙げる。消し忘れ・付け忘れを機械で捕まえるのが方式選択の根拠
   だったので、ここが緩むと方式の前提が崩れる。
4. 自己言及を断つ。統治木の中と .md を走査しない。

注意: この試験の原文に、印として読まれる行を置かない(`_mark` で組み立てる)。
リポジトリ自身を走査したときに、試験の原文が範囲として拾われるのを防ぐ。
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

T = _util.load_core("_tracescan")


def _mark(kind, doc_id, lead="# ", tail=""):
    """印の行を組み立てる。原文に印そのものを書かないための helper。"""
    return "%sdoctrine:%s %s%s" % (lead, kind, doc_id, tail)


def _block(doc_id, body_lines, lead="# ", tail=""):
    return "\n".join(
        [_mark("begin", doc_id, lead, tail)] + body_lines
        + [_mark("end", doc_id, lead, tail)])


class LanguageAgnosticTest(unittest.TestCase):
    """1. 六通りの注釈記号で、同じ範囲・同じ指紋が得られる。"""

    LEADS = [
        ("# ", ""),          # Python / Ruby / Shell
        ("// ", ""),         # C / Java / Go / Rust
        ("-- ", ""),         # SQL / Haskell / Lua
        ("; ", ""),          # Lisp / asm / ini
        ("% ", ""),          # TeX / Erlang
        ("/* ", " */"),      # ブロック注釈
    ]

    def test_all_comment_styles_yield_the_same_range(self):
        body = ["def foo():", "    return 1"]
        seen = set()
        for lead, tail in self.LEADS:
            with self.subTest(lead=lead):
                r, f = T.scan_text(_block("SPEC-014", body, lead, tail), "a.src")
                self.assertEqual(f, [], "%s: 誤りが出てはならない" % lead)
                self.assertEqual(len(r), 1, lead)
                self.assertEqual(r[0]["id"], "SPEC-014")
                self.assertEqual((r[0]["begin_line"], r[0]["end_line"]), (1, 4))
                seen.add(r[0]["fingerprint"])
        self.assertEqual(len(seen), 1,
                         "注釈記号を変えただけで指紋が変わってはならない")

    def test_html_style_block_comment(self):
        r, f = T.scan_text(_block("SPEC-014", ["x"], "<!-- ", " -->"), "a.html")
        self.assertEqual(f, [])
        self.assertEqual(len(r), 1)

    def test_marker_without_space_after_comment_char(self):
        r, f = T.scan_text(_block("SPEC-014", ["x"], "#"), "a.py")
        self.assertEqual(f, [])
        self.assertEqual(len(r), 1)

    def test_bare_marker_with_no_comment_leader(self):
        r, f = T.scan_text(_block("SPEC-014", ["x"], ""), "a.txt")
        self.assertEqual(f, [])
        self.assertEqual(len(r), 1)

    def test_marker_inside_code_is_not_a_mark(self):
        """行の先頭に語文字があれば印にしない(文字列の中の綴りを拾わない)。"""
        src = 'x = "%s"\ny = 1\n' % _mark("begin", "SPEC-014", "")
        r, f = T.scan_text(src, "a.py")
        self.assertEqual(r, [])
        self.assertEqual(f, [])

    def test_lowercase_id_is_not_a_mark(self):
        """id は登録簿の書式(大文字-数字)。緩めると偶然の一致が増える。"""
        r, f = T.scan_text(_block("spec-014", ["x"]), "a.py")
        self.assertEqual(r, [])
        self.assertEqual(f, [])


class FingerprintStabilityTest(unittest.TestCase):
    """2. 環境の差で指紋が割れない。"""

    def test_crlf_and_lf_agree(self):
        body = ["def foo():", "    return 1"]
        lf = _block("SPEC-014", body)
        crlf = lf.replace("\n", "\r\n")
        a, _ = T.scan_text(lf, "a.py")
        b, _ = T.scan_text(crlf, "a.py")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"],
                         "改行コードの違いで指紋が割れてはならない")

    def test_lone_cr_agrees(self):
        body = ["x = 1"]
        a, _ = T.scan_text(_block("SPEC-014", body), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", body).replace("\n", "\r"), "a.py")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"])

    def test_trailing_whitespace_is_ignored(self):
        a, _ = T.scan_text(_block("SPEC-014", ["x = 1", "y = 2"]), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", ["x = 1   ", "y = 2\t"]), "a.py")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"],
                         "整形器が落とす行末の空白で古びと判じてはならない")

    def test_trailing_blank_lines_are_ignored(self):
        a, _ = T.scan_text(_block("SPEC-014", ["x = 1"]), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", ["x = 1", "", ""]), "a.py")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"])

    def test_leading_indentation_is_significant(self):
        """字下げは意味を持つ(Python)。落としてはならない。"""
        a, _ = T.scan_text(_block("SPEC-014", ["x = 1"]), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", ["    x = 1"]), "a.py")
        self.assertNotEqual(a[0]["fingerprint"], b[0]["fingerprint"])

    def test_comment_style_of_marks_does_not_enter_the_fingerprint(self):
        a, _ = T.scan_text(_block("SPEC-014", ["x = 1"], "# "), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", ["x = 1"], "// "), "a.js")
        self.assertEqual(a[0]["fingerprint"], b[0]["fingerprint"],
                         "印の行は指紋に入らない")

    def test_content_change_changes_the_fingerprint(self):
        a, _ = T.scan_text(_block("SPEC-014", ["x = 1"]), "a.py")
        b, _ = T.scan_text(_block("SPEC-014", ["x = 2"]), "a.py")
        self.assertNotEqual(a[0]["fingerprint"], b[0]["fingerprint"])

    def test_bom_does_not_change_the_fingerprint(self):
        """BOM 付きと無しで指紋が割れない(Windows の編集器が付けることがある)。

        除去は復号側(utf-8-sig)が担う。ここは走査を通した結果で固定する。
        """
        root = _util.make_repo({})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        block = _block("SPEC-014", ["x = 1"])
        with open(os.path.join(root, "plain.py"), "wb") as fh:
            fh.write(block.encode("utf-8"))
        with open(os.path.join(root, "withbom.py"), "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + block.encode("utf-8"))
        r, f = T.scan_tree(root)
        self.assertEqual(len(r), 2, f)
        self.assertEqual(r[0]["fingerprint"], r[1]["fingerprint"])

    def test_fingerprint_notation_matches_ext(self):
        r, _ = T.scan_text(_block("SPEC-014", ["x"]), "a.py")
        fp = r[0]["fingerprint"]
        self.assertTrue(fp.startswith("sha256:"), fp)
        self.assertEqual(len(fp), len("sha256:") + 64, fp)


class PairingErrorsTest(unittest.TestCase):
    """3. 対応付けの誤りを四種に分けて挙げる(消し忘れ・付け忘れの検出)。"""

    def codes(self, findings):
        return [f["code"] for f in findings]

    def test_nested_range_is_flagged(self):
        src = "\n".join([
            _mark("begin", "SPEC-014"), "x", _mark("begin", "SPEC-015"), "y",
            _mark("end", "SPEC-015"), _mark("end", "SPEC-014")])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_nested", self.codes(f))

    def test_id_mismatch_is_flagged(self):
        src = "\n".join([_mark("begin", "SPEC-014"), "x",
                         _mark("end", "SPEC-015")])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_id_mismatch", self.codes(f))
        self.assertEqual(r, [], "食い違った対から範囲を作ってはならない")

    def test_unclosed_range_is_flagged(self):
        """終了の付け忘れ。ファイルの終端まで閉じない。"""
        src = "\n".join([_mark("begin", "SPEC-014"), "x", "y"])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_unclosed", self.codes(f))
        self.assertEqual(r, [])

    def test_unopened_end_is_flagged(self):
        """開始の消し忘れ。終了だけが残る。"""
        src = "\n".join(["x", _mark("end", "SPEC-014")])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_unopened", self.codes(f))

    def test_empty_range_is_flagged(self):
        src = "\n".join([_mark("begin", "SPEC-014"), _mark("end", "SPEC-014")])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_empty_range", self.codes(f))

    def test_one_error_does_not_swallow_later_ranges(self):
        """一つの誤りが、後続の正しい範囲を巻き込まない。"""
        src = "\n".join([
            "x", _mark("end", "SPEC-999"),
            _mark("begin", "SPEC-014"), "y", _mark("end", "SPEC-014")])
        r, f = T.scan_text(src, "a.py")
        self.assertIn("trace_unopened", self.codes(f))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], "SPEC-014")

    def test_sequential_ranges_are_allowed(self):
        src = "\n".join([
            _mark("begin", "SPEC-014"), "x", _mark("end", "SPEC-014"),
            _mark("begin", "SPEC-015"), "y", _mark("end", "SPEC-015")])
        r, f = T.scan_text(src, "a.py")
        self.assertEqual(f, [])
        self.assertEqual([x["id"] for x in r], ["SPEC-014", "SPEC-015"])

    def test_same_id_twice_is_allowed(self):
        """一つの仕様を複数の場所で実装しうる。"""
        src = "\n".join([
            _mark("begin", "SPEC-014"), "x", _mark("end", "SPEC-014"),
            _mark("begin", "SPEC-014"), "y", _mark("end", "SPEC-014")])
        r, f = T.scan_text(src, "a.py")
        self.assertEqual(f, [])
        self.assertEqual(len(r), 2)


class TreeScanTest(unittest.TestCase):
    """4. 走査の対象と、機械をまたいで共有できる形。"""

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_governance_tree_is_not_scanned(self):
        """統治木の中は走査しない。文書は追跡の終点にならない。"""
        root = self._repo({
            "docs/_system/glossary.md": "x",
            "docs/notes.txt": _block("SPEC-014", ["y"]),
            "src/a.py": _block("SPEC-015", ["z"]),
        })
        r, f = T.scan_tree(root, docs_root=os.path.join(root, "docs"))
        self.assertEqual([x["id"] for x in r], ["SPEC-015"])

    def test_markdown_is_not_scanned(self):
        """この書式を説明する文書自身の印を読まない(自己言及を断つ)。"""
        root = self._repo({"README.md": _block("SPEC-014", ["x"])})
        r, f = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_binary_is_skipped(self):
        root = self._repo({})
        p = os.path.join(root, "blob.bin")
        with open(p, "wb") as fh:
            fh.write(b"\x00\x01" + _block("SPEC-014", ["x"]).encode("utf-8"))
        r, f = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_dot_directories_are_skipped(self):
        root = self._repo({".git/hooks/x.py": _block("SPEC-014", ["x"])})
        r, f = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_paths_are_relative_posix_and_carry_no_absolute_path(self):
        root = self._repo({"src/pkg/a.py": _block("SPEC-014", ["x"])})
        r, f = T.scan_tree(root)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["path"], "src/pkg/a.py")
        self.assertNotIn(root, str(r))

    def test_result_is_deterministic_and_sorted(self):
        root = self._repo({
            "b.py": _block("SPEC-015", ["x"]),
            "a.py": _block("SPEC-014", ["y"]),
        })
        first, _ = T.scan_tree(root)
        second, _ = T.scan_tree(root)
        self.assertEqual(first, second)
        self.assertEqual([x["path"] for x in first], ["a.py", "b.py"])

    def test_file_count_cap_is_announced_not_silent(self):
        """上限を超えたら黙って切り詰めず、飛ばした事実を告げる。"""
        files = {"f%03d.py" % i: _block("SPEC-014", ["x"]) for i in range(8)}
        root = self._repo(files)
        r, f = T.scan_tree(root, max_files=3)
        self.assertTrue(any(x["code"] == "trace_scan_truncated" for x in f),
                        "切り詰めを黙って行ってはならない")

    def test_oversize_file_is_announced(self):
        root = self._repo({"big.py": _block("SPEC-014", ["x" * 100])})
        r, f = T.scan_tree(root, max_file_bytes=10)
        self.assertTrue(any(x["code"] == "trace_scan_truncated" for x in f))
        self.assertEqual(r, [])

    def test_files_without_the_marker_are_ignored(self):
        root = self._repo({"a.py": "print(1)\n", "b.py": _block("SPEC-014", ["x"])})
        r, f = T.scan_tree(root)
        self.assertEqual([x["path"] for x in r], ["b.py"])

    def test_undecodable_file_does_not_stop_the_scan(self):
        root = self._repo({"good.py": _block("SPEC-014", ["x"])})
        with open(os.path.join(root, "bad.py"), "wb") as fh:
            fh.write(b"# doctrine:begin SPEC-015\n\xff\xfe not utf8\n")
        r, f = T.scan_tree(root)
        self.assertEqual([x["id"] for x in r], ["SPEC-014"])

    def test_missing_root_returns_empty(self):
        r, f = T.scan_tree("/nonexistent/path/xyz")
        self.assertEqual((r, f), ([], []))

    def test_none_root_returns_empty(self):
        r, f = T.scan_tree(None)
        self.assertEqual((r, f), ([], []))


class TraceIndexCLITest(unittest.TestCase):
    """索引の問い合わせ(ADR-055): ファイルに置かず、毎回導出する。"""

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _run(self, argv):
        out, code = _util.invoke("trace-index", argv)
        return out, code

    def test_json_carries_no_absolute_path(self):
        """機械をまたいで共有できる形を保つ(絶対パスも利用者名も出さない)。"""
        root = self._repo({"src/a.py": _block("SPEC-014", ["x"])})
        out, code = self._run(["--root", root, "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["schema"], "trace-index/1")
        self.assertNotIn(root, out, "絶対パスが出てはならない")
        self.assertEqual([r["path"] for r in data["ranges"]], ["src/a.py"])

    def test_id_filter_gives_the_reverse_link(self):
        """仕様の側から見た逆リンク(その仕様を実装する範囲)。"""
        root = self._repo({
            "a.py": _block("SPEC-014", ["x"]),
            "b.py": _block("SPEC-015", ["y"]),
        })
        out, code = self._run(["--root", root, "--id", "SPEC-015",
                               "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual([r["id"] for r in data["ranges"]], ["SPEC-015"])

    def test_findings_are_reported_but_exit_stays_zero(self):
        """問い合わせの CLI であって、違反を止めるゲートではない。"""
        root = self._repo({"a.py": "\n".join([_mark("begin", "SPEC-014"), "x"])})
        out, code = self._run(["--root", root, "--format", "json"])
        self.assertEqual(code, 0, "所見があっても 0 を返す")
        data = json.loads(out)
        self.assertTrue(any(f["code"] == "trace_unclosed"
                            for f in data["findings"]))

    def test_governance_tree_excluded_via_docs_root(self):
        root = self._repo({
            "docs/_system/glossary.md": "x",
            "docs/notes.txt": _block("SPEC-014", ["y"]),
            "src/a.py": _block("SPEC-015", ["z"]),
        })
        out, code = self._run(["--root", root, "--docs-root",
                               os.path.join(root, "docs"), "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in json.loads(out)["ranges"]],
                         ["SPEC-015"])

    def test_repeated_queries_agree(self):
        """索引を置かないので、毎回の導出が同じ答えになることが要る。"""
        root = self._repo({"a.py": _block("SPEC-014", ["x"])})
        first, _ = self._run(["--root", root, "--format", "json"])
        second, _ = self._run(["--root", root, "--format", "json"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
