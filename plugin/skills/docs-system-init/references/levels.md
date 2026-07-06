# 段階導入の対応表（§4.4）

体系の重さを規模に合わせる。全部を最初から置かない。痛みが出た所だけ足す。これは体系自身の最小性である。`[R8]`

## Level 2（縮小構成・小規模）

- 必須キーだけ（§3.4）。
- 型は `ICD`・`REQ`・`SPEC`・`ADR`・`DECIDED`・`OVERVIEW`（投影）に絞る。`DECIDED` は `review_by` を持つ。
- 動くスクリプトは `docs-linter.py`・`policy-guard.py`（予防のみ）・`inject-contract.py` と、それらが引く共有コア（`_frontmatter.py`・`_registry.py`・`_termcheck.py`・`_depgraph.py`）。
- `scaffold.py` はこの縮小構成を置く（`.docs-level` に `level: 2` を書く）。
- 縮小は自主停止で効く（ADR-019）: 全構成の Hook のまま、SessionEnd の監査・起動後ガード（block）・レビューのナッジが `.docs-level` を読んで静かに済ませる。`change-impact` と `docs-curate`、`review_by` 超過の点検はこの Level では使えない。スキルは欠けた能力と必要な Level を述べて、止まらずに済ませる。

## Level 3（中規模）

- `depends_on`・`impacts` を加える。
- `dep-graph.py`・`change-impact`・`docs-audit.py` を足す。
- `review_by` 超過の点検はここから入る。

## Level 4（大規模）

- `canonical_for` と全件監査・投影一式・ドメイン連携を加える。

## 段差とフロントマター

段差はフロントマターの Level に対応する（§3.4）。上位へ上げるのは、その情報が要るとわかってからにする。`doctrine_docs/_system/.docs-level` に効いている段差を一行で記す（`level: N`）。`scaffold.py` がべき等に書く。SessionEnd の監査・起動後ガード・レビューのナッジが登録簿の `docs_level(docs_root)` でこれを読み、Level 2 では自主停止する（ADR-019）。目印が無い・不正なときは全構成（Level 4）として扱う。段を変えたら、新しいセッションから効く（Hook 設定はセッション開始時に固定されるため）。
