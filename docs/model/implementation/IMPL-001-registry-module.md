---
id: IMPL-001
title: `_registry.py` の実装メモ
type: IMPL
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [SPEC-001]
llm_context: task
---

# `_registry.py` の実装メモ

SPEC-001 の登録簿契約を実装するときの制約と、はまりやすい落とし穴をまとめる。[R6][R8]

## 実装制約

- 標準ライブラリだけで書く。型・`status`・`llm_context`・必須キー・置き場所の規則をここに一度だけ定義し、ほかのスクリプトで二重定義しないこと。
- `id` の照合には正規表現 `^([A-Z]+)-(\d+)$` を使う。桁数は固定しない。仕様に書いた番号は例であって、桁数の規則ではない。
- `status_allowed` と `allowed_locations` は、呼び出すたびに新しいコレクションを生成して返す。登録簿そのものを外へ渡さない。
- CURRENT_STATUSES は frozenset とし、変更できないようにする。

## 注意点

- `type_of` は、接頭辞が登録簿の型でないとき None を返す。既知の型かどうかを判定する `is_known_type` と取り違えないこと。
- `domain_of` をここに足さないこと。`id` だけではドメインを決められないため、その解決は graph に委ねる。
- `effective_llm_context` は、meta が辞書でないときや型が不明のとき None を返す。こうした入力でも壊れないようにする。R5（never を渡さない）は、この解決のあとの値に対して適用する。
- `required_keys` の level は {2,3,4} だけを許し、それ以外なら ValueError を投げる。

## 対象部品

`plugin/scripts/_registry.py`。定数は TYPES（型コード一覧）・TYPE_DEFAULT_STATUS・TYPE_DEFAULT_LLM_CONTEXT・TYPE_LOCATION・ALL_STATUSES・CURRENT_STATUSES。関数は `status_allowed`・`is_current`・`required_keys`・`type_of`・`is_known_type`・`default_status`・`default_llm_context`・`effective_llm_context`・`allowed_locations`・`is_projection`。

<!-- 入れない: 仕様の正本 -->
