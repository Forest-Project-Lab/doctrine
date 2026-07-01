---
id: IMPL-007
title: `docs-linter.py` の実装メモ
type: IMPL
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/docs-linter.py]
depends_on: [SPEC-007]
llm_context: task
---

# `docs-linter.py` の実装メモ

## 実装制約

- 各点検は `_check_*` という関数として並べ、`lint_text` が登録簿の順に呼ぶ。`decision` は決して立てず、`build_response` は `additionalContext` だけを組み立てる[R7]。
- 必須キー・`status`・型・置き場所は `_registry` に問い合わせる。フロントマターの解析には `_frontmatter.parse` を使う。各点検を ERROR（重大度・誤り）と WARN（重大度・警告）のどちらにするかは、SPEC-007 の表に従う[R2]。

## 注意点

- 依存先がどのドメインに属するかは、`_build_graph_for` が `_depgraph.build_graph` を一度だけ呼んで解決する。`_depgraph` が無い環境では、止まらずに `ICD_DEP_UNVERIFIED`（WARN）へ落として動き続ける。
- `_is_system_singleton` は、`_system` の固定ファイル名（投影と正本）を、id とファイル名の一致点検から外す。
- `main` は、標準入力の読み取り・パスの解決・点検・助言文の組み立てをすべて例外処理で包み、終了コードは常に 0 を返す。

## 対象部品

`plugin/scripts/docs-linter.py`。`_registry`・`_frontmatter`・`_termcheck`・`_depgraph` を import する。

<!-- 入れない: 仕様の正本 -->
