---
id: CHANGE-010
title: 層Aの読み口の完全化（issue #294 の受け。2026-08-13 の一括波）
type: CHANGE
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-08-13
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", "https://github.com/Forest-Project-Lab/doctrine/issues/212"]
depends_on: [ICD-008, ICD-002, ICD-005, ICD-007]
llm_context: task
---

# 層Aの読み口の完全化（issue #294 の受け。2026-08-13 の一括波）

## 変更内容

外部の消費者が層A（統治の実態）を描くための読み口を、一括の一波で完全化する。
権限の記録は ADR-151。決定は ADR-152〜ADR-159 の八本。

- 外部読み口の進化規約を確定し、DECIDED-001 の事実13 として置く（ADR-152）。
- dep-graph の CLI の返す値を `dep-graph/1` として宣言し、`schema`・`root` の鍵を足し、
  診断を標準エラーへ移す（ADR-153）。統治木の発見の口 `--find-root` を足す（ADR-154）。
- `trace-index/1`・`dep-graph/1`・`docs-audit/1` の最上位に `source_revision`・`source_dirty`・
  `generator` を足す（ADR-155・ADR-156）。ICD-005 に `root` の意味と `findings` の項目形を
  宣言する（ADR-156）。
- 刻印の書式を外部の表示製品と共用する（ADR-157）。
- map-draft-check を複数リポジトリ受けにし、口を ICD-007 の外部条項として宣言する（ADR-158）。
- scaffold に必須節の名の問い合わせ `--list-sections` を足す（ADR-159）。

## 理由（要求元）

issue #294（System Map を doctrine 導入済みの任意プロジェクトで見える物にするために
上流へ要るもの）と、その洗い出しで判明した宣言の穴（依存グラフの CLI が宣言なき消費に
なっている・返す値が測った木の版を名乗らない・欄追加の互換規約が無い）。issue #212 発の
二件（追跡所見の重さの読み先・必須節の名を返す口）も同波で受ける。所有者指示は
2026-08-13（ADR-151 に恒久記録）。一波にまとめる理由は INC-040 の税（文書追加の一波ごとに
保証台帳の再判定が掛かる）。

## 影響の初期見積

- 文書: ADR 新規 9 本（ADR-151〜159）・ICD-002・ICD-005・ICD-007・DECIDED-001（事実13）・
  SPEC-006・SPEC-026・SPEC-011・SPEC-015・SPEC-029・投影（Overview・ICD 一覧）・
  CHANGELOG（リリースごとの変更を利用者向けに記す変更履歴ファイル）。
- 実装: `dep-graph.py`・`trace-index.py`・`docs-audit.py`・`map-draft-check.py`・`scaffold.py`・
  共有の補助 `_revinfo.py`（新規）。
- テスト: 依存グラフ CLI・追跡索引 CLI・監査要約・出所検証の門・scaffold の各試験へ追加。
- ドメイン跨ぎ: 鍵の追加は互換（確定事実13）。既存の内部の呼び手は Python 関数と既存の鍵だけを
  読むため影響しない。外部の消費者（doctrine-lens）はリリース後に pin を更新して追随する。

## 実施の記録

2026-08-13 に実施。決定は ADR-151〜ADR-159、影響の列挙は IMPACT-010。ICD-002・ICD-005・
ICD-007・DECIDED-001（事実13）・SPEC-006・SPEC-026・SPEC-011・SPEC-015・SPEC-029 を改訂し、
`_revinfo.py` を新設、五本のスクリプトを改修、受入は `plugin/tests/test_read_surface.py`
（30 件）で凍結した。上流の更新に伴う source_drift 34 件は四巡の追随で不動点に収束し、
公開ビュー 3 件は主張の現行性を確かめて刻印を打ち直した。全件監査
error 0 / warn 0 / advisory 0、試験 1385/1385、投影の照合・整合点検・release-check の
全ゲート通過を確認した。リリース 0.12.0 の実施は本波の出荷の段として続ける。
