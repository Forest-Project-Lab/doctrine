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
- `load_schema(path)`: 同梱した器の一枚（`plugin/schemas/system-map-gold-model-0.1.json`）を
  読み、`(schema, 理由)` を返す。読めなければ `schema` は None である。
- **器から導く表**: `MODEL_SCHEMA`（器の版）・`TOP_KEYS`・`ENTITY_LISTS`・`REQUIRED_FIELDS`
  （実体ごとと系）・`STEP_FIELDS`（シナリオの段）・`PROVENANCE_FIELDS`（出所）・`ENUMS`
  （器が `enum` を書いた欄を機械的に集めた表）と、呼び手が引く別名の列挙。**手で並べた表を
  持たない**（ADR-165 決定2）。`PROSE_FIELDS` と `RETIRED_STATUSES` は doctrine 側の定めで
  あり、器には無い。
- `prose_values(model)`: 塊の中の散文の値を `(where, 行, 文字列)` の列で返す。用語の門を
  塊の中へ届かせるための口であり、対象は `PROSE_FIELDS` の欄に限る（ADR-164 決定3）。

## 制約

- 標準ライブラリだけで書く。決定的に動く（壁時計も乱数も読まない）。
- **兄弟文書を読まない。** 検めるのは渡された一文書の本文だけであり、参照の実在も文書の中に
  限る（per-turn の規律。NONGOAL-001 第5項）。
- **意味の正しさを検めない。** その要素が本当に在るか、その流れが実際に起きるかは見ない。
  出所の実在は `map-draft-check.py`（SPEC-029）が、M 層の不変条件は doctrine-lens 側の
  validator が、確定の判断は人が持つ。
- 必須節の名の正本は登録簿（`REQUIRED_SECTIONS["MODEL"]`）であり、この部品は**節名を写さず
  登録簿から導く**（登録簿の並びが器の最上位の欄と一対一であることを使う。ADR-164 決定6。
  写すと、登録簿を直したときに本文の値だけが拾われなくなる）。節名の照合は部分一致とする
  （リンタの必須節検査と同じ規律）。
- **必須節の外に置かれた塊は値として拾わない。** 散文の例示を値にしない。
- 描く向きは .md から JSON への一方通行とする。JSON を読んで .md を組む口は持たない
  （ADR-161 決定3）。
- **器の形の正本は doctrine-lens の `schema.json` であり、doctrine は固定した一枚を同梱して
  そこから導く**（ADR-165・EXT-007）。器の版（`MODEL_SCHEMA`）も一枚から読む。版の進め方は
  ADR-165 決定4 が持つ。
- **器の一枚を読めないときは黙って通さない** —— `MODEL_SCHEMA_UNREADABLE`（ERROR）一件だけを
  返し、他の検査を行わない（器を持たないまま緑を出さない）。

## エラー時挙動

- 例外を投げない。読めない塊・写像でない塊・配列でない `steps`・配列でない `realized_by`・
  深すぎる入れ子（`RecursionError`）は、いずれも所見にして続ける。
- 所見は `Finding(code, severity, where, message, line)` の列である。`severity` は
  `ERROR` を既定とする。呼び手（リンタ）が自分の段へ写す。
- 所見の名は次のとおり: `MODEL_BAD_JSON`・`MODEL_MISSING_SYSTEM`・`MODEL_DUPLICATE_SYSTEM`・
  `MODEL_MISSING_FIELD`・`MODEL_BAD_ID`・`MODEL_BAD_ENUM`・`MODEL_BAD_PROVENANCE`・
  `MODEL_BAD_REALIZED_BY`・`MODEL_DUPLICATE_ID`・`MODEL_HEADING_ID_MISMATCH`・
  `MODEL_HEADING_WITHOUT_BLOCK`・`MODEL_DANGLING_REF`・`MODEL_SELF_LOOP_WITHOUT_REASON`・
  `MODEL_BAD_STEPS`・`MODEL_UNCONFIRMED_IN_CURRENT`・`MODEL_CONFIRMED_NOT_CURRENT`・
  `MODEL_SCHEMA_UNREADABLE`。
  段は `MODEL_CONFIRMED_NOT_CURRENT` だけが WARN で、ほかは ERROR とする（ADR-164 決定4）。
- **アンカーは値を担わない**（指し先の記述である）ので、`review_status` と `provenance` を
  求めない。
- **必須欄は「鍵が在り、値が `null` でない」ことを求める**（ADR-164 決定5）。鍵だけ在って
  値が `null` の欄は、欠落と同じに数える。
- **引退した位置づけ**（`deprecated`・`superseded`・`archived`）では、確定の同値を検めない
  （ADR-164 決定2）。

## 実装の指紋

この節がある文書だけが、コードとの追跡の対象になる（ADR-056 の opt-in）。更新は
`trace-index.py --id SPEC-031` が返す行を写す。

- sha256:1503addc972e6513150e479fe4e2ae8002dd8ab402921595b1e5e57aa32d9058

## 受入基準

- 六つの節の塊が、節ごとに正しく拾われる。必須節の外の塊は拾われない。
- 読めない塊は所見になり、他の塊の点検は続く（例外にしない）。
- 必須欄の欠落・語彙の外れ・id の重複・見出しと id の食い違い・文書の中に無い参照・
  理由の無い自己ループが、それぞれ固有の名の所見になる。
- `status` が `current` なのに `confirmed` でない値が在れば ERROR になる。全ての値が
  `confirmed` なのに `current` でなければ WARN になり、その文面は**機械へ確定を指示しない**
  （ADR-163 決定6 の同値と、ADR-164 決定4）。引退した位置づけでは、どちらも検めない。
- 描いた JSON は、最上位が八つの欄を持ち、`target` が最上位に在り、解析の覚え書きを含まず、
  同じ入力から同じ文字列になる。文書の中の出現順が保たれる。
- リンタが同じ規則で MODEL の本文を咎める（規則が二重に定義されていない）。節名は登録簿と
  一致し、必須欄と語彙は同梱した器の一枚と一致する（どちらも写しを持たない）。
- シナリオの段の必須欄（器の `Scenario.steps.items.required`）が検められる。
- 器の一枚を取り除くと `MODEL_SCHEMA_UNREADABLE` だけが出て、他の検査が黙って通らない。
- 配列でない `realized_by`・`null` の必須欄・空でない文字列でない id・塊を持たない見出しが、
  それぞれ固有の名の所見になり、**例外を漏らさない**。
- 塊の中の散文（`PROSE_FIELDS`）に用語の門が掛かる。
- 対応するテストは TEST-031 が確認する。

<!-- 入れない: 廃止、検討、実装コードの写し -->
