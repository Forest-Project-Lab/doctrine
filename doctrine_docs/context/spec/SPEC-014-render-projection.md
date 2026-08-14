---
id: SPEC-014
title: 投影の決定論描画
type: SPEC
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
sources: [plugin/scripts/render-projection.py]
depends_on: [REQ-009, ICD-001]
llm_context: task
---

# 投影の決定論描画

`render-projection.py` は、投影（Overview・ICD 一覧・Context Map の骨組み）を正本から決定論で描画する `[R1]`。手で書き溜める作業をなくし、投影ドリフトを検出する `[R8]`。

## 入出力

- 入力: モード `overview|icd-index|context-map-skeleton|all` のうち一つと、`[--docs-root R] [--out PATH|-] [--check]`。源は、各文書のフロントマターと §3 の登録簿（ICD-001）。本文は読まない。
- 投影ごとの「源」の定義: Overview の源は現行の全ソース文書、ICD 一覧の源は現行の全 ICD、Context Map の源はドメイン集合とドメイン越えの `depends_on` 端の当事者。源が違うため、三つの投影の `updated` は互いにずれてよい（ずれは古びではない）。
- 投影の境界（ADR-016）: 投影と呼ぶのは、この仕様の三つと SessionStart 契約のように、正本から描画し直せる派生表示だけである。外部ツールのデータから作る図表と、複数の現行文書から組み立てる刊行物（FAQ・リリースノートなど）は投影ではなく、描画先にも `--check` の対象にも含めない。投影の種類を足すときは ADR で決める。
- 描画先: `_system/overview.md`・`_system/icd-index.md`・`_system/context-map.md`。Overview と ICD 一覧の冒頭一行は「描画される。手で編集しない。」とする。
- 投影自身のフロントマターは `type: OVERVIEW`、`id: OVERVIEW-<n>` とする（C8とは凍結した契約の整合を見る判断項目をいう。INDEX（索引）型は作らない）。

## 制約

- 決定論で動く。壁時計は読まない。投影の `updated` は、各源の `updated` のうち最大のものにそろえる。二度描画すれば、結果はバイト単位で一致する（冪等）。
- 並びはすべて明示キーで決める。Overview の並びは、ドメイン昇順（`_system` を先頭）、次に §3.2 登録簿の型順、最後に id 昇順とする。
- 投影そのもの（OVERVIEW・CTXMAP と、固定名の投影ファイル）は Overview の一覧に載せない。投影が自分自身を載せてずれが生じるのを避けるためである。
- Context Map では、印で囲んだ骨組みの区間だけを書き換える。印の外側の散文はそのまま保つ。

## エラー時挙動

- 統治木のルートが無いときは終了コード 3、引数に不備があるときは 2 を返す。id を持たない文書は飛ばす。
- `--check` は描画結果とディスク上の内容を突き合わせる。ずれていれば（または未生成なら）非ゼロで終了し、一致すれば 0 を返す。

## 実装の指紋

対象は投影モードの正本。更新は `trace-index.py --id SPEC-014` が返す行を写す（ADR-061）。

- sha256:c76cbbc7d83d569b6907c55f66800dcadd9e16ac072858f3ffd972d5447ad0d1

## 受入基準

TEST-014 に対応する。次の三つを合否とする。同じ源から描き直すとバイト単位で一致すること。`--check` が投影ドリフトを非ゼロ終了で知らせること。投影が自分自身を Overview に載せないこと。

<!-- 入れない: 廃止、検討、実装コードの写し -->
