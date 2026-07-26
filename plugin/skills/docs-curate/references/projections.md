# 投影の描き直し（§3.9）

投影はモデルから描いた派生表示である。手で保守しない。現行集合を変えたら描き直す。

## 決定論の投影

Overview と ICD 一覧は、フロントマターから決定論に描ける。`render-projection.py` が描き直す。壁時計を使わず、同じ入力からは同じ結果を返す。`updated` は出所の `updated` の最大値とする。

## 意味の投影

用語の定義や Context Map の結合の説明は、機械だけでは描けない。この技能が助ける。意味の判断は人間に委ねる部分が残る。

## Context Map の印（手で書いてよい境界）

Context Map は `<!-- BEGIN PROJECTION:context-map-skeleton -->` と `<!-- END PROJECTION:context-map-skeleton -->` の印を持つ。印の内側の骨格（ドメインの一覧・ドメイン越えの依存の端）だけを機械が描き、印の外側の散文（結合の要点の説明）は手で書いて保たれる。印の内側を手で触ると照合が落ちる。結合の説明を書くときは、必ず印の外側に書く。

## ドリフトの検出

投影と現行集合の差をドリフトと呼ぶ。`${CLAUDE_PLUGIN_ROOT}/scripts/render-projection.py all --check --docs-root <統治木>` がドリフトを検出し、差があれば非ゼロで終える（モードの指定は必須。`all` のほかに `overview`・`icd-index`・`context-map-skeleton` を単体でも指せる）。監査も投影ドリフトを一覧化する。ドリフトが出たら `--check` を外して描き直す。
