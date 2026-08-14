---
id: CHANGE-011
title: 意味モデルの型 MODEL を新設する（ADR-161・ADR-163 の実施）
type: CHANGE
domain: model
status: proposed
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-14
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", "2026-08-14 の所有者の裁定（会話）"]
depends_on: [ADR-163]
llm_context: task
---

# 意味モデルの型 MODEL を新設する（ADR-161・ADR-163 の実施）

## 変更内容

系の意味モデル（要素・流れ・契約・シナリオからなる系の模型）を統治木の中で持つための型
`MODEL` を登録簿へ足す。第一波で足すのは器そのもの——型・既定値・置き場所・必須節・点検
周期・雛形と、それらを凍らせる期待表である。

- 登録簿（`plugin/scripts/_registry.py`）: `TYPES`・`TYPE_DEFAULT_STATUS`（proposed）・
  `TYPE_DEFAULT_LLM_CONTEXT`（task）・`TYPE_LOCATION`（`<domain>/model/`）・
  `REQUIRED_SECTIONS`（六節）・`TYPE_REVIEW_CYCLE_DAYS`（180）。
- 雛形 `plugin/templates/model.md.tmpl`（実体ごとに見出しと JSON の塊を置く形。ADR-163 決定3）。
- 手書きの凍結表: `EXPECTED_TYPES`・`EXPECTED_DEFAULT_STATUS`・`EXPECTED_DEFAULT_LLM_CONTEXT`・
  `EXPECTED_TYPE_LOCATION`（`test_registry.py`）、`EXPECTED_REQUIRED_SECTIONS`
  （`test_linter.py`）、`TYPE_TEMPLATES`（`test_templates.py`）。
- 宣言の側: SPEC-001・DATA-001・ICD-001・TEST-001、および上位設計書 §3.2 の型表と、それを
  指す EXT-003 の指紋。
- 件数の表記: 型と雛形の数を散文に書いていた箇所（SPEC-017・ICD-007・IMPL-016・TEST-017）を、
  件数を書かない形へ改める（ADR-075 の規律。実測で IMPL-016 は「計20個」と書いたまま実物が
  21 個になっていた）。

**第一波に含めないもの**: 本文の構造を検めるリンタの検査群、`.md` から JSON を描く口、
起草の技能の書き換え。これらは第二波・第三波で足す（同じ ADR-163 の帰結の下）。

## 理由（要求元）

所有者の裁定（2026-08-14、会話）。意味モデルの正本を統治木の中へ移す方向（ADR-161）が決まり、
H 層の判定を受けて器の凍結が解けた（ADR-162）。ADR-163 が型の設計を定めた。要求の元は
issue #294 の洗い出し B2（模型の置き場の規約）である。

## 影響の初期見積

- 触る先の列挙は IMPACT-011 が持つ。
- 段取りは三波に分ける。第一波（本 CHANGE）は器だけを足し、既存の振る舞いを変えない——
  MODEL 型の文書が一件も無い状態では、どの検査の結果も動かない。
- 退行の危険は二つ。(1) 手書きの凍結表と正本の片方だけを直すと、規則を変えても黙って通る
  状態へ戻る（ADR-060 の様式が守る）。(2) 節名に裸の一般語を使うと、その語が用語チェッカーの
  照合から体系全体で外れる（ADR-135 の覆い。実測で試験が落ち、節名を複合語へ改めた）。

<!-- 入れない: 承認前の決定、設計の理由（ADR-163 が持つ） -->
