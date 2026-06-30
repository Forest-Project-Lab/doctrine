# 型登録簿への案内（§3.2）

型登録簿の表をここに写さない。正本は §3.2 にある。各文書はこの表を二重定義しない（§3）。

## 引き方

- 型コードは `id` の接頭辞である（例 `SPEC-014` の `SPEC`）。置き場所と既定の `llm_context` を決める。
- リンタは、型と置き場所と `status` の整合をこの表で点検する。
- 既定の `status` と `llm_context` は型ごとに §3.2 が定める。`ADR` は `accepted`、`CHANGE` は `proposed`、`RESEARCH` は `draft`（`llm_context: never`）、`ARCHIVE` は `archived`（`llm_context: never`）。それ以外の多くは `current`。
- 新しい型を増やすのは、既存型で表せない情報が出てからにする。空の型を先に作らない（§3.2／§8 最小性）。

## コードで持たない

型→置き場所→既定 `status`→`llm_context` の対応は、`${CLAUDE_PLUGIN_ROOT}/scripts/_registry.py` が唯一の符号化として持つ。スキルもリンタも、この対応を別に書き写さない。
