---
id: IMPL-012
title: `inject-contract.py` の実装メモ
type: IMPL
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/inject-contract.py]
depends_on: [SPEC-012]
llm_context: task
---

# `inject-contract.py` の実装メモ

SPEC-012 を実装する、注入スクリプトの実装メモである `[R5]`。

## 実装制約

- `estimate_tokens` は `ceil(len/4.0)` で計算する。副作用のない関数で、同じ入力には同じ値を返す。`model_chars_per_token` で値を上書きできる。
- `_build_sections` は、全ブロックを `(タイトル, 行, tier)` の組にして順序付きで返す。`_assemble` は、切り詰める前の推定値で超過を判定する。超過していれば、まず通知の分を割り当てから差し引き、そのうえで `_trim_to_fit` が本体を削る。
- `_load_audit_summary` は、`_plugin_root_cache_candidates`（`${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json` を第一候補とする）から `docs-audit/1` を読む。

## 注意点

- 上限を超えても、通知は必ず残す。削るのは詳細だけで、節のマーカーと先頭一行は残す。
- `_first_fact_line` は見出し一行だけを抜き出し、本文の全量は保持しない `[R5]`。
- どの例外も main の外へ出さず、常に終了コード 0 を返す。エラー時はセッションを落とさない側に倒し、最小限ながら妥当な JSON を返す。

## 対象部品

`plugin/scripts/inject-contract.py`（`estimate_tokens`・`_build_sections`・`_assemble`・`_trim_to_fit`・`_load_audit_summary`）。共有の `_registry`・`_frontmatter` を import する。
