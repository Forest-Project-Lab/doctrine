---
id: SPEC-018
title: term-extract（c-TF-IDF 候補語抽出）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/term-extract.py]
depends_on: [REQ-012]
llm_context: task
---

# term-extract（c-TF-IDF 候補語抽出）

`term-extract.py` は、あるドメインを他のドメインから際立たせる語の候補を出す。各ドメイン（フォルダ）を一つのまとまりとみなし、c-TF-IDF でその特徴語を測る。c-TF-IDF は、ドメインをまとまり単位に置き換えた TF-IDF（語の出現頻度と希少さから特徴語を測る指標）である。辞書の素案づくりに使い、ファイルは読むだけで書き込まない。`[R6]`

## 入出力

入力は CLI（コマンド行）引数 `term-extract.py [--root PATH] [--domain NAME ...] [--top 25] [--min-df 2] [--format text|json|csv] [--include-system] [--all]`。返すのは各ドメインの候補表で、`c-tf-idf` の高い順に並べ、同点は語の昇順で並べる。`text`・`json`・`csv` のいずれの様式にも、これは候補にすぎず採否は人が決める旨の注記を載せる。

## 制約

標準ライブラリだけで動く。スコアは `tf(t,c) * log(1 + A / f(t))` で求める。ここで `A` はまとまり1個あたりの平均トークン数、`f(t)` は全まとまりを通じた語 `t` の出現総数である。トークン（数える最小の語片）への分割は、正規表現と文字バイグラムによる近似で、形態素の切り出しではない。ファイルには何も書き込まない。既定では `_system`・`archive/`・`llm_context:never`（ARCHIVE・RESEARCH）を対象から外す。同じ入力には同じ候補表を返す。

## エラー時挙動

ファイルへの書き込みは一切しない。ドメインが1つだけだと比較対象が無いため、結果の信頼が低い旨の注意を出す。引数の誤りは終了コード 2 とする。本体で異常が起きても、この処理は問い合わせ専用なので終了コード 0 を返し、呼び出した側の処理を止めない。

## 受入基準

候補が `c-tf-idf` の高い順、同点は語の昇順で並び、同じ入力には同じ並びを返すこと。`--min-df` がその語を含む文書数で語を落とすこと。ドメインが1つのとき、信頼が低い旨の注意が出ること。ファイルに何も書き込まないこと。以上を TEST-018 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
