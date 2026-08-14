---
id: SPEC-024
title: review-nudge（手編集への doc-review の促しと捕捉の印）
type: SPEC
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-14
sources: [plugin/scripts/review-nudge.py]
depends_on: [ICD-004]
llm_context: task
---

# review-nudge（手編集への doc-review の促しと捕捉の印）

`review-nudge.py`(PostToolUse、リンタと同じ並びの三本目)の仕様である。doc-author を介さない手編集にも doc-review を促す、判断層のもう一つの入口を担う(ADR-012 の閉じた輪)`[R10][R12]`。

## 入出力

- 入力: PostToolUse のエンベロープ(tool_input の file_path、session_id)。
- 返す値(助言): 対象が型付き統治文書のとき、doc-review の起動を促す一行(文章規範・一覧外カルク・位置づけ・定例3点。書き戻し先は運用正本 `_system/glossary.md`)。additionalContext のみで、decision は決して出さない(WATCH-001 第4項をリンタと共有する)。
- 返す値(印): 型付き文書の編集で `edits-<セッションid>`、記録の型(ADR・DECIDED・WATCH・CHANGE)かセッションメモ(`.session-notes`)への書き込みで `recorded-<セッションid>` を残す(SPEC-022 の捕捉の輪の入力)。

## 制約

- 助言を返すのは Level 3 以上(ADR-019 の自主停止)。捕捉の印は Level に依らず残す(ADR-030)。
- 型なしの .md と文書でないファイルには何も出さない(セッションメモは印だけ)。
- 標準ライブラリのみ。決して例外を外へ出さない。終了コードは常に 0。

## エラー時挙動

- フロントマターが読めない対象は文書でないとみなして無音。
- 印の置き場が作れないときは印を諦める(助言層なので安全側は沈黙)。

## 実装の指紋

対象はdoc-review 促し文の正本。更新は `trace-index.py --id SPEC-024` が返す行を写す（ADR-061）。

- sha256:43805d7f7fb8f78046a9c6a36e1e423a58e9e28d4fd37bffce1b601f2da2d9af

## 受入基準

- 型付き文書の編集で助言が出て、decision を含まない。
- Level 2 では助言が出ず、印は残る。
- 記録の型とセッションメモで `recorded` の印が残る。
- 受入は TEST-024 が凍結する。
