---
id: EXT-007
title: 意味モデルの器（`gold-model/schema.json`）の固定した写しへの依存
type: EXT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
review_by: 2026-11-14
llm_context: task
---

# 意味モデルの器（`gold-model/schema.json`）の固定した写しへの依存

統治木の外への依存を登録するアンカーである（ADR-026）。中身は写さない。MODEL 型の本文が
満たすべき**形の正本は doctrine-lens 側の `gold-model/schema.json`** であり（#294 の
B7（語彙の正本をどちらが持つかの項目））、
doctrine はその固定した一枚を配布物へ同梱して、必須欄・語彙・段の必須欄をそこから導く
（ADR-165）。

## 何に依存しているか

`plugin/schemas/system-map-gold-model-0.2.json` は、doctrine-lens リポジトリの
`research/system-map/gold-model/schema.json` を、tag `system-map/gold-model-0.2`
（commit `991b8a6e3e6870d9651279956a8f7a60292e47af`）から採った写しである。`_model.py`
（SPEC-031）はこの一枚を読み、**手で並べた表を持たない。**

上流が版を上げるときの規約の正本は、この一枚の `$comment` が持つ（ADR-168 決定2）。要点——
受け入れる集合が狭まる変更（必須欄の追加・語彙の縮小・制約の追加）は版の名を上げ、
doctrine-lens が #294 へ告知し、doctrine が追随する（逆はしない。正本は一つ）。0.1 から 0.2
への上げは 2026-08-14 に告知され、2026-08-16 に追随した（ADR-168）。

## 期待

- 対象: `plugin/schemas/system-map-gold-model-0.2.json`
- 検査: hash（内容の指紋）
- 指紋: sha256:92fa79c38b4db5e53ed1c02c73bdab948ccb41d6f7188531ee32972b5cb5a30c
- 期待する状態: 在ること。加えて、上流の同じ固定点の一枚と同じ内容であること。写しを手で
  書き換えないこと（上流が版を上げたときだけ、告知を受けて採り直す）。

## 動いたら何が壊れるか

この一枚が黙って書き換わると、`_model.py` が導く必須欄と語彙が動き、**リンタの門が上流の器と
食い違ったまま緑になる**。実際、写しを持っていた頃に同じ食い違いが起きた——Scenario の必須欄が
器では九つ、doctrine 側では五つで、描いた投影が上流の門（M-18）で落ちた（2026-08-14 の実測）。
指紋は中身の当否を保証せず、**変化に人の目が一度入ること**だけを保証する。上流の版が動いた
ことは、この指紋では検出できない（通信しないため）。それは `review_by` の見張りと #294 の
告知に委ねる。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
