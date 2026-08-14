---
id: EXT-007
title: 意味モデルの器（`gold-model/schema.json`）の固定した写しへの依存
type: EXT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-14
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

`plugin/schemas/system-map-gold-model-0.1.json` は、doctrine-lens リポジトリの
`research/system-map/gold-model/schema.json` を、tag `system-map/phase-1-continue`
（commit `d920130f5113541ae4603d16e242064fc66ff588`。EXT-006 と同じ固定点）から採った写しで
ある。`_model.py`（SPEC-031）はこの一枚を読み、**手で並べた表を持たない。**

上流が版を上げるときの規約は #294 で合意した——欄の追加（既存の投影が通り続ける物）は版を
上げない。必須欄の追加・削除、語彙の縮小は `0.1` から名を上げ、doctrine-lens が #294 へ告知し、
doctrine が追随する（逆はしない。正本は一つ）。

## 期待

- 対象: `plugin/schemas/system-map-gold-model-0.1.json`
- 検査: hash（内容の指紋）
- 指紋: sha256:d927a69a549270b76b93826885bbd9342e581f0321d74cc10747d49344f02105
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
