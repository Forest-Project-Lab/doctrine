---
id: IMPACT-007
title: 追跡索引の読み口の宣言 — 影響の列挙
type: IMPACT
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-08-03
updated: 2026-08-03
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-007, ICD-002]
llm_context: task
---

# 追跡索引の読み口の宣言 — 影響の列挙

CHANGE-007 の影響集合。列挙は dep-graph の実測による（2026-08-03）。

## 影響する文書

- ICD-002（`trace-index-api` の宣言を追加。題も契約の範囲に合わせて改める）
- ADR（新規: ADR-111）
- 投影 2 件（ICD 一覧・Overview。描き直し）
- DECIDED-001（見出しの件数表記のみ。決定なしの同乗。現行逆依存 0 を確認済み）

## 影響する実装

- なし。`trace-index.py`・`_tracescan.py` は変更しない。返す形は既に SPEC-026 の正本どおりであり、宣言が実装へ合わせる（逆ではない）。

## 影響するテスト

- なし。挙動の変更が無く、受入は TEST-026 が凍結済み。

## 境界の分類

正本は graph。ICD-002 の現行逆依存は 5 件（ICD-004・SPEC-003・SPEC-007・SPEC-011・SPEC-019）だが、宣言の追加は前方寛容で既存の依存グラフ契約に手を触れない——逆依存側の更新は不要（CHANGE-003 と同じ判断）。越境の消費者（doctrine-lens）は着地後に自側の文書参照を追随するが、doctrine 側の依存端は増えない（NONGOAL-001 第10項: リポジトリ間の依存を持たない）。

## 工数見積

小。ICD への宣言の追記と投影の描き直しが本体。実装・テストは動かない。
