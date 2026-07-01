---
id: SPEC-008
title: 用語チェッカーの照合規則
type: SPEC
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_termcheck.py]
depends_on: [REQ-006, REQ-007]
llm_context: task
---

# 用語チェッカーの照合規則

`_termcheck.py`（用語チェッカーの中核）は、承認辞書に照らして本文を照合することだけを担う。辞書はこの体系の中で一度だけ符号化し、二重には定義しない[R6]。

## 入出力

- 入力: `check(body, meta, glossary) -> Finding[]`。`glossary` には `load_glossary(docs_root)` の戻り値を渡す。
- 辞書の探し順: まず運用版（対象リポジトリの `docs/_system/glossary.md`）を読む。無ければ同梱の `templates/glossary.md.tmpl` を種子として使う。運用版はあるが解析できないときは、種子に切り替えたうえで `GLOSSARY_PARSE_ERROR`（警告）を添える。
- 返す値: `Finding(code, severity, message, line)` の一覧。

## 制約

- 標準ライブラリだけを使い、同じ入力には常に同じ結果を返す。承認語・禁止同義語・カルク表はハードコードせず、辞書本体から読み取る[R6]。
- 照合規則は四つある。`BANNED_SYNONYM`（その重大度は ERROR（誤り）。禁止同義語が文字列としてそのまま現れたら一致）、`CALQUE`（ERROR。§1 のカルク表 9 行）、`CALQUE_WORDTRAP`（WARN（警告）。一語訳の罠である `status`・`native`・`robust`・`leverage`）、`UNDEFINED_TERM`（WARN。辞書にない専門語の初出）[R10]。
- 複合語の覆い隠し: 承認語の一部にたまたま禁止同義語が含まれる複合語は、文字列照合の前に、長さを保ったまま伏せる。たとえば`入出力`は`出力`を、`現在形`は`現在`を覆う。覆いの外に素のまま現れた禁止同義語は、これまでどおり一致する。
- 末尾注記の扱い: 禁止同義語セルの末尾には `（…）` の注記が付くものがある。「可」を含む注記（例 `差し替え（…可。状態名は置換）`）は、使ってよい文脈があるため文脈依存とみなし、文字列照合の対象にしない。`インターフェース（単独語）`のように「可」を含まない注記は、素のトークンを取り出して照合する。
- 借用語の扱い: 定着した借用語（データ・リスク など）は弾かない。

## エラー時挙動

- 例外は投げない。GLOSSARY 正本の本文（型=GLOSSARY）と投影の本文（型=OVERVIEW／CTXMAP）は、辞書を載せる都合上どうしても禁止語を含むため、点検そのものを飛ばす。
- コードフェンス・インラインコード・URL・フロントマターは伏せ、擬陽性を避ける。

## 受入基準

- `tests/test_termcheck.py` が、四つの照合規則と、複合語の覆い隠し・末尾注記・種子への切り替えを、発火すべき入力と発火すべきでない入力の両方で確認する。観点ごとの対応は TEST-008 に示す。

<!-- 入れない: 廃止、検討、実装コードの写し -->
