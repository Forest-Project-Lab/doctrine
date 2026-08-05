---
id: TEST-021
title: 統治ハートビートと死活警告の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-29
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
- 紐づけキャンペーン(ADR-065) → 未宣言の先頭一件を三つの出口つきで促し(test_trace_campaign_prompts_the_next_undeclared_spec)、停滞に触れ(test_trace_campaign_mentions_stagnation)、書式に合わない id を文面に載せず(test_trace_campaign_rejects_a_malformed_id)、移行キャンペーンが出す間は順番を待つ(test_trace_campaign_waits_for_md_migration)。
- 発火の印の対の食い違い(ADR-062) → 他が健全でも「拒否経路の疑い」を告げる(test_guard_liveness_gap_is_announced)。
- 監査の走った証跡が要約より新しい(ADR-119) → 鮮度の警告が「監査は走っている」と原因を名指しし、従来の「動いていない可能性」を出さない(test_stale_with_a_newer_stamp_names_the_write_failure)。書き込みの印が失敗を告げるときも名指しする(test_stale_with_a_failed_write_flag_names_it)。証跡が無ければ従来の文面のまま(test_stale_without_a_stamp_keeps_the_old_wording)。
- 版の切替(ADR-066) → 冒頭の版と今の版が違えば毎セッション再起動を促し(test_version_drift_is_announced_every_session)、印が無ければ黙る(test_no_version_drift_without_the_stamp)。注入が版の印を刻むこと・判定の規則は `test_inject.py` の TestVersionStamp と `test_auditcache.py` が凍結する。
- 版の遅れ(ADR-070) → マニフェストの宣言と実行中の版が食い違えば更新の言い方まで含めて促し(test_version_lag_advises_update_in_a_self_marketplace_repo)、マニフェストの無い導入先では黙る(test_no_version_lag_without_a_manifest)。判定の規則(正本は source の先を優先・同名の項目だけ・不一致のみで向きを言わない)は `test_auditcache.py` の VersionLagTest が凍結する。
- Level 昇格の案内(ADR-066) → Level 2 + 監査の実績で一度だけ出て、印で以後黙り(test_level_hint_appears_once_for_a_level2_tree_with_audit_record)、実績が無ければ出ない(test_no_level_hint_without_an_audit_record)。
- 悉皆モードの案内(ADR-072) → 未宣言 0+印なし残で一度だけ出て印で黙り(test_trace_mode_hint_appears_once_when_specs_are_done)、モードを入れた体系(test_no_trace_mode_hint_when_already_on)と未宣言が残る体系(test_no_trace_mode_hint_while_undeclared_remain)では出ない。印の書き読み・欠落/古さの判定・新鮮な対の無音・書き手の入口(リンタ/ガード)は `test_auditcache.py` の HookStampsTest が、監査側の advisory は `test_audit.py` の GuardLivenessTest が凍結する。
- 注入側の鮮度警告と未選別メモ節(TestInjectLiveness)。
- Level 2 で監査の死活を誤報しない(test_level2_missing_audit_is_not_flagged)。
- 移行キャンペーン: 未分類ありで統治率つきの1件を促し、ゼロなら無音(TestMigrationCampaign)。
- メモリの影: 統治文書へ言及するメモリを advisory で挙げ、索引と無言及・置き場なしは無音(TestMemoryShadow)。
- 不具合の兆候の促し(ADR-074): エラージャーナルに記録があれば、報告の手順(下書き→承認→gh→感謝)を含む促しが出て、記録が無ければ出ず、記録ファイルの削除で消える。監査の死活の警告があるときはそちらが勝つ。ジャーナルの読み書き(許可制 — 例外の自由文を写さない・上限20件・決して例外を投げない)は ErrorJournalTest が凍結する(TestErrorReportPrompt / ErrorJournalTest)。
- 世代の照合(ADR-053): 統治木を作り直したとき、前の世代の要約を読まない。読み手(注入と鼓動)が同じ答えを返す。印を持たない木では判じない。tests/test_auditcache.py が凍らせる。

## 退行観点

- 警告が毎会話出続けない(一度きりの印)。
- 統治木の無いプロジェクトを騒がせない。
- 返す値は助言のみ(decision を含まない)。

## 合否基準

上記テストがすべて緑であること。`CI` と `plugin/run_tests.py` で走る。
