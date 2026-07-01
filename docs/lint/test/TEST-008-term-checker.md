---
id: TEST-008
title: 用語チェッカーのテスト計画
type: TEST
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_termcheck.py]
depends_on: [SPEC-008]
llm_context: task
---

# 用語チェッカーのテスト計画

## 受入基準への対応

- SPEC-008 の四つの照合規則 `BANNED_SYNONYM`・`CALQUE`[R10]・`CALQUE_WORDTRAP`・`UNDEFINED_TERM`[R6] を、発火すべき入力と発火すべきでない入力の両方で確認する。
- 種子への切り替えを確認する。運用辞書が無いときは種子を使うこと、解析に失敗したときは種子を使ったうえで `GLOSSARY_PARSE_ERROR` を添えることである。あわせて、GLOSSARY 正本と投影の本文を点検から飛ばすことも確認する。

## 退行観点

- `入出力`の中の`出力`、`現在形`の中の`現在`を誤検出しないこと（複合語の覆い隠し）。WATCH に挙げた懸念事項と突き合わせて確かめる。
- 末尾注記の場合分け: 「可」を含む注記は文字列照合の対象にせず、含まない注記は素のトークンを照合すること。
- 辞書を二重に定義しない、すなわち承認語表をハードコードしないこと[R6]。

## 合否基準

- `tests/test_termcheck.py` が全観点で合格すること。期待どおりのコード・重大度・行番号で発火し、擬陽性が無いことを合格とする。

<!-- 入れない: 無関係な要求 -->
