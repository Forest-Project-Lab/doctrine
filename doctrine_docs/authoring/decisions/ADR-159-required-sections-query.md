---
id: ADR-159
title: 必須節の名を CLI から問えるようにする — scaffold に list-sections の口を足す
type: ADR
domain: authoring
status: accepted
owner: doctrine-maintainers
created: 2026-08-13
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/212", "https://github.com/Forest-Project-Lab/doctrine/issues/294", plugin/scripts/scaffold.py]
depends_on: [SPEC-015, ICD-007]
llm_context: task
---

# 必須節の名を CLI から問えるようにする — scaffold に list-sections の口を足す

## 背景

型ごとの必須節の名の正本は登録簿（`_registry.REQUIRED_SECTIONS`。確定事実1）だが、
これを返す宣言済みの口が無い。外部の表示製品は「禁止一覧に必須節の名を入れない」という
自分の規範を機械で守る手段が無く、内部モジュールの直読みは読み口の規律に反し、写しは
上流が名を変えた日に黙って古びる（issue #212 第2信の依頼。#294 の受けと同波。権限は
ADR-151）。守れない穴は「まだその木に無い型」の節名で、最初の一件を書くまで誰も気づかない。

## 却下した選択肢

- **内部モジュール（`_registry`）の直読みを許す。** 外部が依存してよいのは ICD の外部条項が
  宣言した CLI の返す値だけ（確定事実13）。内部の形は契約ではない。
- **消費者側へ節名の表を写す。** 同じ事実の二重定義になり、上流の変更で黙って古びる。
  この穴こそが依頼の理由である。
- **dep-graph や docs-audit に載せる。** 節の規範は文書の作成（authoring）の関心であり、
  グラフにも監査にも属さない。既に登録簿を読んで文書を作る scaffold が最小の宿である。

## 決定

`scaffold.py` に問い合わせ `--list-sections [--type <型>] --json` を足し、ICD-007 の
外部条項として宣言する。

1. 返す値は `{"schema": "scaffold-sections/1", "sections": {<型>: [<節名>…]}, "generator": {…}}`。
   `--type` を与えればその型だけ、与えなければ必須節を持つ全型を返す。`generator` の意味は
   ADR-155 と同じ（この口は木を測らないので、木の版の鍵は持たない）。
2. 正本は登録簿のまま動かさない。この口は写しではなく、登録簿をその場で読む参照である。
3. 未知の型は使い方の誤り（終了コード 2）。問い合わせは足場を一切書かない（読みだけ）。

## 帰結

- 外部の消費者は、まだ自分の木に無い型の必須節の名も、上流の答えとして機械で引ける。
- scaffold は「置く」だけの道具から「規範を問える」道具になるが、書く既定の挙動は変えない。
- 保証限界: 返すのは節の**名**だけであり、節に何を書くべきかの規範は各型のテンプレートと
  技能の領分に残る。

<!-- 入れない: 節名の表の写し（登録簿が正本）、実装コード -->
