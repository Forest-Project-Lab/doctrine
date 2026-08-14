---
name: system-map-draft
description: '対象リポジトリから系の意味モデルの下書き(MODEL 型の .md。proposed 限定の候補)を統治木の中へ起草する。全ての値に出所(読んだ場所・確認日・判定)を付け、構造はリンタが、出所は map-draft-check.py が機械検証する。確定(confirmed への昇格と status の一押し)は人が行う。"draft a system map"・"generate a proposed system model"・「System Map の下書きを起草して」・「意味モデルの下書きを作って」と言われたときに使う。'
---

# system-map-draft

## 役割

対象リポジトリから系の意味モデルの下書きを起草する。書く先は**統治木の中の MODEL 型の .md**
であり（ADR-161・ADR-163）、値は本文の見出しの直下に置いた JSON の塊が持つ。JSON は
`render-projection.py` が .md から一方通行で描く投影であり、手で保守しない。全ての値は
`review_status: proposed` の候補にとどまり、**確定（`confirmed` への昇格と、文書の
`status` を `current` にする一押し）は人が行う。**

## 委ねる先

- 宣言済み CLI — 構造の事実の取り口（ICD-002・ICD-005）。`${CLAUDE_PLUGIN_ROOT}/scripts/` の
  `trace-index.py`・`dep-graph.py`・`docs-audit.py --json`。`dep-graph.py` はモードを一つ必ず
  指定する（`--classify-edges` など。`--json` は修飾子であってモードではない。ADR-110）。
- `docs-linter.py` — 本文の構造の担保（`MODEL_*`。SPEC-031）。必須欄・語彙・id の一意・
  文書の中の参照の実在・確定の同値を検める。
- `render-projection.py model --id <id>` — .md から JSON への描画（正本の .md の隣へ同じ名の
  `.json`）。
- `map-draft-check.py` — 出所の機械検証（検収の門。捏造出所を落とす）。掛ける先は描いた JSON。
- lens 側の `gold-model/validate.mjs` — M-01〜M-16 の不変条件（検収の第二門）。EXT-006 の tag
  で固定した複製で回す（`references/acceptance-gates.md`）。

## 入出力

- 入力: 対象リポジトリの root（既定は `CLAUDE_PROJECT_DIR`）・統治木の docs root・対象名
  （kebab-case）・置くドメイン。
- 書き出すもの: `<統治木>/<ドメイン>/model/MODEL-<連番>-<対象名>.md` を一つ。フロントマターは
  八つの必須キーを持ち、`type: MODEL`・`status: proposed`・`llm_context: task` とする。
  本文は六つの必須節（「系の概要」「要素の一覧」「流れの一覧」「契約の一覧」「シナリオの一覧」
  「アンカーの一覧」）を持つ。雛形は `templates/model.md.tmpl`。
- 併せて描くもの: 同じ場所の `.json`（`render-projection.py model --id <id>`）。**手で書かない。**

## 手順

1. 対象を確かめる。root・docs root・対象名・置くドメインを利用者と確かめ、示されなければ
   既定を使う。ドメインのフォルダと `model/` の層は、書く直前に作る（遅延生成）。
2. 構造の事実を宣言済み CLI から取る。`trace-index.py --format json`（注釈対の範囲と指紋）・
   `dep-graph.py --classify-edges --json`（依存の事実 —— ただし Flow の材料にしない。M-08）・
   `docs-audit.py --json --today <日付>`（所見）。`.claude/.cache` は読まない（M-13。導出された
   事実は宣言済み CLI からだけ取る。ADR-136）。
3. 意味を読む。`README`・統治文書・コード・git log を直接読み、読んだ場所を全ての値の
   `provenance` に書く（`references/provenance-rules.md`）。
4. 節ごとに起草する。「系の概要」→「要素の一覧」→「流れの一覧」→「契約の一覧」→
   「シナリオの一覧」→「アンカーの一覧」の順で、実体ごとに `### <id> — <表示名>` の見出しと、
   その直下の ```json の塊を置く。各欄の判断は `references/model-shape.md` に従う。
5. 検収の門を順に回す（`references/acceptance-gates.md`）。**構造**（`docs-linter.py <path>`。
   `MODEL_*` の所見が無くなるまで直す）→ **描画**（`render-projection.py model --id <id>`）→
   **出所**（`map-draft-check.py --model <描いた .json>`）→ **M 層**（lens 側 validator）。
6. 報告する。四つの門の判定・要素数（要素・流れ・契約・シナリオ・アンカーの各件数）・
   `unknown` の contract の数と負の出所の数・書き出した .md と .json の場所。

## 起草の規律

- 全ての値に `review_status: proposed` を付ける。`confirmed` を書かない。文書の `status` も
  `proposed` のままにする（昇格は人の仕事。両者は同値であり、リンタが食い違いを咎める）。
- 実際に読んでいない場所を出所に書かない。捏造出所は検証器が落とす。
- `unknown` の contract には負の出所を付ける —— どこを見て・いつ・`silent` だったか（M-11）。
  未調査と「確認したが記載が無かった」を混同しない。
- `depends_on`・`impacts` の辺を Flow へ変換しない（M-08）。Flow は本文・コードの記述そのものを
  根拠に取り、取れなければ書かない（`references/flow-evidence.md`）。
- 全ての Flow に `label` を付ける（M-09。無名の矢印を作らない）。自己ループには
  `self_loop_reason` を書く（M-03。リンタも咎める）。
- 見出しの id と塊の `id` を揃える。**文書の中に無い id を指さない**（流れの端・シナリオの段・
  `parent`・`realized_by`。リンタが咎める）。
- anchor の `authority` はちょうど一つ（M-10。`doctrine` か `gold_model`）。doctrine 権威の
  `code_range` anchor には、`source_revision` に完全 SHA（コミットを一意に指す指紋）を、
  `url` に SHA 固定の参照を持たせる。
- **描いた JSON を手で直さない。** 直すのは .md であり、JSON は描き直す（一方通行。
  ADR-161 決定3）。

## 詳細（references/）

- `references/model-shape.md` — 各欄の起草の手引き（必須欄・enum 値・条件必須）と .md の並べ方。
- `references/provenance-rules.md` — Source の形・CLI 由来の事実・負の出所。
- `references/flow-evidence.md` — Flow の根拠になる記述と、取れないときの扱い（M-08・M-04）。
- `references/acceptance-gates.md` — 検収の門の実行手順。

## 保証限界

- 予防: 起草者は意味の正しさを保証しない。全ての値は `proposed` の候補であり、昇格は人が行う。
- 検出: 本文の構造は `docs-linter.py`（`MODEL_*`。SPEC-031）が、出所の実在と形は
  `map-draft-check.py` が、M 層の不変条件は lens 側の validator が検める。
- 委ねる: `confirmed` への昇格と `status` の一押し・Flow の意味判断・対象の境界の裁定は人に
  委ねる。
