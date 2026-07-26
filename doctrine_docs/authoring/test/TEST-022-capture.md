---
id: TEST-022
title: 会話知識の捕捉の受入
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [plugin/tests/test_liveness_capture.py]
depends_on: [SPEC-022]
llm_context: task
---

# 会話知識の捕捉の受入

SPEC-022 の受入を `plugin/tests/test_liveness_capture.py` が機械で確認する `[R12]`。

## 受入基準への対応

- 編集あり・記録なしの終端を一度だけ差し止める(TestCaptureNudge.test_edits_without_record_blocks_once)。
- 記録済み・編集なし・`stop_hook_active` は無音(test_recorded_session_is_silent ほか)。
- 圧縮前の退避指示(TestPrecompactDump)。
- 捕捉の印: SPEC 編集→`edits`、ADR 編集→`recorded`、セッションメモ書き込み→`recorded`(TestReviewNudgeFlags)。
- 未選別メモの選別義務は TEST-021(注入側)と共有する。

## 退行観点

- 差し止めが無限ループしない(二重の歯止め)。
- 記録の型の一覧(ADR・DECIDED・WATCH・CHANGE)が黙って狭まらない。
- 印が cache に無限に積もらない(7 日で掃除)。

## 合否基準

上記テストがすべて緑であること。`CI` と `plugin/run_tests.py` で走る。
