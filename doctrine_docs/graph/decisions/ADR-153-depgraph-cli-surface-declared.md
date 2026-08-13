---
id: ADR-153
title: dep-graph の CLI の返す値を宣言する — 実装の内部形を黙った契約にしない
type: ADR
domain: graph
status: accepted
owner: doctrine-maintainers
created: 2026-08-13
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", plugin/scripts/dep-graph.py]
depends_on: [ICD-002]
llm_context: task
---

# dep-graph の CLI の返す値を宣言する — 実装の内部形を黙った契約にしない

## 背景

追跡索引には外部条項がある —— 「外部の消費者が依存してよいのは CLI の返す値だけ」
（ICD-002、ADR-112）。一方、依存グラフの宣言は内部向けの Python 関数と終了コードだけで、
CLI `dep-graph.py --json` が返す値の形はどこにも宣言が無い。外部の表示製品（doctrine-lens）は
既に `--classify-edges --json` を読んでおり、監査要約で一度踏んだ形（宣言なき消費。
ADR-137 の背景）が依存グラフで再演されている。issue #294 の洗い出しで判明した
（権限は ADR-151）。あわせて衛生の不備が三つある: 返る値が自分の根を名乗らない
（内部の `to_json()` は根を持つが CLI が捨てる）、根が無いときの診断が stdout に出て
JSON を汚す、`--reverse-refs` が宣言に無い。

## 却下した選択肢

- **返り値を設計し直して綺麗な形で宣言する。** 既存の消費者の読みが壊れる。宣言は
  実装へ合わせる（逆ではない。IMPACT-009 と同じ向き）。足すのは互換の鍵だけにする。
- **`--classify-edges` の `result` と `edges` の重複を消す。** どちらを読んでいる消費者も
  居りうる。互換を壊す変更であり、版上げに値する利得が無い。重複は宣言に明記して残す。
- **Python 関数の宣言だけを保つ（何もしない）。** 外部の消費者は CLI しか呼べない。
  宣言なき消費が続く。

## 決定

CLI `dep-graph.py` の返す値をスキーマ名 `dep-graph/1` として ICD-002 に宣言し、外部条項を置く。

1. `--json` の返す値の最上位に `schema`（`"dep-graph/1"`）と `root`（名前だけ。絶対パスを
   載せない —— trace-index/1 と同義）を足す。既存の鍵（`nodes`・`edges`・`result`・`mode` ほか）は
   そのまま。鍵の追加は互換である（確定事実13。ADR-152）。
2. モードを閉じて列挙する: `--impacts`・`--dependents`・`--classify-edges`・`--reverse-orphans`・
   `--reverse-refs`（従来から在るが宣言に無かった）。`--json` は修飾子であってモードではない（ADR-110）。
3. `--classify-edges` の `result` は `edges` と同じ内容の重複であることを宣言し、読み手は
   どちらか一方だけを読むと明記する。
4. 診断（根が無い等）は標準エラーへ出す。stdout は JSON（または人向けの本文）だけにする。
   終了コードの規約（0/2/3）は変えない。
5. 節点の項の正本は従来どおり SPEC-006 の `to_json()`（節点は隠さない。ADR-087）。
   本宣言は入口（CLI の返す値の形）だけを固定する。

## 帰結

- 層A（統治の実態）の材料の三口（依存グラフ・追跡索引・監査要約）がすべて宣言済みになり、
  #294 の「宣言済みの読み口だけで層Aが作れる」が依存グラフの分でも成立する。
- 既存の内部の呼び手（ガード・監査）は Python 関数を使っており、影響しない。
- 保証限界: 宣言するのは形だけであり、グラフの内容の解釈は読み手に残る。診断の文言は
  契約ではない。

<!-- 入れない: 節点の項の列挙の写し（SPEC-006 が正本）、実装コード -->
