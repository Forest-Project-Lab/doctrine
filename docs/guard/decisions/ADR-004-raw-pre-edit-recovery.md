---
id: ADR-004
title: PostToolUse の事前状態を raw 全文で復元する
type: ADR
domain: guard
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/policy-guard.py]
depends_on: [SPEC-003]
llm_context: task
---

# PostToolUse の事前状態を raw 全文で復元する

ADR（設計判断の記録）。1 文書 1 決定。

## 背景
PostToolUse の削除安全ガードが直接読めるのは、書き込んだ後の状態（POST: 書き込み後）だけである。この POST だけを見て降格や本文消しを判じると、もとから deprecated だったり本文が空だったりする文書を、無関係な編集で取り違えて block してしまう。本物の降格・本文消しは書き込む前の状態（PRE: 書き込み前）から POST への遷移なので、PRE の状態を復元しなければ見分けられない。`[R4]`

## 却下した選択肢
- POST の状態だけで判じる: もとから deprecated だったり本文が空だったりする文書への無関係な編集を、取り違えて block する。
- フロントマターと本文から組み直した近似に編集を逆当てする: 組み直したフロントマターのバイト列は原文と食い違うことがあり、フロントマター内を触る編集では逆当てが外れる。

## 決定
PostToolUse でディスクから読んだ生の全文に、Edit・MultiEdit を逆向きに当てて PRE の全文を復元する。復元した PRE から POST への遷移が、本物の降格（現行→廃止・置換・アーカイブ）または本文消しに当たるときだけ block する。逆向きに当てられないときは、安全側として現行かつ本文ありを既定にする。

## 帰結
`_post_delete_safety`・`_reconstruct_pre_edit_state`・`_invert_edits` がこれを実装する。逆向きの当て直しは生の全文（raw_post_text）に対して行い、生の全文が無いときだけ、組み直した近似に退避する。これで取り違えの block が消え、削除安全は本物の遷移だけを咎めるようになる。

<!-- 入れない: 複数決定、現行仕様の全文 -->
