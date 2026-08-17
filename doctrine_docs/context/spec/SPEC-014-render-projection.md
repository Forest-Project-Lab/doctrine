---
id: SPEC-014
title: 投影の決定論描画
type: SPEC
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-16
sources: [plugin/scripts/render-projection.py]
depends_on: [REQ-009, ICD-001]
llm_context: task
---

# 投影の決定論描画

`render-projection.py` は、投影（Overview・ICD 一覧・Context Map の骨組み）を正本から決定論で描画する `[R1]`。手で書き溜める作業をなくし、投影ドリフトを検出する `[R8]`。

## 入出力

- 入力: モード `overview|icd-index|context-map-skeleton|model|all` のうち一つと、`[--docs-root R] [--id ID] [--out PATH|-] [--check] [--list]`。源は、各文書のフロントマターと §3 の登録簿（ICD-001）。**本文を読むのは `model` モードだけである**（MODEL 型は値の正本を本文の JSON の塊に持つ。ADR-163 決定3）。`--id` は `model` モードでだけ使い、`model` で `--out` を使うときは `--id` で一件を指す。
- `--list`（ADR-169）: `model` モード専用。木の中の MODEL の一覧 `model-index/1` を stdout へ返し、ファイルへは何も書かない。`--out`・`--check`・`--id` とは併用しない。形は `{"schema": "model-index/1", "root": <名前だけ>, "source_revision", "source_dirty", "generator", "models": [...]}`。版の三鍵の意味は ICD-002「測った木の版と作り手」と同じ。`models` の各項は `{id, title, target, status, updated, path, projection_path, repos, findings}` で、並びは id 昇順、`path`・`projection_path` は統治木の根からの相対（区切りは `/`）。本文が解けない模型も一覧に載せ、`target` は null、`findings` に構造の所見（誤り級）の件数を書く。`repos` はフロントマターの宣言（ADR-170）の写しで、宣言が無ければ null。外部条項の宣言は ICD-006。
- 投影ごとの「源」の定義: Overview の源は現行の全ソース文書、ICD 一覧の源は現行の全 ICD、Context Map の源はドメイン集合とドメイン越えの `depends_on` 端の当事者。源が違うため、三つの投影の `updated` は互いにずれてよい（ずれは古びではない）。
- 投影の境界（ADR-016）: 投影と呼ぶのは、この仕様の三つと SessionStart 契約のように、正本から描画し直せる派生表示だけである。外部ツールのデータから作る図表と、複数の現行文書から組み立てる刊行物（FAQ（よくある質問と答えの集）・リリースノートなど）は投影ではなく、描画先にも `--check` の対象にも含めない。投影の種類を足すときは ADR で決める。
- 描画先: `_system/overview.md`・`_system/icd-index.md`・`_system/context-map.md`。Overview と ICD 一覧の冒頭一行は「描画される。手で編集しない。」とする。`model` の描画先は、正本の .md と同じ場所・同じ名の `.json` とする（拡張子だけが違う隣。置き場所の正本は ADR-164 決定1）。
- 投影自身のフロントマターは `type: OVERVIEW`、`id: OVERVIEW-<n>` とする（C8とは凍結した契約の整合を見る判断項目をいう。INDEX（索引）型は作らない）。

## 制約

- 決定論で動く。壁時計は読まない。投影の `updated` は、各源の `updated` のうち最大のものにそろえる。二度描画すれば、結果はバイト単位で一致する（冪等）。
- 並びはすべて明示キーで決める。Overview の並びは、ドメイン昇順（`_system` を先頭）、次に §3.2 登録簿の型順、最後に id 昇順とする。
- 投影そのもの（OVERVIEW・CTXMAP と、固定名の投影ファイル）は Overview の一覧に載せない。投影が自分自身を載せてずれが生じるのを避けるためである。
- Context Map では、印で囲んだ骨組みの区間だけを書き換える。印の外側の散文はそのまま保つ。
- `model` の描画は共有コア `_model`（SPEC-031）に委ね、語彙と形をここで二重定義しない。向きは .md から JSON への一方通行とする（JSON を読んで .md を組む口は持たない）。
- **所見の在る模型は描かない。** 構造の所見（SPEC-031）が一件でもあれば、その模型の JSON を書かずに標準エラーへ所見を出し、非ゼロで終える。古い JSON を黙って残さない。

## エラー時挙動

- 統治木のルートが無いときは終了コード 3、引数に不備があるときは 2 を返す。id を持たない文書は飛ばす。
- `--list` は、解けない模型が在っても一覧を返して 0 で終わる（解けないことは `target: null` と `findings` の件数が語る。列挙の成否と模型の良し悪しを混ぜない）。JSON は stdout へ、診断は標準エラーへ（確定事実13）。
- `--check` は描画結果とディスク上の内容を突き合わせる。ずれていれば（または未生成なら）非ゼロで終了し、一致すれば 0 を返す。`model` も同じ規約で、未生成・ドリフト・所見のいずれでも非ゼロを返す。`--id` の指し先が無ければ 3 を返し、`--id` の指し先が二件在れば（id の重複）何も書かずに非ゼロで返す。**正本を持たない取り残しの `.json`**（名が `MODEL-` で始まり、隣に MODEL の .md が無いもの）は、一括の描画と `--check` で告げて非ゼロにする（ADR-164 決定7）。

## 実装の指紋

対象は投影モードの正本。更新は `trace-index.py --id SPEC-014` が返す行を写す（ADR-061）。

- sha256:d66199e9bd0dab78014d003c33062826d3095ceed7cd9a49f81ddb2c001d995f
- sha256:26284e0f9c488a111b4951afdf91194d988dbe18525f7df4fda4924ce83c3c35

## 受入基準

TEST-014 に対応する。次の三つを合否とする。同じ源から描き直すとバイト単位で一致すること。`--check` が投影ドリフトを非ゼロ終了で知らせること。投影が自分自身を Overview に載せないこと。

`--list`（ADR-169）は次を合否に加える。`model-index/1` の宣言の形（版の三鍵を含む）を返すこと。並びが id 昇順で決定論であること。解けない模型が `target: null` と所見の件数つきで一覧に載り、終了コードが 0 のままであること。`repos` の宣言が写り、無宣言の模型では null であること。`--out`・`--check`・`--id` との併用が使い方の誤り（終了コード 2）になること。

<!-- 入れない: 廃止、検討、実装コードの写し -->
