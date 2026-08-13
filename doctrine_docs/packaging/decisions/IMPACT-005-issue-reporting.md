---
id: IMPACT-005
title: 不具合の記録と報告 — 影響の列挙
type: IMPACT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-08-13
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-005, SPEC-021]
llm_context: task
---

# 不具合の記録と報告 — 影響の列挙

CHANGE-005 の影響集合。

## 影響する文書

- SPEC-021（エラージャーナルの契約の正本化、促しの梯子への一項）
- SPEC-011・SPEC-007・SPEC-003・SPEC-012（各エラー時挙動へ記録の一行。
  audit・lint・guard・context の各ドメイン側の更新）
- NONGOAL-001（承認なしの外部送信はしない、の追加）
- ADR（新規: ADR-074）・IMPL-019（鼓動の実装注記）・TEST-021（受入の追記）
- 投影（Overview。文書の追加に伴う描き直し）

## 影響する実装

- `plugin/scripts/_auditcache.py` — ジャーナルの読み書き（`record_error`・
  `read_errors`。許可制・上限20件・決して例外を投げない）
- `plugin/scripts/policy-guard.py`・`docs-linter.py`・`inject-contract.py`・
  `gov-heartbeat.py`・`docs-audit.py` — 例外処理からの記録（最善努力）
- `plugin/scripts/gov-heartbeat.py` — 促しの一項（報告の手順の自己完結文）
- `.github/ISSUE_TEMPLATE/phenomenon-report.yml` — 受け側の定型フォーム
- `CONTRIBUTING.md` — 報告の歓迎と感謝の一節

## 影響するテスト

- `plugin/tests/test_liveness_capture.py`（ジャーナルの読み書き・許可制・
  上限・促しの発火と鎮静・梯子の優先）

## 境界の分類

ジャーナルは guard・lint・context・audit の入口が書き、packaging（鼓動）が
読む。読み書きは共有コア `_auditcache`（発火の印と同じ家）に一本化し、書式の
正本は SPEC-021 に置く。各ドメインの SPEC へはエラー時挙動の一行だけが入り、
ICD の契約変更は無い（キャッシュの追加は前方寛容 — 知らない読み手は無視する）。

## 工数見積

小〜中。機構は小さいが、配線が5本に散る。
