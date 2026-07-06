---
id: IMPL-011
title: docs-audit.py の実装メモ
type: IMPL
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/docs-audit.py]
depends_on: [SPEC-011]
llm_context: task
---

# docs-audit.py の実装メモ

## 実装制約

- 標準ライブラリだけを使う。返す値は毎回同じになる（`run_audit` は所見を check・doc_id・message の順で整列する）。`[R8]`
- `_resolve_today` は基準日を次の優先順位で決める。`--today` を最優先し、なければ config.today を使い、それもなければ最後にシステム時刻に頼る。与えられた値を日付として解釈できなければ `_TodayError` を投げ、main がこれを終了コード 2 に変換する。
- `run_audit` は、graph の `build_graph` で依存グラフを組んだ後、`_attach_bodies` で各文書の本文を一度だけノードに付ける。これにより各 `_check_*` が本文を読み直さずに済む。
- `_is_reproducible` は再現可能かどうかを三つの分岐（`type`==RESEARCH、`llm_context`==never、`reproducible: true`）で判定する。孤児判定では ICD・投影・`llm_context`==always を除外する。
- `_atomic_write` は一時ファイルに書いてから `os.replace` で差し替え、途中状態を残さない。書き込みに失敗しても、終了コードはゲートの判定（SessionEnd では 0）に従う。

## 注意点

- ルートが見つからない場合の終了コードは 3 ではなく 0 とする。所見ゼロと同じ扱いにして、CI を不必要に止めない。
- 与えられた基準日が不正なら終了コード 2 を返すが、監査本体がクラッシュした場合は 0 を返す。後者はセッションの後始末を妨げないためで、両者を取り違えてはならない。
- `_check_canonical_conflict` は、置換済み（superseded）になっても `canonical_for` を持ち続ける文書を、正本の移譲をやり残した取りこぼしとみなして衝突に含める。

## 対象部品

対象は `plugin/scripts/docs-audit.py` である。各 `_check_*` は `plugin/scripts/_depgraph.py`（依存グラフ）と `plugin/scripts/_registry.py`（登録簿）を使う。
