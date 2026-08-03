---
id: TEST-011
title: 監査の検査群テスト計画
type: TEST
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/tests/test_audit.py]
depends_on: [SPEC-011]
llm_context: task
---

# 監査の検査群テスト計画

## 受入基準への対応

SPEC-011 の検査群について、それぞれ pass と fail の両側を確認する。新設の 7 検査（stale_current・source_drift・archive_integrity・adr_not_landed・glossary_seed_drift・ext_anchor_broken・memory_shadow）は `plugin/tests/test_liveness_capture.py` が確認する。`[R3][R8]`
- 唯一の見張りである期限（ADR-086）: `検査: review_by のみ` のアンカーについて、①`review_by` 不在が error になること、②30 日超が warn になること、③30 日以内は静かなこと、④`exists` で常時見張られるアンカーには半年先の期限でも課さないこと、を `plugin/tests/test_liveness_capture.py` の `TestExtAnchors` が確認する。**実測を凍らせている** —— ②の見本には `EXT-001` の実際の値（更新 2026-07-26 / 期限 2026-10-26 = 92 日）を使う。

- dead_link: すべての参照が解決すれば pass、解決先のない `depends_on` があれば fail。
- review_by_overrun: `review_by` が未来日なら pass、期限を過ぎていれば fail（DECIDED と WATCH を含む）。DECIDED に `review_by` が無い場合は error。
- stale_draft: draft が最近のものなら pass、古ければ fail。
- stale_proposed（ADR-095）: `proposed` が最近のものなら pass、放置されていれば warn。**`stale_draft` と混ざらないこと**（`proposed` は draft ではない）。走った検査の一覧（`checks_run`）に載ること（黙って消えない。`[R11]`）。**歯止め自身の実効を実測してある**（2026-08-03）: 検査の呼び出しを外すと落ち、戻すと通った。
- orphan: 依存されていれば pass、三条件すべてを満たせば fail。陳腐化していなければ孤児としない。ICD・投影・always は孤児としない。再現可能かどうかで判定が分かれることも確認する。
- reverse_orphan: 要求から仕様、仕様からテストまで連鎖がそろっていれば pass、要求に対応する仕様が無ければ fail、仕様に対応するテストが無ければ fail。
- canonical_conflict: 正本が一つなら pass、二つあれば fail。置換済みなのに正本の移譲をやり残していれば fail。
- icd_dependency_violation: ドメインをまたいで ICD 以外を指していれば fail、ドメインをまたいでも ICD を指していれば pass。
- projection_drift: Overview（全体図の投影）が一致すれば pass、項目が欠けていれば fail、廃止した項目が残っていれば fail。ICD-index の欠落も fail。Context Map は、骨格が一致すれば pass、ドメインや依存端の過不足・印の区間の不在は error、ICD 列挙や境界違反マークのずれは warn。
- near_duplicate: 助言（advisory）にとどまり error にはならないこと、本文が別物なら酷似と判定しないことを確認する。
- unregistered_document / shadowed_document: 登録簿の外の `.md`（frontmatter や `id` の無いもの）と、重複 `id` で影になった文書が error で挙がること。登録済みだけのコーパスでは挙がらないこと。所見が告げる採用先が、登録簿の `resolve_duplicate_id` の答え（グラフ・注入と同じ一件）と一致すること（ADR-049）。
- stray_document: doctrine_docs/ の外の型付き .md が warn、分類の記録に無い .md が advisory、期限を過ぎた保留が warn で挙がること。記録された非文書・投影（末尾 `/` の配下指定を含む）は挙がらないこと。実在しないパスを指す記録の項目が advisory で挙がること。
- view_stale（ADR-073）: 「ビュー」と分類された .md の刻印の欠落・読めない刻印（必須欄の欠落）が warn で挙がること。刻印が新しければ無音、`refs` の参照先が刻印より新しい・現行でない・実在しないときと、`refs` 無しで正本が刻印より新しいときが advisory で挙がること。プレフィクス項目（末尾 `/`）のビューは対象にしないこと。完全一致の項目がプレフィクスの一括分類に勝つこと（ViewStaleTest が確認する）。
- trace_*: opt-in（`## 実装の指紋` の節を持つ文書）が無ければ一件も挙がらないこと。状態×指紋一致の全マス（`ALL_STATUSES` を添字に列挙した 16 マス）が手書きの期待表と一致すること — 現行/accepted は一致で無音・不一致で warn、それ以外の全状態は現行でない id への warn（ADR-060。廃止だけが opt-in の木でも挙がること）。範囲の不在で warn、実在しない id で error、印の対応付けの誤りで error になること。「コード対応なし」の宣言は実態が伴えば無音・範囲があれば warn になり、節の無い現行 SPEC を範囲が指せば advisory で名指しされること（ADR-061）。統治外（exempt）の宣言と範囲の印の同居が warn になり、宣言したファイルにしか発火しないこと（ADR-067）。未宣言があるとき `next_undeclared` が整列順の先頭を運び、無ければ載らないこと。停滞計（`stagnation_streak`）が、直前の要約と和が同値の監査で積み上がり、値が動けば 0 に戻り、直前が無ければ 0 であること（ADR-065）。現行 SPEC の三分類（traced・no_code・undeclared）が要約に載ること。検査名の一覧が独立転記の表と全量一致すること（凍結の実在。ADR-060）。
- guard_liveness_gap: 印が無ければ黙り、リンタの印だけが進めば advisory で挙がること。判定が鼓動と同じ共有コアにあること（ADR-062）。綴りの揺れた印が advisory（trace_marker_suspect）で挙がり、合否（error/warn）を変えないこと。走査の切り詰めが advisory（trace_scan_truncated）で転記されること。走査が走ったとき要約に `trace_coverage` が載り、保存則の和が合うこと（ADR-058・ADR-059。`plugin/tests/test_audit.py` の CodeTraceTest が確認する）。
- trace_unmarked_backlog（ADR-072）: 悉皆モードの体系でだけ、印なしの残高が warn 一件で挙がり、既定では挙がらないこと。設定除外（trace_exempt）が残高を減らし、理由の無い宣言が成立しないこと。設定は木の `_system/.context-config.json` から既定で読まれること（ExhaustiveTraceTest が確認する）。
- ADR-075: 仮名・漢字が地の文で直接隣接する id 参照（助詞が id の直後に続く形、id の直前に助詞が来る形）を dead_link が拾うこと。全角の括弧・句読点・鉤括弧に囲まれた形も同様。
- ADR-075: 設定の数値キーを文字列で書いても監査が落ちず、既定へ落ちること。

## 退行観点

WATCH と突き合わせ、後退させてはならない事項を挙げる。

- 不正な基準日を与えたときは終了コード 2 を返す（黙ってシステム時刻に切り替えない）。
- SessionEnd 経路では、標準入力を読まず、入力待ちで止まらず、終了コード 0 を返す。書き込みに失敗しても 0 を返す。
- 同じコーパスと同じ `--today` を与えれば、JSON はバイト単位まで同一になる（結果が毎回同じになる）。

## 合否基準

`plugin/tests/test_audit.py` の全クラス（DeadLinkTest・ReviewByTest・StaleDraftTest・OrphanTest・ReverseOrphanTest・CanonicalConflictTest・IcdViolationTest・ProjectionDriftTest・IcdIndexDriftTest・CtxmapDriftTest・DepCycleTest（ADR-038: 循環なし・自己依存 warn・多頂点循環 warn）・ExtHashTest（ADR-039: hash 一致=無言・不一致 warn・期待値なし warn・対象なし error）・ChecksRunTest（#95: 要約に checks_run が載り、発火した所見の check 名は必ず checks_run に宣言済み）・NearDuplicateTest・SummaryHandshakeTest・DeterminismTest・DetectedFallbackTest・UnregisteredTest）が通れば合格とする。
