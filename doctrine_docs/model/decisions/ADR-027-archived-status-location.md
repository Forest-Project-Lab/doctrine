---
id: ADR-027
title: status archived の文書は型に依らず倉庫に置き、状態でも不変にする
type: ADR
domain: model
status: accepted
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [全体批判レビュー 2026-07-26]
depends_on: [SPEC-001]
---

# status archived の文書は型に依らず倉庫に置き、状態でも不変にする

## 背景

§3.2 は型で置き場所を決め、§3.8 はアーカイブで本文を `<domain>/archive/` へ移すと定める。この二つの衝突が未解決のまま、唯一の `status: archived` 文書(RESEARCH-001)は `research/` に居座り、パス判定だけの不変ガードの保護外で編集自由になり、さらに孤児検査の削除候補にも昇格しうる露出があった。アーカイブの不変条件が、状態と場所のどちらにも機械で結ばれていなかった。

## 却下した選択肢

- 型の置き場所を常に優先する: 「倉庫へ退避した状態」という語の意味(用語辞書)と §3.8 の階段が崩れる。
- 場所だけで守り続ける: 状態だけ archived の文書が編集自由のまま残る(実際に起きた)。
- 孤児検査の対象に archived を残す: 倉庫の証跡が削除候補へ昇格する。

## 決定

三つを一体で定める。(1) `status: archived` の文書は、型に依らず `<domain>/archive/` に置く(登録簿の `ARCHIVED_LOCATION`。リンタの `ARCHIVED_LOCATION_MISMATCH` と監査の `archive_integrity` が整合を点検する)。(2) 不変性ガードは、パスに加えて `status: archived` でも編集を拒否する(現行から archived への遷移の書き込み自体は対象外。それは降格の操作であり、削除安全ガードが逆参照ゼロを守る)。(3) 孤児検査は archived を対象外とする。RESEARCH の証跡アーカイブは後継を持たないことがあるため、`superseded_by` の不在は RESEARCH 以外にだけ助言する。

## 帰結

- アーカイブの語の意味・置き場所・不変性・削除候補からの除外が、状態一つに機械で結ばれる。
- 既存の RESEARCH-001 は `model/archive/` へ移す。
- アーカイブする操作の順序は変わらない(逆参照ゼロ→status 変更→倉庫へ移動)。
