---
id: TEST-015
title: scaffold の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_scaffold.py]
depends_on: [SPEC-015]
llm_context: task
---

# scaffold の検証

`scaffold.py` の受入を検証する。`[R8]`

## 受入基準への対応

SPEC-015 の受入基準に対応する。次の各点を確認する。最小集合を過不足なくちょうど置くこと。書き出した文書がリンタの必須キーと日付の点検を通ること。DECIDED の `review_by` が空でなく created+90日であること。GLOSSARY が §1 の表を写していること。OVERVIEW が投影の雛形であること。ルートの案内が知識を持たないこと。

## 退行観点

次の各点が崩れていないかを WATCH と突き合わせて確かめる。既存ファイルを上書き・併合・切り詰めしないこと。ドメインのフォルダ・各層・watchlist・context-map・icd-index・hooks・skills を作らないこと。`--dry-run` が何も書かないこと。

## 合否基準

全飛ばしでも終了コード 0、引数誤りと入出力エラーで 2。`plugin/tests/test_scaffold.py` が合格する。

<!-- 入れない: 無関係な要求 -->
