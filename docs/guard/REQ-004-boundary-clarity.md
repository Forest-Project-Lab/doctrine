---
id: REQ-004
title: 境界明瞭（越境依存は相手ICD宛のみ許す）
type: REQ
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §3.5]
llm_context: task
---

# 境界明瞭（越境依存は相手ICD宛のみ許す）

## 要求文
ドメイン間の依存は、相手ドメインの ICD 宛だけを許す。`[R7]` ある `depends_on` が自ドメインの外を指し、しかも相手の ICD 以外を指していれば、ガードはこれを拒否する。同ドメイン内の依存と、ICD 宛の越境依存は許す。判定が見るのは構造（相手のドメインと、型が ICD かどうか）だけで、相手の `status` は見ない（C12: frozen-contract の整合判断id）。こうすると、ICD を変えない限り、内部をいくら変えても境界を越えない。

## 優先度
高

## 受入基準参照
TEST-003（§6 「R7 境界明瞭」行に対応。受入シナリオ TC（番号は次のとおり）。TC-070 ICD宛越境=許可・TC-071 非ICD宛越境=拒否・TC-072 同ドメイン=許可・TC-117 相手 `status` 無関係）。

## 出所
spec §3.5（ICDが依存の入口）・§4.2（ICD依存ガードの擬似仕様）・§6 受入の R7 行。

<!-- 入れない: 実現方法 -->
