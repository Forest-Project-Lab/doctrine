---
id: IMPL-020
title: capture-nudge.py / precompact-dump.py（捕捉）の実装メモ
type: IMPL
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-13
sources: [plugin/scripts/capture-nudge.py, plugin/scripts/precompact-dump.py]
depends_on: [SPEC-022]
llm_context: task
---

# capture-nudge.py / precompact-dump.py（捕捉）の実装メモ

SPEC-022 の実装注記である `[R12]`。

## 対象部品

- `capture-nudge.py`(Stop): 印(`edits-`/`recorded-`/`nudged-`)を読み、差し止め(`decision: block`)を一度だけ出す。`stop_hook_active` と `nudged` の印の二重の歯止め。7 日より古い印の掃除(`_sweep_stale`)も担う。
- `precompact-dump.py`(PreCompact): 退避指示の注入だけを行う。ファイルへの書き込みは自分ではしない(書くのはモデル。書けたかは次セッションの選別義務が拾う)。
- 印の書き手は lint ドメインの `review-nudge.py`(SPEC-024)。印の置き場の解決(plugin cache → `.claude/.cache`)は書き手と読み手で同じ順序を保つ。

## 実装制約

- 差し止めは助言的な一度きりの停止であり、決定論の拒否(deny)ではない。拒否は PreToolUse のガードだけが持つ(ADR-028)。
- 印を残せない環境では問わない(ループの恐れを避ける安全側)。
- 標準ライブラリのみ。例外は決して外へ出さない。終了コードは常に 0。

## 注意点

- 記録の型の一覧(ADR・DECIDED・WATCH・CHANGE)は SPEC-024 の印の仕様と一致させる。片方だけ変えると、差し止めが誤発火するか黙る。
- PreCompact の additionalContext が届かない実行環境の版では、退避の輪は Stop の差し止めと SessionStart の選別義務だけで回る(劣化しても壊れない)。
