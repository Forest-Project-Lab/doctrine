---
id: SPEC-001
title: 登録簿の契約（registry contract）
type: SPEC
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [DOCTRINE-001]
depends_on: [REQ-001, DATA-001]
llm_context: task
---

# 登録簿の契約（registry contract）

`scripts/_registry.py` が公開する、構造規則の単一正本としての契約。[R2][R3][R6][R8]

## 入出力

- `type_of(id)`: `id` の接頭辞（最初の `-` より前）を型として返す。例えば `SPEC-014` は `SPEC` を返す。接頭辞が未知、`id` が不正、または文字列でない場合は None を返す。
- `is_known_type(type)`: 20 型のいずれかなら真を返す。
- `default_status(type)` と `default_llm_context(type)`: 既定値を返す。未知の型なら None を返す。
- `status_allowed(type)`: 許可する `status` の集合を返す。毎回新しい集合を返す。
- `allowed_locations(type)`: 許可する置き場所の列を返す。毎回新しいリストを返す。**`REQ` は `<domain>/` と `_system/` の二つを許す**（ADR-091）—— `_system/` に置いた `REQ` は製品の粒度、`<domain>/` に置いた `REQ` は文書・機能の粒度である。**粒度は置き場所が言い、新しい欄を作らない**（`_system/` は既に横断の三本 `DECIDED`・`NONGOAL`・`WATCH` を置く棚であり、横断・一木に一つ・正本という性質が揃っている）。粒度そのものは機械で判じられないので、取り違えは人とレビューが見る。
- `is_projection(type)`: 投影型（OVERVIEW・CTXMAP）なら真を返す。
- `is_current(status)`: `status` が current または accepted なら真を返す。
- `effective_llm_context(meta)`: フロントマターの `llm_context` を優先して返し、無ければ型の既定を返す。
- `required_keys(level, type)`: 必須キーの列を返す。DECIDED と WATCH には `review_by` を加える。
- `resolve_duplicate_id(paths)`: 同じ id を持つ複数のパスから、採用する一つを返す。整列した順の最初を採る（先勝ち。ADR-049）。空なら None を返す。「どれが正本か」の答えを体系内で一つにするための規則であり、グラフ・注入・監査はこれを呼び、自前の整列規則を持たない。

## 制約

- 標準ライブラリだけで書き、純データと純関数で構成する。pip も通信も使わない。動きは決定的とする。
- 集合やリストを返す関数は、毎回新しいコレクションを返す。呼び出し側が登録簿そのものを書き換えられないようにする。
- accepted は ADR だけに使う。draft は RESEARCH だけに許す。これは整合判断 C5（凍結した契約の整合を見る判断項目の番号）にあたる。
- CURRENT_STATUSES は frozenset で {current, accepted} とする。ほかのスクリプトは `== "current"` の直接比較を使わない。
- `domain_of(id)` は持たない。`id` だけではドメインが決まらないため、その解決は graph（ICD-002）に委ねる。

## エラー時挙動

- 未知の入力（不正な `id` や未知の型）に対しては例外を投げず、None・空集合・空リストのいずれかを返す。違反の報告はリンタ・ガード・監査に委ねる。
- `required_keys(level, ...)` の level が {2,3,4} 以外なら ValueError を投げる。

## 実装の指紋

この節がある文書だけが、コードとの追跡の対象になる（ADR-056 の opt-in）。指紋は位置を含まないので、コードを別のファイルへ移しても古びと判じない。更新は `trace-index.py --id SPEC-001` が返す行を写す。

- sha256:562f529660783690724a35042f527b0730ede241f3587c1f9604ff08c8c591ba

## 受入基準

- 20 型の登録簿、`status` の許可表、型ごとの既定値、置き場所、既定点検周期（ADR-025）、archived の置き場所（ADR-027）が、DATA-001 と一致する。
- 置き場所の規則は、手書きの期待表（`EXPECTED_TYPE_LOCATION`）で凍らせる（ADR-060 の様式。ADR-091）。**正本から生成しない** —— 以前この凍結は無く、置き場所を変えても黙って通った（`TYPES`・既定 `status`・既定 `llm_context` は凍結済みだったのに、置き場所だけが凍結されていなかった）。
- 返したコレクションを書き換えても、登録簿は変わらない。
- `resolve_duplicate_id` は、与える順序に依らず整列した順の最初を返す。空の入力には None を返し、例外を投げない。
- accepted は ADR だけで、draft は RESEARCH だけで許可される。
- 対応するテストは TEST-001 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
