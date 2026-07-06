---
id: ADR-022
title: 統治木の既定名を doctrine_docs にし、素の docs は他所の土地として触れない
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-07-06
updated: 2026-07-06
sources: [plugin/scripts/_registry.py]
depends_on: [SPEC-019, ICD-001]
llm_context: task
---

# 統治木の既定名を doctrine_docs にし、素の docs は他所の土地として触れない

## 背景

統治木の置き場所は `doctrine_docs/` に固定されていた。しかし導入先のプロジェクトが成熟した独自の `doctrine_docs/` を既に持つ場合、doctrine がそこを統治木と誤認して害を及ぼす経路が実在した。scaffold が `doctrine_docs/_system` を書き込んで入植する。全件監査が相手の全 .md を未登録文書の error として挙げる。相手の `doctrine_docs/<名>/archive/` 配下への編集を不変ガードが誤って拒否する。リンタが編集のたびに「フロントマターが無い」と助言し続ける。いずれも相手の運用への干渉であり、導入の安全を損なう。[R8][R9]

## 却下した選択肢

- `doctrine_docs/` のまま、干渉する検査を個別に弱める。弱めた分だけ本来の統治も弱まり、どの検査を弱めたかの一覧が増え続ける。
- 統治木の名前を設定ファイルで自由にする。解決の分岐が増え、フック・スクリプト・文書のすべてが「名前は設定次第」という条件文を抱える。既定の一つの名前で足りる。
- 既存利用者に `doctrine_docs/` から `doctrine_docs/` への移行を強制する。動いている体系を壊す。

## 決定

統治木の既定名を `doctrine_docs/` にする。scaffold は `doctrine_docs/_system` を置く。統治木の自動解決は登録簿に一度だけ実装し（`DOCS_DIR_NAMES`・`locate_docs_root`・`walkup_docs_root`）、優先順は次のとおり。①明示の引数（`--root`・`--docs-root`）は常に最優先で、名前を問わず統治木として扱う。②`doctrine_docs/` が在ればそれ。③`doctrine_docs/` は `doctrine_docs/_system` が在る場合だけ統治木と認める（doctrine が初期化した印。既存利用者の後方互換）。④どちらも無ければ統治木なし（ブートストラップ）。`_system` を持たない素の `doctrine_docs/` は他所の土地であり、scaffold・監査・ガード・注入のいずれも統治木として触れない。既に `doctrine_docs/_system` を持つプロジェクトでは、scaffold は `doctrine_docs/` を新設せず `doctrine_docs/` 側を使い続ける（統治木を二つにしない）。

## 帰結

成熟した独自の `doctrine_docs/` を持つプロジェクトに導入しても、doctrine は相手の木に入らない。既存の `doctrine_docs/_system` 体系はそのまま動く。統治木の名前が `doctrine_docs` になり、見た目からも doctrine の管理下だと分かる。本リポジトリ自身の統治木も `doctrine_docs/` へ移す（新既定の自己適用）。保証限界: 明示の引数で素の `doctrine_docs/` を指した場合は利用者の判断を尊重して統治木として扱う。`doctrine_docs/` という名前の独自ディレクトリを持つプロジェクトとの衝突は想定しない（衝突したら明示の引数で逃がす）。

<!-- 入れない: 複数決定、現行仕様の全文 -->
