---
id: EXT-002
title: 自己適用の設定（.claude/settings.json のマーケットプレイス登録）への依存
type: EXT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [.claude/settings.json]
review_by: 2026-10-26
llm_context: task
---

# 自己適用の設定（.claude/settings.json のマーケットプレイス登録）への依存

統治木の外への依存を登録するアンカーである(ADR-026)。中身は写さない。

## 何に依存しているか

本リポジトリの自己適用(ドッグフード)は、二つに依存する。(1) `.claude/settings.json` のマーケットプレイス登録(絶対パス `/workspaces/doctrine`)がプラグインを解決できること。(2) `~/.claude` ボリューム側の導入状態(installed_plugins)にプラグインが入っていること。どちらが欠けても、注入・ガード・リンタ・監査の全フックが警報なしに沈黙する(2026-07-22 の改名と、ボリュームの作り直しで実際に起きた)。ボリューム側は devcontainer の postCreateCommand が自己導入で復元する。導入は複製(cache)であり、`plugin/` の変更後は `claude plugin update doctrine` で追随させる。

## 期待

- 対象: `.claude/settings.json`
- 検査: exists(存在。パスの中身の妥当性は R11 のハートビートが監査の鮮度で間接に見張る)
- 期待する状態: ファイルが在り、マーケットプレイスのパスがいまの作業フォルダを指す。作業フォルダを改名したら、パス修正→新セッション→契約注入の確認、を必ず行う(CONTRIBUTING)

## 動いたら何が壊れるか

自己適用の全フックが停止する。検出は本アンカーの存在検査(監査)と、監査の鮮度警告(SPEC-021)と、案内(CLAUDE.md)の生存期待の三重で行う。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
