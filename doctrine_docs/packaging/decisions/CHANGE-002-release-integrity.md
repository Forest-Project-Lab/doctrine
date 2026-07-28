---
id: CHANGE-002
title: リリースの整合を CI の門で検める — 変更履歴の書き忘れを止める
type: CHANGE
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-28
sources: [CHANGELOG.md, .github/workflows/checks.yml]
depends_on: [SPEC-020]
llm_context: task
---

# リリースの整合を CI の門で検める — 変更履歴の書き忘れを止める

## 変更内容

リポジトリ直下 `scripts/`（自己適用。SPEC-020 の書き分けに従う）へ
`release-check.py` を足し、CI（checks.yml）が毎回走らせる。検めるのは二つ。

1. **版の整合**: CHANGELOG（リリースごとの変更を利用者向けに記す変更履歴ファイル。実体は CHANGELOG.md）の先頭の版付き節が、版番号の正本
   （`plugin/.claude-plugin/plugin.json` の version）と一致し、日付を持つこと。
   plugin.json と marketplace.json の一致は既存の単体テスト（TEST-020）が
   強制済みであり、本検査は二重定義しない。
2. **記録の義務**: pull request が `plugin/` を変えるなら、同じ pull request が
   CHANGELOG.md（常設の「未リリース」節）にも触れること。記録が要らない変更は、
   pull request の題名に印を書いて明示的に免れる（無音の迂回を許さない）。

あわせて CHANGELOG.md に「未リリース」節を常設し、リリース手順（節へ版番号と
日付を付け、正本の版を上げる）を PROC-001 に正本化する。

## 理由（要求元）

リリース時に CHANGELOG の記載を忘れても、いまは何も止めない。版番号の正本
（plugin.json）と marketplace.json の一致はテストが強制するが、CHANGELOG は
どの門も見ておらず、「版は上がったのに変更履歴が無い」状態が main に入れた。
変更履歴が欠けると、版を上げる利用者への注意（0.5.0 の節のような移行の案内）が
書かれず、版管理が読み手にとって機能しない。書き忘れは「リリース時にまとめて
思い出して書く」運用が原因なので、変更のたびに一行を積む「未リリース」節を
常設し、積み忘れ自体を pull request の門で止める。

## 影響の初期見積

- 文書: ADR（新規1件）、SPEC（新規1件。自己適用スクリプトの仕様）、
  PROC-001（リリース手順の節を追加）、TEST（新規1件）。
- 実装: `scripts/release-check.py`（新規）、`.github/workflows/checks.yml`
  （段を1つ追加）、CHANGELOG.md（「未リリース」節の常設と冒頭の案内）。
- テスト: `plugin/tests/test_release_check.py`（新規）。
- ドメイン跨ぎ: なし（packaging の中で閉じる）。

## 実施の記録

2026-07-28 に完了。決定は ADR-071、影響の列挙は IMPACT-002。仕様は SPEC-027、
受入は TEST-027（`plugin/tests/test_release_check.py`）。実装は
`scripts/release-check.py`・checks.yml の段・CHANGELOG の「未リリース」節の常設。
リリース手順は PROC-001 に正本化した。
