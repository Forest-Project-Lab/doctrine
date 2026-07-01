---
id: ADR-002
title: フロントマター解析の3要素戻り値（C1）
type: ADR
domain: model
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [SPEC-002]
llm_context: task
---

# フロントマター解析の3要素戻り値

ADR（Architecture Decision Record、決定の記録）。本文書は一つの決定だけを扱う。C1とは、凍結した契約の整合を見る判断項目の番号をいう。[R3][R8]

## 背景

フロントマター解析の戻り値の形が、呼び出し側ごとに食い違った。本文だけが欲しい側もあれば、構文エラーの通知まで欲しい側もある。解析は毎ターン Hook から呼ばれるため、編集途中の半端な内容でも落ちてはならない。

## 却下した選択肢

- 2 要素 `(meta, body)` を返す案。構文エラーを呼び出し側へ渡せない。検出を解析の中に閉じ込めるか、黙って捨てるかのどちらかになる。却下した。
- 内容が不正なら例外を投げる案。Hook が毎ターン落ちる恐れがある。却下した。

## 決定

`parse(text) -> (fm, body, errors)` として 3 要素を返す。本文だけが欲しい呼び出し側は `fm, body, _ = parse(...)` と書く。補助として、薄い関数 parse_frontmatter・parse_file・as_list を添える。内容がどうであっても例外は投げない。

## 帰結

構文上の問題は errors の列に構造化して入れ、呼び出し側へ渡せる。必須キー・`status`・`id` の一致といった意味の検査は、呼び出し側に委ねる。本決定は、DECIDED-001 の確定事実（フロントマター解析は 3 要素を返す）の根拠となる。

<!-- 入れない: 複数決定、現行仕様の全文 -->
