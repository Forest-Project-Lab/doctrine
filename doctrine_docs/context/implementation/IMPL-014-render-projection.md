---
id: IMPL-014
title: `render-projection.py` の実装メモ
type: IMPL
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/render-projection.py]
depends_on: [SPEC-014]
llm_context: task
---

# `render-projection.py` の実装メモ

SPEC-014 を実装する、投影描画スクリプトの実装メモである `[R1]`。

## 実装制約

- `_collect_docs` は os.walk で順序を整えて走査し、フロントマターだけを読む（本文は読まない）。id が重複したときは、先に見つけたパスを採る。
- `_max_updated` は、投影の `updated` を各源の `updated` のうち最大のものにそろえる。壁時計は読まない（冪等）。
- `render_overview` と `render_icd_index` は明示キーで並べる。`_splice_ctxmap` は印の内側だけを書き換え、外側の散文はそのまま保つ。
- `_atomic_write` は一時ファイルを経由して書き、途中状態が残らないようにする。

## 注意点

- 投影そのもの（`_is_projection_doc` で判定する）は Overview の一覧に載せない。これにより、`all` で描画したあと `--check` しても、自分自身を載せたことによるずれは出ない。
- `_do_check` は、Context Map では印の内側（骨組み）だけを比べる。外側の散文はドリフト扱いにしない。
- 投影のフロントマターは、固定したキー順で `type: OVERVIEW`・`id: OVERVIEW-<n>` とする（C8とは凍結した契約の整合を見る判断項目をいう）。

## 対象部品

`plugin/scripts/render-projection.py`（`render_overview`・`render_icd_index`・`render_ctxmap_skeleton`・`_splice_ctxmap`・`_do_check`）。共有の `_depgraph`・`_frontmatter`・`_registry` を import する。
