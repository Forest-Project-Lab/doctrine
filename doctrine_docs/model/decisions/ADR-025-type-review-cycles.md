---
id: ADR-025
title: 型ごとの既定点検周期で全現行文書に実効期限を張る
type: ADR
domain: model
status: accepted
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [全体批判レビュー 2026-07-26]
depends_on: [SPEC-001]
---

# 型ごとの既定点検周期で全現行文書に実効期限を張る

## 背景

`review_by` が必須なのは DECIDED・WATCH だけで、体系の現行文書の大半(実測で 100 件中 95 件)は老化の信号を一つも持たなかった。陳腐化の検知面が狭すぎ、利用者が気にして手で頼まない限り古びが見つからない。全文書へ `review_by` を一斉に書かせる案は、導入の摩擦が大きく最小性にも反する。

## 却下した選択肢

- 全型で `review_by` を必須にする: 全文書のフロントマター改修を強いる。導入の壁になる。
- `updated` の古さだけで一律に警告する: 型の性質(投影・不変の決定・一時物)を無視し、擬陽性で警報の信頼を摩耗させる。
- 何もしない: 陳腐化検知が DECIDED・WATCH と draft 放置に閉じたままになる。

## 決定

登録簿(`plugin/scripts/_registry.py` の `TYPE_REVIEW_CYCLE_DAYS`)に型ごとの既定点検周期(日)を一度だけ定義する。明示の `review_by` を持たない現行文書の実効期限は `updated` + 既定周期とし、超過を監査の `stale_current` 検査が warn で挙げる。明示の `review_by` は常に既定より優先する。投影・ADR・DECIDED・WATCH・CHANGE・IMPACT・RESEARCH・ARCHIVE は周期の対象外とする(それぞれ描画物・不変・明示期限必須・一時物・draft 検査・不変のため)。

## 帰結

- 全現行文書が、フロントマターの一斉改修なしに、その日から老化の信号を持つ。
- 超過の受け皿は SessionStart の注入の促し(doc-review・docs-curate 名指し)と `gov-heartbeat.py` の督促が担う。
- 周期の値は運用で調整してよいが、変更は本 ADR を置換して行う。
