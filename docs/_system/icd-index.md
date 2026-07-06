---
id: OVERVIEW-002
title: ICD一覧
type: OVERVIEW
domain: _system
status: current
owner: render-projection
updated: 2026-07-06
llm_context: always
sources: []
---

描画される。手で編集しない。

# ICD一覧

| domain | ICD id | title | canonical_for | updated |
|---|---|---|---|---|
| audit | ICD-005 | audit のインターフェース（全件監査の境界） | corpus-audit, audit-summary-schema | 2026-06-30 |
| authoring | ICD-007 | authoring のインターフェース（作成・初期化・支援） | scaffolding, term-extraction, skills, templates | 2026-07-02 |
| context | ICD-006 | context のインターフェース（注入・パック・投影描画の契約） | context-injection, context-pack, projection-render | 2026-06-30 |
| graph | ICD-002 | graph のインターフェース（依存グラフ問い合わせ契約） | dependency-graph-api | 2026-06-30 |
| guard | ICD-003 | guard のインターフェース（三ガードの公開境界） | policy-guards | 2026-06-30 |
| lint | ICD-004 | lint のインターフェース（リンタと用語チェッカーの公開契約） | document-lint, term-check | 2026-06-30 |
| model | ICD-001 | model のインターフェース（登録簿と解析の公開契約） | type-registry, status-vocabulary, frontmatter-schema, frontmatter-parser, llm-context-policy | 2026-07-06 |
| packaging | ICD-008 | packaging のインターフェース（配布物の形・Hook配線・段差） | plugin-packaging, hook-wiring, level-staging | 2026-07-06 |
