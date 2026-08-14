---
id: IMPL-001
title: `_registry.py` の実装メモ
type: IMPL
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
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
- `required_keys` は型だけを取る。**段（level）の口は落ちている**（ADR-106。受け取って無視していた口を公開しない）。以前ここは「level が不正なら ValueError」と書いており、口が消えた後も残っていた。
- `resolve_duplicate_id` は整列した順の最初を返す（先勝ち。ADR-049）。呼び出す側が自前で `sorted(...)[0]` や `[-1]` を書かないこと。ここが二つに割れると、監査が「採用」と告げる文書と、注入が実際に運ぶ文書が食い違う。文字列でない要素は無視し、空なら None を返す（例外を投げない）。
- ADR-075: 走査から外す範囲（`is_outside_governance`）と倉庫の判定（`is_archived_path`）をここに置く。監査とリンタが二重に持たない。

## 対象部品

`plugin/scripts/_registry.py`。定数は TYPES（型コード一覧）・TYPE_DEFAULT_STATUS・TYPE_DEFAULT_LLM_CONTEXT・TYPE_LOCATION・REQUIRED_SECTIONS（型ごとの必須節。ADR-090）・TYPE_REVIEW_CYCLE_DAYS（既定点検周期。ADR-025）・ARCHIVED_LOCATION・ALL_STATUSES・CURRENT_STATUSES・SUBDOMAIN_KINDS。関数は `status_allowed`・`is_current`・`required_keys`・`required_sections`・`review_cycle_days`・`type_of`・`is_known_type`・`default_status`・`default_llm_context`・`effective_llm_context`・`allowed_locations`・`is_projection`・`is_archived_path`・`is_outside_governance`・`resolve_duplicate_id`。**型を一つ増やすときは、六つの表すべてに行を足す**（ADR-163 の MODEL が直近の例）。

<!-- 入れない: 仕様の正本 -->
