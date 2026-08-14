---
id: SPEC-031
title: 意味モデルの本文の形と機械の担保（`_model.py` の契約）
type: SPEC
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-14
sources: [plugin/scripts/_model.py, "https://github.com/Forest-Project-Lab/doctrine/issues/294"]
depends_on: [SPEC-001]
llm_context: task
---

# 意味モデルの本文の形と機械の担保（`_model.py` の契約）

`_model.py` は、MODEL 型（系の意味モデル。ADR-163）の本文を解き、器が要する構造を
機械的に担保し、描く先の JSON を組む共有の部品である。リンタ（ICD-004）と描き手
（ICD-006）と出所の門（SPEC-029）は、この部品を呼び、語彙と形を二重定義しない。[R2][R6][R8]

## 入出力

- `parse_blocks(body)`: 本文から `(節名, 見出し, 塊の文字列, 行番号)` の列を出現順で返す。
  節は `## 見出し`、実体は `### 見出し`、値はその直後の ```json の囲みである。
- `parse_model(body)`: `(model, findings)` を返す。`model` は
  `{system, elements, flows, contracts, scenarios, anchors}` の写像で、解析の覚え書き
  （先頭が `_` の鍵）を各実体に付ける。JSON として読めない塊は所見にし、その塊だけを落とす。
- `check_structure(model, findings)`: 必須欄・語彙・id の一意・見出しと id の一致・文書の中の
  参照の実在・自己ループの理由を検め、`findings` へ足す。
- `check_confirmation(model, status, findings)`: 文書の `status` と値の `review_status` の
  同値を検める（ADR-163 決定6）。
- `check_document(body, status)`: 上の三つを続けて呼び、所見の列を返す。リンタの口はこれ一つ。
- `render_json(model)`: 描く先の JSON の文字列を返す。最上位は
  `schema`・`target`・`system`・`elements`・`flows`・`contracts`・`scenarios`・`anchors`。
  `target` は「系の概要」の塊から最上位へ持ち上げる。並びは文書の中の出現順、鍵は整列、
  末尾に改行を一つ置く。
- 語彙の正本: `MODEL_SCHEMA`・`TOP_KEYS`・`ENTITY_LISTS`・`REQUIRED_FIELDS`・
  `PROVENANCE_FIELDS` と、六つの列挙（`ENUM_REVIEW_STATUS`・`ENUM_VERDICT`・
  `ENUM_TARGET_KIND`・`ENUM_AUTHORITY`・`ENUM_VERIFICATION_STATUS`・`ENUM_ELEMENT_KIND`・
  `ENUM_FLOW_KIND`・`ENUM_SCENARIO_KIND`）。

## 制約

- 標準ライブラリだけで書く。決定的に動く（壁時計も乱数も読まない）。
- **兄弟文書を読まない。** 検めるのは渡された一文書の本文だけであり、参照の実在も文書の中に
  限る（per-turn の規律。NONGOAL-001 第5項）。
- **意味の正しさを検めない。** その要素が本当に在るか、その流れが実際に起きるかは見ない。
  出所の実在は `map-draft-check.py`（SPEC-029）が、M 層の不変条件は doctrine-lens 側の
  validator が、確定の判断は人が持つ。
- 必須節の名の正本は登録簿（`REQUIRED_SECTIONS["MODEL"]`）であり、この部品は節名と描く先の
  欄の**対応表**だけを持つ。節名の照合は部分一致とする（リンタの必須節検査と同じ規律）。
- **必須節の外に置かれた塊は値として拾わない。** 散文の例示を値にしない。
- 描く向きは .md から JSON への一方通行とする。JSON を読んで .md を組む口は持たない
  （ADR-161 決定3）。
- 器の版（`MODEL_SCHEMA`）はこの部品が持つ定数とする（ADR-163 決定9）。版の進め方は
  issue #294 の B1（器の正本と版の進め方）が持ち、本仕様は決めない。

## エラー時挙動

- 例外を投げない。読めない塊・写像でない塊・配列でない `steps` は所見にして続ける。
- 所見は `Finding(code, severity, where, message, line)` の列である。`severity` は
  `ERROR` を既定とする。呼び手（リンタ）が自分の段へ写す。
- 所見の名は次のとおり: `MODEL_BAD_JSON`・`MODEL_MISSING_SYSTEM`・`MODEL_DUPLICATE_SYSTEM`・
  `MODEL_MISSING_FIELD`・`MODEL_BAD_ENUM`・`MODEL_BAD_PROVENANCE`・`MODEL_DUPLICATE_ID`・
  `MODEL_HEADING_ID_MISMATCH`・`MODEL_DANGLING_REF`・`MODEL_SELF_LOOP_WITHOUT_REASON`・
  `MODEL_BAD_STEPS`・`MODEL_UNCONFIRMED_IN_CURRENT`・`MODEL_CONFIRMED_NOT_CURRENT`。
- **アンカーは値を担わない**（指し先の記述である）ので、`review_status` と `provenance` を
  求めない。

## 実装の指紋

この節がある文書だけが、コードとの追跡の対象になる（ADR-056 の opt-in）。更新は
`trace-index.py --id SPEC-031` が返す行を写す。

- sha256:a97d432ec73322c775d7f57226c26666789c1f45edd39d483ad281f5cade7304

## 受入基準

- 六つの節の塊が、節ごとに正しく拾われる。必須節の外の塊は拾われない。
- 読めない塊は所見になり、他の塊の点検は続く（例外にしない）。
- 必須欄の欠落・語彙の外れ・id の重複・見出しと id の食い違い・文書の中に無い参照・
  理由の無い自己ループが、それぞれ固有の名の所見になる。
- `status` が `current` なのに `confirmed` でない値が在れば所見になる。全ての値が
  `confirmed` なのに `current` でなければ所見になる（ADR-163 決定6 の同値）。
- 描いた JSON は、最上位が八つの欄を持ち、`target` が最上位に在り、解析の覚え書きを含まず、
  同じ入力から同じ文字列になる。文書の中の出現順が保たれる。
- リンタが同じ規則で MODEL の本文を咎める（規則が二重に定義されていない）。
- 対応するテストは TEST-031 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
