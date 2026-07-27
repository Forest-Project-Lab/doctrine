---
id: TEST-021
title: 統治ハートビートと死活警告の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-27
sources: [plugin/tests/test_liveness_capture.py]
depends_on: [SPEC-021]
llm_context: task
---

# 統治ハートビートと死活警告の受入

SPEC-021 の受入を `plugin/tests/test_liveness_capture.py` が機械で確認する `[R11]`。

## 受入基準への対応

- 新鮮な監査+期限内の定例 → 無音(TestHeartbeat.test_fresh_audit_and_recent_cadence_is_silent)。
- 監査の鮮度超過 → R11 警告(test_stale_audit_warns)。要約なし+状態あり → 死活の疑い(test_missing_audit_with_state_warns)。
- 使い始めの前・統治木の外 → 無音(test_brand_new_tree_is_silent / test_no_tree_is_silent)。
- 定例の記録なし・周期超過 → 実行と記録先を含む督促(test_missing_cadence_record_with_audit_prompts / test_cadence_overdue_warns)。
- セッションに一度だけ(test_once_per_session)。
- 注入側の鮮度警告と未選別メモ節(TestInjectLiveness)。
- Level 2 で監査の死活を誤報しない(test_level2_missing_audit_is_not_flagged)。
- 移行キャンペーン: 未分類ありで統治率つきの1件を促し、ゼロなら無音(TestMigrationCampaign)。
- メモリの影: 統治文書へ言及するメモリを advisory で挙げ、索引と無言及・置き場なしは無音(TestMemoryShadow)。

## 退行観点

- 警告が毎会話出続けない(一度きりの印)。
- 統治木の無いプロジェクトを騒がせない。
- 返す値は助言のみ(decision を含まない)。

## 合否基準

上記テストがすべて緑であること。`CI` と `plugin/run_tests.py` で走る。
