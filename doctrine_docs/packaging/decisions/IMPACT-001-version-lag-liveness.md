---
id: IMPACT-001
title: 版の遅れの照合 — 影響の列挙
type: IMPACT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-08-14
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-001, SPEC-021]
llm_context: task
---

# 版の遅れの照合 — 影響の列挙

CHANGE-001 の影響集合。dep-graph の逆向き（`--dependents SPEC-021`）で列挙した。

## 影響する文書

- SPEC-021（更新: 照合の追加と受入基準）
- ADR（新規: 決定の捕捉。ADR-070）
- IMPL-019（更新: 判定の関数と助言の一行を注記）
- TEST-021（更新: 受入基準への対応）
- SPEC-021 の逆参照 ADR-062・ADR-066 は決定として不変（内容の変更なし）。

## 影響する実装

- `plugin/scripts/_auditcache.py` — 判定の関数を一つ足す（読み手をまたいで一つ。ADR-053 と同じ置き方）。
- `plugin/scripts/gov-heartbeat.py` — 助言の一行を足す。SPEC-021 の指紋の範囲（既定値2行）には触れない。

## 影響するテスト

- `plugin/tests/test_auditcache.py` — 判定の関数の単体。
- `plugin/tests/test_liveness_capture.py` — 鼓動の助言の受入。

## 境界の分類

ドメイン跨ぎなし。packaging の中で閉じる。ICD の変更なし（相手ドメインの合意は不要）。

## 工数見積

小。関数一つ・助言一行・文書4件の更新。
