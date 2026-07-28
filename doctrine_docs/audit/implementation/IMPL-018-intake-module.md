---
id: IMPL-018
title: _intake.py（分類の記録の共有コア）の実装メモ
type: IMPL
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-28
sources: [plugin/scripts/_intake.py]
depends_on: [SPEC-011]
llm_context: task
---

# _intake.py（分類の記録の共有コア）の実装メモ

`plugin/scripts/_intake.py` は、体系外 .md の分類の記録(`_system/.md-intake`)の読み取りと照合を一箇所に持つ共有コアである(ADR-021 の書式、ADR-024 の一本化)。監査(全体を見る)とリンタ(一件を見る)が同じコードで同じ記録を読むことで、同じファイルへの判定の食い違いを構造的に防ぐ `[R6][R8]`。

## 対象部品

- `load_ledger(docs_root)`: `_system/.md-intake` を読み、(entries, bad_lines) を返す。書式は一行一項目 `パス: 非文書|投影|保留 [YYYY-MM-DD]`(保留は期限必須。末尾 `/` は配下全体)。決して例外を投げない。
- `entry_for(relpath, entries)`: 末尾 `/` はプレフィクス一致、それ以外は完全一致。
- `disposition_for(abspath, docs_root)`: リンタが一件のファイルの分類を引く入口。

## 実装制約

- 書式の定義の正本は audit の ICD(intake-ledger-format)であり、各 SPEC は正本を参照する(二重定義しない。ADR-001/ADR-005 と同じ規律)。
- 標準ライブラリのみ(ADR-031)。呼び出し側(監査・リンタ・整合点検)を壊さないため、決して例外を投げない。

## 注意点

- 利用者は監査(`docs-audit.py`)・リンタ(`docs-linter.py`)・整合点検(`scripts/consistency-check.py`)の三つ。新たな読み手を足すときも必ずこのコアを経由する(別実装の読み取りが WATCH-001 第5項の再発になる)。
- テストは `plugin/tests/test_audit.py`(stray 検査)・`test_linter.py`(ADR-024 受入)が共有で覆う。
