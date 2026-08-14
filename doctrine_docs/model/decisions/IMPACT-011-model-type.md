---
id: IMPACT-011
title: 意味モデルの型 MODEL の新設の影響（CHANGE-011）
type: IMPACT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-14
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
depends_on: [CHANGE-011]
llm_context: task
---

# 意味モデルの型 MODEL の新設の影響（CHANGE-011）

決定の正本は ADR-163（型の設計）であり、その上位の方向づけは ADR-161（正本は .md、JSON は
一方通行の投影）、凍結の解除は ADR-162 が持つ。

## 影響する文書

第一波で直したもの:

- `doctrine_docs/model/spec/SPEC-001-registry-contract.md` — 型の件数の表記を件数の書かない
  形へ、受入基準へ必須節を加え、実装の指紋を打ち直した。
- `doctrine_docs/model/spec/DATA-001-registry-frontmatter-schema.md` — 型コードの列挙・既定値・
  置き場所・点検周期・必須節に MODEL を足した。
- `doctrine_docs/model/ICD.md` — type-registry の宣言に MODEL を足した。
- `doctrine_docs/model/test/TEST-001-registry.md` — MODEL の登録の凍結を受入基準へ足した。
- `spec/doctrine.ja.md` §3.2 の型表 — MODEL の行を足した。これに伴い
  `doctrine_docs/model/external/EXT-003-upstream-spec.md` の指紋を打ち直した。
- `doctrine_docs/authoring/spec/SPEC-017-templates.md`・`doctrine_docs/authoring/ICD.md`・
  `doctrine_docs/authoring/implementation/IMPL-016-skills-templates.md`・
  `doctrine_docs/authoring/test/TEST-017-templates.md` — 雛形の件数の表記を、件数を書かない
  形へ改めた（ADR-075）。

第二波で直したもの: **SPEC-031・TEST-031**（新設。共有コアの契約と受入）・SPEC-007（リンタの
検査群）・SPEC-014（描画の口）・ICD-006（描く口の宣言）・ICD-001（`semantic-model-shape` の
宣言）・SPEC-029（語彙の写しの廃止と門の掛け先）・TEST-007・TEST-014。

第三波で直したもの: `plugin/skills/system-map-draft/SKILL.md` と参照三点
（`acceptance-gates.md`・`model-shape.md`）、SPEC-016 の技能の記述。あわせて実例
`doctrine_docs/packaging/model/MODEL-001-doctrine.md` と、その投影
`MODEL-001-doctrine.json` を同梱した。

実例の門の実測（2026-08-14）: リンタ所見 0 件 / 描画 成功 / 出所の門は **出所 12 件・所見 0 件・
機械検証不能 0 件**。M 層（lens 側 validator）は**回していない** —— 実行に複製の取得（通信）が
要り、本波の作業では行っていない。

## 影響する実装

- `plugin/scripts/_registry.py` — 六つの表に MODEL の行を足した（`doctrine:begin SPEC-001` の
  印の内側なので指紋を打ち直した）。
- `plugin/templates/model.md.tmpl` — 新設。`plugin/templates/` は追跡の対象外である
  （設定の `trace_exempt`。生成の種であり、統治は生成先の木が行う）。
- `plugin/skills/doc-author/references/lazy-domain-gen.md` — 層の遅延生成の一覧へ
  `MODEL` → `<domain>/model/` を足した。あわせて、以前の型追加が取り残していた `PROC` →
  `<domain>/procedures/` と `EXT` → `<domain>/external/` も補った。
- 触らないもの: `scaffold.py`（`--list-sections` は登録簿をその場で読むので自動で追随する）。

第二波の実装:

- `plugin/scripts/_model.py`（新設。印の対で SPEC-031 と結び、指紋を記録した）。
- `plugin/scripts/docs-linter.py`（`_check_model` を足した。印の内側は触っていないので
  SPEC-007 の指紋は動かない）。
- `plugin/scripts/render-projection.py`（`model` モード・`--id`・隣へ `.json` を描く口。
  `MODES` は印の内側なので SPEC-014 の指紋を打ち直した）。
- `plugin/scripts/map-draft-check.py`（語彙の写しを共有コアへ寄せた。印の内側なので SPEC-029 の
  指紋を打ち直した）。
- `plugin/tests/test_model.py`（新設。31 件）。

## 影響するテスト

- `plugin/tests/test_registry.py` — `EXPECTED_TYPES`・既定値の二表・`EXPECTED_TYPE_LOCATION`
  へ MODEL を足し、`test_types_in_order` の件数の直書きを表の長さへ改め、
  `test_model_registration` と点検周期の主張を足した。
- `plugin/tests/test_linter.py` — `EXPECTED_REQUIRED_SECTIONS` へ MODEL の六節を足した。
- `plugin/tests/test_templates.py` — 在庫表へ `model.md.tmpl` を足した。
- `plugin/tests/test_termcheck.py` — 直していない。ただし**この試験が設計の欠陥を捕まえた**:
  節名「流れ」を置いた初版で `test_operational_extends_seed` が落ちた（節名は用語チェッカーの
  照合から外れるため、その語を禁止同義語に持つ木で照合が黙って落ちる。ADR-135）。節名を
  複合語（「流れの一覧」など）へ改めて解いた。

## 工数見積

第一波は半日規模（実測: 登録簿の六表・雛形一枚・凍結表三本・宣言六文書・指紋二本）。
第二波（本文の構造を検める解析器と検査群、`.md` から JSON を描く口、対応する SPEC と TEST）は
一日規模、第三波（起草の技能の書き換えと実例）は半日規模と見込む。**見込みであり、測った値
ではない。**

<!-- 入れない: 感想、設計の理由（ADR-163 が持つ） -->
