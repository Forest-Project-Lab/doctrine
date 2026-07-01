---
id: SPEC-001
title: 登録簿の契約（registry contract）
type: SPEC
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [REQ-001, DATA-001]
llm_context: task
---

# 登録簿の契約（registry contract）

`scripts/_registry.py` が公開する、構造規則の単一正本としての契約。[R2][R3][R6][R8]

## 入出力

- `type_of(id)`: `id` の接頭辞（最初の `-` より前）を型として返す。例えば `SPEC-014` は `SPEC` を返す。接頭辞が未知、`id` が不正、または文字列でない場合は None を返す。
- `is_known_type(type)`: 18 型のいずれかなら真を返す。
- `default_status(type)` と `default_llm_context(type)`: 既定値を返す。未知の型なら None を返す。
- `status_allowed(type)`: 許可する `status` の集合を返す。毎回新しい集合を返す。
- `allowed_locations(type)`: 許可する置き場所の列を返す。毎回新しいリストを返す。
- `is_projection(type)`: 投影型（OVERVIEW・CTXMAP）なら真を返す。
- `is_current(status)`: `status` が current または accepted なら真を返す。
- `effective_llm_context(meta)`: フロントマターの `llm_context` を優先して返し、無ければ型の既定を返す。
- `required_keys(level, type)`: 必須キーの列を返す。DECIDED と WATCH には `review_by` を加える。

## 制約

- 標準ライブラリだけで書き、純データと純関数で構成する。pip も通信も使わない。動きは決定的とする。
- 集合やリストを返す関数は、毎回新しいコレクションを返す。呼び出し側が登録簿そのものを書き換えられないようにする。
- accepted は ADR だけに使う。draft は RESEARCH だけに許す。これは整合判断 C5（凍結した契約の整合を見る判断項目の番号）にあたる。
- CURRENT_STATUSES は frozenset で {current, accepted} とする。ほかのスクリプトは `== "current"` の直接比較を使わない。
- `domain_of(id)` は持たない。`id` だけではドメインが決まらないため、その解決は graph（ICD-002）に委ねる。

## エラー時挙動

- 未知の入力（不正な `id` や未知の型）に対しては例外を投げず、None・空集合・空リストのいずれかを返す。違反の報告はリンタ・ガード・監査に委ねる。
- `required_keys(level, ...)` の level が {2,3,4} 以外なら ValueError を投げる。

## 受入基準

- 18 型の登録簿、`status` の許可表、型ごとの既定値、置き場所が、DATA-001 と一致する。
- 返したコレクションを書き換えても、登録簿は変わらない。
- accepted は ADR だけで、draft は RESEARCH だけで許可される。
- 対応するテストは TEST-001 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
