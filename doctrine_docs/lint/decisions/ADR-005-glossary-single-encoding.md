---
id: ADR-005
title: 承認辞書を体系内で一度だけ符号化する
type: ADR
domain: lint
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_termcheck.py]
depends_on: [SPEC-008]
llm_context: task
---

# 承認辞書を体系内で一度だけ符号化する

## 背景

用語チェッカーは、承認語・禁止同義語・カルク表を必要とする。これらを複数のスクリプトに書き込むと、辞書を更新するたびに何箇所も直すことになり、どれが正しいか分からなくなって正本が崩れる[R6]。

## 却下した選択肢

- 各スクリプトに承認語表をハードコードする案。同じ辞書が二重に定義され、§1 の正本が一つに定まらなくなるため却下した[R8]。

## 決定

辞書は `load_glossary` が一箇所で読む。読む先は、GLOSSARY 正本（運用版）か、それが無ければ同梱テンプレートである。`_termcheck` 側にはハードコードしない。こうして §1 はこの体系の中で一度だけ符号化される。

## 帰結

辞書の更新は、GLOSSARY 正本の一箇所だけで済む。運用辞書が無い、または解析できないときは、同梱テンプレートの種子に切り替え、`GLOSSARY_PARSE_ERROR` を添える。

<!-- 入れない: 複数決定、現行仕様の全文 -->
