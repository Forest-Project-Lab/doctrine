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

- 複製の固定点は EXT-007 の tag `system-map/gold-model-0.2`（コミット `991b8a6e3e6870d9651279956a8f7a60292e47af`。ADR-168 決定4）。
- 取得はネットワークを伴う。利用者の同意の上で行う — 体系のスクリプト自身は通信しない（確定事実7: すべてのスクリプトは標準ライブラリだけで動き、pip にも通信にも依存しない）。

```sh
git clone --depth 1 --branch system-map/gold-model-0.2 https://github.com/Forest-Project-Lab/doctrine-lens <作業場所>
node <作業場所>/research/system-map/gold-model/validate.mjs <draft.json>
```

判定は `PASS` / `FAIL` / `SKIP` の三値で、終了コード 0（`FAIL` なし）で通過。`SKIP` は合格ではない（発火しない門を緑と呼ばない）。M 層の指摘が出たら下書きを直して再実行する。validator を書き換えて通すことは検収にならない。

第四門が何を検めるかの機械可読の一覧は、requirements 口が返す（EXT-008。ADR-168 決定3）。口は 0.2 の tag より後に入ったので、lens 側の main（実測 commit `d3888382bf11b561dcbb853cbc3dac735b1bc2a8` 以降）の複製で呼ぶ。

```sh
node <作業場所>/research/system-map/gold-model/validate.mjs --requirements --json
```

返る `container.sha256` が、同梱の一枚（`plugin/schemas/system-map-gold-model-0.2.json`）の指紋（EXT-007）と一致することを確かめる——一致しなければ、どちらかの版が動いており、貼り直し（追随）が要る。一覧の `proven: false` は「述べているが負例で確かめていない」の意であり、合格の証拠と読み違えない。

## 報告

四つの門の判定（通過・不通過）・要素数・`unknown` の contract の数と負の出所の数・書き出した場所を報告に載せる。
