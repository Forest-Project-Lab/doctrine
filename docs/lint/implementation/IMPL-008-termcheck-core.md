---
id: IMPL-008
title: `_termcheck.py` の実装メモ
type: IMPL
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_termcheck.py]
depends_on: [SPEC-008]
llm_context: task
---

# `_termcheck.py` の実装メモ

## 実装制約

- `parse_glossary` は、承認語表とカルク表の二つを見出しで見分けて読む。承認語・禁止同義語・カルク表はハードコードしない[R6]。
- `check` は、四つの点検 `_check_banned_synonyms`・`_check_calque`・`_check_wordtrap`・`_check_undefined` を順に呼ぶ。その前に `mask_body` が、コードフェンス・インラインコード・URL を、長さを保ったまま伏せる。

## 注意点

- `_mask_approved_compounds` は、文字列照合の前に `入出力` や `現在形` を伏せ、覆いの外に素のまま現れた禁止同義語だけを照合に残す[R10]。
- 末尾注記 `（…）` の場合分け: 「可」を含めば文脈依存とみなして文字列照合の対象から外し、含まなければ素のトークンを取り出す。判定には `_TRAILING_PARENS_RE` と `_PARENS_ONLY_RE` を使う。
- 運用辞書が解析できないときは、`_load_template_seed` が同梱テンプレートの種子に切り替える。あわせて `parse_error` を立て、呼び手が `GLOSSARY_PARSE_ERROR` を出せるようにする。

## 対象部品

`plugin/scripts/_termcheck.py`。

<!-- 入れない: 仕様の正本 -->
