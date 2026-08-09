#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""#197 のカルク軸 / ADR-135 の覆いすぎ — 最長字面優先の仲裁（後継 ADR）。

凍結したいこと:

- **板挟みの解消（カルク軸）**: 利用者のカルク表(表B)が必須節名を禁じても、
  節見出しは書ける。書けば CALQUE・消せば MISSING_SECTION の詰みを作らない。
  ADR-135 は禁止同義語(表A)の軸だけを直しており、同じ論法が当てはまる
  カルク軸へ運ばれていなかった（独立再監査 2026-08-09 で 55 節名中 52 件が
  不可書であることを実測）。
- **覆いすぎの解消（両軸）**: 節名を含む「より長い」禁止語は、覆いに飲まれず
  発火する。`理由付け`(⊃`理由`) や `エラーハンドリング`(⊃`エラー`) が黙って
  無効になっていた。これは ADR-135 が申告した限界の外側であった。
- **ADR-135 の限界は保つ**: 節名そのものを禁じた場合は、その語は覆われる
  （書き手は節名を言い換えられないため）。同点は覆いが勝つ。
"""
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

sys.path.insert(0, _util.SCRIPTS)
import _registry as reg  # noqa: E402
import _termcheck as tc  # noqa: E402


class CalqueMaskTestBase(unittest.TestCase):
    def _glossary(self, table_a=(), table_b=()):
        """表A(承認語)と表B(カルク)へ行を差し込んだ辞書を組む。"""
        tmpl = _util.read(os.path.join(_util.TEMPLATES, "glossary.md.tmpl"))
        if table_a:
            tmpl = tmpl.replace(
                "| 文書 | 管理対象の最小単位",
                "\n".join(table_a) + "\n| 文書 | 管理対象の最小単位")
        if table_b:
            tmpl = tmpl.replace(
                "| 同じページにいる | 認識を揃える | on the same page |",
                "\n".join(table_b)
                + "\n| 同じページにいる | 認識を揃える | on the same page |")
        root = _util.make_repo({"docs/_system/glossary.md": tmpl})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return tc.load_glossary(os.path.join(root, "docs"))

    @staticmethod
    def _codes(findings, code):
        return [f for f in findings if f.code == code]


class Issue197CalqueAxisTest(CalqueMaskTestBase):
    def test_a_calque_row_cannot_make_a_required_section_unwritable(self):
        """表B が必須節名を禁じても、その節は書ける（#197 のカルク軸）。"""
        g = self._glossary(table_b=[
            "| 影響するテスト | 影響する試験 | affected tests |"])
        body = ("## 影響する文書\nx\n## 影響する実装\ny\n"
                "## 影響するテスト\nz\n## 工数見積\nw\n")
        fs = tc.check(body, {"type": "IMPACT"}, g)
        self.assertEqual(self._codes(fs, "CALQUE"), [],
                         "必須節の名がカルクとして咎められた(#197 の袋小路)")
        self.assertEqual(self._codes(fs, "MISSING_SECTION"), [])

    def test_a_two_character_section_name_in_the_calque_table(self):
        """2 文字の節名（ADR の『決定』）でも詰まない。"""
        g = self._glossary(table_b=["| 決定 | 判断 | decision |"])
        body = ("## 背景\na\n## 却下した選択肢\nb\n## 決定\nc\n## 帰結\nd\n")
        fs = tc.check(body, {"type": "ADR"}, g)
        self.assertEqual(self._codes(fs, "CALQUE"), [])

    def test_a_calque_surface_that_is_part_of_a_section_name(self):
        """節名の断片（`エラー時` ⊂ `エラー時挙動`）でも詰まない。

        カルクは素の部分一致なので、禁止同義語軸より射程が広い。
        """
        g = self._glossary(table_b=["| エラー時 | 失敗したとき | on error |"])
        fs = tc.check("## エラー時挙動\n仕様のとおり。\n", {"type": "SPEC"}, g)
        self.assertEqual(self._codes(fs, "CALQUE"), [])

    def test_every_registry_section_name_is_writable_against_the_calque_table(self):
        """性質で持つ —— 全型・全節名を表B で禁じても、雛形どおりに書ける。"""
        names = sorted({n for secs in reg.REQUIRED_SECTIONS.values()
                        for n in secs})
        g = self._glossary(table_b=["| %s | 言い換え | x%d |" % (n, i)
                                    for i, n in enumerate(names)])
        offenders = []
        for type_code, secs in sorted(reg.REQUIRED_SECTIONS.items()):
            body = "".join("## %s\n本文。\n" % n for n in secs)
            fs = tc.check(body, {"type": type_code}, g)
            for f in self._codes(fs, "CALQUE"):
                offenders.append((type_code, f.message))
        self.assertEqual(offenders, [],
                         "表B の下で書けない必須節がある: %r" % (offenders[:5],))

    def test_a_real_calque_in_prose_still_fires(self):
        """射程を狭めすぎない —— 地の文の本物のカルクは従来どおり咎める。"""
        g = self._glossary()
        fs = tc.check("同じページにいることを確かめる。", {"type": "SPEC"}, g)
        self.assertTrue(self._codes(fs, "CALQUE"))

    def test_a_calque_row_longer_than_a_section_name_still_fires(self):
        """節名を含む「より長い」カルクは覆いに飲まれない。"""
        g = self._glossary(table_b=[
            "| 決定を行う | 決める | make a decision |"])
        fs = tc.check("## 背景\na\n## 却下した選択肢\nb\n"
                      "## 決定\n決定を行う。\n## 帰結\nd\n", {"type": "ADR"}, g)
        self.assertTrue(self._codes(fs, "CALQUE"),
                        "節名より長いカルクが黙って無効になった")


class MaskDoesNotVoidLongerUserBansTest(CalqueMaskTestBase):
    """ADR-135 が申告していなかった偽陰性の解消（表A 軸）。"""

    def test_a_banned_synonym_containing_a_section_name_still_fires(self):
        g = self._glossary(table_a=["| 動機 | 行為の理由 | 理由付け |"])
        fs = tc.check("理由付けを述べる。", {"type": "IMPL"}, g)
        self.assertTrue(
            [f for f in self._codes(fs, "BANNED_SYNONYM")
             if "理由付け" in f.message],
            "節名『理由』を含む長い禁止語が黙って無効になった")

    def test_the_api_case(self):
        g = self._glossary(table_a=["| 失敗処理 | 失敗時の処理 | エラーハンドリング |"])
        fs = tc.check("エラーハンドリングを実装する。", {"type": "IMPL"}, g)
        self.assertTrue(
            [f for f in self._codes(fs, "BANNED_SYNONYM")
             if "エラーハンドリング" in f.message])

    def test_the_section_name_itself_stays_masked(self):
        """ADR-135 の限界は保つ —— 節名そのものを禁じたら覆う（同点は覆いが勝つ）。"""
        g = self._glossary(table_a=["| 不具合記録 | 検査の記録 | エラー |"])
        fs = tc.check("## エンドポイント\na\n## 入出力\nb\n## エラー\nc\n",
                      {"type": "API"}, g)
        self.assertEqual(self._codes(fs, "BANNED_SYNONYM"), [])

    def test_longest_wins_is_an_axis_not_a_case(self):
        """軸で持つ —— 全節名について「S+付け を禁じれば発火し、## S は黙る」。"""
        names = sorted({n for secs in reg.REQUIRED_SECTIONS.values()
                        for n in secs})
        bad = []
        for name in names:
            longer = name + "の件"
            g = self._glossary(table_a=["| 代替語%d | 意味 | %s |"
                                        % (len(name), longer)])
            fs = tc.check("%s を述べる。" % longer, {"type": "IMPL"}, g)
            if not [f for f in self._codes(fs, "BANNED_SYNONYM")
                    if longer in f.message]:
                bad.append(longer)
        self.assertEqual(bad, [], "覆いに飲まれた長い禁止語: %r" % (bad[:5],))


class CalqueTokenSourceIsSingleTest(unittest.TestCase):
    """カルクの字面の解釈が二箇所に散らないこと（DECIDED-001 事実1）。"""

    def test_calque_tokens_helper_exists(self):
        self.assertTrue(hasattr(tc, "_calque_tokens"))

    def test_the_matcher_does_not_reparse_the_surface(self):
        import inspect
        src = inspect.getsource(tc._check_calque)
        self.assertNotIn('split("／")', src,
                         "カルクの字面の解釈は _calque_tokens に一本化する")
        self.assertNotIn('lstrip("〜")', src)


if __name__ == "__main__":
    unittest.main()
