# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""意味モデル(MODEL 型)の解析・担保・描画の試験(SPEC-031 / ADR-163)。

検めるのは三つの面である。
- 解析: `### 見出し` の直下の ```json の塊を、節ごとに拾う(ADR-163 決定3)。
- 担保: 必須欄・語彙・id の一意・文書の中の参照・確定の同値(決定6・決定7)。
- 描画: .md から JSON への一方通行。決定的で、二度描けばバイト一致(ADR-161 決定3)。

温度差のある二つの入口(リンタと描き手)が同じ規則を使うことも、ここで検める
——規則の実体は共有コア `_model` に一つだけ在る(DECIDED-001 事実1)。
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

_model = _util.load_core("_model")


def _block(obj):
    return "```json\n%s\n```" % json.dumps(obj, ensure_ascii=False, indent=2)


SYSTEM = {
    "target": "demo",
    "purpose": "検証のための最小の系。",
    "boundary": "内側は demo、外側は利用者。",
    "provenance": [{"source": "demo: README.md", "locator": "L1",
                    "checked_at": "2026-08-14", "verdict": "present"}],
    "review_status": "proposed",
}
ELEMENT_A = {
    "id": "e-a", "name": "受け口", "kind": "component",
    "purpose": "外からの求めを受ける。", "responsibilities": ["受理"],
    "owner": "demo-maintainers",
    "provenance": [{"source": "demo: src/a.py", "locator": "L10",
                    "checked_at": "2026-08-14", "verdict": "present"}],
    "review_status": "proposed",
}
ELEMENT_B = dict(ELEMENT_A, id="e-b", name="蓄え", kind="subsystem")
FLOW = {
    "id": "f-1", "from": "e-a", "to": "e-b", "label": "書き込む",
    "kind": "data", "payload_or_action": "受理した記録", "condition": "常時",
    "provenance": [{"source": "demo: src/a.py", "locator": "「書き込む」",
                    "checked_at": "2026-08-14", "verdict": "present"}],
    "review_status": "proposed",
}
CONTRACT = {
    "id": "c-1", "subject": "e-b", "assumptions": ["定性的である"],
    "guarantee": "受理した記録を失わない。",
    "response_measure": "定性的である(測定基準は未定義)",
    "verification_status": "unknown", "owner": "demo-maintainers",
    "provenance": [{"source": "demo: README.md", "locator": "全文(言及なし)",
                    "checked_at": "2026-08-14", "verdict": "silent"}],
    "review_status": "proposed",
}
SCENARIO = {
    "id": "s-1", "name": "正常系", "kind": "normal",
    "steps": [{"actor": "e-a", "receiver": "e-b", "flow": "f-1"}],
    "provenance": [{"source": "demo: README.md", "locator": "L3",
                    "checked_at": "2026-08-14", "verdict": "present"}],
    "review_status": "proposed",
}
ANCHOR = {
    "id": "a-1", "target_kind": "document", "target": "demo: README.md",
    "source_revision": "0123456789abcdef0123456789abcdef01234567",
    "observed_at": "2026-08-14", "authority": "gold_model",
}


def body(system=SYSTEM, elements=(ELEMENT_A, ELEMENT_B), flows=(FLOW,),
         contracts=(CONTRACT,), scenarios=(SCENARIO,), anchors=(ANCHOR,)):
    """六つの節を持つ MODEL の本文を組む。"""
    parts = ["# デモの意味モデル", "", "## 系の概要", "", _block(system), ""]
    for name, items in (("要素の一覧", elements), ("流れの一覧", flows),
                        ("契約の一覧", contracts), ("シナリオの一覧", scenarios),
                        ("アンカーの一覧", anchors)):
        parts += ["## %s" % name, ""]
        for item in items:
            parts += ["### %s — %s" % (item["id"], item.get("name", "")), "",
                      _block(item), ""]
    return "\n".join(parts)


class ParseTest(unittest.TestCase):
    """節と塊の拾い方(ADR-163 決定3)。"""

    def test_blocks_are_collected_per_section(self):
        model, findings = _model.parse_model(body())
        self.assertEqual(findings, [])
        self.assertEqual(model["system"]["target"], "demo")
        self.assertEqual([e["id"] for e in model["elements"]], ["e-a", "e-b"])
        self.assertEqual([f["id"] for f in model["flows"]], ["f-1"])
        self.assertEqual([c["id"] for c in model["contracts"]], ["c-1"])
        self.assertEqual([s["id"] for s in model["scenarios"]], ["s-1"])
        self.assertEqual([a["id"] for a in model["anchors"]], ["a-1"])

    def test_blocks_outside_required_sections_are_not_values(self):
        """散文の例示を値にしない —— 必須節の外の塊は拾わない。"""
        text = body() + "\n## 補足\n\n" + _block(dict(ELEMENT_A, id="e-x")) + "\n"
        model, _ = _model.parse_model(text)
        self.assertEqual([e["id"] for e in model["elements"]], ["e-a", "e-b"])

    def test_unreadable_block_is_reported_not_raised(self):
        text = body().replace('"id": "f-1"', '"id": f-1', 1)
        model, findings = _model.parse_model(text)
        self.assertTrue(any(f.code == "MODEL_BAD_JSON" for f in findings))
        self.assertEqual(model["flows"], [])          # その塊だけ落ちる
        self.assertEqual(len(model["elements"]), 2)   # 他は生きている


class StructureTest(unittest.TestCase):
    """必須欄・語彙・一意・参照(ADR-163 決定7)。"""

    def _codes(self, text, status="proposed"):
        return sorted({f.code for f in _model.check_document(text, status)})

    def test_clean_model_has_no_findings(self):
        self.assertEqual(self._codes(body()), [])

    def test_missing_required_field(self):
        broken = dict(ELEMENT_A)
        del broken["owner"]
        self.assertIn("MODEL_MISSING_FIELD",
                      self._codes(body(elements=(broken, ELEMENT_B))))

    def test_bad_enum_value(self):
        self.assertIn("MODEL_BAD_ENUM",
                      self._codes(body(elements=(dict(ELEMENT_A, kind="module"),
                                                 ELEMENT_B))))

    def test_duplicate_id(self):
        self.assertIn("MODEL_DUPLICATE_ID",
                      self._codes(body(elements=(ELEMENT_A,
                                                 dict(ELEMENT_B, id="e-a")))))

    def test_heading_and_block_id_must_match(self):
        text = body().replace("### e-b — 蓄え", "### e-z — 蓄え", 1)
        self.assertIn("MODEL_HEADING_ID_MISMATCH", self._codes(text))

    def test_dangling_flow_endpoint(self):
        self.assertIn("MODEL_DANGLING_REF",
                      self._codes(body(flows=(dict(FLOW, to="e-missing"),))))

    def test_dangling_scenario_step(self):
        bad = dict(SCENARIO, steps=[{"actor": "e-a", "receiver": "e-b",
                                     "flow": "f-none"}])
        self.assertIn("MODEL_DANGLING_REF", self._codes(body(scenarios=(bad,))))

    def test_self_loop_needs_a_reason(self):
        loop = dict(FLOW, id="f-self", to="e-a")
        self.assertIn("MODEL_SELF_LOOP_WITHOUT_REASON",
                      self._codes(body(flows=(loop,))))
        ok = dict(loop, self_loop_reason="再入する")
        self.assertNotIn("MODEL_SELF_LOOP_WITHOUT_REASON",
                         self._codes(body(flows=(ok,))))

    def test_provenance_must_be_a_nonempty_list(self):
        self.assertIn("MODEL_BAD_PROVENANCE",
                      self._codes(body(elements=(dict(ELEMENT_A, provenance=[]),
                                                 ELEMENT_B))))

    def test_provenance_verdict_vocabulary(self):
        bad = dict(ELEMENT_A, provenance=[dict(ELEMENT_A["provenance"][0],
                                               verdict="maybe")])
        self.assertIn("MODEL_BAD_ENUM", self._codes(body(elements=(bad, ELEMENT_B))))

    def test_missing_system_section(self):
        text = body().replace("## 系の概要", "## 別の見出し", 1)
        self.assertIn("MODEL_MISSING_SYSTEM", self._codes(text))


class HardeningTest(unittest.TestCase):
    """独立検証(2026-08-14)が挙げた壊れ方を凍らせる(ADR-164)。"""

    def _findings(self, text, status="proposed"):
        return _model.check_document(text, status)

    def _codes(self, text, status="proposed"):
        return sorted({f.code for f in self._findings(text, status)})

    def test_realized_by_that_is_not_a_list_does_not_raise(self):
        """配列でない realized_by で例外を漏らさない(リンタが全検査を落とす形を防ぐ)。"""
        for value in (3, "a-1", {"a": 1}):
            codes = self._codes(body(elements=(dict(ELEMENT_A, realized_by=value),
                                               ELEMENT_B)))
            self.assertIn("MODEL_BAD_REALIZED_BY", codes)
            self.assertNotIn("MODEL_DANGLING_REF", codes,
                             "文字列を一字ずつ辿らない")

    def test_null_value_counts_as_a_missing_field(self):
        """鍵が在っても値が null なら欠落と数える(器は出所を一件以上要する)。"""
        self.assertIn("MODEL_MISSING_FIELD",
                      self._codes(body(elements=(dict(ELEMENT_A, provenance=None),
                                                 ELEMENT_B))))
        self.assertIn("MODEL_MISSING_FIELD",
                      self._codes(body(system=dict(SYSTEM, purpose=None))))

    def test_id_must_be_a_non_empty_string(self):
        for bad in (1, "", "  ", None):
            self.assertIn("MODEL_BAD_ID",
                          self._codes(body(elements=(dict(ELEMENT_A, id=bad),
                                                     ELEMENT_B))),
                          repr(bad))

    def test_empty_id_is_not_a_reference_target(self):
        text = body(elements=(dict(ELEMENT_A, id=""), ELEMENT_B),
                    flows=(dict(FLOW, **{"from": ""}),))
        self.assertIn("MODEL_DANGLING_REF", self._codes(text))

    def test_heading_without_a_block_is_reported(self):
        """見出しが在るのに塊が無い実体は、黙って投影から消えない。"""
        text = body() + "\n## 要素の一覧\n\n### e-c — 塊を書き忘れた\n\n（説明だけ）\n"
        self.assertIn("MODEL_HEADING_WITHOUT_BLOCK", self._codes(text))

    def test_non_json_fence_is_reported_through_the_heading(self):
        text = body().replace("### e-b — 蓄え\n\n```json", "### e-b — 蓄え\n\n```", 1)
        self.assertIn("MODEL_HEADING_WITHOUT_BLOCK", self._codes(text))

    def test_retired_models_keep_their_confirmed_values(self):
        """引退した位置づけでは確定の同値を検めない(引退の道を塞がない)。"""
        confirmed = body(system=dict(SYSTEM, review_status="confirmed"),
                         elements=(dict(ELEMENT_A, review_status="confirmed"),
                                   dict(ELEMENT_B, review_status="confirmed")),
                         flows=(dict(FLOW, review_status="confirmed"),),
                         contracts=(dict(CONTRACT, review_status="confirmed"),),
                         scenarios=(dict(SCENARIO, review_status="confirmed"),))
        for status in ("deprecated", "superseded", "archived"):
            self.assertEqual(self._codes(confirmed, status), [], status)

    def test_confirmed_not_current_is_a_warning_and_does_not_order_the_machine(self):
        """機械へ『確定せよ』とは言わない。段も WARN に留める(ADR-164 決定4)。"""
        confirmed = body(system=dict(SYSTEM, review_status="confirmed"),
                         elements=(dict(ELEMENT_A, review_status="confirmed"),
                                   dict(ELEMENT_B, review_status="confirmed")),
                         flows=(dict(FLOW, review_status="confirmed"),),
                         contracts=(dict(CONTRACT, review_status="confirmed"),),
                         scenarios=(dict(SCENARIO, review_status="confirmed"),))
        found = [f for f in self._findings(confirmed, "proposed")
                 if f.code == "MODEL_CONFIRMED_NOT_CURRENT"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, "WARN")
        self.assertIn("人が行う", found[0].message)
        self.assertNotIn("current へ", found[0].message)

    def test_section_names_are_derived_from_the_registry(self):
        """節名を写さない(登録簿から導く。WATCH-001 第2項)。"""
        reg = _util.load_core("_registry")
        names = reg.required_sections("MODEL")
        self.assertEqual(_model.SYSTEM_SECTION, names[0])
        self.assertEqual(tuple(_model.SECTION_FOR_LIST[k]
                               for k in _model.ENTITY_LISTS), tuple(names[1:]))

    def test_prose_values_carry_only_prose_fields(self):
        model, _ = _model.parse_model(body())
        values = [v for _w, _l, v in _model.prose_values(model)]
        self.assertIn("受け口", values)             # name は散文の欄
        self.assertIn("受理", values)               # responsibilities の要素
        self.assertNotIn("e-a", values)             # id は機械の値
        self.assertNotIn("component", values)       # 種別は機械の値
        self.assertNotIn("2026-08-14", values)      # 日付は機械の値


class ConfirmationTest(unittest.TestCase):
    """確定の一押しは status で表す(ADR-163 決定6)。"""

    def _codes(self, text, status):
        return sorted({f.code for f in _model.check_document(text, status)})

    def test_current_with_proposed_values_is_an_error(self):
        self.assertIn("MODEL_UNCONFIRMED_IN_CURRENT",
                      self._codes(body(), "current"))

    def test_all_confirmed_but_not_current_is_an_error(self):
        conf = {k: dict(v, review_status="confirmed") if isinstance(v, dict) else v
                for k, v in {"s": SYSTEM}.items()}
        text = body(system=conf["s"],
                    elements=(dict(ELEMENT_A, review_status="confirmed"),
                              dict(ELEMENT_B, review_status="confirmed")),
                    flows=(dict(FLOW, review_status="confirmed"),),
                    contracts=(dict(CONTRACT, review_status="confirmed"),),
                    scenarios=(dict(SCENARIO, review_status="confirmed"),))
        self.assertIn("MODEL_CONFIRMED_NOT_CURRENT", self._codes(text, "proposed"))

    def test_all_confirmed_and_current_is_clean(self):
        text = body(system=dict(SYSTEM, review_status="confirmed"),
                    elements=(dict(ELEMENT_A, review_status="confirmed"),
                              dict(ELEMENT_B, review_status="confirmed")),
                    flows=(dict(FLOW, review_status="confirmed"),),
                    contracts=(dict(CONTRACT, review_status="confirmed"),),
                    scenarios=(dict(SCENARIO, review_status="confirmed"),))
        self.assertEqual(self._codes(text, "current"), [])

    def test_anchors_do_not_carry_confirmation(self):
        """アンカーは値を担わない(指し先の記述)。review_status を求めない。"""
        codes = self._codes(body(), "proposed")
        self.assertNotIn("MODEL_MISSING_FIELD", codes)


class RenderTest(unittest.TestCase):
    """一方通行の描画(ADR-161 決定3)。"""

    def test_json_shape_and_schema(self):
        model, _ = _model.parse_model(body())
        out = json.loads(_model.render_json(model))
        self.assertEqual(out["schema"], _model.MODEL_SCHEMA)
        self.assertEqual(out["target"], "demo")
        self.assertEqual(sorted(out), sorted(_model.TOP_KEYS))
        self.assertNotIn("target", out["system"])   # 最上位へ持ち上げる
        self.assertEqual([e["id"] for e in out["elements"]], ["e-a", "e-b"])

    def test_internal_bookkeeping_never_leaks(self):
        model, _ = _model.parse_model(body())
        text = _model.render_json(model)
        self.assertNotIn("_line", text)
        self.assertNotIn("_heading", text)

    def test_deterministic_and_idempotent(self):
        model_a, _ = _model.parse_model(body())
        model_b, _ = _model.parse_model(body())
        self.assertEqual(_model.render_json(model_a), _model.render_json(model_b))

    def test_document_order_is_preserved(self):
        model, _ = _model.parse_model(body(elements=(ELEMENT_B, ELEMENT_A)))
        out = json.loads(_model.render_json(model))
        self.assertEqual([e["id"] for e in out["elements"]], ["e-b", "e-a"])


class RendererCliTest(unittest.TestCase):
    """render-projection の model モード(書き出し・--check・--id)。"""

    def _repo(self, text, status="proposed"):
        doc = ("---\nid: MODEL-001\ntitle: デモの意味モデル\ntype: MODEL\n"
               "domain: demo\nstatus: %s\nowner: demo-maintainers\n"
               "created: 2026-08-14\nupdated: 2026-08-14\nsources: []\n"
               "llm_context: task\n---\n\n" % status) + text
        root = _util.make_repo({
            "doctrine_docs/_system/glossary.md":
                "---\nid: GLOSSARY-001\ntitle: 用語\ntype: GLOSSARY\n"
                "domain: _system\nstatus: current\nowner: x\n"
                "updated: 2026-08-14\nsources: []\n---\n\n# 用語\n",
            "doctrine_docs/demo/model/MODEL-001-demo.md": doc,
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_render_writes_sibling_json(self):
        root = self._repo(body())
        docs = os.path.join(root, "doctrine_docs")
        out, rc = _util.invoke("render-projection.py",
                               ["model", "--docs-root", docs])
        self.assertEqual(rc, 0, out)
        target = os.path.join(docs, "demo", "model", "MODEL-001-demo.json")
        self.assertTrue(os.path.exists(target))
        self.assertEqual(json.loads(_util.read(target))["target"], "demo")

    def test_check_detects_missing_and_drifted_projection(self):
        root = self._repo(body())
        docs = os.path.join(root, "doctrine_docs")
        _out, rc = _util.invoke("render-projection.py",
                                ["model", "--docs-root", docs, "--check"])
        self.assertEqual(rc, 1, "未生成はドリフト扱い")
        _util.invoke("render-projection.py", ["model", "--docs-root", docs])
        _out, rc = _util.invoke("render-projection.py",
                                ["model", "--docs-root", docs, "--check"])
        self.assertEqual(rc, 0)
        target = os.path.join(docs, "demo", "model", "MODEL-001-demo.json")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        _out, rc = _util.invoke("render-projection.py",
                                ["model", "--docs-root", docs, "--check"])
        self.assertEqual(rc, 1, "手で直した JSON はドリフトとして落ちる")

    def test_broken_model_is_not_rendered(self):
        root = self._repo(body(flows=(dict(FLOW, to="e-missing"),)))
        docs = os.path.join(root, "doctrine_docs")
        _out, rc = _util.invoke("render-projection.py",
                                ["model", "--docs-root", docs])
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(
            os.path.join(docs, "demo", "model", "MODEL-001-demo.json")))

    def test_unknown_id_is_missing_target(self):
        root = self._repo(body())
        docs = os.path.join(root, "doctrine_docs")
        _out, rc = _util.invoke(
            "render-projection.py",
            ["model", "--docs-root", docs, "--id", "MODEL-999"])
        self.assertEqual(rc, 3)

    def test_out_requires_a_single_id(self):
        out, rc = _util.invoke("render-projection.py",
                               ["model", "--out", "-"])
        self.assertEqual(rc, 2)
        self.assertIn("--id", out)

    def test_all_includes_the_model_projection(self):
        root = self._repo(body())
        docs = os.path.join(root, "doctrine_docs")
        _out, rc = _util.invoke("render-projection.py",
                                ["all", "--docs-root", docs])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(
            os.path.join(docs, "demo", "model", "MODEL-001-demo.json")))


class LinterWiringTest(unittest.TestCase):
    """リンタが同じ規則を使う(規則を二重定義しない)。"""

    def _lint(self, text, status="proposed"):
        doc = ("---\nid: MODEL-001\ntitle: デモの意味モデル\ntype: MODEL\n"
               "domain: demo\nstatus: %s\nowner: demo-maintainers\n"
               "created: 2026-08-14\nupdated: 2026-08-14\nsources: []\n"
               "llm_context: task\n---\n\n" % status) + text
        root = _util.make_repo({
            "doctrine_docs/_system/glossary.md":
                "---\nid: GLOSSARY-001\ntitle: 用語\ntype: GLOSSARY\n"
                "domain: _system\nstatus: current\nowner: x\n"
                "updated: 2026-08-14\nsources: []\n---\n\n# 用語\n",
            "doctrine_docs/demo/model/MODEL-001-demo.md": doc,
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        path = os.path.join(root, "doctrine_docs", "demo", "model",
                            "MODEL-001-demo.md")
        out, rc = _util.invoke("docs-linter.py", [path])
        self.assertEqual(rc, 0, "リンタは常に 0 で返す(拒否はガードの領分)")
        return out

    def test_clean_model_passes_the_linter(self):
        out = self._lint(body())
        self.assertNotIn("MODEL_", out)

    def test_dangling_reference_is_reported_as_error(self):
        out = self._lint(body(flows=(dict(FLOW, to="e-missing"),)))
        self.assertIn("MODEL_DANGLING_REF", out)
        self.assertIn("[ERROR]", out)

    def test_missing_sections_are_still_reported(self):
        """必須節の検査は登録簿の側が持ち、本文の検査と重ならない。"""
        out = self._lint("# デモ\n\n## 系の概要\n\n" + _block(SYSTEM) + "\n")
        self.assertIn("MISSING_SECTION", out)


if __name__ == "__main__":
    unittest.main()
