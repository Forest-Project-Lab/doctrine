---
id: IMPACT-002
title: リリース整合の門 — 影響の列挙
type: IMPACT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-29
sources: [plugin/scripts/dep-graph.py]
depends_on: [CHANGE-002, SPEC-020]
llm_context: task
---

# リリース整合の門 — 影響の列挙

CHANGE-002 の影響集合。dep-graph の逆向き（`--dependents SPEC-020`）で列挙した。

## 影響する文書

- ADR（新規: 決定の捕捉。ADR-071）
- SPEC（新規: SPEC-027。自己適用スクリプト `scripts/release-check.py` の仕様。
  SPEC-023 と同じ置き方 — リポジトリ直下 `scripts/` の一本として）
- PROC-001（更新: リリース手順の節を追加）
- TEST（新規: TEST-027。受入の凍結）
- SPEC-020 の逆参照 IMPL-017・TEST-020 は不変（plugin.json と marketplace.json の
  一致の強制は TEST-020 に残し、本変更は二重定義しない）。

## 影響する実装

- `scripts/release-check.py` — 新規（標準ライブラリのみ。配布物に含めない）。
- `.github/workflows/checks.yml` — 段を1つ追加（リリース整合の門）。
- CHANGELOG（リリースごとの変更を利用者向けに記す変更履歴ファイル。実体は
  CHANGELOG.md） — 「未リリース」節の常設と、冒頭への運用の一文。

## 影響するテスト

- `plugin/tests/test_release_check.py` — 新規（版の整合・日付・記録の義務・免除の印）。

## 境界の分類

ドメイン跨ぎなし。packaging の中で閉じる。ICD の変更なし（相手ドメインの合意は不要）。

## 工数見積

小。スクリプト一本・CI の段一つ・文書5件（新規3・更新2）。
