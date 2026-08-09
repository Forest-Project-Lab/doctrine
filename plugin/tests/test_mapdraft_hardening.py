#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""出所の機械検証が素通りさせていた形を塞ぐ（INC-035）。

独立再監査 2026-08-09 の故障注入が、宣言された 4 検出は全発火する一方で
**約 35 の素通り経路**を実測した。全要素を捏造したモデルが
`所見: 0 件 / 機械検証不能: 0 件` で終了コード 0 になる。

ここで凍結するのは、素通りしていた形が**所見か「機械検証不能」のどちらかへ
必ず落ちる**こと。黙って緑にしないことが要点であり、すべてを所見にする
必要はない —— 検証の道が無いものは、道が無いと言えばよい。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

CHECK = os.path.join(_util.SCRIPTS, "map-draft-check.py")


def _model(**over):
    m = {
        "schema": "system-map/gold-model/0.1",
        "target": "fixture",
        "system": {"purpose": "p", "boundary": "b", "review_status": "proposed",
                   "provenance": [{"source": "doctrine: real.md",
                                   "locator": "L1「実在する一行目の文」",
                                   "checked_at": "2026-08-03",
                                   "verdict": "present"}]},
        "elements": [], "flows": [], "contracts": [], "scenarios": [],
        "anchors": [],
    }
    m.update(over)
    return m


class HardeningBase(unittest.TestCase):
    def setUp(self):
        base = tempfile.mkdtemp(prefix="mdc-repo-")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        # 接頭の既定は --repo の名なので、木の名を doctrine にする。
        self.repo = os.path.join(base, "doctrine")
        os.makedirs(self.repo)
        with open(os.path.join(self.repo, "real.md"), "w", encoding="utf-8") as fh:
            fh.write("実在する一行目の文\n"
                     + "".join("埋め草の行 %d\n" % i for i in range(2, 20))
                     + "二十行目に引用したい語句がある\n")
        self.work = tempfile.mkdtemp(prefix="mdc-work-")
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def run_check(self, model, *extra):
        path = os.path.join(self.work, "m.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(model, fh, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, CHECK, "--model", path, "--repo", self.repo,
             "--today", "2026-08-09", "--json"] + list(extra),
            capture_output=True, text=True, timeout=300,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            data = {"findings": [], "unverifiable": [], "_raw": proc.stdout}
        return proc.returncode, data

    def assertNotSilentlyGreen(self, model, why, *extra):
        """所見か「機械検証不能」のどちらかへ落ちること（黙って緑にしない）。"""
        rc, data = self.run_check(model, *extra)
        landed = len(data.get("findings", [])) + len(data.get("unverifiable", []))
        self.assertGreater(
            landed, 0,
            "%s が黙って緑になった (rc=%s, %r)" % (why, rc, data)[:400])

    def assertFinding(self, model, why, *extra):
        rc, data = self.run_check(model, *extra)
        self.assertTrue(data.get("findings"),
                        "%s が所見にならない (rc=%s, %r)" % (why, rc, data)[:400])


class BaselineStillPassesTest(HardeningBase):
    def test_an_honest_model_passes(self):
        rc, data = self.run_check(_model())
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["findings"], [])
        self.assertEqual(data["unverifiable"], [])


class ProvenanceMustExistTest(HardeningBase):
    def test_missing_provenance_is_not_silently_green(self):
        m = _model()
        del m["system"]["provenance"]
        self.assertNotSilentlyGreen(m, "provenance を丸ごと省いた模型")

    def test_non_list_provenance_is_not_silently_green(self):
        m = _model()
        m["system"]["provenance"] = "doctrine: 何か"
        self.assertNotSilentlyGreen(m, "provenance が配列でない模型")

    def test_empty_provenance_is_not_silently_green(self):
        m = _model()
        m["system"]["provenance"] = []
        self.assertNotSilentlyGreen(m, "provenance が空配列の模型")

    def test_non_dict_source_items_are_not_silently_green(self):
        m = _model()
        m["system"]["provenance"] = ["doctrine: どこにも無い.md"]
        self.assertNotSilentlyGreen(m, "Source が dict でない模型")


class PathSafetyTest(HardeningBase):
    def test_absolute_path_is_a_finding(self):
        m = _model()
        m["system"]["provenance"][0]["source"] = "doctrine: /etc/hosts"
        m["system"]["provenance"][0]["locator"] = "L1"
        self.assertFinding(m, "絶対パスの出所")

    def test_parent_traversal_is_a_finding(self):
        m = _model()
        m["system"]["provenance"][0]["source"] = "doctrine: ../../etc/passwd"
        m["system"]["provenance"][0]["locator"] = "L1"
        self.assertFinding(m, "`..` で作業木の外を指す出所")

    def test_a_symlink_escaping_the_repo_is_a_finding(self):
        link = os.path.join(self.repo, "escape.md")
        try:
            os.symlink("/etc/hosts", link)
        except OSError:
            self.skipTest("シンボリックリンクを作れない環境")
        m = _model()
        m["system"]["provenance"][0]["source"] = "doctrine: escape.md"
        m["system"]["provenance"][0]["locator"] = "L1"
        self.assertFinding(m, "作業木の外へ抜けるシンボリックリンク")


class LocatorMustActuallyLocateTest(HardeningBase):
    def test_a_locator_with_no_anchor_is_not_silently_green(self):
        m = _model()
        m["system"]["provenance"][0]["locator"] = "第4章 性能要件の表 3-2、右列"
        self.assertNotSilentlyGreen(m, "行番号も引用も無い locator")

    def test_a_quote_from_a_different_line_is_a_finding(self):
        """L1 と言いながら三行目の語句を引く形。"""
        m = _model()
        m["system"]["provenance"][0]["locator"] = "L1「引用したい語句」"
        self.assertFinding(m, "引いた行と引用の行が違う出所")

    def test_a_quote_at_the_cited_line_passes(self):
        m = _model()
        m["system"]["provenance"][0]["locator"] = "L20「引用したい語句」"
        rc, data = self.run_check(m)
        self.assertEqual(data["findings"], [])

    def test_a_one_character_quote_is_not_silently_green(self):
        m = _model()
        m["system"]["provenance"][0]["locator"] = "L1「の」"
        self.assertNotSilentlyGreen(m, "一文字の引用")

    def test_lowercase_l_line_number_is_still_checked(self):
        m = _model()
        m["system"]["provenance"][0]["locator"] = "l99999"
        self.assertNotSilentlyGreen(m, "小文字 l の行番号")

    def test_spaced_line_number_is_still_checked(self):
        m = _model()
        m["system"]["provenance"][0]["locator"] = "99999 行"
        self.assertNotSilentlyGreen(m, "空白入りの行番号")


class SilentVerdictMeansAbsenceTest(HardeningBase):
    def test_a_silent_source_whose_quote_is_present_is_a_finding(self):
        """負の出所の主張は「無いこと」である。在れば主張が偽。"""
        m = _model()
        m["system"]["provenance"][0]["verdict"] = "silent"
        m["system"]["provenance"][0]["locator"] = "「引用したい語句」"
        self.assertFinding(m, "silent と言いながら本文に在る引用")

    def test_a_silent_source_whose_quote_is_absent_passes(self):
        m = _model()
        m["system"]["provenance"][0]["verdict"] = "silent"
        m["system"]["provenance"][0]["locator"] = "「どこにも書かれていない語」"
        rc, data = self.run_check(m)
        self.assertEqual(data["findings"], [], data)


class SelfConfirmationTest(HardeningBase):
    def test_missing_review_status_is_not_silently_green(self):
        m = _model()
        del m["system"]["review_status"]
        self.assertNotSilentlyGreen(m, "review_status を省いた模型")

    def test_nested_confirmed_is_a_finding(self):
        m = _model()
        m["contracts"] = [{
            "id": "c1", "review_status": "proposed",
            "verification_status": "verified",
            "provenance": m["system"]["provenance"],
            "evidence": [{"ref": "x", "review_status": "confirmed"}]}]
        self.assertFinding(m, "入れ子の confirmed")


class ShapeAndIntegrityTest(HardeningBase):
    def test_non_dict_list_items_are_a_finding(self):
        m = _model()
        m["elements"] = ["ghost", 42, None]
        self.assertFinding(m, "リストの中の非 dict 要素")

    def test_a_flow_pointing_at_a_missing_element_is_a_finding(self):
        m = _model()
        m["elements"] = [{"id": "e1", "name": "n", "kind": "system",
                          "review_status": "proposed",
                          "provenance": m["system"]["provenance"]}]
        m["flows"] = [{"id": "f1", "from": "居ない要素", "to": "e1",
                       "label": "x", "review_status": "proposed",
                       "provenance": m["system"]["provenance"]}]
        self.assertFinding(m, "実在しない要素を指す Flow")

    def test_duplicate_ids_are_a_finding(self):
        m = _model()
        e = {"id": "e1", "name": "n", "kind": "system",
             "review_status": "proposed", "provenance": m["system"]["provenance"]}
        m["elements"] = [dict(e), dict(e)]
        self.assertFinding(m, "id の重複")

    def test_deep_nesting_does_not_crash_into_the_missing_target_code(self):
        """再帰の深さで落ちても、終了コードは「対象が無い」に化けないこと。

        json.dump 自身も深い入れ子で再帰するので、生の文字列で書き出す。
        """
        depth = 20000
        deep = "{\"n\":" * depth + "null" + "}" * depth
        base = json.dumps(_model(), ensure_ascii=False)
        raw = base[:-1] + ', "deep": ' + deep + "}"
        path = os.path.join(self.work, "deep.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(raw)
        proc = subprocess.run(
            [sys.executable, CHECK, "--model", path, "--repo", self.repo,
             "--today", "2026-08-09", "--json"],
            capture_output=True, text=True, timeout=300,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertNotEqual(
            proc.returncode, 3,
            "深い入れ子が『対象が無い』(3)に化けた: %s"
            % (proc.stdout or proc.stderr)[:300])


class DepEdgeEvasionTest(HardeningBase):
    def test_japanese_paraphrase_of_a_dependency_edge_is_caught(self):
        m = _model()
        m["elements"] = [{"id": "e1", "name": "n", "kind": "system",
                          "review_status": "proposed",
                          "provenance": m["system"]["provenance"]}]
        m["flows"] = [{"id": "f1", "from": "e1", "to": "e1", "label": "x",
                       "review_status": "proposed",
                       "self_loop_reason": "r",
                       "provenance": [{"source": "doctrine: real.md",
                                       "locator": "依存グラフの辺から起こした",
                                       "checked_at": "2026-08-03",
                                       "verdict": "present"}]}]
        self.assertFinding(m, "依存グラフの辺の和文の言い換え")


class PrefixTest(HardeningBase):
    def test_a_foreign_prefix_is_not_validated_against_this_repo(self):
        """他リポジトリを読んだという主張を、こちらの木で検証しない。"""
        m = _model()
        # 自リポジトリの出所に、越境の引用を一つ混ぜる（多数派が検証対象）。
        m["system"]["provenance"].append(
            {"source": "doctrine: real.md", "locator": "L1「実在する一行目の文」",
             "checked_at": "2026-08-03", "verdict": "present"})
        m["system"]["provenance"].append(
            {"source": "doctrine-lens: real.md", "locator": "L1「実在する一行目の文」",
             "checked_at": "2026-08-03", "verdict": "present"})
        rc, data = self.run_check(m)
        self.assertEqual(
            data["findings"], [],
            "他リポジトリの出所を所見にしてはならない: %r" % (data,))
        self.assertTrue(
            data["unverifiable"],
            "他リポジトリの出所は『機械検証不能』へ回すこと: %r" % (data,))


if __name__ == "__main__":
    unittest.main()
