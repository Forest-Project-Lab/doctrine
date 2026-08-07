---
id: IMPACT-009
title: 監査要約の読み口の宣言 — 影響の列挙
type: IMPACT
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-07
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-009, ICD-005]
llm_context: task
---

# 監査要約の読み口の宣言 — 影響の列挙

CHANGE-009 の影響集合。列挙は dep-graph の実測による（2026-08-07）。

## 影響する文書

- ICD-005（データ契約へ外部読み口の一行を追加）
- ADR（新規: ADR-137）
- 投影（ICD 一覧・Overview。描き直し）

## 影響する実装

- なし。`docs-audit.py` の `--json`・`--today` は実装済みで、宣言が実装へ合わせる
  （逆ではない）。

## 影響するテスト

- なし。挙動の変更が無い。要約スキーマの受入は既存の監査試験が凍結済み。

## 工数見積

小。ICD への一行と ADR・投影の描き直しだけ。外部利用者（doctrine-lens）は着地後に
自側の参照を追随するが、doctrine 側の依存端は増えない（NONGOAL-001 第10項）。
