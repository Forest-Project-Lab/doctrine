---
id: IMPL-012
title: `inject-contract.py` の実装メモ
type: IMPL
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-27
sources: [plugin/scripts/inject-contract.py]
depends_on: [SPEC-012]
llm_context: task
---

# `inject-contract.py` の実装メモ

SPEC-012 を実装する、注入スクリプトの実装メモである `[R5]`。

## 実装制約

- `estimate_tokens` は `ceil(len/4.0)` で計算する。副作用のない関数で、同じ入力には同じ値を返す。`model_chars_per_token` で値を上書きできる。
- `_build_sections` は、全ブロックを `(タイトル, 行, tier)` の組にして順序付きで返す。`_assemble` は、切り詰める前の推定値で超過を判定する。超過していれば、まず通知の分を割り当てから差し引き、そのうえで `_trim_to_fit` が本体を削る。
- `_load_audit_summary` は共有コア `_auditcache.load` の薄い前面である（ADR-053）。候補順・`schema` 照合・`root` 照合・世代の照合を、ここで持ち直さないこと。持ち直すと、鼓動（`gov-heartbeat.py`）と答えが割れる。実際に割れていた（照合の段が違い、未知のスキーマの候補が先にあると一方だけがそこで止まった）。
- `_tree_initialized` も `_auditcache.has_initialized_marker` へ委ねる。判定は印の有無だけで行い、日付の可否を条件にしないこと。日付を要ると、印が壊れた木の初日が中立の案内ではなく警告から始まる（ADR-041 の意図を裏切る）。

## 注意点

- 上限を超えても、通知は必ず残す。削るのは詳細だけで、節のマーカーと先頭一行は残す。
- `_first_fact_line` は見出し一行だけを抜き出し、本文の全量は保持しない `[R5]`。
- どの例外も main の外へ出さず、常に終了コード 0 を返す。エラー時はセッションを落とさない側に倒し、最小限ながら妥当な JSON を返す。

## 対象部品

`plugin/scripts/inject-contract.py`（`estimate_tokens`・`_build_sections`・`_assemble`・`_trim_to_fit`・`_load_audit_summary`・`_frontmatter.sanitize_inline`（ADR-040）・`_fact_lines`/`_facts_lines`（ADR-043 要点行の抽出と描画））。共有の `_registry`・`_frontmatter`・`_auditcache` を import する。監査要約の候補順はプロジェクトスコープ先・旧プラグインroot配置は後方互換の最後（ADR-037、#69）。順序も照合も `_auditcache` が正本で、`gov-heartbeat.py` の `_audit_summary` は同じ関数を呼ぶ（ADR-053）。
