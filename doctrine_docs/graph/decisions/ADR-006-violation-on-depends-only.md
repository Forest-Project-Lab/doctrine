---
id: ADR-006
title: cross_domain_violation は depends_on 端のみに付ける
type: ADR
domain: graph
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_depgraph.py]
depends_on: [SPEC-006]
llm_context: task
---

# cross_domain_violation は depends_on 端のみに付ける

越境した端をどう分類するかの規則を、ADR（決定の記録、Architecture Decision Record）として定める。

## 背景

端には依存（depends_on）と影響（impacts）の二種類がある。端が越境した（別ドメインの文書を指し、しかも相手が ICD でない）とき、これを違反として扱うかどうかを、どちらの端でも同じ基準で決めておく必要がある。

## 却下した選択肢

越境した impacts 端も `cross_domain_violation` として扱う案。これは影響の波及を構造上の違反と取り違えてしまい、変更耐性のために行う影響列挙の結果を歪めてしまう。

## 決定

`cross_domain_violation` は depends_on 端だけに付ける。越境した impacts 端は `cross_domain_impact`（助言）に分類し、拒否も違反扱いもしない。[R7][R4]

## 帰結

ガードと監査は、depends_on 端の分類だけを R7 違反として読めばよくなる。影響集合のほうは越境した端も含めて素直に列挙でき、構造違反の検出と影響の波及をそれぞれ別々に扱える。
