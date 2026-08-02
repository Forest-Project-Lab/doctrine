---
id: TEST-025
title: 被覆マトリクスの受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-27
sources: [plugin/tests/test_packaging.py]
depends_on: [SPEC-025]
llm_context: task
---

# 被覆マトリクスの受入

SPEC-025 の受入である `[R11][R9]`。

## 受入基準への対応

- hooks.json のイベント集合(7 個)は `plugin/tests/test_packaging.py` の test_has_all_seven_events が凍結する。
- 各 command が `${CLAUDE_PLUGIN_ROOT}/scripts/` 配下の .py であることは test_every_command_is_a_plugin_script が凍結する。
- 表の行(R1〜R12 の被覆)の意味の妥当性は機械で閉じないため、doc-review の定例が本文書を点検の対象に含める(発火経路を足す・消す変更のたびに本表を同じ変更で更新する)。

## 退行観点

- イベントを足す・消す変更が本表の更新なしに入らない(テストが先に赤になる)。
- 「結線済みでも NONGOAL でもない行」を作らない。

## 合否基準

test_packaging の該当テスト(`test_required_events_are_all_wired`・`test_coverage_matrix_has_no_empty_cell`・`test_coverage_matrix_demonstrations_exist`)が緑で、本表の R1〜R12 の全行が **6 列**を空白なく埋めること(#94。Level 2 での担保の列と、実効の証の列を含む。ADR-084)。

実効の証の列については次を検める。**この門自身が効くことを実測で確かめてある**(2026-08-02)。

| 与えた状況 | 期待 | 実測 |
|---|---|---|
| 実在しない試験を名指す | 落ちる（腐りの検出） | 落ちた |
| `未証` を黙って増やす | 落ちる（受入の集合と一致しない） | 落ちた |
| 理由の無い `未証` を書く | 落ちる | 落ちた |
| 正しい表 | 通る | 通った |

**この列は実効の証明ではない**。機械が検めるのは名指された試験が実在することだけであり、名指された試験が弱ければ強い欄が弱い経路を飾る(ADR-084 の保証限界)。効くのは著述の時点で問いが立つことである。
