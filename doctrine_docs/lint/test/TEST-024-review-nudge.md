---
id: TEST-024
title: review-nudge の受入
type: TEST
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-13
sources: [plugin/tests/test_review_nudge.py, plugin/tests/test_liveness_capture.py]
depends_on: [SPEC-024]
llm_context: task
---

# review-nudge の受入

SPEC-024 の受入を `plugin/tests/test_review_nudge.py`(助言の挙動)と `plugin/tests/test_liveness_capture.py`(捕捉の印)が機械で確認する `[R10][R12]`。

## 受入基準への対応

- 型付き文書 → doc-review を促す助言、decision なし(test_review_nudge.py)。
- 非文書・型なし → 無音(同上)。
- Level 2 → 助言なし(同上の段差ゲート受入)。
- 捕捉の印: SPEC 編集→`edits`、ADR 編集→`recorded`、セッションメモ→`recorded`(test_liveness_capture.py TestReviewNudgeFlags)。

## 退行観点

- decision/permissionDecision を出す変更を入れない。
- 印の書き込みを Level ゲートの内側へ移さない(捕捉は全 Level)。

## 合否基準

上記テストがすべて緑であること。`CI` と `plugin/run_tests.py` で走る。
