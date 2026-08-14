# 検収の門

下書きは、四つの門を順に通ってはじめて検収に達する。門の側は直さない — 落ちたら下書き（.md）を直す。**JSON は描き直すものであり、手で直さない。**

## 第一門: 本文の構造（リンタ）

```sh
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/docs-linter.py <MODEL の .md の道>
```

`MODEL_*` の所見（必須欄・語彙・id の一意・見出しと id の一致・文書の中の参照の実在・自己ループの理由・確定の同値）が無くなるまで直す。規則の正本は SPEC-031。

## 第二門: 描画（.md から JSON へ）

```sh
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render-projection.py model --id <MODEL-連番> --docs-root <統治木>
```

正本の .md の隣へ同じ名の `.json` が出る。**所見の在る模型は描かれない**（第一門を先に通す）。

## 第三門: 出所の機械検証

```sh
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/map-draft-check.py --model <描いた .json> --repo <対象リポジトリの root> --today <日付>
```

終了コード 0 で通過。捏造出所（実在しないパス・節）と形の崩れを落とす。所見を読み、**.md の側の**出所を直して第二門から回し直す。

## 第四門: M 層の不変条件

lens 側の `gold-model/validate.mjs` を、無修正の複製で回す。

- 複製の固定点は EXT-006 の tag `system-map/phase-1-continue`（コミット `d920130f5113541ae4603d16e242064fc66ff588`）。
- 取得はネットワークを伴う。利用者の同意の上で行う — 体系のスクリプト自身は通信しない（確定事実7: すべてのスクリプトは標準ライブラリだけで動き、pip にも通信にも依存しない）。

```sh
git clone --depth 1 --branch system-map/phase-1-continue https://github.com/Forest-Project-Lab/doctrine-lens <作業場所>
node <作業場所>/research/system-map/gold-model/validate.mjs <draft.json>
```

判定は `PASS` / `FAIL` / `SKIP` の三値で、終了コード 0（`FAIL` なし）で通過。`SKIP` は合格ではない（発火しない門を緑と呼ばない）。M-01〜M-16 の指摘が出たら下書きを直して再実行する。validator を書き換えて通すことは検収にならない。

## 報告

四つの門の判定（通過・不通過）・要素数・`unknown` の contract の数と負の出所の数・書き出した場所を報告に載せる。
