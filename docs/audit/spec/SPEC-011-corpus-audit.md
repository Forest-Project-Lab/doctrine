---
id: SPEC-011
title: 全件監査の検査群・要約スキーマ・決定性
type: SPEC
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md#4.2]
depends_on: [REQ-008, ICD-001, ICD-002]
llm_context: task
---

# 全件監査の検査群・要約スキーマ・決定性

`docs-audit.py` がコーパス全件を走査し、所見と要約を出すための契約を定める。文書集合が過不足なく最小であることを過剰側と不足側の両方から検査し、あわせて古びも検出する。`[R1][R3][R4][R8]`

## 入出力

- 入力: コマンドライン引数 `[--root docs/] [--json] [--summary-out PATH] [--fail-on error|never] [--config PATH] [--today YYYY-MM-DD]`。標準入力は読まない。入力内容に結果が左右されないからであり、対話端末から起動しても入力待ちで止まらない。
- 処理: docs ルート配下のすべての .md について、graph（ICD-002）が依存グラフを組み、登録簿（ICD-001）が各文書の型・`status`・`llm_context` を解決する。本文は一度だけ読んでノードに付ける。
- 返す値: 要約スキーマ `docs-audit/1`。形は `{schema, generated_at, today, root, totals:{error,warn,advisory}, counts_by_check, top_findings, findings}`。`--json` を付けると機械向けの JSON を、付けなければ人間向けの平文を出す。`--summary-out` を指定すると、要約を一時ファイルに書いてから改名して差し替え、途中状態を残さない。

## 制約

- 標準ライブラリだけを使う。pip での外部パッケージ取得も、ネットワーク通信もしない。返す値は毎回同じになる（所見を check・doc_id・message の順で整列する）。
- 9 検査の重大度は固定とする（ICD-005 の表のとおり）。`top_findings` は error を優先し、上限 20 件とする。
- `generated_at` は `today` から決める（`today.isoformat()+"T00:00:00Z"`）。テストが制御できないシステム時刻は参照しない。`[R1]`
- 孤児は三条件すべてを満たす文書とする（どの現行文書からも依存されない、かつ陳腐化している、かつ再現可能）。投影・`llm_context`==always・ICD は孤児にしない。`[R8]`
- 逆孤児は現行文書だけを対象とする（判定は graph の `reverse_orphans` に委ねる）。`[R3]`
- ドメインをまたぐ `depends_on` の違反だけを icd_dependency_violation として上げる。ドメインをまたぐ impacts は違反としない。`[R4]`

## エラー時挙動

- ルートが見つからない場合: 所見ゼロと同じ扱いにして終了コード 0 を返す。CI も SessionEnd もここで止めない。
- 与えられた `--today` または config.today を日付として解釈できない場合: 使い方の誤りとして終了コード 2 を返す。黙ってシステム時刻に切り替えることはしない。
- 監査本体がクラッシュした場合: stderr に記録して終了コード 0 を返し、Hook の連鎖を妨げない。要約の書き込みに失敗した場合も 0 を保つ。

## 受入基準

TEST-011 で確認する。受入シナリオ TC（TC-082〜130 系）で各検査の pass/fail、要約の受け渡し、結果が毎回同じになること、不正な基準日で終了コード 2 になることを検証する。各検査は pass と、fail または上限到達の両側を持つこと。
