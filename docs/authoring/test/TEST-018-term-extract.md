---
id: TEST-018
title: term-extract の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_extract.py]
depends_on: [SPEC-018]
llm_context: task
---

# term-extract の検証

`term-extract.py` の受入を検証する。`[R6]`

## 受入基準への対応

SPEC-018 の受入基準に対応する。次の各点を確認する。候補が `c-tf-idf` の高い順、同点は語の昇順で並び、同じ入力には同じ並びを返すこと。`--min-df` がその語を含む文書数で語を落とすこと。ドメインが1つのとき、信頼が低い旨の注意が出ること。`text`・`json`・`csv` のいずれの様式にも、人の承認が要る旨の注記が載ること。

## 退行観点

次の各点が崩れていないかを WATCH と突き合わせて確かめる。ファイルに何も書き込まないこと（読むだけ）。既定で `_system`・`archive/`・`llm_context:never` を対象から外すこと。

## 合否基準

問い合わせ専用なので、本体で異常が起きても終了コード 0 を返し、引数の誤りでは 2 を返すこと。返す候補表が、`PYTHONHASHSEED` の値によらずバイト単位で一致し、同じ入力には同じ結果を返すこと。`plugin/tests/test_extract.py` が合格する。

<!-- 入れない: 無関係な要求 -->
