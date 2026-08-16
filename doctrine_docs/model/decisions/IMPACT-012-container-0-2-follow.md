---
id: IMPACT-012
title: 器 0.2 への追随と requirements 口への参照切り替えの影響（CHANGE-012）
type: IMPACT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
depends_on: [CHANGE-012]
llm_context: task
---

# 器 0.2 への追随と requirements 口への参照切り替えの影響（CHANGE-012）

決定の正本は ADR-168。その土台は ADR-165（器の形を写さず、固定した一枚から導く）である。

## 影響する文書

- `doctrine_docs/model/decisions/ADR-168-container-0-2-and-requirements-port.md` — 新設。
  追随の決定・版の進め方の規約の改まり・requirements 口への参照切り替え。
- `doctrine_docs/model/external/EXT-007-gold-model-schema.md` — 依存の対象を 0.2 の一枚へ
  付け替え、固定点と指紋を打ち直す。
- `doctrine_docs/model/external/EXT-008-requirements-port.md` — 新設。requirements 口への
  依存の登録。
- `doctrine_docs/model/spec/SPEC-031-model-body-contract.md` — 同梱の一枚の道と、版の
  進め方の規約の指し先（器の `$comment` が正本）を更新。
- `doctrine_docs/authoring/spec/SPEC-029-map-draft-check.md` — 器の版名の表記を更新。

## 影響する実装

- `plugin/schemas/system-map-gold-model-0.2.json` — 固定点から採った一枚を同梱
  （`system-map-gold-model-0.1.json` は置き換えて取り除く。同梱は一枚だけ）。
- `plugin/scripts/_model.py` — 読み込む道と冒頭の註釈の版名。
- `plugin/scripts/map-draft-check.py` — 冒頭の註釈の版名。
- `plugin/README.md` — 部品表の版名。
- `plugin/skills/system-map-draft/references/acceptance-gates.md` — 第四門の固定点を 0.2 の
  tag へ動かし、requirements 口の参照を足す。
- `plugin/skills/system-map-draft/references/model-shape.md` — 器の版名。

## 影響するテスト

- `plugin/tests/test_model.py` — `SchemaDerivationTest` が読む一枚の道。導出の照合は器の
  一枚から採るので、期待値の書き換えは要らない。
- `plugin/tests/test_mapdraft.py`・`plugin/tests/test_mapdraft_hardening.py`・
  `plugin/tests/test_read_surface.py` — 模型を組む fixture（試験の入力）の `schema` の値。

## 影響する投影

- `doctrine_docs/packaging/model/MODEL-001-doctrine.json` — 描き直しで `schema` の値が
  0.2 になる（これが上流の門 M-18 の窓を閉じる）。
- `doctrine_docs/_system/overview.md` — 新設文書の行が増える。

## 工数見積

半日以内。決定は上流と #294 で合意済みであり、必須欄と語彙が動いていないことは実測済み
なので、導出の表の設計は変わらない。

<!-- 入れない: 感想、決定の理由づけ -->
