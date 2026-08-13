---
id: SPEC-015
title: scaffold（_system 非破壊シード）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-13
sources: [plugin/scripts/scaffold.py]
depends_on: [REQ-011]
llm_context: task
---

# scaffold（_system 非破壊シード）

`scaffold.py` は初期化の足場を置く。置くのは `_system` の最小限のファイルとルートの案内だけで、既存は壊さない。`[R1][R8]`

## 入出力

入力は CLI（コマンド行）引数 `scaffold.py [--level {2,3,4}] [--root PATH] [--dry-run] [--fallback] [--list-sections [--type <型>] [--json]]`（試験用に `--today` を持つ）。`--list-sections` は問い合わせであり、足場を一切書かない — 登録簿（ICD-001 の `REQUIRED_SECTIONS`）をその場で読み、型ごとの必須節の名を返す（ADR-159。宣言は ICD-007 の外部条項）。`--json` の返す値は `{"schema": "scaffold-sections/1", "sections": {<型>: [<節名>…]}, "generator": {...}}`（`generator` の意味は ADR-155 と同じ。木を測らないので木の版の鍵は持たない）。`--type` に登録簿に無い型を与えたら使い方の誤り（終了コード 2）。統治木は既定で `doctrine_docs/` に置く。既に `docs/_system` が在る（doctrine が初期化した印を持つ）場合だけ `docs/` を使い続け、統治木を二つにしない（ADR-022）。`_system` を持たない素の `docs/` には決して入植しない。書き出すのは次のファイルだけである。各ファイルのフロントマター（文書先頭の YAML メタデータ）の日付欄は、実行した日付で埋める。

- `doctrine_docs/_system/glossary.md`（GLOSSARY。§1 の承認語表とカルク表を雛形に写す）。
- `doctrine_docs/_system/decided-facts.md`（DECIDED。`review_by` を created+90日で埋める）。
- `doctrine_docs/_system/non-goals.md`（NONGOAL）。
- `doctrine_docs/_system/overview.md`（OVERVIEW 投影。この実行で新規に置いた場合だけ、種蒔きの直後に `render-projection.py` を呼び、置いた正本から導出した一覧で置き直す。既存の overview には触れない）。
- `doctrine_docs/_system/.docs-level`（`level: N` の一行。いま使われている Level を公開する）。
- `doctrine_docs/_system/.governance-state`（`initialized: <作成日>` と `last_cadence_review: <作成日>` を種蒔きする。導入初日を警告・催促で始めないため。ADR-041、#74）。
- ルートの `AGENTS.md`・`CLAUDE.md`（案内。手で保守する最小の入口。知識は持たせない。ADR-029。統治の生存期待の一行を含む: セッション冒頭に契約の注入が無ければ統治は死んでいる、と利用者へ報せる `[R11]`）。既定の Level は 2 とする（ADR-030）。
- ルートの `.gitignore` に `.claude/.cache/` を非破壊で追記する（監査キャッシュを追跡から外す。既存行は消さない。ADR-041、#74）。

`--fallback` を付けると、`_system` の文書と案内を `.claude/` 配下へ移す（プラグインを導入していない場合の経路）。

## 制約

標準ライブラリだけで動き、pip も通信も使わない。書き込みは原子的で、何度実行しても結果は変わらない。対象が既にあれば飛ばし、上書き・併合・切り詰めはしない。ドメインのフォルダ・各層・watchlist・context-map・icd-index・hooks・skills は先に作らない。DECIDED の `review_by` は created+90日に設定する。GLOSSARY の雛形は §1 の表をそのまま写すので、辞書を二重に定義しない。ただし `--level N` が既存の `.docs-level` と食い違うときは、明示の選択として印を更新し昇格・降格を報告する（`.docs-level` は制御の入力であり、内容の種とは別に扱う。非破壊の対象外。ADR-041、#90）。`--dry-run` は後段（Level 更新・`.gitignore` の追記）の意図も見せる。

## エラー時挙動

`--dry-run` は何を書くかを表示するだけで、ディレクトリも文書も書かない。引数の誤りは終了コード 2 とする。入出力エラー（権限不足や読み取り専用）も 2 とする。原子的な書き込みが一時ファイルを片づけるので、書きかけのファイルは残らない。overview の導出に失敗した場合は雛形を残したまま 0 で終わり、`render-projection.py` の手動実行を促す一行を出す。`--root` に `doctrine_docs/` 自体を渡した取り違えには注意書きを出す（処理は続行する）。

## 実装の指紋

対象は契約の要約(モジュール冒頭)。更新は `trace-index.py --id SPEC-015` が返す行を写す（ADR-061）。

- sha256:f27a6b5e1a6f7b9172286f10e315a644b0e41d7fa33ff67ccc531b6bbf5ec7f0

## 受入基準

最小集合を、過不足なくちょうど置くこと。書き出した文書が、リンタの必須キーと日付の点検を通ること。DECIDED の `review_by` が空でなく、created+90日であること。全ファイルを飛ばした場合でも終了コード 0 を返すこと。**初期化直後のコーパスに、人が埋める箇所（雛形の指示文）以外の所見が出ないこと**（ADR-098）。以前は「所見ゼロで通る」を凍結していたが、**その緑は偽りだった** —— 用語辞書の正本が `owner: <記入>` のまま緑で通り、呼び手の木では初期化から今日まで誰も気づかなかった（doctrine#182）。**埋まっていない正本を健全と呼ばない。** いま凍結するのは緑ではなく、**指示文以外の所見が出ないこと**（投影ドリフト・孤児・逆孤児のような道具の側の不備が一件も出ないこと）と、**指示文の所見が `_system/` の正本に限ること**である。overview が `render-projection` の導出とずれないこと。以上を TEST-015 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
