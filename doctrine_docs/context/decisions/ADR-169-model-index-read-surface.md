---
id: ADR-169
title: 木の中の MODEL を列挙する読み口 model-index/1 を宣言する
type: ADR
domain: context
status: accepted
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
depends_on: [ICD-001]
llm_context: task
---

# 木の中の MODEL を列挙する読み口 model-index/1 を宣言する

## 背景

doctrine-lens が #294 第5信で挙げた（欠けの1番）。宣言済みの外部読み口（`dep-graph/1`・
`trace-index/1`・`docs-audit/1`・`map-draft-check/1`・`scaffold-sections/1`）はどれも
「この木にどの MODEL が在るか」を返さない。外部の表示製品は、対象の一覧を自分の
`registry.json` へ手書きしており、模型が統治木へ移っても列挙だけが手書きのまま残る。
画面が要るのは、各件の id・title・target（模型が描く系の名）・`status`・updated・
投影 JSON の正本パスである。

## 却下した選択肢

- **新しい入口スクリプトを足す。** 入口が増えるほど配線と試験の面が広がる。MODEL の
  本文を読む口は既に `render-projection.py` の model モードが持っており（ADR-163
  決定3。投影はここだけが本文を読む）、列挙は同じ読みの副産物で出せる。
- **`dep-graph.py` の nodes を型で絞って使ってもらう。** dep-graph はフロントマターしか
  読まないので `target` を返せない。投影の正本パス（ADR-164 決定1 の規則の適用結果）も
  依存グラフの関心ではない。読み手に規則の再実装をさせないことが本読み口の目的である。
- **列挙を消費者の手書きに残す。** 第5信の現状そのもの。模型が統治木へ移る方針
  （lens は view に徹する）と両立しない。

## 決定

1. **`render-projection.py model --list` を読み口とし、`model-index/1` を stdout へ
   返す**（診断は標準エラーへ。確定事実13）。`--list` は model モード専用で、
   `--out`・`--check`・`--id` とは併用しない。
2. **形**: 最上位は `{"schema": "model-index/1", "root": <名前だけ>, "source_revision",
   "source_dirty", "generator", "models": [...]}`。版の三鍵の意味は ICD-002「測った木の
   版と作り手」の宣言（ADR-155）と同じで、再定義しない。`models` の各項は
   `{id, title, target, status, updated, path, projection_path, repos, findings}`。
   並びは id 昇順。`path`（正本の .md）と `projection_path`（隣の .json。ADR-164
   決定1 の規則の適用結果）は統治木の根からの相対で、区切りは `/`。
3. **「分からない」を空にしない。** 本文が解けず `target` を読めない模型も一覧に載せ、
   `target` は null、`findings` に構造の所見（重大度が誤り級のもの）の件数を書く。
   `repos` は正本のフロントマターの宣言（ADR-170）の写しで、宣言が無ければ null とする。
4. **ICD-006 の外部条項で宣言する。** 進化の規約は確定事実13（欄の追加は互換・壊す
   変更はスキーマ名の版上げ）に従う。

## 帰結

- ICD-006 に外部条項の節が新しくでき、DECIDED-001 事実13 の採用先に ICD-006 が加わる。
- SPEC-014 に `--list` の入出力が載り、TEST-014 が受入を持つ。
- 外部の表示製品は対象の列挙を手書きしなくてよくなる。lens 側 `registry.json` の
  `targets[]` の置き換え先がこの口である。
- 保証限界: 一覧が返すのは統治木の中の MODEL だけである。統治木の外（旧来の
  `.claude/system-map/` の下書きなど）は列挙しない。`target` の意味の正しさは検めない
  （構造の所見の件数を添えるまで）。

<!-- 入れない: 複数決定の混在、実装コードの写し -->
