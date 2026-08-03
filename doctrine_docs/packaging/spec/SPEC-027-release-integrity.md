---
id: SPEC-027
title: リリース整合の門（release-check — 版の整合と記録の義務）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-29
sources: [scripts/release-check.py, .github/workflows/checks.yml, CHANGELOG.md]
depends_on: [SPEC-020, ICD-005]
llm_context: task
---

# リリース整合の門（release-check — 版の整合と記録の義務）

リポジトリ直下 `scripts/`（プラグインの `plugin/scripts/` とは別の場所。SPEC-020
の書き分けに従う）にある一本の仕様である。CHANGELOG（リリースごとの変更を
利用者向けに記す変更履歴ファイル。実体は CHANGELOG.md）の書き忘れを CI の門で
止める（ADR-071）。

## 入出力

- `scripts/release-check.py`: 入力なし。**版の整合**を検める — CHANGELOG の
  先頭の版付き節（`## [X.Y.Z] — 日付` の形。「未リリース」節は飛ばす）が、
  版番号の正本（`plugin/.claude-plugin/plugin.json` の version。SPEC-020）と
  一致し、日付を持つこと。違反を列挙し、あれば終了コード 1、無ければ 0。
- `scripts/release-check.py --diff-base <ref>`: 上に加えて**記録の義務**を
  検める — `git diff --name-only <ref> HEAD` が `plugin/` 配下を含むなら、
  同じ差分が CHANGELOG.md も含むこと。環境変数 `RELEASE_CHECK_PR_TITLE` に
  `[no-changelog]` が含まれれば、この検査だけを免除し、免除した旨を告げる
  （版の整合は免除しない）。
- あわせて**公開ビューの刻印**を検める（ADR-073）— 公開ビュー3件
  （`README.md`・`plugin/README.md`・`CONTRIBUTING.md`）が刻印（書式の正本は
  ICD-005 の `view-stamp-format`）を持ち、その `as-of` が版番号の正本
  （plugin.json の version）と一致すること。刻印が無い・読めない・版が
  食い違うのは違反とする。版を上げるときは、公開ビューの内容を検めてから
  刻印を打ち直す（リリースごとの再確認の義務）。
- marketplace.json との一致は検めない（TEST-020 が強制済み。二重定義しない）。

## 制約

- 本リポジトリ専用の自己適用。プラグインの配布物には含めない。
- 標準ライブラリのみ（ADR-031）。git の呼び出しは `--diff-base` のときだけ。
- 「未リリース」節は常設だが、検査上は任意（節が無くても版の整合は判じる）。
- 配布物の衛生（常時）: `plugin/` の下に `.cache`・`.claude`・`__pycache__` が無いこと。ディレクトリ配布ではそのまま利用者へ複製される（ADR-075）。
- 設定の見張り（常時）: 統治の設定 `doctrine_docs/_system/.context-config.json` が在るなら、それを対象にする EXT アンカーが在り、その**検査が hash** で、**指紋の行を持つ**こと（ADR-096）。設定が無い木では何も言わない。**なぜここに置くか** —— 指紋が動けば監査が warn を出すが、**アンカーそのものが消されても監査は何も言わない**（見張りが無くなった状態は、見張りでは分からない）。同梱の試験には置けない（配布物の外を素で読む形になる。ADR-075）ので、リポジトリ側の門が持つ。検査の種別は**監査と同じ形**（`検査:` の行）で読む —— 本文全体で `hash` を探す書き方は、散文の「`hash` にする」で通ってしまう（実測）。

## エラー時挙動

- plugin.json・CHANGELOG.md が読めない、または版付き節が一つも無いときは、
  理由を出して終了コード 2（黙って通さない）。
- `--diff-base` で git の呼び出しに失敗したときも、理由を出して終了コード 2。

## 実装の指紋

対象は契約の要約（モジュール冒頭）。更新は `trace-index.py --id SPEC-027` が
返す行を写す（ADR-061）。

- sha256:17706db56aec9f93cc0c1c4f9ebe5bc64fdfb70ac518179146ff242a234b287d

## 受入基準

- 版の整合: 先頭の版付き節の版が plugin.json と食い違えば赤（終了コード 1）。
  一致し日付があれば緑（0）。
- 記録の義務: 差分が `plugin/` を含み CHANGELOG.md を含まなければ赤。両方
  含めば緑。`[no-changelog]` の印があれば緑（免除の旨を告げる）。
- 公開ビューの刻印: 3件のどれかが刻印を欠く・読めない・`as-of` が plugin.json
  の version と食い違えば赤。3件とも一致すれば緑（`[no-changelog]` では
  免除しない）。
- 前提が読めなければ 2 で止まる（0 で通らない）。
- 受入は TEST-027 が凍結する。

<!-- 入れない: リリース手順の正本(PROC-001)、ADR の再掲 -->
