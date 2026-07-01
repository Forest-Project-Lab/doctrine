---
id: ICD-004
title: lint のインターフェース（リンタと用語チェッカーの公開契約）
type: ICD
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/docs-linter.py]
depends_on: [ICD-001, ICD-002]
canonical_for: [document-lint, term-check]
llm_context: task
---

# lint ICD

リンタ（文書を機械的に点検するスクリプト）と用語チェッカー（リンタのうち、未承認語と未定義語を弾く機能）の公開契約。

## 公開する用語

- リンタ: 一つの文書を機械的に点検するスクリプト。助言だけを出し、決して拒否しない。
- 用語チェッカー: リンタのうち、未承認語・禁止同義語・カルク・未定義語を弾く機能。

## 正本である事実

- `document-lint`: PostToolUse での単一文書点検の契約と、その検出コード集合の正本。
- `term-check`: 承認辞書に対する照合規則（`check(body, meta, glossary) -> Finding[]`）の正本。

## データ契約

- リンタの助言: `docs-linter.py` は、PostToolUse の Hook（編集などのイベントで起動するスクリプト）が渡す JSON を標準入力で受け取る。何か見つかれば、`hookSpecificOutput.additionalContext` に `[severity] CODE: message` の行を並べた助言 JSON を返す。`decision` も `permissionDecision` も返さず、終了コードは常に 0 にする。
- 用語チェッカー: 関数は `check(body, meta, glossary) -> Finding[]`。`Finding` は `(code, severity, message, line)` の四つ組である。
- 検出コードの一覧は次のとおり。フロントマターと登録簿に関わる `MISSING_FRONTMATTER`・`MISSING_KEY`・`EMPTY_KEY`・`BAD_STATUS`・`UNKNOWN_TYPE`・`ID_FILENAME_MISMATCH`・`BAD_FILENAME`・`TYPE_LOCATION_MISMATCH`・`DOMAIN_PATH_MISMATCH`・`BAD_LLM_CONTEXT`・`RESEARCH_HAS_DECISION`・`SPEC_MISSING_SECTION`・`SPEC_EMPTY_SECTION`・`MISSING_TRACE`・`ICD_DEP_VIOLATION`・`ICD_DEP_UNVERIFIED`、用語側の `BANNED_SYNONYM`・`CALQUE`・`CALQUE_WORDTRAP`・`UNDEFINED_TERM`・`GLOSSARY_PARSE_ERROR`。

## 依存してよい入口

- 型・`status`・置き場所・必須キーを定める登録簿は、model の ICD（ICD-001）に依存して引く。
- 依存先がどのドメインに属するかの解決は、graph の ICD（ICD-002）に依存して引く。
- 他ドメインがこの lint に依存してよいのは、この ICD だけである。lint の内部スクリプトを直接 depends_on することはできない。

<!-- 入れない: 内部実装、内部の検討 -->
