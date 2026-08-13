---
id: ADR-155
title: graph の読み口は測った木の版と作り手を名乗る — source_revision・source_dirty・generator
type: ADR
domain: graph
status: accepted
owner: doctrine-maintainers
created: 2026-08-13
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", plugin/scripts/trace-index.py, plugin/scripts/dep-graph.py]
depends_on: [ICD-002]
llm_context: task
---

# graph の読み口は測った木の版と作り手を名乗る — source_revision・source_dirty・generator

## 背景

宣言済みの読み口の返す値は、どれも自分がいつの木を測ったかを言わない（issue #294 の
観測。最上位の鍵に版を名乗るものはゼロ。権限は ADR-151）。消費者は数回 CLI を呼ぶ間に
木が動いても気づけず、自前で `git rev-parse` を叩けば叩いた瞬間と CLI が読んだ瞬間が
ずれる。外部の表示製品はこの欄の不在を自前の記録で埋め合わせており、正しさを保証
できていない。あわせて、作った道具の版も名乗られない —— plugin の配置には `.git` が
無いため、道具が名乗れるのは plugin.json の版までで、それすら返していない。

## 却下した選択肢

- **消費者が `git rev-parse` を併走する現状を維持する。** 叩いた瞬間と読んだ瞬間のずれは
  原理的に消えない。測った側が名乗るのが唯一ずれない形である。
- **dirty（未コミット変更のある）木でも木の版だけを返す。** その版の値は「見た内容」を
  指さない。版の欄が嘘をつく形は、欄が無いより悪い。
- **道具の版は問い合わせのフラグで別に問う。** 返す値と別の呼び出しで取った版は、また
  ずれの窓を作る。返す値の中に居るのが正しい置き場である。
- **空文字や欄の省略で「分からない」を表す。** 「分からない」と「調べていない」が同じ形に
  なる（#294 の提案どおり null を使う）。

## 決定

graph の宣言済みの読み口（`trace-index/1`・`dep-graph/1`）の最上位に、次の三つの鍵を足す。
鍵の追加は互換である（確定事実13。ADR-152）。

1. `source_revision`: 測った木の版。git が返す HEAD（作業木が向いているコミット）の
   完全 SHA（コミットを一意に指す指紋。ADR-112 と同じ語）。解決できない木（git が無い・
   リポジトリでない）では **null**。
2. `source_dirty`: 測った木に未コミットの変更（無視されないファイルの追加を含む）が
   在れば true、無ければ false、git で解決できなければ null。`source_revision` は dirty でも
   解決できる限り書き、読み手はこの欄で版の証拠を割り引く。
3. `generator`: `{name, version}`。`name` はスクリプト名、`version` は plugin.json の版
   （知れなければ null）。SHA 粒度の道具の固定は、従来どおり消費者側の pin（tag と SHA）の仕事。

意味論はここで一度だけ決め、他ドメインの読み口が同じ鍵を名乗るときは本決定の意味を
そのまま使う（監査要約は ADR-156）。**第二の役割**として、複数の読み口の返す値の
`source_revision` が同値であることを「同じ木を測った」ことの照合に使う —— `root` の
意味は口ごとに違ってよく（名前だけ／絶対パス）、木の同一性の照合はこの鍵が担う。

## 帰結

- 消費者は `git` を併走せずに、返る値だけで「いつの木か・汚れていないか・誰が作ったか」を
  読める。複数回の呼び出しのずれは `source_revision` の食い違いとして検出できる。
- 版の解決の失敗は所見にしない（検出に徹し判定はしない、の従来の規律のまま）。
- 保証限界: dirty の木では、`source_revision` は「HEAD がこの値だった」ことしか言わない。
  見た内容の同一性は `source_dirty: false` のときだけ主張できる。

<!-- 入れない: 実装の詳細（subprocess の呼び方）、他ドメインの宣言の写し -->
