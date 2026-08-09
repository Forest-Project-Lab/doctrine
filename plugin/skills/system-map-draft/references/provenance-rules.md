# 出所の規則

全ての値の `provenance` は Source の配列（最低 1 件）である。`map-draft-check.py` が出所の実在を照合するので、書けるのは実際に読んだ場所だけである。

## Source の形

- `source` — URL、またはリポジトリ接頭付きのパス（例 `doctrine: doctrine_docs/graph/ICD.md@8cd29bd`）。パス単独は書かない。似た名の文書が別のリポジトリに在るとき、どちらを読んだかが決まらなくなる。
- `locator` — 節・見出し・行など、確認した箇所。
- `checked_at` — 実際に確認した日（`ISO 8601`）。起草した日をまとめて書くのではなく、その値を確かめた日を書く。
- `verdict` — `present`（記載があった）か `silent`（確認したが記載が無かった）。

```json
{ "source": "doctrine: doctrine_docs/graph/ICD.md@8cd29bd",
  "locator": "データ契約(resolve の行)", "checked_at": "2026-08-03", "verdict": "present" }
```

## CLI 由来の事実

宣言済み CLI から取った事実は、`source` にスクリプトのパスと rev（例 `doctrine: plugin/scripts/trace-index.py@<rev>`）を、`locator` に標準の返り形の中の場所（例 「trace-index/1 の ranges」「dep-graph --classify-edges の edges」）を書く。実行そのものが確認であり、`checked_at` は実行した日である。

## 負の出所（M-11）

`unknown` の contract には、`verdict: silent` の出所を最低 1 件付ける — どこを見て・いつ・記載が無かったか。

```json
{ "source": "doctrine-lens: doctrine_docs/_system/REQ-000-what-this-product-solves.md",
  "locator": "全文(性能への言及なし)", "checked_at": "2026-08-04", "verdict": "silent" }
```

未調査と沈黙を混同しない。まだ見ていない場所については出所そのものを書かない — 出所の不在が「未調査」を表し、`silent` は「確認したが記載が無かった」を表す。

## 書いてはならないもの

- 読んでいない場所。実在しないパス・節。`map-draft-check.py` が実在を照合して落とす。
- これから読むつもりの場所。読んでから書く。
