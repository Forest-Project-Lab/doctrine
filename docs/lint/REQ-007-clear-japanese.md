---
id: REQ-007
title: 明快な日本語（カルクを照合する）
type: REQ
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
llm_context: task
---

# 明快な日本語

## 要求文

訳語臭（カルク）を排せること。[R10] 用語チェッカーは、§1 の禁止表現（カルク辞書）を機械的に照合し（`CALQUE`）、一語訳の罠（`CALQUE_WORDTRAP`）を警告する。一覧に無い訳語臭は doc-review の逆翻訳テルに委ねる。

## 優先度

中

## 受入基準参照

TEST-008（§6 R10 行に対応する pass/fail）

## 出所

仕様 §1 禁止表現（カルク辞書）、§2 R10 明快な日本語。

<!-- 入れない: 実現方法 -->
