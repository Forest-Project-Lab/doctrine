---
id: SPEC-017
title: templates（18型＋icd-index）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §3.4]
depends_on: [REQ-011, ICD-001]
llm_context: task
---

# templates（18型＋icd-index）

テンプレートは、型ごとに様式をかたどった雛形である。18種の型のテンプレートと、1種の投影の雛形（icd-index）で計19個。§1 の語彙を、体系の中でテンプレートが一度だけ書き写し、ほかには持たせない。`[R6][R8]`

## 入出力

入力は型コードである。返すのは `templates/<型コード>.md.tmpl`（小文字）の18種と `icd-index.md.tmpl`。各テンプレートは、§3.4 のフロントマター（文書先頭の YAML メタデータ）と、型ごとの本文見出しを持つ。

## 制約

既定の `status` と `llm_context` は、登録簿（ICD-001）に合わせる。`icd.md.tmpl` は付録A をそのまま写す。`glossary.md.tmpl` は、20個の承認語の表、9行のカルク表、一語訳の行を雛形に持つ。SPEC は、入出力・制約・エラー時挙動・受入基準の4節を必須の見出しに持つ。DECIDED・WATCH は `review_by` を必須欄に持つ。投影テンプレート（overview・ctxmap・icd-index）は、本文の冒頭に「自動で描画される。手で編集しない。」を置く。icd-index の型は `OVERVIEW` とし、新しい型コードは作らない。

## エラー時挙動

「入れない」項目は本文に出さず、`<!-- 入れない: ... -->` の HTML コメントとして書く（投影に出さない）。Level 2 の縮小構成では、ICD・REQ・SPEC・ADR・DECIDED・OVERVIEW の6型だけを使う。

## 受入基準

型のテンプレートが18個、投影の雛形が1個あること。各テンプレートの既定値が登録簿と一致すること。SPEC が必須4節の見出しを持つこと。DECIDED・WATCH が `review_by` 欄を持つこと。投影テンプレートが冒頭の注記を持つこと。GLOSSARY の雛形が20個の承認語を持つこと。以上を TEST-017 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
