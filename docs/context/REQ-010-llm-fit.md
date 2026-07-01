---
id: REQ-010
title: LLM適合（常時投入を最小に・never群を渡さない）
type: REQ
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §3.9]
llm_context: task
---

# LLM適合（常時投入を最小に・never群を渡さない）

## 要求文

LLM へ渡す常時集合は、最小に保たねばならない `[R5]`。`llm_context: never` の群（RESEARCH・ARCHIVE と、明示的に never としたもの）は本文を渡さない。どの文書も、本文の全量は注入に混ぜない。注入もパックも上限を守り、運ぶのは要点と出所だけにする。こうして、文脈窓がふくれあがること（context-rot）を機械的な歯止めで防ぐ。文脈窓とは、モデルが一度に読み込める入力の量をいう。

## 優先度

高

## 受入基準参照

TEST-012（注入の上限強制と never 不混入）／TEST-013（パックの never 硬除外）。

## 出所

spec §3.9 と規約「最小性」。要求タグ `[R5]`。

<!-- 入れない: 実現方法 -->
