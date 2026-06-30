# 段階導入の対応表（§4.4）

体系の重さを規模に合わせる。全部を最初から置かない。痛みが出た所だけ足す。これは体系自身の最小性である。`[R8]`

## Level 2（縮小構成・小規模）

- 必須キーだけ（§3.4）。
- 型は `ICD`・`REQ`・`SPEC`・`ADR`・`DECIDED`・`OVERVIEW`（投影）に絞る。`DECIDED` は `review_by` を持つ。
- スクリプトは `_frontmatter.py`・`docs-linter.py`・`policy-guard.py`・`inject-contract.py` だけ。
- `scaffold.py` はこの縮小構成を置く。
- 監査（`docs-audit.py`）と依存グラフ（`dep-graph.py`）は無い。`change-impact` と `docs-curate`、`review_by` 超過の点検はこの Level では使えない。スキルは欠けた能力と必要な Level を述べて、止まらずに済ませる。

## Level 3（中規模）

- `depends_on`・`impacts` を加える。
- `dep-graph.py`・`change-impact`・`docs-audit.py` を足す。
- `review_by` 超過の点検はここから入る。

## Level 4（大規模）

- `canonical_for` と全件監査・投影一式・ドメイン連携を加える。

## 段差とフロントマター

段差はフロントマターの Level に対応する（§3.4）。上位へ上げるのは、その情報が要るとわかってからにする。`docs/_system/.docs-level` に効いている段差を一行で記す（`level: N`）。`scaffold.py` がべき等に書く。リンタと `doc-author` がこれを読み、効いている段差を知る。
