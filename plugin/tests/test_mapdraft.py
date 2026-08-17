# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for map-draft-check.py (SPEC-029 / ADR-136).

決定的である: 壁時計を読まず --today を固定する。@rev / source_revision の検査は
git の無い素のディレクトリで「機械検証不能」へ退くこと(no-git の道)を確かめる。
追跡範囲は --trace-json で注入し、trace-index の子プロセス実行に依存しない。
"""
import contextlib
import io
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

TODAY = "2026-08-07"


def _source(**over):
    base = {"source": "doctrine: doctrine_docs/_system/non-goals.md",
            "locator": "第1項", "checked_at": "2026-08-03",
            "verdict": "present"}
    base.update(over)
    return base


def _model(**over):
    base = {
        "schema": "system-map/gold-model/0.2",
        "target": "fixture",
        "system": {"purpose": "p", "boundary": "b",
                   "provenance": [_source()], "review_status": "proposed"},
        "elements": [
            {"id": "e1", "name": "要素", "kind": "system", "purpose": "p",
             "responsibilities": ["r"], "owner": "o", "parent": None,
             "provenance": [_source()], "review_status": "proposed"},
        ],
        "flows": [],
        "contracts": [],
        "scenarios": [],
        "anchors": [],
    }
    base.update(over)
    return base


def _flow(prov, flow_id="f1"):
    return {"id": flow_id, "from": "e1", "to": "e1", "kind": "data",
            "label": "l", "payload_or_action": "p", "condition": "c",
            "provenance": prov, "review_status": "proposed"}


def _contract(prov, status="unknown"):
    return {"id": "c1", "subject": "e1", "assumptions": ["a"],
            "guarantee": "g", "response_measure": "m",
            "verification_status": status, "owner": "o",
            "provenance": prov, "review_status": "proposed"}


class _MapDraftFixture(unittest.TestCase):
    """共有のヘルパだけを持つ基底(試験は持たない)。

    継承で試験を増やすと、loader の収集数と索引(assurance の system_index)の
    件数が食い違う —— 試験メソッドの継承はしない。
    """

    def _repo(self):
        """git の無い素の木(no-git の道)。出所の実ファイルを一つ持つ。"""
        root = _util.make_repo({
            "doctrine_docs/_system/non-goals.md":
                "# やらないこと\n第1項 これはしない\n三行目\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _write_json(self, obj, name="model.json"):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        return path

    def _run(self, model, extra=None, repo=None):
        path = self._write_json(model)
        argv = ["--model", path, "--repo", repo or self._repo(),
                "--today", TODAY] + (extra or [])
        with contextlib.redirect_stderr(io.StringIO()):
            return _util.invoke("map-draft-check", argv=argv)


class MapDraftCheckTest(_MapDraftFixture):

    # -- 正例 -------------------------------------------------------------

    def test_valid_model_exit_0(self):
        out, code = self._run(_model())
        self.assertEqual(code, 0, out)
        self.assertIn("所見: 0 件", out)

    # -- D2: 出所の実在(捏造出所ゼロの門) --------------------------------

    def test_missing_source_path_is_d2_finding(self):
        m = _model()
        m["system"]["provenance"] = [
            _source(source="doctrine: doctrine_docs/_system/absent.md")]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D2_SOURCE_UNRESOLVED", out)

    def test_locator_line_beyond_eof_is_finding(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="L99")]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D2_SOURCE_UNRESOLVED", out)
        self.assertIn("行数", out)

    def test_locator_gyo_form_beyond_eof_is_finding(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="99行")]
        out, code = self._run(m)
        self.assertEqual(code, 1)

    def test_locator_quote_missing_is_finding(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="「存在しない引用」")]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("引用", out)

    def test_locator_quote_present_passes(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="「これはしない」")]
        out, code = self._run(m)
        self.assertEqual(code, 0, out)

    def test_silent_verdict_skips_quote_check(self):
        """負の出所の引用は「無いこと」の要約でありうる。実在を求めない。"""
        m = _model()
        m["system"]["provenance"] = [
            _source(locator="「性能の言及なし」", verdict="silent")]
        out, code = self._run(m)
        self.assertEqual(code, 0, out)

    def test_rev_without_git_degrades_to_unverifiable(self):
        """no-git の道: @rev は所見にならず機械検証不能の一覧へ退く。"""
        m = _model()
        m["system"]["provenance"] = [_source(
            source="doctrine: doctrine_docs/_system/non-goals.md@0123abc")]
        out, code = self._run(m, extra=["--json"])
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["findings"], [])
        self.assertTrue(any("0123abc" in u["source"]
                            for u in payload["unverifiable"]))

    def test_url_source_is_unverifiable_not_finding(self):
        m = _model()
        m["system"]["provenance"] = [
            _source(source="https://example.com/issues/1")]
        out, code = self._run(m, extra=["--json"])
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["findings"], [])
        self.assertTrue(any(u["source"].startswith("https://")
                            for u in payload["unverifiable"]))

    def test_prose_source_is_unverifiable_not_finding(self):
        m = _model()
        m["system"]["provenance"] = [_source(source="会話")]
        out, code = self._run(m)
        self.assertEqual(code, 0, out)
        self.assertIn("機械検証不能", out)

    def test_repo_prefix_filters_other_repos(self):
        """別接頭の出所は --repo で解決せず、実在しなくても所見にしない。"""
        m = _model()
        m["system"]["provenance"] = [_source(source="doctrine: no/such.md")]
        out, code = self._run(m, extra=["--repo-prefix", "doctrine-lens"])
        self.assertEqual(code, 0, out)
        self.assertIn("機械検証不能", out)

    # -- D3: 日付 ---------------------------------------------------------

    def test_future_checked_at_is_d3(self):
        m = _model()
        m["system"]["provenance"] = [_source(checked_at="2026-12-31")]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D3_BAD_DATE", out)

    def test_malformed_date_is_d3(self):
        m = _model()
        m["system"]["provenance"] = [_source(checked_at="2026/08/03")]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D3_BAD_DATE", out)

    # -- D4: アンカーと追跡範囲 -------------------------------------------

    def _anchor(self, target):
        return {"id": "a1", "target_kind": "code_range", "target": target,
                "source_revision": "0123abc", "observed_at": "2026-08-03",
                "authority": "doctrine"}

    def _trace_json(self, paths):
        return self._write_json(
            {"schema": "trace-index/1", "root": "x", "findings": [],
             "ranges": [{"id": "SPEC-001", "path": p, "begin_line": 1,
                         "end_line": 2, "fingerprint": "sha256:0"}
                        for p in paths]},
            name="trace.json")

    def test_anchor_path_absent_from_trace_is_d4(self):
        m = _model(anchors=[self._anchor("src/main.py の注釈対")])
        tj = self._trace_json(["src/other.py"])
        out, code = self._run(m, extra=["--trace-json", tj])
        self.assertEqual(code, 1)
        self.assertIn("D4_ANCHOR_UNMATCHED", out)

    def test_anchor_path_present_passes_and_rev_degrades(self):
        """一致すれば所見なし。source_revision は no-git で検証不能へ退く。"""
        m = _model(anchors=[self._anchor("src/other.py の注釈対")])
        tj = self._trace_json(["src/other.py"])
        out, code = self._run(m, extra=["--trace-json", tj])
        self.assertEqual(code, 0, out)
        self.assertIn("機械検証不能", out)

    # -- D5: 依存辺の Flow 化 --------------------------------------------

    def test_flow_provenance_citing_dep_graph_is_d5(self):
        m = _model(flows=[_flow([_source(locator="dep-graph --impacts の答え")])])
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D5_FLOW_FROM_DEP_EDGE", out)

    def test_flow_provenance_citing_depends_on_is_d5(self):
        m = _model(flows=[_flow([_source(source="doctrine: depends_on.md")])])
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D5_FLOW_FROM_DEP_EDGE", out)

    # -- D6: 負の出所 -----------------------------------------------------

    def test_unknown_contract_without_silent_is_d6(self):
        m = _model(contracts=[_contract([_source(verdict="present")])])
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D6_UNKNOWN_WITHOUT_NEGATIVE", out)

    def test_unknown_contract_with_silent_passes(self):
        m = _model(contracts=[_contract([_source(verdict="silent")])])
        out, code = self._run(m)
        self.assertEqual(code, 0, out)

    # -- D1: 自己確定 -----------------------------------------------------

    def test_confirmed_review_status_is_d1(self):
        m = _model()
        m["elements"][0]["review_status"] = "confirmed"
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D1_NOT_PROPOSED", out)

    # -- D7: 形と語彙 -----------------------------------------------------

    def test_missing_top_key_is_d7(self):
        m = _model()
        del m["anchors"]
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D7_SHAPE", out)

    def test_bad_enum_is_d7(self):
        m = _model(contracts=[_contract([_source(verdict="silent")],
                                        status="banana")])
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D7_SHAPE", out)

    def test_flow_missing_from_to_is_d7(self):
        f = _flow([_source()])
        del f["from"]
        del f["to"]
        m = _model(flows=[f])
        out, code = self._run(m)
        self.assertEqual(code, 1)
        self.assertIn("D7_SHAPE", out)

    # -- CLI: 終了コードと --json ----------------------------------------

    def test_missing_model_arg_is_usage_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            out, code = _util.invoke("map-draft-check",
                                     argv=["--repo", "/tmp"])
        self.assertEqual(code, 2)

    def test_unknown_arg_is_usage_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            out, code = _util.invoke("map-draft-check", argv=["--bogus"])
        self.assertEqual(code, 2)

    def test_model_file_missing_is_3(self):
        repo = self._repo()
        with contextlib.redirect_stderr(io.StringIO()):
            out, code = _util.invoke(
                "map-draft-check",
                argv=["--model", "/no/such/model.json", "--repo", repo])
        self.assertEqual(code, 3)

    def test_repo_missing_is_3(self):
        path = self._write_json(_model())
        with contextlib.redirect_stderr(io.StringIO()):
            out, code = _util.invoke(
                "map-draft-check",
                argv=["--model", path, "--repo", "/no/such/repo"])
        self.assertEqual(code, 3)

    def test_json_shape(self):
        out, code = self._run(_model(), extra=["--json"])
        self.assertEqual(code, 0, out)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "map-draft-check/1")
        self.assertEqual(payload["findings"], [])
        # INC-035: 散文の locator（「第1項」など）は、機械では位置を確かめ
        # られない。黙って緑にせず「機械検証不能」として数える。形の試験
        # なので、空であることではなく形が揃っていることを見る。
        self.assertIsInstance(payload["unverifiable"], list)
        for u in payload["unverifiable"]:
            self.assertEqual(sorted(u), ["reason", "source", "where"])
        self.assertEqual(payload["totals"]["findings"], 0)
        self.assertEqual(payload["totals"]["sources"], 2)

    def test_broken_json_model_is_d7_finding_exit_1(self):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "model.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        with contextlib.redirect_stderr(io.StringIO()):
            out, code = _util.invoke(
                "map-draft-check",
                argv=["--model", path, "--repo", self._repo()])
        self.assertEqual(code, 1)
        self.assertIn("D7_SHAPE", out)


class PerSourceVerdictTest(_MapDraftFixture):
    """出所ごとの機械の判定(ADR-171)。map-draft-check/1 の sources の欄。

    共有の基底(_repo・_write_json・_run)を使う。試験メソッドは継承しない。
    """

    def _payload(self, model, repo=None):
        out, _code = self._run(model, extra=["--json"], repo=repo)
        return json.loads(out)

    def _by_where(self, payload, where):
        for s in payload["sources"]:
            if s["where"] == where:
                return s
        raise AssertionError("出所が sources に無い: %s" % where)

    def test_matched_quote_is_verified(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="「これはしない」")]
        s = self._by_where(self._payload(m), "system.provenance[0]")
        self.assertEqual(s["verdict"], "verified")
        self.assertEqual(s["claimed"], "present")
        self.assertEqual(s["reasons"], [])

    def test_anchorless_locator_is_mixed(self):
        """ファイルの実在は検めたが、位置は機械検証の道が無い。"""
        s = self._by_where(self._payload(_model()), "system.provenance[0]")
        self.assertEqual(s["verdict"], "mixed")

    def test_missing_quote_is_mismatched(self):
        m = _model()
        m["system"]["provenance"] = [_source(locator="「存在しない引用」")]
        s = self._by_where(self._payload(m), "system.provenance[0]")
        self.assertEqual(s["verdict"], "mismatched")
        self.assertTrue(s["reasons"])

    def test_url_source_is_unverifiable(self):
        m = _model()
        m["system"]["provenance"] = [
            _source(source="https://example.com/spec")]
        s = self._by_where(self._payload(m), "system.provenance[0]")
        self.assertEqual(s["verdict"], "unverifiable")

    def test_unverifiable_rev_with_matched_quote_is_mixed(self):
        m = _model()
        m["system"]["provenance"] = [_source(
            source="doctrine: doctrine_docs/_system/non-goals.md@" + "a" * 40,
            locator="「これはしない」")]
        s = self._by_where(self._payload(m), "system.provenance[0]")
        self.assertEqual(s["verdict"], "mixed",
                         "引用は検めたが @rev は git の無い木で検証不能")

    def test_empty_source_is_malformed(self):
        m = _model()
        m["system"]["provenance"] = [_source(source="")]
        s = self._by_where(self._payload(m), "system.provenance[0]")
        self.assertEqual(s["verdict"], "malformed")

    def test_by_verdict_totals_match_sources(self):
        payload = self._payload(_model())
        by_verdict = payload["totals"]["by_verdict"]
        self.assertEqual(sorted(by_verdict),
                         ["malformed", "mismatched", "mixed",
                          "unverifiable", "verified"])
        self.assertEqual(sum(by_verdict.values()), len(payload["sources"]))
        self.assertEqual(len(payload["sources"]),
                         payload["totals"]["sources"])

    def test_repos_carries_revision_keys_not_paths(self):
        payload = self._payload(_model())
        self.assertEqual(len(payload["repos"]), 1)
        entry = payload["repos"][0]
        self.assertEqual(sorted(entry),
                         ["prefix", "source_dirty", "source_revision"])
        self.assertIsNone(entry["prefix"], "旧形の単一 --repo は接頭を持たない")
        self.assertIsNone(entry["source_revision"], "git の無い木は null")

    def test_new_form_repo_has_prefix(self):
        repo = self._repo()
        path = self._write_json(_model())
        with contextlib.redirect_stderr(io.StringIO()):
            out, _code = _util.invoke(
                "map-draft-check",
                argv=["--model", path, "--repo", "doctrine=%s" % repo,
                      "--today", TODAY, "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["repos"][0]["prefix"], "doctrine")

    def test_generator_names_the_tool(self):
        payload = self._payload(_model())
        self.assertEqual(payload["generator"]["name"], "map-draft-check.py")


if __name__ == "__main__":
    unittest.main()
