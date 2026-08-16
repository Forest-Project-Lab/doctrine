---
id: EXT-008
title: M 層の不変条件の機械可読の一覧（requirements 口）への依存
type: EXT
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294"]
review_by: 2026-09-15
llm_context: task
---

# M 層の不変条件の機械可読の一覧（requirements 口）への依存

統治木の外への依存を登録するアンカーである（ADR-026）。中身は写さない。器（JSON Schema）が
書けない M 層の不変条件（要素の到達など）の機械可読の一覧は、doctrine-lens 側の
requirements 口が持つ。doctrine はこれを写さず参照する（ADR-165 決定6 の切り替え。
ADR-168 決定3）。

## 何に依存しているか

doctrine-lens リポジトリの `research/system-map/gold-model/validate.mjs` を
`--requirements --json` で呼ぶと、`system-map/requirements/1` の形で一覧が返る。
一覧は新しい事実を持たず、lens 側の正本（`schema.json`・`registry.json`・
`negatives.json`）から導かれる。#294 第4信（2026-08-15）で告知され、当時の実測は
lens 側 main の commit `d3888382bf11b561dcbb853cbc3dac735b1bc2a8`（模型を判ずる検査器
18・負例で裏づけ済み 5・裏づけ無し 13）。

一覧の `container.sha256` は、参照した器の指紋を返す。doctrine が同梱する一枚
（EXT-007）の指紋と突き合わせれば、貼り直しの済みと参照先の器のずれを機械で確かめられる。

## 期待

- 対象: `https://github.com/Forest-Project-Lab/doctrine-lens` の
  `research/system-map/gold-model/validate.mjs --requirements --json`
- 検査: review_by のみ（対象が外部リポジトリのため exists・hash の機械検査はできない。
  通信しない）
- 期待する状態: 口が `system-map/requirements/1` を返し続けること。`proven` の旗
  （負例で裏づけたか）が実体と一致し続けること（lens 側の門
  `meta:requirements-complete` が見張る）。`container.sha256` が EXT-007 の指紋と
  一致すること（一致しなければ、どちらかの版が動いている）。

## 動いたら何が壊れるか

口が消える・形が変わると、第四門が何を検めるかを機械で読む道が失われ、M 層の不変条件は
散文（#294 のやり取り）からしか辿れなくなる。写しは持たないので、doctrine 側の門は
壊れない——失われるのは参照だけである。検出は本アンカーの `review_by`（期限の見張り）と
#294 上の告知に委ねる。`proven: false` の 13 件は「述べているが確かめていない」と上流が
明示しており、参照する側もこの区別を保つ（ADR-168 帰結）。

<!-- 入れない: 外部の正本の中身の写し(不変条件の一覧の転記)。要点の転記と出所の参照だけを許す -->
