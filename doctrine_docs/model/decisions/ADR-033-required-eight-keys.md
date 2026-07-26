---
id: ADR-033
title: 必須キーはちょうど 8 個とする(追認)
type: ADR
domain: model
status: accepted
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [spec/doctrine.ja.md §3.4, DATA-001]
depends_on: [SPEC-001]
---

# 必須キーはちょうど 8 個とする(追認)

## 背景

必須キー(id・title・type・domain・status・owner・updated・sources。`created` は含めない)は DATA-001 と登録簿に実装され、決定事実(DECIDED-001 事実3)にも載る運用済みの決定だが、根拠として挙げられた ADR-001 は構造規則の単一正本化を決めた ADR であり、キーの数は決めていなかった。

## 却下した選択肢

- `created` も必須にする: 現行性の点検に使うのは `updated` であり、`created` の強制は書き手の負担だけを増やす。
- 必須を減らす: 出所(sources)と責任(owner)と現行性(updated)の追跡が壊れる。

## 決定

Level 2 以降の必須キーは、ちょうど次の 8 個とする: `id`・`title`・`type`・`domain`・`status`・`owner`・`updated`・`sources`。DECIDED・WATCH はこれに加えて `review_by` を必須とする。`created` はテンプレートに含めるが必須にしない。

## 帰結

- DECIDED-001 事実3 の根拠を本 ADR に張り替える。
- 必須キーを変える変更は本 ADR の置換を要する。
