---
id: IMPACT-010
title: 層Aの読み口の完全化 — 影響の列挙
type: IMPACT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-08-13
updated: 2026-08-13
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-010, ICD-002, ICD-005, ICD-007]
llm_context: task
---

# 層Aの読み口の完全化 — 影響の列挙

CHANGE-010 の影響集合。列挙は dep-graph の実測と #294 の洗い出しによる（2026-08-13）。

## 影響する文書

- ICD-002（依存グラフの外部条項 `dep-graph/1`・`--find-root`・測った木の版の三鍵・
  `--id` の列挙・進化規約の採用行）
- ICD-005（`docs-audit/1` の三鍵・`root` の意味・`findings` の項目形・刻印の共用・採用行）
- ICD-007（`map-draft-check/1` と `scaffold-sections/1` の外部条項・採用行）
- DECIDED-001（事実13 の追加。12事実→13事実）
- SPEC-006（CLI の返す値の節）・SPEC-026（問い合わせの三鍵）・SPEC-011（返す値の三鍵）・
  SPEC-015（`--list-sections`）・SPEC-029（複数リポジトリの引数）
- ADR（新規: ADR-151〜ADR-159）・投影（Overview・ICD 一覧。描き直し）

## 影響する実装

- `plugin/scripts/_revinfo.py`（新規。木の版と作り手の解決を一箇所に置く）
- `plugin/scripts/dep-graph.py`（`schema`・`root`・三鍵・`--find-root`・診断の標準エラー化）
- `plugin/scripts/trace-index.py`（三鍵）
- `plugin/scripts/docs-audit.py`（三鍵）
- `plugin/scripts/map-draft-check.py`（`--repo <接頭>=<経路>` の反復・後勝ちの廃止・
  `--trace-json` の反復）
- `plugin/scripts/scaffold.py`（`--list-sections`）

## 影響するテスト

- `plugin/tests/test_depgraph.py`（CLI の鍵・find-root・診断の行き先）
- `plugin/tests/test_tracescan.py`（追跡索引 CLI の鍵）
- `plugin/tests/test_audit.py`（要約の鍵）
- `plugin/tests/test_mapdraft.py`（複数リポジトリ・使い方の誤り）
- `plugin/tests/test_scaffold.py`（節名の問い合わせと登録簿の一致）
- `plugin/tests/test_revinfo.py`（新規。clean・dirty・git 無しの三態）

## 工数見積

中。鍵の追加は互換（確定事実13）なので既存の読み手は壊れない。最大の作業は
map-draft-check の引数と索引の複数化で、旧形の互換と誤りの検出を試験で凍らせる。
外部の消費者（doctrine-lens）はリリース 0.12.0 の後に pin を更新して追随する
（doctrine 側の依存端は増えない。NONGOAL-001 第10項）。
