---
id: TEST-017
title: templates の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
sources: [plugin/tests/test_templates.py]
depends_on: [SPEC-017]
llm_context: task
---

# templates の検証

テンプレートの受入を検証する（件数は在庫表が持つ。ADR-075）。`[R8]`

## 受入基準への対応

SPEC-017 の受入基準に対応する。次の各点を確認する。ディスク上の `*.md.tmpl` の集合が在庫表（`TYPE_TEMPLATES` と投影の種）と過不足なく一致すること。各テンプレートの既定の `status`・`llm_context` が登録簿と一致すること。SPEC が必須4節の見出しを持つこと。PROC が4節（目的と発動条件・前提・手順・切り戻し）の見出しを持つこと。DECIDED・WATCH が `review_by` 欄を持つこと。投影テンプレートが冒頭の注記を持つこと。GLOSSARY の雛形が承認語の表を持つこと。icd-index の型が `OVERVIEW` であること。

## 退行観点

次の各点が崩れていないかを WATCH と突き合わせて確かめる。「入れない」項目が HTML コメントにとどまり、投影に出ないこと。新しい型コードを先に作らないこと。

## 合否基準

`plugin/tests/test_templates.py` が合格する。

<!-- 入れない: 無関係な要求 -->
