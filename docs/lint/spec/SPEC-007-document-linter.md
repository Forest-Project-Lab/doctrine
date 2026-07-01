---
id: SPEC-007
title: 単一文書リンタの全 PostToolUse 点検
type: SPEC
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/docs-linter.py]
depends_on: [REQ-005, REQ-006, REQ-007, ICD-001, ICD-002]
llm_context: task
---

# 単一文書リンタの全 PostToolUse 点検

`docs-linter.py`（リンタ）は、編集された一つの文書だけを点検する。現行性[R2]と境界のずれを助言として知らせるだけで、編集を拒否することはない。拒否はガードに委ねる[R7]。

## 入出力

- 入力: PostToolUse の Hook（編集などのイベントで起動するスクリプト）が渡す JSON を標準入力で受け取る。点検する対象パスは、`tool_input.file_path`、`tool_input.path`、`tool_response.filePath`、最上位の `file_path` の順に探し、どれも無ければ `argv[1]` を使う。
- 返す値: 何か見つかれば、`hookSpecificOutput.additionalContext` に `[severity] CODE: message` の行を並べた助言 JSON を返す。何も無ければ空を返す。終了コードは常に 0 にする。

## 制約

- 標準ライブラリだけを使う。文書は編集された一つだけを読み、全件は走査しない。`decision` は決して返さず、助言だけを出す[R7]。
- 各点検の重大度は次のとおり。`MISSING_KEY`・`EMPTY_KEY`・`BAD_STATUS`・`UNKNOWN_TYPE`・`ID_FILENAME_MISMATCH`・`BAD_FILENAME`・`TYPE_LOCATION_MISMATCH`・`DOMAIN_PATH_MISMATCH`は ERROR（重大度・誤り）。`BAD_LLM_CONTEXT`は、値が不正なら ERROR、既定値の上書きなら WARN（重大度・警告）。`RESEARCH_HAS_DECISION`は WARN。`SPEC_MISSING_SECTION`・`SPEC_EMPTY_SECTION`・`MISSING_TRACE`は ERROR。
- 必須キーの 8 つも、`status` の型別許可表も、登録簿（model）に問い合わせる。`_system` の固定ファイル名は、`id` とファイル名の一致点検を免除する。
- 依存先がどのドメインに属するかは dep-graph に解決を委ねる。解決できない依存は、ERROR で止めず `ICD_DEP_UNVERIFIED`（WARN）に落とす。別ドメインの ICD 以外を横断して依存していれば `ICD_DEP_VIOLATION`（助言の ERROR）を出すが、それでも編集は拒否しない[R7]。

## エラー時挙動

- 例外は投げない。内部で例外が起きたときは、その旨の注記を助言に出し、終了コード 0 を返す。こうして後続の Hook の連鎖を壊さない。
- フロントマターが無い、または読み取れないときは、`MISSING_FRONTMATTER`（ERROR）一件だけを出して止める。他の点検はいずれも型の情報を要するためである。
- 既に削除されてディスク上に無いファイルには、何も出さない。

## 受入基準

- `tests/test_linter.py` の各点検が、発火すべき入力と発火すべきでない入力の両方で期待どおりに動く。観点ごとの対応は TEST-007 に示す。`decision` は決して出さない。

<!-- 入れない: 廃止、検討、実装コードの写し -->
