---
id: EXT-004
title: 継続的結合の定義（.github/workflows/checks.yml）への依存
type: EXT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [.github/workflows/checks.yml]
review_by: 2026-10-26
llm_context: task
---

# 継続的結合の定義（.github/workflows/checks.yml）への依存

統治木の外への依存を登録するアンカーである(ADR-026)。中身は写さない。

## 何に依存しているか

監査の周期の二本足のうち一本(`CI`)は、`.github/workflows/checks.yml` がテスト・全件監査(`--fail-on error`)・投影ドリフト・ルート文書の用語点検・辞書シードの退行検査を回すことに依存する。もう一本(SessionEnd)はセッションの正常終了に依存するため不安定であり、`CI` が唯一のセッション非依存の足である。

## 期待

- 対象: `.github/workflows/checks.yml`
- 検査: exists(存在)
- 期待する状態: 在ること。push(main)と pull_request で走ること。Level の段差に依らず全件監査すること(§4.4)

## 動いたら何が壊れるか

消える・骨抜きになると、マージ前の全件検証が失われ、監査は SessionEnd(不安定)だけになる。検出は本アンカーの存在検査と、`CI` の実行履歴(外部の正本)に委ねる。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
