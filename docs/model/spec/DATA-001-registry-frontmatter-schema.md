---
id: DATA-001
title: 登録簿とフロントマターのスキーマ
type: DATA
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [REQ-001]
llm_context: task
---

# 登録簿とフロントマターのスキーマ

`_registry.py` と `_frontmatter.py` が保持する純データを、データモデルとして記す。いずれもコード内に置く純データであり、外部のデータストアは持たない。[R2][R3][R6]

## エンティティ

型登録簿は 18 型ぶんの行を持つ。各行は次の属性を持つ。

- 型コード: ICD, OVERVIEW, GLOSSARY, CTXMAP, DECIDED, NONGOAL, WATCH, REQ, SPEC, DATA, API, ADR, CHANGE, IMPACT, IMPL, TEST, RESEARCH, ARCHIVE（登録簿の順）。
- 既定 `status`: 多くは current。ADR は accepted、CHANGE は proposed、RESEARCH は draft、ARCHIVE は archived。
- 既定 `llm_context`: OVERVIEW・GLOSSARY・DECIDED・NONGOAL・WATCH は always、RESEARCH・ARCHIVE は never、ほかは task。
- 置き場所: 型ごとに許可するディレクトリ。WATCH だけは二箇所（`_system/` と `<domain>/test/`）を許す。

`status` 統制語彙は 8 値（proposed, accepted, current, deprecated, superseded, archived, open, draft）。CURRENT_STATUSES は {current, accepted}。型ごとの許可表は次のとおり。ADR は {proposed, accepted, superseded, deprecated}。ほかの型は accepted を除く 6 値とし、RESEARCH だけはこれに draft を加える。

フロントマター・スキーマは次のとおり。必須 8 キーは REQUIRED_KEYS_L2=(`id`, title, `type`, `domain`, `status`, `owner`, `updated`, `sources`)。created は必須としない。DECIDED と WATCH は `review_by` も必須とする。Level 3 キーは (`depends_on`, impacts, `review_by`)、Level 4 キーは (`canonical_for`)。`llm_context` の値は (always, task, never)。

`_system` のファイル名は固定する。投影ファイルは (overview.md, icd-index.md, context-map.md)。正本ファイルは (glossary.md, decided-facts.md, non-goals.md, overview.md, watchlist.md)。これらは id をファイル名に埋め込まない。

## 保存方針

すべてコード内の定数（タプル・辞書・frozenset）として保持する。読み出しは純関数で行う。呼び出し側へは複製を返し、登録簿そのものを書き換えられないようにする。外部のデータストア、通信、pip への依存は持たない。

## 保持期間

恒久に保持する。規則を変えるときは ADR で決め、本データと用語辞書の正本を更新して反映する。古い値は履歴として ADR に残す。

<!-- 入れない: 処理ロジック -->
