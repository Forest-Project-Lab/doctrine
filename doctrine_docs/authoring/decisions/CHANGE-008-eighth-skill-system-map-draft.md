---
id: CHANGE-008
title: 配布技能に system-map-draft を加える（issue #212 分担合意の doctrine 側実装）
type: CHANGE
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/212"]
depends_on: [SPEC-016]
llm_context: task
---

# 配布技能に system-map-draft を加える（issue #212 分担合意の doctrine 側実装）

## 変更内容

配布技能に `system-map-draft`（proposed 限定の意味モデルの下書きを起草する技能）を加え、
技能の数の固定（ADR-010）を「一覧の正本は SPEC-016、増減は根拠ADRの置換のみ」へ改める
（ADR-136）。あわせて出所の機械検証スクリプト `map-draft-check.py` を配布物に加える
（仕様は SPEC-029、受入は TEST-029）。

## 理由（要求元）

issue #212（System Map Phase 2）の分担合意 —— 意味モデルの下書き生成は書き込み系であり
doctrine 側の領分（合意台帳 v3.2-4）。lens 側から設計案（置き場・呼び出し形・入出力）の
提示を求められていた。2026-08-07 の所有者裁定が、配布 8 個目の技能として出すことを選んだ。

## 影響の初期見積

- 文書: ADR-136（新規。ADR-010 を置換）・DECIDED-001 事実8・SPEC-016・TEST-016・
  IMPL-016・authoring の ICD・SPEC-029/TEST-029（新規）・公開ビュー 2 件
  （README・plugin/README）・`spec/doctrine.ja.md` §4.1・投影（Overview）。
- 実装: `plugin/skills/system-map-draft/`（新規）・`plugin/scripts/map-draft-check.py`
  （新規）。既存スクリプトは変えない。
- 試験: `test_skills.py`（技能一覧の凍結を 8 件へ）・`test_meta.py`（技能列挙）・
  `test_mapdraft.py`（新規）。
- ドメイン跨ぎ: なし（authoring の内側。lens 側の消費は EXT-006 の外部参照のまま）。

## 実施の記録

2026-08-07 に着手。決定は ADR-136、影響の列挙は IMPACT-008。技能本体と検証器は
続く変更で入る（本 CHANGE は連鎖の起点）。
