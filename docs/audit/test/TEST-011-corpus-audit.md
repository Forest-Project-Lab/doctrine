---
id: TEST-011
title: 監査の検査群テスト計画
type: TEST
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_audit.py]
depends_on: [SPEC-011]
llm_context: task
---

# 監査の検査群テスト計画

## 受入基準への対応

SPEC-011 の 9 検査について、それぞれ pass と fail の両側を確認する。`[R3][R8]`

- dead_link: すべての参照が解決すれば pass、解決先のない `depends_on` があれば fail。
- review_by_overrun: `review_by` が未来日なら pass、期限を過ぎていれば fail（DECIDED と WATCH を含む）。DECIDED に `review_by` が無い場合は error。
- stale_draft: draft が最近のものなら pass、古ければ fail。
- orphan: 依存されていれば pass、三条件すべてを満たせば fail。陳腐化していなければ孤児としない。ICD・投影・always は孤児としない。再現可能かどうかで判定が分かれることも確認する。
- reverse_orphan: 要求から仕様、仕様からテストまで連鎖がそろっていれば pass、要求に対応する仕様が無ければ fail、仕様に対応するテストが無ければ fail。
- canonical_conflict: 正本が一つなら pass、二つあれば fail。置換済みなのに正本の移譲をやり残していれば fail。
- icd_dependency_violation: ドメインをまたいで ICD 以外を指していれば fail、ドメインをまたいでも ICD を指していれば pass。
- projection_drift: Overview（全体図の投影）が一致すれば pass、項目が欠けていれば fail、廃止した項目が残っていれば fail。
- near_duplicate: 助言（advisory）にとどまり error にはならないこと、本文が別物なら酷似と判定しないことを確認する。

## 退行観点

WATCH と突き合わせ、後退させてはならない事項を挙げる。

- 不正な基準日を与えたときは終了コード 2 を返す（黙ってシステム時刻に切り替えない）。
- SessionEnd 経路では、標準入力を読まず、入力待ちで止まらず、終了コード 0 を返す。書き込みに失敗しても 0 を返す。
- 同じコーパスと同じ `--today` を与えれば、JSON はバイト単位まで同一になる（結果が毎回同じになる）。

## 合否基準

`plugin/tests/test_audit.py` の全クラス（DeadLinkTest・ReviewByTest・StaleDraftTest・OrphanTest・ReverseOrphanTest・CanonicalConflictTest・IcdViolationTest・ProjectionDriftTest・NearDuplicateTest・SummaryHandshakeTest・DeterminismTest）が通れば合格とする。
