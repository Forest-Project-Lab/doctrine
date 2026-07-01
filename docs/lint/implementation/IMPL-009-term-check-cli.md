---
id: IMPL-009
title: `term-check.py` の実装メモ
type: IMPL
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/term-check.py]
depends_on: [SPEC-008]
llm_context: task
---

# `term-check.py` の実装メモ

## 実装制約

- 中核 `_termcheck` に処理を渡すだけの薄い入口である。`check_file` は、`_frontmatter.parse_file` で本文を取り出し、`load_glossary` と `check` を呼び、その結果を表示用の文字列に整える[R6]。
- 運用辞書の在処は `_resolve_docs_root` が解決する。`--docs-root` の指定があればそれを使い、無ければファイルから親方向へ `docs` を探す。

## 注意点

- `main` は終了コードを常に 0 に保つ。リンタの一機能として、後続の Hook の連鎖を壊さないためである。
- 引数の解析は最小限で、`[--docs-root R] FILE...` だけを受ける。存在しないファイルは飛ばす。

## 対象部品

`plugin/scripts/term-check.py`。

<!-- 入れない: 仕様の正本 -->
