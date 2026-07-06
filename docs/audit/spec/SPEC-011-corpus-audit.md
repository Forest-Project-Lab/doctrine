---
id: SPEC-011
title: 全件監査の検査群・要約スキーマ・決定性
type: SPEC
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-06
sources: [spec/doctrine.ja.md#4.2]
depends_on: [REQ-008, ICD-001, ICD-002]
llm_context: task
---

# 全件監査の検査群・要約スキーマ・決定性

`docs-audit.py` がコーパス全件を走査し、所見と要約を出すための契約を定める。文書集合が過不足なく最小であることを過剰側と不足側の両方から検査し、あわせて古びも検出する。`[R1][R3][R4][R8]`

## 入出力

- 入力: コマンドライン引数 `[--root docs/] [--json] [--summary-out PATH] [--fail-on error|never] [--config PATH] [--today YYYY-MM-DD] [--respect-docs-level]`。標準入力は読まない。入力内容に結果が左右されないからであり、対話端末から起動しても入力待ちで止まらない。
- 処理: docs ルート配下のすべての .md について、graph（ICD-002）が依存グラフを組み、登録簿（ICD-001）が各文書の型・`status`・`llm_context` を解決する。本文は一度だけ読んでノードに付ける。
- 返す値: 要約スキーマ `docs-audit/1`。形は `{schema, generated_at, today, root, totals:{error,warn,advisory}, counts_by_check, top_findings, findings}`。`root` は絶対パスに正規化して書く（注入側が相対 root を照合不能として捨てるため。SPEC-012）。`--json` を付けると機械向けの JSON を、付けなければ人間向けの平文を出す。`--summary-out` を指定すると、要約を一時ファイルに書いてから改名して差し替え、途中状態を残さない。

## 制約

- 標準ライブラリだけを使う。pip での外部パッケージ取得も、ネットワーク通信もしない。返す値は毎回同じになる（所見を check・doc_id・message の順で整列する）。
- 10 検査の重大度は固定とする（ICD-005 の表のとおり）。`top_findings` は error を優先し、上限 20 件とする。
- 語彙的酷似（near_duplicate）の対走査は O(n^2) であり、規模上限 `near_dup_max_docs`（既定 800、`--config` で上書き）を設ける。現行文書数がこの上限を超えた場合は対走査を省き、省いた事実を near_duplicate の助言一つで正直に告げる（黙って切り詰めない）。重大度は advisory のまま（ICD-005 不変）。`[R8]`
- `generated_at` は `today` から決める（`today.isoformat()+"T00:00:00Z"`）。テストが制御できないシステム時刻は参照しない。`[R1]`
- 孤児は三条件すべてを満たす文書とする（どの現行文書からも依存されない、かつ陳腐化している、かつ再現可能）。投影・`llm_context`==always・ICD は孤児にしない。`[R8]`
- 逆孤児は現行文書だけを対象とする（判定は graph の `reverse_orphans` に委ねる）。`[R3]`
- ドメインをまたぐ `depends_on` の違反だけを icd_dependency_violation として上げる。ドメインをまたぐ impacts は違反としない。`[R4]`
- 未登録/影文書は、`build_graph` が既に集める `parse_warnings`（frontmatter か id が無い .md）と `dup_ids`（id 衝突で影に隠れた別ファイル）を読むだけで検出する。新たな走査はしない。他の全検査は登録簿ノード上の述語なので、ノードにならないファイルはこの検査だけが拾える。取り除きではなく、型を与えて登録するか archive/ へ退避する候補として error で挙げる。`[R1][R8]`
- 投影ドリフトは三つの投影を対象とする。Overview と ICD-index は id 集合の差（error）。Context Map は印の区間の骨格を内部で再導出して突き合わせ、構造の差（ドメインの過不足・ドメイン越え依存端の過不足・印の区間が無い）を error、ラベルの差（ドメイン行の ICD 列挙・境界違反マーク）を warn とする（ICD-005 の表のとおり）。`[R1][R8]`
- テスト不能記述は検査しない。意味の判断であり、doc-review が担う（ADR-020）。

## エラー時挙動

- ルートが見つからない場合: 所見ゼロと同じ扱いにして終了コード 0 を返す。CI も SessionEnd もここで止めない。
- `--respect-docs-level` 付きで、対象の `docs/_system/.docs-level` が `level: 2` の場合: 監査を飛ばした旨を出して終了コード 0 を返し、要約は書かない（ADR-019。全件監査は Level 3 から）。この旗は SessionEnd の配線だけが付ける。CI は付けず、Level に依らず監査する。
- 与えられた `--today` または config.today を日付として解釈できない場合: 使い方の誤りとして終了コード 2 を返す。黙ってシステム時刻に切り替えることはしない。
- 監査本体がクラッシュした場合: stderr に記録して終了コード 0 を返し、Hook の連鎖を妨げない。要約の書き込みに失敗した場合も 0 を保つ。

## 受入基準

TEST-011 で確認する。受入シナリオ TC（TC-082〜130 系）で各検査の pass/fail、要約の受け渡し、結果が毎回同じになること、不正な基準日で終了コード 2 になることを検証する。各検査は pass と、fail または上限到達の両側を持つこと。
