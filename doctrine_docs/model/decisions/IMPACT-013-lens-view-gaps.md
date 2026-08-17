---
id: IMPACT-013
title: 第5信の欠けへの応えの影響（CHANGE-013）
type: IMPACT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
depends_on: [CHANGE-013]
llm_context: task
---

# 第5信の欠けへの応えの影響（CHANGE-013）

決定の正本は ADR-169（列挙の読み口）・ADR-170（複数の木）・ADR-171（出所ごとの判定）・
ADR-172（語彙と解釈規範の在り処）。

## 影響する文書

- `doctrine_docs/context/decisions/ADR-169-model-index-read-surface.md` — 新設。
- `doctrine_docs/model/decisions/ADR-170-model-spanning-repositories.md` — 新設。
- `doctrine_docs/authoring/decisions/ADR-171-per-source-verdicts.md` — 新設。
- `doctrine_docs/model/decisions/ADR-172-semantics-upstream-display-downstream.md` — 新設。
- `doctrine_docs/context/spec/SPEC-014-render-projection.md` — `model --list` の口。
- `doctrine_docs/authoring/spec/SPEC-029-map-draft-check.md` — `sources` の一覧・五値の
  verdict・`repos`・`generator`・`totals.by_verdict`。
- `doctrine_docs/model/spec/SPEC-031-model-body-contract.md` — `repos` 宣言の検査
  （`MODEL_BAD_REPOS`・`MODEL_UNDECLARED_REPO`）と接頭の解析の正本。
- `doctrine_docs/context/ICD.md`（ICD-006） — 外部条項の新設（`model-index/1`）。
- `doctrine_docs/authoring/ICD.md`（ICD-007） — `map-draft-check/1` の宣言の拡張。
- `doctrine_docs/graph/ICD.md`（ICD-002） — 鮮度の三値の判定規則（ADR-172）。
- `doctrine_docs/_system/decided-facts.md` — 事実13 の採用先に ICD-006 を足す。
- `doctrine_docs/context/test/TEST-014-render-projection.md`・
  `doctrine_docs/authoring/test/TEST-029-map-draft-check.md`・
  `doctrine_docs/model/test/TEST-031-model-body-contract.md` — 受入観点の追加。
- `doctrine_docs/context/implementation/IMPL-014-render-projection.md` — 部品の注記。

## 影響する実装

- `plugin/scripts/render-projection.py` — `model --list`（`model-index/1` を stdout へ）。
- `plugin/scripts/map-draft-check.py` — 出所ごとの判定の記録と JSON の欄追加。
- `plugin/scripts/_model.py` — 接頭の解析の正本（`SOURCE_RE` の移設）と `repos` 宣言の
  検査。リンタ・描き手・門は写しを持たずここを引く。
- `plugin/scripts/docs-linter.py` — `repos` 宣言の検査の配線（`_model` 経由）。
- `doctrine_docs/packaging/model/MODEL-001-doctrine.md` — `repos: ["doctrine=self"]` の
  宣言を実例として足す。

## 影響するテスト

- `plugin/tests/test_model.py` — `repos` 宣言の検査（`ReposDeclarationTest`）と
  `model --list` の形・決定論・壊れた模型の扱い（`ModelIndexListTest`。model モードの
  実装試験はこのファイルに集まっている）。
- `plugin/tests/test_mapdraft.py` — `sources` の五値・`repos`・`generator`・互換
  （`PerSourceVerdictTest`）。

## 影響する投影

- `doctrine_docs/_system/overview.md` — 新設文書の行が増える。
- `doctrine_docs/packaging/model/MODEL-001-doctrine.json` — 本文は動かさないので内容は
  変わらない（フロントマターは投影に載らない）。

## ドメイン跨ぎの境界

- ADR-172 の鮮度規則は graph ドメインの ICD-002 に載る（版の鍵の宣言の一部）。model →
  graph の影響は ICD を通る（R7）。
- 外部（doctrine-lens）への境界は ICD-006・ICD-007 の外部条項と #294 の告知で通す。
  いずれも欄の追加（互換）であり、スキーマ名の版は上げない（確定事実13）。

## 工数見積

一日以内。複数の木の宣言（第5信の欠けの2番）は任意キーで後方互換、列挙の読み口と
出所ごとの判定（同 1番・5番）は欄と口の追加であり、既存の読み手を壊す変更は無い。

<!-- 入れない: 感想、決定の理由づけ -->
