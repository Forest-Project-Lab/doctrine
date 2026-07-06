---
id: TEST-002
title: フロントマター解析契約のテスト計画
type: TEST
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [SPEC-002]
llm_context: task
---

# フロントマター解析契約のテスト計画

SPEC-002 のフロントマター解析契約を検証する。実装テストは `plugin/tests/test_frontmatter.py`（解析の事例 T1（解析行列の事例番号）から T27（同）までの解析行列）。[R3][R8]

## 受入基準への対応

- `parse` がどの入力でも例外を投げない。
- フロントマター無しなら `({}, text, [])` を返す。閉じ無しなら残りを解析し、body を空とし、`missing_close` を記録する。
- 真偽値（true/false だけ）・None・空文字・空リストを区別する。
- 本文の CRLF をそのまま残す。重複キーは後のものを採り、`duplicate_key` を併記する。
- フローリスト・引用・行内の注記を正しく扱う。`as_list` が None・スカラ・リストを正しく変換する。

## 退行観点

- `入出力` の中の `出力` のような複合語を誤検出しないのは用語チェッカー側の役目だが、解析が本文を改変しないことを確認し、下流に誤検出の元を作らない（WATCH-001 と整合する）。
- `missing_open` を `parse` が出さないこと。
- `parse_file` が、内容では例外を投げず、読み書きや復号の失敗のときだけ例外を投げること。

## 合否基準

T1–T27 の全ケースが期待どおりの (fm, body, errors) を返し、どの入力でも例外を投げないことと、CRLF をそのまま残すことが成り立ったとき合格とする。

<!-- 入れない: 無関係な要求 -->
