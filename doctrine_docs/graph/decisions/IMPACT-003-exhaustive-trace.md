---
id: IMPACT-003
title: 悉皆トレース — 影響の列挙
type: IMPACT
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-29
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-003, SPEC-026]
llm_context: task
---

# 悉皆トレース — 影響の列挙

CHANGE-003 の影響集合。

## 影響する文書

- SPEC-026（走査に設定除外の分類を追記）・SPEC-011（検査名簿。audit ドメイン側の
  更新）・SPEC-021（鼓動の一度きりの案内。packaging ドメイン側の更新）
- ADR（新規: ADR-072）
- TEST-026・TEST-011・TEST-021（受入の追記）
- 注釈を新たに張るスクリプト12本の指す先（SPEC-011・SPEC-022・SPEC-023・
  SPEC-026 は指紋の節の更新を伴う）

## 影響する実装

- `plugin/scripts/_tracescan.py` — `exempt_paths` の分類（読む前に統治外へ落とす）
- `plugin/scripts/_audit_trace.py` — 悉皆モードの残高 warn
- `plugin/scripts/docs-audit.py` — 設定キー2つ（`trace_mode`・`trace_exempt`）
- `plugin/scripts/gov-heartbeat.py` — 一度きりの案内（印は `.governance-state`）

## 影響するテスト

- `test_tracescan.py`・`test_audit.py`・`test_liveness_capture.py`

## 境界の分類

正本は graph（走査と分類の規則）。audit は要約と検査面の消費者（ICD-005）、
packaging は案内の運び手。ICD の契約変更なし（設定キーの追加は前方寛容 —
読み手は知らないキーを無視する）。

## 工数見積

中。機構は小さいが、自己適用（62件の分類）が本体。
