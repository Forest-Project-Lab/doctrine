---
id: SPEC-006
title: 依存グラフの契約（forward/reverse/classify/reverse-orphans）
type: SPEC
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-27
sources: [plugin/scripts/_depgraph.py]
depends_on: [REQ-002, REQ-003, ICD-001]
llm_context: task
---

# 依存グラフの契約（forward/reverse/classify/reverse-orphans）

`_depgraph.py`（グラフを組み立てるエンジン）と `dep-graph.py`（問い合わせ用の CLI）が外部に公開する契約を定める。フロントマター（文書の先頭に置く YAML 形式のメタデータ）の解析と型の解決は、ICD-001（model）に依存する。[R3][R4][R7]

## 入出力

入力は統治木のルート配下のすべての `.md` ファイルである。`build_graph(root)` が各ファイルの `id`・`type`・`domain`・`status`・`depends_on`・`impacts`・`canonical_for` を読み、有向グラフを組み立てる。問い合わせの戻り値は次の通りで、いずれも整列済みであり、同じ入力には同じ結果を返す。

- `forward_impacts(id)` → impacts 端の推移閉包（id 自身を含めない）。[R4]
- `reverse_dependents(id, current_only, transitive)` / `reverse_current_dependents(id)` → depends_on で id を指すノード集合。[R3]
- `resolve(id)` → `{path, domain, type, status}` か None。
- `classify_edges()` → `Edge{src, dst, field, kind, mirrored}` の整列リスト。`mirrored` は「反対向きの相手が居るか」（ADR-088）—— `A --depends_on--> B` に対して `B --impacts--> A` が在れば真、逆も同じ。**同じ事実を両端から書いたという意味であって、循環という意味ではない**（循環は `find_cycles` が返す。二つを混同しない）。`kind` とは別の軸なので別の欄に持つ（一つの端が同時に「越境違反」かつ「両端書き」でありうる）。読み手はこの印で二本を一本に畳める —— 畳み方の規則を読み手に発明させないためである（実測: 呼び手の木で辺の 28% が両端書きだった）。片方だけ書かれた端は偽であり、**咎めない**（両端に書く義務は無く、印は事実の報告に留まる）。
- `reverse_orphans()` → `{req_without_spec, spec_without_test}`。`req_without_spec` は、現行 `SPEC` が `depends_on` で指していない現行 `REQ` である。**ただし横断の棚（`_system/`）に在る要求は除く**（ADR-091）—— この体系では `_system` の正本（`DECIDED`・`NONGOAL`・`WATCH`）は本文で参照され、frontmatter の `depends_on` では指されない（実測: 一件も無い。`_system` に ICD が無いため、越境依存のガードがそもそも拒む）。製品の粒度の要求も同じ棚に在るので、辺で指されないことを欠陥として扱わない。**除いただけで緩めていない** —— ドメインの `REQ` は引き続き立つ。
- `find_cycles()` → `depends_on` 端の循環の整列リスト（各要素は id の整列 list。自己依存 A→A は `[A]`）。索引に無い端はたどらない。Tarjan の強連結成分でサイクル安全。[R3]（ADR-038）
- `to_json()` → `{root, nodes, edges, dup_ids, parse_warnings}`。**節点は隠さない**（ADR-087）。組み立てが節点へ入れた項をすべて返す。白名簿を持たない —— 以前は八項に絞っており、正本がどこにも無いまま組み立てと別々に手で保つ形になっていて、実際にずれた（組み立てが四項を足した後も白名簿は八項のままで、必須項の `title` は最初から集められてさえいなかった）。
  - 返る項: `id`・`title`・`path`・`type`・`domain`・`status`・`depends_on`・`impacts`・`canonical_for`・`superseded_by`・`updated`・`review_by`・`llm_context`・`subdomain`・`sources`・`reproducible`。組み立てが項を足せば、そのまま返る。
  - `subdomain` はドメインの**種類**（`core`・`supporting`・`generic`。語彙の正本は model の `SUBDOMAIN_KINDS`。ADR-092）。**未分類は空文字で返し、項を落とさない** —— 項が消えると読み手が「未分類」と「取れなかった」を見分けられない。**値の当否はここでは検めない**（リンタが検める）。語彙に無い値も黙って捨てず、そのまま運ぶ。既定は無く、型からも導かない。
  - `sources` も必須項である（確定事実3）。**題名と同じく集めていなかった**ので、宣言した道が実在するかを誰も検められなかった（ADR-097）。ADR-087 が名指した「必須項が集められてさえいない」欠陥の二件目である。一覧として返し、値でない要素は落とす。
  - スカラの項は、入れ物（一覧・写像）が来ても内部表記を漏らさず空文字にする。以前は `str()` を当てており、`title: [t]` が `"['t']"` として問い合わせに載った。**一項ではなく、スカラの項すべてが通る共有の補助の欠陥だった**（ADR-092）。
  - **唯一の例外**: `depends_on` と `impacts` は、生のフロントマターの値ではなく**索引の値**（解決済みの端）を返す。読み手にはこちらが有用である。
  - 組み立てと直列化の項が一致することは受入が凍らせる。正本を書いても、一致を機械が見ていなければまたずれる。

## 制約

- 標準ライブラリだけで実装する。pip も通信も使わない。
- 依存（depends_on）と影響（impacts）は別々の端として保持し、混ぜない。前向き影響集合は impacts 端から、逆依存・逆孤児・越境の判定は depends_on 端から出す。
- `cross_domain_violation` は depends_on 端だけに付ける。越境した impacts 端は `cross_domain_impact`（助言）に分類する。[R7]
- ドメインはフロントマターの domain から引く。id だけからドメインは決まらないので、`resolve` が解決を担う。
- 逆孤児の対象は現行（current/accepted）の文書だけである。たどるリンクは depends_on に限る。
- すべての走査は、訪問済みの集合を持って循環で止まるようにし、無限ループに陥らない。

## エラー時挙動

- フロントマターの無いファイルや id を持たないファイルは、ノードにせず `parse_warnings` に記録する。
- 同じ id が重複したときは、採用先を登録簿の `resolve_duplicate_id`（整列した順の最初。先勝ち。ADR-049）に問い、両方を `dup_ids` に記録する。自前の整列規則を持たない。注入・監査も同じ関数を呼ぶので、「どれが正本か」の答えは体系内で一つになる。
- depends_on / impacts の宛先が索引に無い id を指していたら、その端を `dangling` に分類する。ここでは拒否せず、リンク切れかどうかの判定は監査に委ねる。
- CLI の終了コードは、問い合わせが成立すれば所見の有無にかかわらず 0、使い方を誤れば 2、ルートが見つからなければ 3 とする。これは問い合わせのための CLI であって、違反を止めるゲートではない。

## 実装の指紋

対象は依存端の分類の正本。更新は `trace-index.py --id SPEC-006` が返す行を写す（ADR-061）。

- sha256:3d1b4d19a66ffdaafccd56c22f6e7f5ea98a1bf584daf126e9cec3739cc416cc

## 受入基準

TEST-006 で確認する。受入シナリオの識別子（TC：以下に挙げる番号）ごとに、次のすべてに合格すること。前向き影響集合（TC-113..116）、逆依存を現行文書のみに絞る挙動（TC-078・TC-090）、端の分類（intra_domain / cross_domain_icd / cross_domain_violation / dangling、TC-069..072・TC-117・TC-123・TC-083）、逆孤児を二種類に分ける検査（TC-093..095）。
