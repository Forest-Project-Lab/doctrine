---
id: REQ-005
title: 現行性（型↔status・id↔ファイル名・型↔置き場所を機械点検）
type: REQ
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
llm_context: task
---

# 現行性

## 要求文

どれが現行（いま効いている版）かを機械的に判別できること。[R2] リンタは、編集された一つの文書について、型ごとの `status` 許可表・`id` とファイル名の一致・型と置き場所の整合を点検し、ずれがあれば助言として指摘する。

## 優先度

高

## 受入基準参照

TEST-007（§6 R2 行に対応する pass/fail）

## 出所

仕様 §2 R2 現行性、§3.2／§3.3／§3.4。

<!-- 入れない: 実現方法 -->
