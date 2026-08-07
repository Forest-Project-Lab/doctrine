# 検収の二門

下書きは、二つの門を両方通ってはじめて検収に達する。門の側は直さない — 落ちたら下書きを直す。

## 第一門: 出所の機械検証

```sh
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/map-draft-check.py --model <draft.json> --repo <対象リポジトリの root> --today <日付>
```

終了コード 0 で通過。捏造出所（実在しないパス・節）と形の崩れを落とす。所見を読み、下書きの出所を直して再実行する。

## 第二門: M 層の不変条件

lens 側の `gold-model/validate.mjs` を、無修正の複製で回す。

- 複製の固定点は EXT-006 の tag `system-map/phase-1-continue`（コミット `d920130f5113541ae4603d16e242064fc66ff588`）。
- 取得はネットワークを伴う。利用者の同意の上で行う — 体系のスクリプト自身は通信しない（確定事実7: すべてのスクリプトは標準ライブラリだけで動き、pip にも通信にも依存しない）。

```sh
git clone --depth 1 --branch system-map/phase-1-continue https://github.com/Forest-Project-Lab/doctrine-lens <作業場所>
node <作業場所>/research/system-map/gold-model/validate.mjs <draft.json>
```

判定は `PASS` / `FAIL` / `SKIP` の三値で、終了コード 0（`FAIL` なし）で通過。`SKIP` は合格ではない（発火しない門を緑と呼ばない）。M-01〜M-16 の指摘が出たら下書きを直して再実行する。validator を書き換えて通すことは検収にならない。

## 報告

両門の判定（通過・不通過）・要素数・`unknown` の contract の数と負の出所の数・書き出した場所を報告に載せる。
