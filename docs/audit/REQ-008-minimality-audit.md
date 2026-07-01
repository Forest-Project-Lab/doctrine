---
id: REQ-008
title: 最小性の監査（過剰と不足の両側を全件検出）
type: REQ
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md#R8]
llm_context: task
---

# 最小性の監査

## 要求文

監査は、文書集合が過不足なく最小であることを、過剰側と不足側の両方について全件検出できること。`[R1][R3][R4][R8]`

- 過剰の検出: 孤児（どの現行文書からも依存されない文書）、正本の重複（同一トピックに現行の `canonical_for` が二つ以上ある状態）、投影ドリフト（投影が正本の現行集合とずれている状態）を一覧にする。
- 不足の検出: 逆孤児（対応する仕様を持たない要求、対応するテストを持たない仕様）を一覧にする。
- 古びの検出: `review_by` の期限超過（DECIDED と WATCH を含む）と、draft のまま放置された文書も対象とする。
- 起動は人手のコマンドに頼らない。SessionEnd の Hook と CI の二経路から走らせる。一往復ごと（per-turn）には走らせない。

## 優先度

高

## 受入基準参照

TEST-011。spec §6 の R1・R3・R4・R8 の各行に対応する全件検査の pass/fail を確認する。

## 出所

spec §4.2（監査の一覧）、および §5（要求とその充足、R8 最小性）。
