---
id: TEST-011
title: 監査の検査群テスト計画
type: TEST
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-27
sources: [plugin/tests/test_audit.py]
depends_on: [SPEC-011]
llm_context: task
---

# 監査の検査群テスト計画

## 受入基準への対応

SPEC-011 の 18 検査について、それぞれ pass と fail の両側を確認する。新設の 7 検査（stale_current・source_drift・archive_integrity・adr_not_landed・glossary_seed_drift・ext_anchor_broken・memory_shadow）は `plugin/tests/test_liveness_capture.py` が確認する。`[R3][R8]`

- dead_link: すべての参照が解決すれば pass、解決先のない `depends_on` があれば fail。
- review_by_overrun: `review_by` が未来日なら pass、期限を過ぎていれば fail（DECIDED と WATCH を含む）。DECIDED に `review_by` が無い場合は error。
- stale_draft: draft が最近のものなら pass、古ければ fail。
- orphan: 依存されていれば pass、三条件すべてを満たせば fail。陳腐化していなければ孤児としない。ICD・投影・always は孤児としない。再現可能かどうかで判定が分かれることも確認する。
- reverse_orphan: 要求から仕様、仕様からテストまで連鎖がそろっていれば pass、要求に対応する仕様が無ければ fail、仕様に対応するテストが無ければ fail。
- canonical_conflict: 正本が一つなら pass、二つあれば fail。置換済みなのに正本の移譲をやり残していれば fail。
- icd_dependency_violation: ドメインをまたいで ICD 以外を指していれば fail、ドメインをまたいでも ICD を指していれば pass。
- projection_drift: Overview（全体図の投影）が一致すれば pass、項目が欠けていれば fail、廃止した項目が残っていれば fail。ICD-index の欠落も fail。Context Map は、骨格が一致すれば pass、ドメインや依存端の過不足・印の区間の不在は error、ICD 列挙や境界違反マークのずれは warn。
- near_duplicate: 助言（advisory）にとどまり error にはならないこと、本文が別物なら酷似と判定しないことを確認する。
- unregistered_document / shadowed_document: 登録簿の外の `.md`（frontmatter や `id` の無いもの）と、重複 `id` で影になった文書が error で挙がること。登録済みだけのコーパスでは挙がらないこと。所見が告げる採用先が、登録簿の `resolve_duplicate_id` の答え（グラフ・注入と同じ一件）と一致すること（ADR-049）。
- stray_document: doctrine_docs/ の外の型付き .md が warn、分類の記録に無い .md が advisory、期限を過ぎた保留が warn で挙がること。記録された非文書・投影（末尾 `/` の配下指定を含む）は挙がらないこと。実在しないパスを指す記録の項目が advisory で挙がること。
- trace_*: opt-in（`## 実装の指紋` の節を持つ仕様）が無ければ一件も挙がらないこと。指紋の一致で無音、不一致で warn、範囲の不在で warn、実在しない id で error、印の対応付けの誤りで error になること。綴りの揺れた印が advisory（trace_marker_suspect）で挙がり、合否（error/warn）を変えないこと。走査の切り詰めが advisory（trace_scan_truncated）で転記されること。走査が走ったとき要約に `trace_coverage` が載り、保存則の和が合うこと（ADR-058・ADR-059。`plugin/tests/test_audit.py` の CodeTraceTest が確認する）。

## 退行観点

WATCH と突き合わせ、後退させてはならない事項を挙げる。

- 不正な基準日を与えたときは終了コード 2 を返す（黙ってシステム時刻に切り替えない）。
- SessionEnd 経路では、標準入力を読まず、入力待ちで止まらず、終了コード 0 を返す。書き込みに失敗しても 0 を返す。
- 同じコーパスと同じ `--today` を与えれば、JSON はバイト単位まで同一になる（結果が毎回同じになる）。

## 合否基準

`plugin/tests/test_audit.py` の全クラス（DeadLinkTest・ReviewByTest・StaleDraftTest・OrphanTest・ReverseOrphanTest・CanonicalConflictTest・IcdViolationTest・ProjectionDriftTest・IcdIndexDriftTest・CtxmapDriftTest・DepCycleTest（ADR-038: 循環なし・自己依存 warn・多頂点循環 warn）・ExtHashTest（ADR-039: hash 一致=無言・不一致 warn・期待値なし warn・対象なし error）・ChecksRunTest（#95: 要約に checks_run が載り、発火した所見の check 名は必ず checks_run に宣言済み）・NearDuplicateTest・SummaryHandshakeTest・DeterminismTest・DetectedFallbackTest・UnregisteredTest）が通れば合格とする。
