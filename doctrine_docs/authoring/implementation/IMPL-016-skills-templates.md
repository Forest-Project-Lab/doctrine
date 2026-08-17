---
id: IMPL-016
title: skills/templates の実装注記
type: IMPL
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-16
sources: [spec/doctrine.ja.md §4.1]
depends_on: [SPEC-016, SPEC-017]
llm_context: task
---

# skills/templates の実装注記

8つの技能と、型ごとのテンプレートを実装するうえでの制約を記す。`[R8]`

## 実装制約

技能は `skills/<name>/SKILL.md` と `references/*.md` で構成し、本文は500行未満に保つ。`description` は三人称で書く。各技能は `## 保証限界` 節と、予防・検出・委ねるの三層を持つ。機械で割り切れる処理は `scripts/` のスクリプト（点検を機械にやらせる処理）に任せ、技能の本文には登録簿を書き写さない。

テンプレートは、`templates/<型コード>.md.tmpl`（登録簿の各型）と `icd-index.md.tmpl` から成る。**件数は書かない**——数は在庫表（`plugin/tests/test_templates.py`）と登録簿が持つ（ADR-075。以前ここは「19種で計20個」と書いたまま実物が 21 個になっていた）。既定の `status`・`llm_context` を登録簿に合わせる。`glossary.md.tmpl` が承認語の表とカルク表を持ち、これが §1 を写した体系内で唯一の場所となる。

## 注意点

技能の本文と `references/` も体系の文書とみなし、用語チェッカーで点検する（自分の道具を自分にも使う）。icd-index の型は `OVERVIEW` なので、リンタが行う id とファイル名の照合、型と置き場所の照合は、`_system` の投影ファイル名をあらかじめ許可一覧に載せておくことを前提とする。「入れない」項目は HTML コメントにとどめ、投影には出さない。

## 対象部品

`plugin/skills/`（8つの技能）・`plugin/templates/`（型ごとのテンプレートと投影の種）。

<!-- 入れない: 仕様の正本 -->
