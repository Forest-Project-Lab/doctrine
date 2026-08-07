---
name: system-map-draft
description: '対象リポジトリから System Map の意味モデルの下書き(proposed 限定の候補)を起草する。全ての値に出所(読んだ場所・確認日・判定)を付け、出所は map-draft-check.py が機械検証する。確定(confirmed への昇格)は人が行う。"draft a system map"・"generate a proposed system model"・「System Map の下書きを起草して」・「意味モデルの下書きを作って」と言われたときに使う。'
---

# system-map-draft

## 役割

対象リポジトリから System Map の意味モデルの下書きを起草する。器は lens 側の検証用スキーマ `system-map/gold-model/0.1` であり、doctrine の正式スキーマではない(ADR-112 のスキーマ不変は維持。ADR-136)。全ての値は `review_status: proposed` の候補にとどまり、確定(`confirmed` への昇格)は人が行う。統治木は書き換えない。

## 委ねる先

- 宣言済み CLI — 構造の事実の取り口(ICD-002・ICD-005)。`${CLAUDE_PLUGIN_ROOT}/scripts/` の `trace-index.py`・`dep-graph.py`・`docs-audit.py --json`。
- `${CLAUDE_PLUGIN_ROOT}/scripts/map-draft-check.py` — 出所の機械検証(検収の第一門。捏造出所を落とす)。
- lens 側の `gold-model/validate.mjs` — M-01〜M-16 の不変条件(検収の第二門)。EXT-006 の tag `system-map/phase-1-continue` で固定した複製で回す(`references/acceptance-gates.md`)。

## 入出力

- 入力: 対象リポジトリの root(既定は `CLAUDE_PROJECT_DIR`)・統治木の docs root・対象名(kebab-case)・書き出す先。
- 書き出すもの: 1 つの JSON(`"schema": "system-map/gold-model/0.1"`)。既定の置き場は `${CLAUDE_PROJECT_DIR}/.claude/system-map/draft-<対象名>.json`。これは統治木の外の機械生成物であり、どの ICD の読み口でもない。

## 手順

1. 対象を確かめる。root・docs root・対象名・書き出す先を利用者と確かめ、示されなければ既定を使う。
2. 構造の事実を宣言済み CLI から取る。`trace-index.py --format json`(注釈対の範囲と指紋)・`dep-graph.py --json`(依存の事実 — ただし Flow の材料にしない。M-08)・`docs-audit.py --json --today <日付>`(所見)。`.claude/.cache` は読まない(M-13。導出された事実は宣言済み CLI からだけ取る。ADR-136)。
3. 意味を読む。`README`・統治文書・コード・git log を直接読み、読んだ場所を全ての値の `provenance` に書く(`references/provenance-rules.md`)。
4. `elements` → `flows` → `contracts` → `scenarios` → `anchors` の順に起草する。各欄の判断は `references/model-shape.md` に従う。
5. 検収の二門を回す。まず `map-draft-check.py` で出所を機械検証し、落ちた所見に沿って下書きを直す。次に lens 側 `validate.mjs` を無修正で回し、M 層の指摘を直す(`references/acceptance-gates.md`)。
6. 報告する。両門の判定・要素数(`elements`・`flows`・`contracts`・`scenarios`・`anchors` の各件数)・`unknown` の contract の数と負の出所の数・書き出した場所。

## 起草の規律

- 全ての値に `review_status: proposed` を付ける。`confirmed` を書かない(昇格は人の仕事)。
- 実際に読んでいない場所を出所に書かない。捏造出所は検証器が落とす。
- `unknown` の contract には負の出所を付ける — どこを見て・いつ・`silent` だったか(M-11)。未調査と「確認したが記載が無かった」を混同しない。
- `depends_on`・`impacts` の辺を Flow へ変換しない(M-08)。Flow は本文・コードの記述そのものを根拠に取り、取れなければ書かない(`references/flow-evidence.md`)。
- 全ての Flow に `label` を付ける(M-09。無名の矢印を作らない)。自己ループには `self_loop_reason` を書く(M-03)。
- anchor の `authority` はちょうど一つ(M-10。`doctrine` か `gold_model`)。doctrine 権威の `code_range` anchor には、`source_revision` に完全 SHA(コミットを一意に指す指紋)を、`url` に SHA 固定の参照を持たせる(overlay の鮮度判定と M-14 の到達に要る)。

## 詳細（references/）

- `references/model-shape.md` — 各欄の起草の手引き(必須欄・enum 値・条件必須)。
- `references/provenance-rules.md` — Source の形・CLI 由来の事実・負の出所。
- `references/flow-evidence.md` — Flow の根拠になる記述と、取れないときの扱い(M-08・M-04)。
- `references/acceptance-gates.md` — 検収の二門の実行手順。

## 保証限界

- 予防: 起草者は意味の正しさを保証しない。全ての値は `proposed` の候補であり、昇格は人が行う。
- 検出: 出所の実在と形は `map-draft-check.py` が、M 層の不変条件は lens 側の validator(`validate.mjs`)が検める。
- 委ねる: `confirmed` への昇格・Flow の意味判断・対象の境界の裁定は人に委ねる。
