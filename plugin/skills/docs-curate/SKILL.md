---
name: docs-curate
description: "Curates the document set one item at a time: inspects, then merges duplicate facts / demotes one step / or deletes, always checking reverse references first (zero current dependents before any demotion), re-rendering the projections (Overview, ICD-index, Context Map) from the model afterward, and shrinking the always-injected set whenever it exceeds the injection cap by consolidating facts and clearing expired review_by items. Use this skill when the user wants to \"clean up the docs\", \"curate\", \"remove orphans\", \"merge duplicate facts\", \"the context is too big / over the cap\", \"shrink the always-set\", \"deprecate this doc\", \"re-render the projections\", or runs the periodic \"docs cleanup / 定例整理\"."
---

# docs-curate

文書の集合を一片ずつ整える。点検し、重複する事実を統合する／一段だけ降格する／削除する。降格の前には必ず逆参照を確かめ（降格の前に現行の依存元がゼロ）、その後に投影（Overview・ICD 一覧・Context Map）をモデルから描き直し、常時注入する集合が上限を超えたときは、事実を一本化し期限切れの `review_by` 項目を片づけて縮める。主な要求は R8。

決定論の処理は `dep-graph.py`・`render-projection.py`・`term-extract.py` に委ねる。この技能は、何を残すかと、統合か降格か削除かの判断を持つ。

## 何に頼るか

- `dep-graph.py`（逆方向）— 逆参照の確認。降格の前に現行の依存元がゼロかを見る。
- `render-projection.py` — Overview・ICD 一覧をフロントマターから描き直す。
- `term-extract.py` — 用語辞書の候補（c-TF-IDF）。候補だけを出し、採否は人間が決める。
- DECIDED・WATCH 正本 — 期限切れ・置換した事実を一本化するため。`inject-contract.py` の上限と対になる。
- `docs-audit.py` の結果（孤児・逆孤児・`canonical_for` 衝突・語彙の酷似・投影ドリフト・`review_by` 超過）を作業一覧として使う。

## 手順（一片ずつ）

1. 点検。監査の作業一覧（孤児・逆孤児・語彙の近い対・`canonical_for` 衝突・`review_by` 超過・投影ドリフト）を取る。一片ずつ進める。壊す変更をまとめて行わない。
2. 各候補について、統合（重複する事実を一つの正本へ一本化）／降格（§3.8 の階段を一段下げる）／削除（孤児かつ証跡なしかつ再現できる一時文書だけ。§3.8 の段）を決める。
3. 降格の前に逆参照を確かめる（§3.8 の不変条件）。`dep-graph.py` を逆方向で呼び、現行の依存元がゼロを要する。依存が残るなら、同じ変更の中で先に依存元を後継へ付け替えてから降格する。削除安全ガードがこれを守る。迂回しない。
4. 降格は一段だけ（§3.8）。現行→廃止→アーカイブ→git だけ→抹消。`superseded_by` を記し、事実は DECIDED の対の記録に残し、本文を LLM から外す（never の文脈）。
5. 投影を描き直す（§3.9）。現行集合を変えたら、Overview と ICD 一覧を `render-projection.py` で決定論に描き直す。意味の投影（用語の定義、Context Map の結合の説明）はこの技能が助ける。リンタがドリフト（投影と現行集合の差）を検出する。
6. 上限を超えたら常時集合を縮める（§3.9）。`inject-contract.py` が常時集合の上限超過を報せたら、決定事実を一本化し、期限切れの `review_by` 項目を片づけて縮める。何を残すかは人間の判断である（§7）。
7. 降格はすべて後継 id とともに記録し、後から引けるようにする（§3.8）。

## 段差ごとの劣化

Level 2 の縮小設定では `dep-graph.py` と `docs-audit.py` が無い。逆参照の確認と監査の作業一覧が要るため、この技能は Level 3 以上を要する。設定が足りないときは、欠ける機能と要る Level を述べ、誤って動かさない。

## 参照

詳細は `references/` に分ける。

- `references/lifecycle-ladder.md` — §3.8 の五つの段、戻せる範囲、後から引ける記録。
- `references/reverse-ref-check.md` — `dep-graph.py` 逆方向の使い方、依存元の付け替え。
- `references/projections.md` — §3.9 の決定論の投影と意味の投影、ドリフトの検出。
- `references/shrink-always-set.md` — §3.9 の上限との対、一本化と期限切れの片づけ、何を残すかは人間に委ねること。

## 保証限界

R9 の予防／検出／委ねるの切り分けを宣言する。

- 予防: 降格の前に依存元ゼロという不変条件を予防するのは削除安全ガード（Hook）である。この技能は順序を整えて不変条件を守り、決して迂回しない。
- 検出: 監査の検出（孤児・逆孤児・ドリフト・期限切れ・語彙の近い対）を受け取る。
- 委ねる: 意味の重複か矛盾かの最終判断は §7 の限界である。常時集合を縮めるとき何を残すかも人間に委ねる（§7。何を残すかの最終判断は人間に依る）。`canonical_for` の付与、`term-extract.py` の候補からの用語の採用も人間に委ねる。
