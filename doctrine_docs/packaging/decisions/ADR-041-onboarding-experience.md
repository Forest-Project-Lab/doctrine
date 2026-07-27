---
id: ADR-041
title: 導入直後を警告で始めない（状態の種蒔き・Level 昇格・初日の中立案内）
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-07-27
updated: 2026-07-27
sources: [plugin/scripts/scaffold.py, plugin/scripts/gov-heartbeat.py, plugin/scripts/inject-contract.py]
depends_on: [REQ-013]
llm_context: task
---

# 導入直後を警告で始めない（状態の種蒔き・Level 昇格・初日の中立案内）

## 背景

導入直後の体験が警告から始まっていた（#74）。Level 3 以上の統治木を初期化した直後、初回の SessionEnd 監査が走るまでの各セッションで、生存性の照合が「監査が動いていない」という警告を出した。加えて `.governance-state` を種蒔きしないため、最初の監査要約ができた瞬間から「doc-review の定例の実施記録が無い」催促が毎セッション出た。監査キャッシュ `.claude/.cache/last-audit.json` は追跡除外の管理をされず、利用者のリポジトリに未追跡ファイルが常駐した。さらに、選んだ Level を上げ直す手段がツールに無く、`scaffold --level 3` の再実行は `.docs-level` を非破壊で飛ばして Level 2 のままだった（#90）。

つまり、正しく初期化しても、初日は警告と催促から始まり、Level を上げる正規手順も無かった。

## 却下した選択肢

- **監査を per-turn で走らせて初日から要約を出す**: 体感速度を壊す（NONGOAL 第5項）。監査はセッション境界と CI に限る。
- **警告を常に出す（現状）**: 導入直後は監査の停止ではないため誤報。生存性は「沈黙する故障」を警告に変える機構であって、正常な初日を警告にする機構ではない。
- **`.docs-level` を毎回上書き**: 非破壊の原則を崩す。`--level` を明示したときだけ更新する。

## 決定

1. **状態の種蒔き**: `scaffold` が `_system/.governance-state` を `initialized: <作成日>` と `last_cadence_review: <作成日>` で作る。新品の木は定例を「済み」とし（空の木に見直す事実は無い）、以後は周期でだけ促す。
2. **初日の中立案内**: 監査要約が無くても、`initialized` の印が在れば「導入直後。初回監査は SessionEnd に走る」という中立の案内にする（警告ではない）。生存性・注入の両方でこの分岐を持つ。`initialized` の印が無く要約も無い場合（＝停止の疑い）は従来どおり警告を出す。
3. **Level 昇格**: `scaffold --level N` が既存の `.docs-level` と食い違うとき、明示の選択として印を更新し、昇格・降格を報告する。`--level` は制御の入力であり、内容の種とは別に扱う（非破壊の対象外）。
4. **監査キャッシュの追跡除外**: `scaffold` が `.gitignore` に `.claude/.cache/` を非破壊で追記する。`--dry-run` はこれらの後段（Level 更新・`.gitignore`）の意図も正直に見せる。

## 帰結

- 導入初日が、警告と催促ではなく中立の案内から始まる。
- Level を上げる正規手順ができ、`.docs-level` の手編集に頼らない。
- 監査キャッシュが利用者のリポジトリに未追跡で残らない。
- `initialized` の印は監査の停止と初日を区別する一つの手がかりであり、生存性・注入の両方が同じ印を読む（判定を二重化しない）。
- 停止の疑いの警告は保つ（R11 の生存性は弱めない）。
