---
id: IMPL-006
title: `_depgraph.py`＋`dep-graph.py` の実装メモ
type: IMPL
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_depgraph.py]
depends_on: [SPEC-006]
llm_context: task
---

# `_depgraph.py`＋`dep-graph.py` の実装メモ

## 実装制約

- `Graph` は構築時に隣接表（`_dep_out` / `_imp_out` / `_dep_in`）を確定する。`_closure` と `_reverse_closure` は訪問済みの集合を持ち、循環があっても止まりながら推移閉包を出す。[R4]
- `build_graph` は `os.walk` の結果を整列して走査するため、毎回同じ順序でファイルを読む。フロントマターは `_frontmatter.parse_file` と `as_list` で読み、`status` が欠けていれば `_registry.default_status` で補う。
- `classify_edges` の `_classify_one` は、depends_on 端にだけ `cross_domain_violation` を付け、越境した impacts 端は `cross_domain_impact` にする。[R7]
- `reverse_orphans` は現行文書だけを対象に、depends_on をたどって集計する。[R3]

## 注意点

- 同じ id が重複したときは、パスを整列した順で後に来たものを採り、両方を `dup_ids` に残す。
- id を持たないファイルは `parse_warnings` に回し、ノードにはしない。
- CLI の終了コードは、所見の有無にかかわらず成立すれば 0、使い方の誤りで 2、ルート不在で 3 とする。所見が見つかったことを終了コードで止めるゲートにはしない。

## 対象部品

`plugin/scripts/_depgraph.py`（`Graph`・`build_graph`・`classify_edges`・`reverse_orphans`）と、`plugin/scripts/dep-graph.py`（CLI のモード・終了コード・`_emit`）を対象とする。
