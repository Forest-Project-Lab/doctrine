---
id: TEST-015
title: scaffold の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-13
sources: [plugin/tests/test_scaffold.py, plugin/tests/test_read_surface.py]
depends_on: [SPEC-015]
llm_context: task
---

# scaffold の検証

`scaffold.py` の受入を検証する。`[R8]`

## 受入基準への対応

SPEC-015 の受入基準に対応する。次の各点を確認する。最小集合を過不足なくちょうど置くこと。書き出した文書がリンタの必須キーと日付の点検を通ること。DECIDED の `review_by` が空でなく created+90日であること。GLOSSARY が §1 の表を写していること。OVERVIEW が置いた正本を列挙し、**初期化直後のコーパスに指示文以外の所見が出ず、指示文の所見が `_system/` に限られる**こと（ADR-098。以前は「所見ゼロで通る」を凍結していたが、その緑は偽りだった）、`render-projection --check` とずれないこと。**凍結自身の実効を実測してある**（2026-08-03）: 指示文の検査を外すと「指示文の所見が一件も出ない」で落ち、戻すと通った。既存の overview には導出でも触れないこと。`--root` に `doctrine_docs/` を渡した取り違えに注意書きが出ること。ルートの案内が知識を持たないこと。

## 退行観点

次の各点が崩れていないかを WATCH と突き合わせて確かめる。既存ファイルを上書き・併合・切り詰めしないこと。ドメインのフォルダ・各層・watchlist・context-map・icd-index・hooks・skills を作らないこと。`--dry-run` が何も書かないこと。

## 合否基準

全飛ばしでも終了コード 0、引数誤りと入出力エラーで 2。`plugin/tests/test_scaffold.py` が合格する。

<!-- 入れない: 無関係な要求 -->
