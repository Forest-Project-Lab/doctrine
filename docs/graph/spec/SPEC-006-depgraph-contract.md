---
id: SPEC-006
title: 依存グラフの契約（forward/reverse/classify/reverse-orphans）
type: SPEC
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/_depgraph.py]
depends_on: [REQ-002, REQ-003, ICD-001]
llm_context: task
---

# 依存グラフの契約（forward/reverse/classify/reverse-orphans）

`_depgraph.py`（グラフを組み立てるエンジン）と `dep-graph.py`（問い合わせ用の CLI）が外部に公開する契約を定める。フロントマター（文書の先頭に置く YAML 形式のメタデータ）の解析と型の解決は、ICD-001（model）に依存する。[R3][R4][R7]

## 入出力

入力は docs ルート配下のすべての `.md` ファイルである。`build_graph(root)` が各ファイルの `id`・`type`・`domain`・`status`・`depends_on`・`impacts`・`canonical_for` を読み、有向グラフを組み立てる。問い合わせの戻り値は次の通りで、いずれも整列済みであり、同じ入力には同じ結果を返す。

- `forward_impacts(id)` → impacts 端の推移閉包（id 自身を含めない）。[R4]
- `reverse_dependents(id, current_only, transitive)` / `reverse_current_dependents(id)` → depends_on で id を指すノード集合。[R3]
- `resolve(id)` → `{path, domain, type, status}` か None。
- `classify_edges()` → `Edge{src, dst, field, kind}` の整列リスト。
- `reverse_orphans()` → `{req_without_spec, spec_without_test}`。

## 制約

- 標準ライブラリだけで実装する。pip も通信も使わない。
- 依存（depends_on）と影響（impacts）は別々の端として保持し、混ぜない。前向き影響集合は impacts 端から、逆依存・逆孤児・越境の判定は depends_on 端から出す。
- `cross_domain_violation` は depends_on 端だけに付ける。越境した impacts 端は `cross_domain_impact`（助言）に分類する。[R7]
- ドメインはフロントマターの domain から引く。id だけからドメインは決まらないので、`resolve` が解決を担う。
- 逆孤児の対象は現行（current/accepted）の文書だけである。たどるリンクは depends_on に限る。
- すべての走査は、訪問済みの集合を持って循環で止まるようにし、無限ループに陥らない。

## エラー時挙動

- フロントマターの無いファイルや id を持たないファイルは、ノードにせず `parse_warnings` に記録する。
- 同じ id が重複したときは、パスを整列した順で後に来たものを採り、両方を `dup_ids` に記録する。
- depends_on / impacts の宛先が索引に無い id を指していたら、その端を `dangling` に分類する。ここでは拒否せず、リンク切れかどうかの判定は監査に委ねる。
- CLI の終了コードは、問い合わせが成立すれば所見の有無にかかわらず 0、使い方を誤れば 2、ルートが見つからなければ 3 とする。これは問い合わせのための CLI であって、違反を止めるゲートではない。

## 受入基準

TEST-006 で確認する。受入シナリオの識別子（TC：以下に挙げる番号）ごとに、次のすべてに合格すること。前向き影響集合（TC-113..116）、逆依存を現行文書のみに絞る挙動（TC-078・TC-090）、端の分類（intra_domain / cross_domain_icd / cross_domain_violation / dangling、TC-069..072・TC-117・TC-123・TC-083）、逆孤児を二種類に分ける検査（TC-093..095）。
