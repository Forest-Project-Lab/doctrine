---
id: REQ-006
title: 用語統一（未承認語・禁止同義語を弾く）
type: REQ
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
llm_context: task
---

# 用語統一

## 要求文

同じ概念を同じ語で書けること。[R6] 用語チェッカーは、承認辞書（§1）に対して禁止同義語の出現（`BANNED_SYNONYM`）と、辞書にない専門語の初出（`UNDEFINED_TERM`）を機械的に照合し、指摘する。辞書はこの体系の中で一度だけ符号化し、二重定義しない。

## 優先度

高

## 受入基準参照

TEST-008（§6 R6 行に対応する pass/fail）

## 出所

仕様 §1 用語辞書、§2 R6 用語統一、§4.2。

<!-- 入れない: 実現方法 -->
