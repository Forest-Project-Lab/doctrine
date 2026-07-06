---
id: SPEC-002
title: フロントマター解析の契約
type: SPEC
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [REQ-001, DATA-001]
llm_context: task
---

# フロントマター解析の契約

`scripts/_frontmatter.py` が公開する、フラット YAML のフロントマター解析の契約を定める。フロントマターとは、文書冒頭に置くメタデータ部をいう。[R3][R8]

## 入出力

- `parse(text) -> (fm, body, errors)`: フロントマターの写像、本文、構造化エラーの列を返す。冒頭が `---` でなければ `({}, text, [])` を返す。フロントマターが無いのは誤りではない。
- `parse_file(path) -> (fm, body, errors)`: utf-8-sig で読み、改行は変換しない。解析は `parse` に委ねる。
- `parse_frontmatter(text) -> dict`: 写像だけを返す。
- `as_list(value) -> list`: 値が None か空文字なら空リストを、スカラ `x` なら `['x']` を返す。リストはそのまま返す。

sources, depends_on, impacts, canonical_for などリスト型のキーは、None やスカラで返ることがある。そのため呼び出し側は必ず `as_list` を通して読む。

## 制約

- 標準ライブラリだけで実装する。PyYAML は使わない。
- 値は既定で文字列とする。引用なしの true/false だけを真偽値に、null/~/空を None に変換する。引用付きは変換しない。
- None・空リスト・空文字を区別する。それぞれ、空のキー、明示した `[]`、引用した空文字列にあたる。
- 本文の改行はそのまま残す（CRLF は CRLF のまま）。
- 重複キーは後に出たものを採り、`duplicate_key` エラーを併せて出す。
- エラー記録の形は `{code, line, key, detail}`。`missing_open` は厳格な呼び出し側のために予約し、`parse` は出さない。

## エラー時挙動

- 内容がどうであっても例外を投げない。編集途中の半端な内容でも、読める所まで解析した結果と構造化エラーを返し、毎ターン起動する Hook が落ちないようにする。
- 閉じの `---` が無ければ、残り全行を解析し、body は空とし、`missing_close` を記録する。
- `parse_file` は、読み書きや復号に失敗したとき（不在・ディレクトリ・権限・復号失敗）だけ例外を投げる。

## 受入基準

- `parse` がどの入力でも例外を投げない。
- 真偽値・None・空の区別、CRLF をそのまま残すこと、重複キーで後のものを採りエラーを併記すること、これらが成り立つ。
- フロントマター無し、閉じ無し、フローリスト、引用が、想定どおり解析される。
- 対応するテストは TEST-002（解析の事例 T1（解析行列の事例番号）から T27（同）までの行列）が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
