---
id: IMPL-002
title: `_frontmatter.py` の実装メモ
type: IMPL
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [SPEC-002]
llm_context: task
---

# `_frontmatter.py` の実装メモ

SPEC-002 のフロントマター解析契約を実装するときの制約と、はまりやすい落とし穴をまとめる。[R3][R8]

## 実装制約

- 標準ライブラリだけで書く。解析は自前の行スキャナで行い、PyYAML は使わない。
- `FRONTMATTER_VERSION=1` を持つ。解析の意味を変えたら、この値を上げる。
- 行の走査は改行種別をまとめて扱うが、本文は元テキストから切り出し、改行の様式をそのまま残す。
- 先頭の BOM は、ちょうど一つだけ取り除いてから処理する。

## 注意点

- 内容がどうであっても例外を投げないこと。閉じの `---` が無い、行が不正、引用が閉じていない、といった場合は構造化エラー（errors）で伝え、読める所まで解析した結果を返す。
- 真偽値に変換するのは引用なしの true/false だけとし、yes/no/on/off は文字列のまま残す。
- 重複キーは後に出たものを採るが、`duplicate_key` を必ず併せて記録する。
- `missing_open` は出さない。厳格な呼び出し側のために予約してある。フロントマターが無いのは誤りではなく、`({}, text, [])` を返す。
- 値の中の `#` は、引用の外にあり、かつ直前が空白のときだけ注記とみなして落とす。`SPEC-014#3` のような `#` はそのまま残す。

## 対象部品

`plugin/scripts/_frontmatter.py`。公開関数は parse・parse_file・parse_frontmatter・as_list。内部関数は `_parse_lines`・`_scalar`・`_parse_flow_list`・`_slice_body`・`_split_first_unquoted_colon`・`_strip_inline_comment`。

<!-- 入れない: 仕様の正本 -->
