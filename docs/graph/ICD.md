---
id: ICD-002
title: graph のインターフェース（依存グラフ問い合わせ契約）
type: ICD
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_depgraph.py]
canonical_for: [dependency-graph-api]
llm_context: task
---

# graph ICD

## 公開する用語

- 依存（depends_on）: ある文書が他文書を前提とする関係。
- 参照: 文書から別文書への指し示し。依存とは限らない。
- 孤児: どの現行文書からも依存されない文書。
- 逆孤児: あるべき文書の不在（対応する仕様を持たない要求、対応するテストを持たない受入基準）。
- 投影: モデルから描画した派生表示。本ドメインが返すのは投影そのものではなく、投影を描くための素材である。

## 正本である事実

本ドメインは `dependency-graph-api` の正本である。docs 配下の全文書から組み立てた有向グラフに対し、どう問い合わせられるかをここで唯一定める。

## データ契約

他ドメイン（guard・lint・audit・packaging）が依存してよい問い合わせは次の通り。戻り値は整列済みで、同じ入力には同じ結果を返す。所見が一つでも見つかったときも、拒否や警告は返さず結果を返すだけにとどめる（検出に徹し、判定はしない）。[R3][R4][R7]

- `forward_impacts(id)`: impacts 端をたどった推移閉包を返す（id 自身は含めない）。変更耐性が使う影響集合がこれである。[R4]
- `reverse_dependents(id, current_only=False, transitive=False)`: depends_on で id を指すノードをすべて返す。`reverse_current_dependents(id)` は `current_only=True` を呼びやすくした短縮形で、削除安全の判定が使う。[R3]
- `resolve(id)`: その id の `{path, domain, type, status}` を返す。見つからなければ None を返す。ガード・リンタ・監査は、id からドメイン・型・位置づけを引くときこれを使う。
- `classify_edges()`: すべての端を `kind`（intra_domain / cross_domain_icd / cross_domain_violation / cross_domain_impact / dangling）に分類して返す。`cross_domain_violation` が付くのは depends_on 端だけである。[R7]
- `reverse_orphans()`: `{req_without_spec, spec_without_test}` を返す（対象は現行文書のみ）。
- CLI `dep-graph.py` の終了コード: 問い合わせが成立すれば、所見の有無にかかわらず 0。使い方を誤れば 2、ルートが見つからなければ 3。

## 依存してよい入口

他ドメインが depends_on できるのは、この文書（ICD）だけである。`_depgraph.py` の内部や CLI の実装を直接 depends_on してはならない。
