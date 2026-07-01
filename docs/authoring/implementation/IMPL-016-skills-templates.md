---
id: IMPL-016
title: skills/templates の実装注記
type: IMPL
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.1]
depends_on: [SPEC-016, SPEC-017]
llm_context: task
---

# skills/templates の実装注記

7つの技能と19個のテンプレートを実装するうえでの制約を記す。`[R8]`

## 実装制約

技能は `skills/<name>/SKILL.md` と `references/*.md` で構成し、本文は500行未満に保つ。`description` は三人称で書く。各技能は `## 保証限界` 節と、予防・検出・委ねるの三層を持つ。機械で割り切れる処理は `scripts/` のスクリプト（点検を機械にやらせる処理）に任せ、技能の本文には登録簿を書き写さない。

テンプレートは、`templates/<型コード>.md.tmpl` の18種と `icd-index.md.tmpl` で計19個。既定の `status`・`llm_context` を登録簿に合わせる。`glossary.md.tmpl` が20個の承認語の表と9行のカルク表を持ち、これが §1 を写した体系内で唯一の場所となる。

## 注意点

技能の本文と `references/` も体系の文書とみなし、用語チェッカーで点検する（自分の道具を自分にも使う）。icd-index の型は `OVERVIEW` なので、リンタが行う id とファイル名の照合、型と置き場所の照合は、`_system` の投影ファイル名をあらかじめ許可一覧に載せておくことを前提とする。「入れない」項目は HTML コメントにとどめ、投影には出さない。

## 対象部品

`plugin/skills/`（7つの技能）・`plugin/templates/`（19個のテンプレート）。

<!-- 入れない: 仕様の正本 -->
