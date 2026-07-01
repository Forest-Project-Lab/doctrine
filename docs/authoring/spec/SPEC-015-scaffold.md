---
id: SPEC-015
title: scaffold（_system 非破壊シード）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/scaffold.py]
depends_on: [REQ-011]
llm_context: task
---

# scaffold（_system 非破壊シード）

`scaffold.py` は初期化の足場を置く。置くのは `_system` の最小限のファイルとルートの案内だけで、既存は壊さない。`[R1][R8]`

## 入出力

入力は CLI（コマンド行）引数 `scaffold.py [--level {2,3,4}] [--root PATH] [--dry-run] [--fallback]`（試験用に `--today` を持つ）。書き出すのは次のファイルだけである。各ファイルのフロントマター（文書先頭の YAML メタデータ）の日付欄は、実行した日付で埋める。

- `docs/_system/glossary.md`（GLOSSARY。§1 の承認語表とカルク表を雛形に写す）。
- `docs/_system/decided-facts.md`（DECIDED。`review_by` を created+90日で埋める）。
- `docs/_system/non-goals.md`（NONGOAL）。
- `docs/_system/overview.md`（OVERVIEW 投影の雛形。本文に「自動で描画される。手で編集しない」と記す）。
- `docs/_system/.docs-level`（`level: N` の一行。いま使われている Level を公開する）。
- ルートの `AGENTS.md`・`CLAUDE.md`（案内の投影。知識は持たせない）。

`--fallback` を付けると、`_system` の文書と案内を `.claude/` 配下へ移す（プラグインを導入していない場合の経路）。

## 制約

標準ライブラリだけで動き、pip も通信も使わない。書き込みは原子的で、何度実行しても結果は変わらない。対象が既にあれば飛ばし、上書き・併合・切り詰めはしない。ドメインのフォルダ・各層・watchlist・context-map・icd-index・hooks・skills は先に作らない。DECIDED の `review_by` は created+90日に設定する。GLOSSARY の雛形は §1 の表をそのまま写すので、辞書を二重に定義しない。

## エラー時挙動

`--dry-run` は何を書くかを表示するだけで、ディレクトリも文書も書かない。引数の誤りは終了コード 2 とする。入出力エラー（権限不足や読み取り専用）も 2 とする。原子的な書き込みが一時ファイルを片づけるので、書きかけのファイルは残らない。

## 受入基準

最小集合を、過不足なくちょうど置くこと。書き出した文書が、リンタの必須キーと日付の点検を通ること。DECIDED の `review_by` が空でなく、created+90日であること。全ファイルを飛ばした場合でも終了コード 0 を返すこと。以上を TEST-015 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
