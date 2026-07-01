---
id: REQ-002
title: 追跡性（要求→仕様→実装→テスト→決定をたどる）
type: REQ
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
llm_context: task
---

# 追跡性（要求→仕様→実装→テスト→決定をたどる）

## 要求文

文書間の依存（depends_on）をたどり、要求から仕様・実装・テスト・決定まで機械的に追跡できること。あわせて、あるべき文書が欠けていないか（逆孤児）を検出できること。たどるのは depends_on のリンクだけとし、結果は毎回同じ順序で決まる。[R3]

## 優先度

高

## 受入基準参照

TEST-006 で確認する（逆依存の閉包と、逆孤児を二種類に分ける検査）。

## 出所

spec §3.6（ドメイン境界）と §3.8（降格不変条件）が求める追跡性に由来する。
