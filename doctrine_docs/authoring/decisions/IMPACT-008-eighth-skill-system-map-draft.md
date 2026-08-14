---
id: IMPACT-008
title: 配布技能 system-map-draft の追加 — 影響の列挙
type: IMPACT
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-14
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-008]
llm_context: task
---

# 配布技能 system-map-draft の追加 — 影響の列挙

CHANGE-008 の影響集合。列挙は dep-graph と grep の実測による（2026-08-07）。

## 影響する文書

- ADR-136（新規）・ADR-010（`status: superseded` へ遷移。carve-out の正規手順）
- DECIDED-001（事実8 の言い直しと根拠行。現行逆依存は要点の参照のみで契約は変わらない）
- SPEC-016（技能一覧の正本。数の記述を一覧参照へ）・TEST-016・IMPL-016・authoring の ICD
- SPEC-029・TEST-029（新規。出所の機械検証）
- 公開ビュー 2 件（README.md・plugin/README.md。刻印の date を更新）
- `spec/doctrine.ja.md` §4.1（技能の表と数の記述）
- 投影（Overview。描き直し）

## 影響する実装

- `plugin/skills/system-map-draft/`（新規。SKILL.md と references/）
- `plugin/scripts/map-draft-check.py`（新規。標準ライブラリのみ）
- `.claude/skills/assurance-loop/SKILL.md` §7（「配布 Skill 7個」の数の記述を一覧参照へ）
- 既存スクリプトは変えない

## 影響するテスト

- `plugin/tests/test_skills.py`（SKILL_NAMES・凍結断片へ 1 件追加。数の凍結が 8 へ）
- `plugin/tests/test_meta.py`（技能列挙の試験名と一覧）
- `plugin/tests/test_mapdraft.py`（新規。正例と捏造出所の負例）

## 工数見積

中。文書の連鎖（ADR→DECIDED→SPEC→ビュー）と技能本体・検証器・試験が本体。
既存挙動の変更は無く、退行の面は技能一覧の凍結試験が受け持つ。
