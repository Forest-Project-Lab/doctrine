---
id: IMPL-013
title: `collect-context.py` の実装メモ
type: IMPL
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/collect-context.py]
depends_on: [SPEC-013]
llm_context: task
---

# `collect-context.py` の実装メモ

SPEC-013 を実装する、パック・スクリプトの実装メモである `[R5]`。

## 実装制約

- `build_pack` は、`_depgraph.build_graph` で依存グラフを組む。そのうえで、被覆を計算する前に `effective_llm_context` を見て never 群を除外する `[R5]`。
- `greedy_cover` は、貪欲法で覆ったあと不要な文書を後ろ向きにそぎ落とし（reverse-prune）、最少集合に寄せる。`_covers` と `_dep_closure` は depends_on の辺だけを、循環があっても止まらない形でたどる。
- `dependency_closure` は depends_on をたどって ICD を多段に同梱する。never 文書は引かないしたどらない。
- `load_task_pack_cap` は `task_pack_token_cap` だけを読む（`injection_token_cap` は読まない。C10とは凍結した契約の整合を見る判断項目をいう）。

## 注意点

- 出所は、各事実に `source_id` と `source_path` で必ず付ける。語彙の近い文書を取り違えないためである。
- `_enforce_cap` は、ある要求を唯一覆っている文書を落とさない。
- 覆えなかった要求は uncovered として表に出し、その理由を `_uncovered_reasons` で添える。

## 対象部品

`plugin/scripts/collect-context.py`（`build_pack`・`greedy_cover`・`dependency_closure`・`load_task_pack_cap`・`_enforce_cap`）。共有の `_depgraph`・`_frontmatter`・`_registry` を import する。
