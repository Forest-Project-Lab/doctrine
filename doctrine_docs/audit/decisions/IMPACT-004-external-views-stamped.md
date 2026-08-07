---
id: IMPACT-004
title: ビューと刻印 — 影響の列挙
type: IMPACT
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-08-07
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-004, SPEC-011]
llm_context: task
---

# ビューと刻印 — 影響の列挙

CHANGE-004 の影響集合。

## 影響する文書

- ICD-005（記録の書式に分類「ビュー」、刻印の書式の正本化、検査表に view_stale、
  検査数の更新）
- SPEC-011（view_stale の契約の追記、検査数、実装の指紋の更新）
- SPEC-027（公開ビューの刻印の版の検査。packaging ドメイン側の更新）
- SPEC-020（plugin/README の呼称を案内からビューへ。packaging ドメイン側）
- SPEC-007（分類「ビュー」の扱いと刻印の欠落の助言。lint ドメイン側）
- GLOSSARY（承認語「ビュー」「刻印」。投影の禁止同義語から「ビュー」を外す）
- DECIDED-001（ビューと刻印の確定事実の追加）・WATCH-001（再分類による
  骨抜きの監視の追加）
- ADR（新規: ADR-073）
- TEST-011・TEST-027・TEST-007（受入の追記）・TEST-020（刻印の存在）
- 投影（Overview。文書の追加に伴う描き直し）

## 影響する実装

- `plugin/scripts/_intake.py` — 分類「ビュー」の受理と、完全一致優先の照合
- `plugin/scripts/_audit_stray.py` — view_stale（体系外走査の同じ入口に足す）
- `plugin/scripts/docs-audit.py` — 検査名簿 `AUDIT_CHECKS` への追加
- `plugin/scripts/docs-linter.py` — ビュー分類の編集での刻印の欠落の助言
- `scripts/release-check.py` — 公開ビュー3件の `as-of` と版番号の正本の照合
- `plugin/skills/llm-context-pack/SKILL.md` — 生成物への刻印の指示

## 影響するテスト

- `plugin/tests/test_audit.py`（view_stale の pass/fail 両側）
- `plugin/tests/test_linter.py`（刻印の欠落の助言）
- `plugin/tests/test_release_check.py`（刻印の版の門）
- `plugin/tests/test_meta.py`（plugin/README の刻印の存在）

## 境界の分類

正本は audit（分類の記録の書式・刻印の書式・view_stale。ICD-005 が
`canonical_for` で持つ）。lint は共有コア `_intake` の消費者（既存の
SPEC-007 → ICD-005 依存のまま。追加の合意は不要）。packaging は刻印の書式の
消費者（SPEC-027 に ICD-005 への依存を足す。cross_domain_icd で規則に適合）。
監査の要約への検査の追加は前方寛容（`checks_run` を列挙で読む読者はいない。
SPEC-012・SPEC-019・SPEC-021・SPEC-023 への契約変更なし）。

## 工数見積

中。機構は小さいが、書式の正本化（ICD-005）と自己適用（再分類・初期刻印・
README の修正3件）が本体。
