---
id: ADR-045
title: 本文の要求タグは自己適用の約束であり、追跡の正路は depends_on の REQ である
type: ADR
domain: graph
status: accepted
owner: doctrine-maintainers
created: 2026-07-27
updated: 2026-07-27
sources: [plugin/scripts/docs-linter.py]
depends_on: [REQ-003]
llm_context: task
---

# 本文の要求タグは自己適用の約束であり、追跡の正路は depends_on の REQ である

## 背景

追跡性の点検（MISSING_TRACE、リンタ）は、SPEC・IMPL・TEST の本文に `[R番号]` があれば追跡ありと判定する。しかし `[R番号]` の実在は検査していない（#87）。導入先に R1 という要求が定義されていなくても `[R1]` と書けば点検を通る。一方、`collect-context`（llm-context-pack）の被覆計算は、要求＝REQ 文書の id であり、`depends_on` の閉包でのみ被覆と認める。本文タグは数えない。

ここには二つの要求番号の体系が同居する。doctrine の自己適用では、上位設計書 `spec/doctrine.ja.md` の §2 が R1〜R12 を定め、本文に `[R1]` の形で引く（この設計書は EXT-003 が外部アンカーとして登録している）。一方、統治木の中では REQ-002 等の REQ 文書が追跡の要求を定め、`depends_on` で引く。二つは別の名前空間である。

## 却下した選択肢

- **`[R番号]` タグの実在を監査で検査する**: 検査するには R1〜R12 の正本一覧が要る。それは上位設計書 §2 の中にあり、統治木の中に機械可読の形で無い。監査を上位設計書の書式に結び付けると壊れやすくなる（上位が版を上げるたびに監査が追随する結合を生む）。
- **MISSING_TRACE を depends_on だけに寄せる**: doctrine 自己適用の `[R番号]` 参照を一斉に不合格にする。既存の運用を壊す。

## 決定

- 本文の `[R番号]` タグは、doctrine 自己適用の約束とする。上位設計書 §2 の R1〜R12 を引く。実在は機械では検査しない（正本一覧が統治木の外にあるため。既知の限界）。
- 追跡の正路は、REQ 文書への `depends_on` とする。導入先では、SPEC・IMPL・TEST は REQ の id を `depends_on` に載せて追跡する。被覆計算（llm-context-pack）はこの正路だけを数える。
- MISSING_TRACE は、本文の `[R番号]` か `depends_on` の REQ のどちらかがあれば通す（従来どおり）。誤り文言は、タグの置き場所（本文）と正路（depends_on の REQ）を示す（実装済み。#86）。

## 帰結

- 二つの名前空間の役割が明文化される。自己適用は `[R番号]`、導入先の追跡は REQ の `depends_on`。
- 既知の限界: 実在しない `[R番号]` が MISSING_TRACE を通る。これは、要求一覧の正本を統治木の外（上位設計書）に置く自己適用の構造に由来し、受け入れる。導入先が確実な追跡を要るなら REQ の `depends_on` を使う（そちらは dead link 検査が実在を保証する）。
