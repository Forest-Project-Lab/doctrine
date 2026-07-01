---
id: ICD-001
title: model のインターフェース（登録簿と解析の公開契約）
type: ICD
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
canonical_for: [type-registry, status-vocabulary, frontmatter-schema, frontmatter-parser, llm-context-policy]
llm_context: task
---

# model ICD

model ドメインは、構造規則とフロントマターの解析を、体系の唯一の正本として公開する。構造規則とは、型・`status`・置き場所・必須キーの定めをいう。フロントマターとは、文書冒頭に置くメタデータ部をいう。他ドメインはこれらの規則を二重定義しない。この ICD が指す公開関数だけに依存する。[R2][R3][R6][R8]

## 公開する用語

- 文書: 管理対象の最小単位。
- 型: 18 種類の文書種別（ICD・REQ・SPEC など）。
- 正本: ある事実の唯一の権威ある出所。
- 投影: モデルから描画した派生表示。手で保守しない。
- 現行: いま効力を持つ版（`status`=current/accepted）。
- 依存: 文書が他文書を前提とする関係（`depends_on`）。

語の唯一の意味は用語辞書の正本（`_system/glossary.md`）に従う。

## 正本である事実

本 ICD だけが正本である事実を以下に挙げる。`canonical_for` の値と対応する。

- type-registry: 18 型の登録簿。型の順序、既定 `status`、既定 `llm_context`、置き場所を定める。
- `status-vocabulary`: `status` の統制語彙 8 値。accepted は ADR だけに使う。draft は RESEARCH だけに使う。
- frontmatter-schema: 必須 8 キー（`id`, title, `type`, `domain`, `status`, `owner`, `updated`, `sources`）。created は必須としない。DECIDED と WATCH は `review_by` も必須とする。
- frontmatter-parser: フロントマター解析が 3 要素を返す契約。詳細は後述する。
- llm-context-policy: 既定 `llm_context` の表と、その解決規則。フロントマターでの上書きを既定より優先する。

## データ契約

他ドメインが依存してよい公開関数（`scripts/_registry.py`・`scripts/_frontmatter.py`）。

登録簿（`_registry.py`）:

- `type_of(id)`: `id` の接頭辞から型を返す。接頭辞が未知のとき、または `id` が不正なときは None を返す。
- `status_allowed(type)`: 型ごとに許可する `status` の集合を返す。毎回その複製を返す。
- `effective_llm_context(meta)`: `llm_context` を解決する。フロントマターでの上書きを既定より優先する。
- `allowed_locations(type)`: 型ごとに許可する置き場所のパターンを返す。毎回その複製を返す。
- `is_projection(type)`: 投影型（OVERVIEW・CTXMAP）かどうかを返す。
- `is_current(status)`: 現行（current・accepted）かどうかを返す。
- `required_keys(level, type)`: 必須キーの列を返す。level が不正なら ValueError を投げる。

解析（`_frontmatter.py`）:

- `parse(text) -> (fm, body, errors)`: 内容がどうであっても例外を投げない。
- `parse_file(path)`: utf-8-sig で読む。読み書きに失敗したときだけ例外を投げる。
- `parse_frontmatter(text) -> dict`: 写像だけを返す。
- `as_list(value) -> list`: 値が None か空なら空リストを、スカラなら 1 要素のリストを返す。

`domain_of(id)` は本 ICD に置かない。`id` だけではドメインが決まらないため、その解決は graph ドメイン（ICD-002）に委ねる。

## 依存してよい入口

他ドメインは本 ICD（ICD-001）だけを `depends_on` できる。`_registry.py` や `_frontmatter.py` の内部文書を直接 `depends_on` してはならない。

<!-- 入れない: 内部実装、内部の検討 -->
