#!/usr/bin/env python3
# doctrine:begin TEST-026
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
# doctrine:end TEST-026
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
        """行の先頭に語文字があれば印にしない(文字列の中の綴りを拾わない)。

        範囲は決して作らない。ADR-059 以降は無音でもない — 印の形をした文字列は
        疑い(advisory)として挙がる。厳密な照合と疑いの照合の分離を凍結する。
        """
        src = 'x = "%s"\ny = 1\n' % _mark("begin", "SPEC-014", "")
        r, f = T.scan_text(src, "a.py")
        self.assertEqual(r, [])
        self.assertEqual([x["code"] for x in f], ["trace_marker_suspect"])

    def test_lowercase_id_is_not_a_mark(self):
        """id は登録簿の書式(大文字-数字)。緩めると偶然の一致が増える。

        範囲は作らない。ADR-059 以降、綴りの揺れは疑いとして挙がる(begin と
        end の二行それぞれ)。
        """
        r, f = T.scan_text(_block("spec-014", ["x"]), "a.py")
        self.assertEqual(r, [])
        self.assertEqual([x["code"] for x in f],
                         ["trace_marker_suspect", "trace_marker_suspect"])


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
        r, f, _ = T.scan_tree(root)
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
        r, f, _ = T.scan_tree(root, docs_root=os.path.join(root, "docs"))
        self.assertEqual([x["id"] for x in r], ["SPEC-015"])

    def test_markdown_is_not_scanned(self):
        """この書式を説明する文書自身の印を読まない(自己言及を断つ)。"""
        root = self._repo({"README.md": _block("SPEC-014", ["x"])})
        r, f, _ = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_binary_is_skipped(self):
        root = self._repo({})
        p = os.path.join(root, "blob.bin")
        with open(p, "wb") as fh:
            fh.write(b"\x00\x01" + _block("SPEC-014", ["x"]).encode("utf-8"))
        r, f, _ = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_dot_directories_are_skipped(self):
        root = self._repo({".git/hooks/x.py": _block("SPEC-014", ["x"])})
        r, f, _ = T.scan_tree(root)
        self.assertEqual(r, [])

    def test_paths_are_relative_posix_and_carry_no_absolute_path(self):
        root = self._repo({"src/pkg/a.py": _block("SPEC-014", ["x"])})
        r, f, _ = T.scan_tree(root)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["path"], "src/pkg/a.py")
        self.assertNotIn(root, str(r))

    def test_result_is_deterministic_and_sorted(self):
        root = self._repo({
            "b.py": _block("SPEC-015", ["x"]),
            "a.py": _block("SPEC-014", ["y"]),
        })
        first, _, _cov1 = T.scan_tree(root)
        second, _, _cov2 = T.scan_tree(root)
        self.assertEqual(first, second)
        self.assertEqual([x["path"] for x in first], ["a.py", "b.py"])

    def test_file_count_cap_is_announced_not_silent(self):
        """上限を超えたら黙って切り詰めず、飛ばした事実を告げる。"""
        files = {"f%03d.py" % i: _block("SPEC-014", ["x"]) for i in range(8)}
        root = self._repo(files)
        r, f, _ = T.scan_tree(root, max_files=3)
        self.assertTrue(any(x["code"] == "trace_scan_truncated" for x in f),
                        "切り詰めを黙って行ってはならない")

    def test_oversize_file_is_announced(self):
        root = self._repo({"big.py": _block("SPEC-014", ["x" * 100])})
        r, f, _ = T.scan_tree(root, max_file_bytes=10)
        self.assertTrue(any(x["code"] == "trace_scan_truncated" for x in f))
        self.assertEqual(r, [])

    def test_files_without_the_marker_are_ignored(self):
        root = self._repo({"a.py": "print(1)\n", "b.py": _block("SPEC-014", ["x"])})
        r, f, _ = T.scan_tree(root)
        self.assertEqual([x["path"] for x in r], ["b.py"])

    def test_undecodable_file_does_not_stop_the_scan(self):
        root = self._repo({"good.py": _block("SPEC-014", ["x"])})
        with open(os.path.join(root, "bad.py"), "wb") as fh:
            fh.write(b"# doctrine:" + b"begin SPEC-015\n\xff\xfe not utf8\n")
        r, f, _ = T.scan_tree(root)
        self.assertEqual([x["id"] for x in r], ["SPEC-014"])

    def test_missing_root_returns_empty(self):
        r, f, _ = T.scan_tree("/nonexistent/path/xyz")
        self.assertEqual((r, f), ([], []))

    def test_none_root_returns_empty(self):
        r, f, _ = T.scan_tree(None)
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


class CoverageAccountingTest(unittest.TestCase):
    """5. 勘定と保存則(ADR-058)。触れたものは必ずどれか一つに数えられる。"""

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _assert_identity(self, cov):
        """保存則: reached = annotated + unmarked + exempt + Σexcluded(ADR-067)。"""
        self.assertEqual(
            cov["reached_files"],
            cov["annotated_files"] + cov["unmarked_files"]
            + cov["exempt_files"] + sum(cov["excluded"].values()),
            "保存則が破れている: %r" % (cov,))

    def test_all_rule_slots_present_even_at_zero(self):
        """全規則の枠が 0 件でも在る(空欄を許さない。SPEC-025 と同じ原則)。"""
        root = self._repo({})
        _, _, cov = T.scan_tree(root)
        # 枠の対応は定数から導いてよい(これは「勘定の枠が規則の表と一致するか」の検査)。
        # 規則の一覧そのものは下の EXPECTED_EXCLUSION_RULES が手書きで凍らせる。
        file_rules = {rid for rid, kind in T.EXCLUSION_RULES if kind == "file"}
        dir_rules = {rid for rid, kind in T.EXCLUSION_RULES if kind == "dir"}
        # 両方向: 表に在る規則は枠を持ち、枠に在る規則は表に在る。
        self.assertEqual(set(cov["excluded"]), file_rules)
        self.assertEqual(set(cov["pruned_dirs"]), dir_rules)
        self._assert_identity(cov)

    def test_identity_holds_across_file_rules(self):
        """代表的な各規則を一つずつ踏んでも、勘定の和が合う。"""
        root = self._repo({
            "src/a.py": _block("SPEC-014", ["x"]),        # 寄与
            "src/plain.py": "print(1)\n",                  # 印なし
            ".env": "SECRET=1\n",                          # dot_file
            "README.md": _block("SPEC-014", ["x"]),        # md_suffix
        })
        with open(os.path.join(root, "blob.bin"), "wb") as fh:
            fh.write(b"\x00\x01data")                      # binary
        with open(os.path.join(root, "bad.py"), "wb") as fh:
            fh.write(b"# doctrine:" + b"begin SPEC-015\n\xff\xfe\n")  # undecodable
        _, _, cov = T.scan_tree(root, max_file_bytes=1024)
        self.assertEqual(cov["annotated_files"], 1)
        self.assertEqual(cov["unmarked_files"], 1)
        self.assertEqual(cov["excluded"]["dot_file"], 1)
        self.assertEqual(cov["excluded"]["md_suffix"], 1)
        self.assertEqual(cov["excluded"]["binary"], 1)
        self.assertEqual(cov["excluded"]["undecodable"], 1)
        self.assertEqual(cov["reached_files"], 6)
        self._assert_identity(cov)

    def test_no_marker_file_is_unmarked_not_excluded(self):
        """印なしは除外ではない。入れ忘れが住む場所として数える。"""
        root = self._repo({"a.py": "print(1)\n"})
        _, _, cov = T.scan_tree(root)
        self.assertEqual(cov["unmarked_files"], 1)
        self.assertEqual(sum(cov["excluded"].values()), 0)

    def test_marker_word_without_valid_range_is_unmarked(self):
        """印の語はあるが対を成さない(綴りの揺れ)も印なしに数える。"""
        # 原文に疑いの形を書かない(自己反応を避ける)。実行時に連結して作る。
        near_mark = "# doctrine:" + " begin SPEC-014\nx = 1\n"
        root = self._repo({"a.py": near_mark})
        r, _, cov = T.scan_tree(root)
        self.assertEqual(r, [])
        self.assertEqual(cov["unmarked_files"], 1)
        self._assert_identity(cov)

    def test_oversize_is_counted_and_announced(self):
        root = self._repo({"big.py": _block("SPEC-014", ["x" * 100])})
        _, f, cov = T.scan_tree(root, max_file_bytes=10)
        self.assertEqual(cov["excluded"]["oversize"], 1)
        self.assertTrue(any(x["code"] == "trace_scan_truncated" for x in f))
        self._assert_identity(cov)

    def test_truncation_counts_dropped_files_in_the_identity(self):
        """上限打ち切りの既知の残りも勘定に載る(黙って消えない)。"""
        files = {"f%03d.py" % i: _block("SPEC-014", ["x"]) for i in range(8)}
        root = self._repo(files)
        _, _, cov = T.scan_tree(root, max_files=3)
        self.assertTrue(cov["truncated"])
        self.assertGreater(cov["excluded"]["truncated"], 0)
        self._assert_identity(cov)

    def test_dir_pruning_is_counted_per_rule(self):
        root = self._repo({
            ".git/x.py": _block("SPEC-014", ["x"]),
            "node_modules/pkg/y.py": _block("SPEC-014", ["y"]),
            "docs/_system/glossary.md": "x",
            "src/a.py": _block("SPEC-015", ["z"]),
        })
        _, _, cov = T.scan_tree(root, docs_root=os.path.join(root, "docs"))
        self.assertEqual(cov["pruned_dirs"]["dot_dir"], 1)
        self.assertEqual(cov["pruned_dirs"]["skip_dir_name"], 1)
        self.assertEqual(cov["pruned_dirs"]["docs_root"], 1)
        self._assert_identity(cov)

    def test_symlinked_dir_is_counted_not_descended(self):
        """降下しないシンボリックリンクを黙らず数える。"""
        root = self._repo({"src/a.py": _block("SPEC-014", ["x"])})
        outside = _util.make_repo({"b.py": _block("SPEC-015", ["y"])})
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        try:
            os.symlink(outside, os.path.join(root, "linked"))
        except OSError:
            self.skipTest("symlink を作れない環境")
        r, _, cov = T.scan_tree(root)
        self.assertEqual([x["id"] for x in r], ["SPEC-014"])
        self.assertEqual(cov["pruned_dirs"]["symlink_dir"], 1)
        self._assert_identity(cov)

    def test_fifo_is_classified_without_hanging(self):
        """通常ファイル以外は開かない。名前付きパイプで走査が止まらない。"""
        if not hasattr(os, "mkfifo"):
            self.skipTest("mkfifo の無い環境")
        root = self._repo({"src/a.py": _block("SPEC-014", ["x"])})
        os.mkfifo(os.path.join(root, "pipe"))
        r, _, cov = T.scan_tree(root)   # 以前はここで永久に戻らなかった
        self.assertEqual([x["id"] for x in r], ["SPEC-014"])
        self.assertEqual(cov["excluded"]["nonregular"], 1)
        self._assert_identity(cov)

    def test_unreadable_file_and_dir_are_counted(self):
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("権限で読めない状態を作れない環境")
        root = self._repo({
            "src/a.py": _block("SPEC-014", ["x"]),
            "locked.py": _block("SPEC-015", ["y"]),
            "lockdir/z.py": _block("SPEC-016", ["z"]),
        })
        os.chmod(os.path.join(root, "locked.py"), 0)
        os.chmod(os.path.join(root, "lockdir"), 0)
        self.addCleanup(os.chmod, os.path.join(root, "lockdir"), 0o755)
        _, _, cov = T.scan_tree(root)
        self.assertEqual(cov["excluded"]["unreadable"], 1)
        self.assertEqual(cov["pruned_dirs"]["unreadable_dir"], 1)
        self._assert_identity(cov)

    def test_docs_root_equal_to_scan_root_scans_nothing(self):
        """根が統治木そのものでも、配下(サブディレクトリ含む)を走査しない。"""
        root = self._repo({
            "spec/a.txt": _block("SPEC-014", ["x"]),
            "b.txt": _block("SPEC-015", ["y"]),
        })
        r, _, cov = T.scan_tree(root, docs_root=root)
        self.assertEqual(r, [])
        self.assertEqual(cov["reached_files"], 0)

    def test_members_are_absent_by_default_and_sorted_on_request(self):
        """一覧は求めに応じて導出する(既定は件数だけ。ADR-055/ADR-058)。"""
        root = self._repo({
            "b.py": "print(1)\n",
            "a.py": "print(2)\n",
            "src/m.py": _block("SPEC-014", ["x"]),
        })
        _, _, plain = T.scan_tree(root)
        self.assertNotIn("members", plain)
        _, _, cov = T.scan_tree(root, collect_members=True)
        self.assertEqual(cov["members"]["unmarked"], ["a.py", "b.py"])
        self.assertEqual(cov["members"]["annotated"], ["src/m.py"])


class ExemptDeclarationTest(unittest.TestCase):
    """統治外の宣言(ADR-067)。勘定の第四項・矛盾の検出・疑いの拡張。

    原文に印の形を直に書かない(実行時に連結して作る。ADR-059 の規律)。
    """

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _exempt(self, reason=""):
        line = "# doctrine:" + "exempt"
        if reason:
            line += " " + reason
        return line

    def test_exempt_file_counts_in_the_fourth_slot(self):
        root = self._repo({
            "tools/oneoff.py": self._exempt("使い捨ての移行スクリプト") + "\nx=1\n",
            "src/plain.py": "print(1)\n",
        })
        r, f, cov = T.scan_tree(root)
        self.assertEqual(r, [])
        self.assertEqual(cov["exempt_files"], 1)
        self.assertEqual(cov["unmarked_files"], 1)
        self.assertEqual(
            cov["reached_files"],
            cov["annotated_files"] + cov["unmarked_files"]
            + cov["exempt_files"] + sum(cov["excluded"].values()))

    def test_reason_is_optional(self):
        root = self._repo({"a.py": self._exempt() + "\n"})
        _, f, cov = T.scan_tree(root)
        self.assertEqual(cov["exempt_files"], 1)
        self.assertEqual([x for x in f
                          if x["code"] == "trace_marker_suspect"], [],
                         "厳密な exempt 行は疑いにならない")

    def test_exempt_with_ranges_is_a_conflict_and_reality_wins(self):
        """矛盾は所見で指し、範囲は実態として生かす(寄与に数える)。"""
        body = "\n".join([self._exempt("古い宣言"),
                          _block("SPEC-014", ["x = 1"])])
        root = self._repo({"a.py": body})
        r, f, cov = T.scan_tree(root)
        self.assertEqual([x["id"] for x in r], ["SPEC-014"], "範囲は生かす")
        self.assertEqual(cov["annotated_files"], 1)
        self.assertEqual(cov["exempt_files"], 0)
        codes = [x["code"] for x in f]
        self.assertIn("trace_exempt_conflict", codes)

    def test_exempt_typo_is_a_suspect(self):
        """コロンの後の空白などの揺れは疑いとして挙がる(ADR-059 の拡張)。"""
        src = "# doctrine:" + " exempt 理由\nx=1\n"
        root = self._repo({"a.py": src})
        _, f, cov = T.scan_tree(root)
        self.assertIn("trace_marker_suspect", [x["code"] for x in f])
        self.assertEqual(cov["exempt_files"], 0, "揺れた宣言は成立しない")

    def test_members_list_exempt_paths_on_request(self):
        root = self._repo({
            "b.py": self._exempt("理由b") + "\n",
            "a.py": self._exempt("理由a") + "\n",
        })
        _, _, cov = T.scan_tree(root, collect_members=True)
        self.assertEqual(cov["members"]["exempt"], ["a.py", "b.py"])


class MarkerSuspectTest(unittest.TestCase):
    """6. 打ったつもりの印を無音にしない(ADR-059)。

    厳密な照合は変えない。照合に落ちた行のうち、印の語の直後に begin/end が
    続くものだけを疑いとして挙げる。原文に疑いの形を直に書かない(自己反応を
    避けるため、実行時に連結して作る)。
    """

    def codes(self, findings):
        return [f["code"] for f in findings]

    def _suspects(self, src):
        _, f = T.scan_text(src, "a.py")
        return [x for x in f if x["code"] == "trace_marker_suspect"]

    def test_typo_variants_are_flagged_as_suspect(self):
        colon = "# doctrine:"
        word = "doctrine:"
        variants = [
            colon + " begin SPEC-014",          # コロンの後に空白
            colon + "begin spec-014",           # 小文字の id
            colon + "begin SPEC_014",           # 下線の id
            "x" + word + "begin SPEC-014",      # 行頭に語文字(文字列の中)
            colon + "begin SPEC-014 メモ",      # 余計な語
            colon + "begin",                    # id の欠落
        ]
        for src in variants:
            with self.subTest(src=src):
                self.assertEqual(len(self._suspects(src)), 1, src)

    def test_valid_mark_is_not_suspect(self):
        src = _block("SPEC-014", ["x = 1"])
        self.assertEqual(self._suspects(src), [])

    def test_marker_word_alone_in_prose_is_not_suspect(self):
        """印の語だけの散文(定数定義など)は疑いにしない。"""
        src = 'MARKER = "doctrine:"\nprint(MARKER)'
        self.assertEqual(self._suspects(src), [])

    def test_regex_like_source_is_not_suspect(self):
        """コロンの直後が空白でも begin でもない行(照合の原文など)は拾わない。"""
        src = 'PAT = r"doctrine:(begin|end)"'
        self.assertEqual(self._suspects(src), [])

    def test_suspect_points_at_the_line(self):
        src = "x = 1\n" + "# doctrine:" + " begin SPEC-014\n"
        sus = self._suspects(src)
        self.assertEqual([s["line"] for s in sus], [2])

    def test_finding_codes_match_the_transcribed_table(self):
        """所見コードの正本の凍結(ADR-060)。転記表と全量一致する。"""
        expected = (
            "trace_nested", "trace_id_mismatch", "trace_unclosed",
            "trace_unopened", "trace_empty_range", "trace_marker_suspect",
            "trace_scan_truncated", "trace_exempt_conflict",
        )
        self.assertEqual(T.FINDING_CODES, expected,
                         "コードを足した/消したら転記表を同じ変更で更新すること")

    def test_self_scan_of_this_repository_has_no_suspects(self):
        """自己適用: 実装・試験の原文が疑いに一致しない(規律の凍結。ADR-059)。"""
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        docs = os.path.join(repo, "doctrine_docs")
        _, f, _cov = T.scan_tree(repo, docs_root=docs)
        sus = [x for x in f if x["code"] == "trace_marker_suspect"]
        self.assertEqual(sus, [], "原文に印の形を書いた箇所がある: %r" % sus)


class CoverageCLITest(unittest.TestCase):
    """勘定の問い合わせ(ADR-058): 件数は常時、内訳は求めに応じて導出。"""

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _run(self, argv):
        return _util.invoke("trace-index", argv)

    def test_coverage_counts_in_json(self):
        root = self._repo({
            "a.py": _block("SPEC-014", ["x"]),
            "plain.py": "print(1)\n",
        })
        out, code = self._run(["--root", root, "--coverage", "--format", "json"])
        self.assertEqual(code, 0)
        cov = json.loads(out)["coverage"]
        self.assertEqual(cov["annotated_files"], 1)
        self.assertEqual(cov["unmarked_files"], 1)
        self.assertNotIn("members", cov, "既定で一覧を持たない")
        file_rules = {rid for rid, kind in T.EXCLUSION_RULES if kind == "file"}
        self.assertEqual(set(cov["excluded"]), file_rules,
                         "全規則の枠が 0 件でも出る")

    def test_term_drills_down_to_the_member_list(self):
        root = self._repo({
            "a.py": _block("SPEC-014", ["x"]),
            "plain.py": "print(1)\n",
            "sub/other.py": "print(2)\n",
        })
        out, code = self._run(["--root", root, "--coverage",
                               "--term", "unmarked", "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["term"], "unmarked")
        self.assertEqual(data["paths"], ["plain.py", "sub/other.py"])
        self.assertEqual(data["count"], 2)
        self.assertNotIn(root, out, "絶対パスが出てはならない")

    def test_exempt_term_drills_down(self):
        root = self._repo({"tool.py": "# doctrine:" + "exempt 理由\n"})
        out, code = self._run(["--root", root, "--coverage",
                               "--term", "exempt", "--format", "json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["paths"], ["tool.py"])

    def test_unknown_term_is_a_usage_error(self):
        root = self._repo({})
        out, code = self._run(["--root", root, "--coverage",
                               "--term", "excluded:nope"])
        self.assertEqual(code, 2)

    def test_term_without_coverage_is_a_usage_error(self):
        root = self._repo({})
        out, code = self._run(["--root", root, "--term", "unmarked"])
        self.assertEqual(code, 2)


class ConfigExemptTest(unittest.TestCase):
    """設定の適用除外(ADR-072)。注釈を持てない媒体の第二の道。

    読む前に明示管理外へ分類し、保存則の枠は変えない。宣言なき除外を作らない
    (文字列でない・空の項目は捨てる)。
    """

    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _assert_identity(self, cov):
        self.assertEqual(
            cov["reached_files"],
            cov["annotated_files"] + cov["unmarked_files"]
            + cov["exempt_files"] + sum(cov["excluded"].values()),
            "保存則が破れている: %r" % (cov,))

    def test_exact_path_and_prefix_both_classify_as_exempt(self):
        root = self._repo({
            "LICENSE": "MIT License\n",
            "templates/a.tmpl": "seed\n",
            "templates/b.tmpl": "seed\n",
            "src/plain.py": "print(1)\n",
        })
        _, _, cov = T.scan_tree(
            root, exempt_paths=("LICENSE", "templates/"))
        self.assertEqual(cov["exempt_files"], 3, "完全一致1 + 前置き一致2")
        self.assertEqual(cov["unmarked_files"], 1, "対象外の plain.py は印なしのまま")
        self._assert_identity(cov)

    def test_members_list_exempt_paths_on_demand(self):
        root = self._repo({"LICENSE": "MIT License\n"})
        _, _, cov = T.scan_tree(
            root, exempt_paths=("LICENSE",), collect_members=True)
        self.assertIn("LICENSE", cov["members"].get("exempt", []))

    def test_invalid_entries_are_dropped(self):
        root = self._repo({"src/plain.py": "print(1)\n"})
        _, _, cov = T.scan_tree(
            root, exempt_paths=(None, "", 3, b"x"))
        self.assertEqual(cov["exempt_files"], 0, "文字列でない・空の項目は捨てる")
        self.assertEqual(cov["unmarked_files"], 1)
        self._assert_identity(cov)

    def test_no_exempt_paths_changes_nothing(self):
        root = self._repo({"src/plain.py": "print(1)\n"})
        base = T.scan_tree(root)
        with_arg = T.scan_tree(root, exempt_paths=())
        self.assertEqual(base[2], with_arg[2], "未指定と空は同じ答え")


if __name__ == "__main__":
    unittest.main()


# 除外規則の一覧を手で書き写した表(ADR-060 の様式。test_audit の AUDIT_CHECKS と同じ)。
# 規則を足す・消すときは、正本(_tracescan.EXCLUSION_RULES)と**この表の両方**を同じ変更で
# 更新する。**ここを EXCLUSION_RULES から生成したら凍結の意味が消える。**
#
# 以前この凍結は無く、枠の対応(勘定の鍵 == 定数)だけを見ていた。規則を足しても黙って
# 通る状態であり、SPEC-026 の「TEST-026 が凍結する」は枠の一致を指すに過ぎなかった
# (2026-08-02 に ADR-089 で二規則を足したとき、何も落ちなかったことで判明した)。
EXPECTED_EXCLUSION_RULES = (
    ("dot_dir", "dir"),
    ("skip_dir_name", "dir"),
    ("docs_root", "dir"),
    ("symlink_dir", "dir"),
    ("unreadable_dir", "dir"),
    ("gitignored_dir", "dir"),       # ADR-089
    ("dot_file", "file"),
    ("md_suffix", "file"),
    ("nonregular", "file"),
    ("oversize", "file"),
    ("unreadable", "file"),
    ("binary", "file"),
    ("undecodable", "file"),
    ("gitignored_file", "file"),     # ADR-089
    ("truncated", "file"),
)


class ExclusionRulesFreezeTest(unittest.TestCase):
    """除外規則の一覧を手書きの表で凍らせる(ADR-060 の様式)。"""

    def test_rules_match_the_transcribed_table(self):
        self.assertEqual(
            tuple(T.EXCLUSION_RULES), EXPECTED_EXCLUSION_RULES,
            "除外規則が変わった。正本と手書きの表の両方を同じ変更で更新すること"
            "(片方だけ直すと、規則を足しても黙って通る状態へ戻る)")


class GitignoreTest(unittest.TestCase):
    """ADR-089 / #150: 無視される物は走査しない。判定は git に訊く。

    実測（呼び手のリポジトリ）: 修正前は範囲 30 件のうち 12 件（40%）が `.gitignore`
    配下の写しだった。修正後は 0 件になり、`trace_exempt` から out/・dist/ を外しても
    同じだった —— **同じ事実を二箇所に持つ形が消えた**。
    """

    def _repo(self, files, gitignore=None, init=True):
        import subprocess
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        if gitignore is not None:
            with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as fh:
                fh.write(gitignore)
        if init:
            for args in (["init", "--quiet", "-b", "main"],
                         ["config", "user.email", "t@example.invalid"],
                         ["config", "user.name", "t"]):
                subprocess.run(["git"] + args, cwd=root, capture_output=True,
                               timeout=30, check=False)
        return root

    # 印は _mark で組む(原文に印の形を直に書かない規律。ADR-059。自己走査が
    # この試験ファイルを「綴りの揺れ」として咎めるのを避ける)。
    _MARKED = "\n".join([_mark("begin", "SPEC-014"), "x",
                         _mark("end", "SPEC-014")]) + "\n"

    def test_ignored_directory_is_pruned_and_counted(self):
        root = self._repo({"src/a.ts": self._MARKED, "out/a.js": self._MARKED},
                          gitignore="out/\n")
        ranges, _f, cov = T.scan_tree(root)
        paths = {r["path"] for r in ranges}
        self.assertIn("src/a.ts", paths)
        self.assertNotIn("out/a.js", paths, "無視されるものを範囲に返してはならない")
        self.assertEqual(cov["gitignore"], "read")
        # 黙って切り詰めない。規則 id を経由して数える(ADR-058 の保存則)。
        self.assertEqual(cov["pruned_dirs"]["gitignored_dir"], 1)

    def test_ignored_single_file_is_excluded_and_counted(self):
        root = self._repo({"src/a.ts": self._MARKED, "src/b.gen.ts": self._MARKED},
                          gitignore="*.gen.ts\n")
        ranges, _f, cov = T.scan_tree(root)
        paths = {r["path"] for r in ranges}
        self.assertIn("src/a.ts", paths)
        self.assertNotIn("src/b.gen.ts", paths)
        self.assertEqual(cov["excluded"]["gitignored_file"], 1)

    def test_tracked_file_is_scanned_even_if_the_pattern_matches(self):
        """git が追跡しているファイルは走査する。git がそう扱うので、こちらもそう扱う。"""
        import subprocess
        root = self._repo({"src/a.ts": self._MARKED}, gitignore="*.ts\n")
        subprocess.run(["git", "add", "-f", "src/a.ts"], cwd=root,
                       capture_output=True, timeout=30, check=False)
        ranges, _f, _cov = T.scan_tree(root)
        self.assertIn("src/a.ts", {r["path"] for r in ranges})

    def test_no_repo_degrades_to_the_old_behaviour_without_scolding(self):
        """git を使わない木では、いまと同じ挙動へ退く。勘定に状態を残すが所見にしない。"""
        root = self._repo({"src/a.ts": self._MARKED, "out/a.js": self._MARKED},
                          gitignore="out/\n", init=False)
        ranges, findings, cov = T.scan_tree(root)
        self.assertIn(cov["gitignore"], ("not_a_repo", "error", "no_git"), cov)
        # 退いた挙動: .gitignore を見ないので写しも返る(いまと同じ)。
        self.assertIn("out/a.js", {r["path"] for r in ranges})
        # 責めない —— 所見は出さない。
        self.assertEqual([f for f in findings if "gitignore" in str(f)], [])

    def test_conservation_law_still_holds(self):
        """保存則を壊さない: reached = annotated + unmarked + exempt + Σexcluded。"""
        root = self._repo({"src/a.ts": self._MARKED, "out/a.js": self._MARKED,
                           "src/b.gen.ts": self._MARKED},
                          gitignore="out/\n*.gen.ts\n")
        _r, _f, cov = T.scan_tree(root)
        self.assertEqual(
            cov["reached_files"],
            cov["annotated_files"] + cov["unmarked_files"]
            + cov["exempt_files"] + sum(cov["excluded"].values()))
