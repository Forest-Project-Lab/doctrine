---
id: IMPL-015
title: scaffold/term-extract の実装注記
type: IMPL
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/scaffold.py, plugin/scripts/term-extract.py]
depends_on: [SPEC-015, SPEC-018]
llm_context: task
---

# scaffold/term-extract の実装注記

`scaffold.py` と `term-extract.py` を実装するうえでの制約を記す。`[R8]`

## 実装制約

`scaffold.py`: テンプレートの場所は `__file__` を基準に `plugin/templates/` として求める。これにより、どのカレントディレクトリから呼んでも、また `${CLAUDE_PLUGIN_ROOT}` 経由でも動く。書き込みは `_atomic_write_new`（一時ファイルに書いてから `os.replace`）で行い、原子的で既存を壊さない。置き換える直前にもう一度ファイルの有無を確かめ、既存があれば上書きしない。`_decided_seed` が `review_by` を created+90日に設定し直す。

`term-extract.py`: `_frontmatter` と `_registry` を同じ階層のモジュールとして取り込む。`scan_corpus` が `docs/` を `os.walk` でたどり、順序を一定に保って走査する。`_doc_is_excluded` が `archive/` と `llm_context:never` の文書を対象から外す。`compute_ctfidf` がまとまり内で L1（成分の絶対値の和）で正規化したスコアを出し、同点は語の昇順で順位を決める。

## 注意点

`--min-df` はその語を含む文書数で語を落とすが、スコアは出現総数で計算する。この2つを取り違えてはならない。トークンへの分割はバイグラムによる近似なので、ノイズを含む。`scaffold.py` は、異常が起きたときに一時ファイルを必ず片づけ、書きかけのファイルを残さない。

## 対象部品

`plugin/scripts/scaffold.py`・`plugin/scripts/term-extract.py`。どちらも共有の `plugin/scripts/_frontmatter.py`・`plugin/scripts/_registry.py` を取り込む。

<!-- 入れない: 仕様の正本 -->
