---
id: TEST-025
title: 被覆マトリクスの受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
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

test_packaging の該当テストが緑で、本表に空白セルが無いこと。
