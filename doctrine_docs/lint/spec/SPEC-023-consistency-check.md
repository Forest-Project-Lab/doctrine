---
id: SPEC-023
title: 整合点検（linter と audit の食い違いの回帰ガード）と横断リマインダ
type: SPEC
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-16
sources: [scripts/consistency-check.py, scripts/consistency-reminder.py]
depends_on: [ICD-004, ICD-005]
llm_context: task
---

# 整合点検（linter と audit の食い違いの回帰ガード）と横断リマインダ

リポジトリ直下 `scripts/`(プラグインの `plugin/scripts/` とは別の場所)にある二本の仕様である。WATCH-001 第5項(登録済みの非文書へリンタが ERROR を出さない。ADR-024)を守る回帰ガード自身を、統治の外に置かない `[R2][R6]`。

## 入出力

- `scripts/consistency-check.py`: 入力なし(統治木を walkup で解決)。`.md-intake` に「非文書/投影/ビュー」と登録された各 .md に リンタ(ICD-004)を実際に走らせ、ERROR が出たものを食い違いとして列挙する(ビューの刻印の欠落は警告の助言であり食い違いではない。ADR-073)。食い違いが 1 件でもあれば終了コード 1、無ければ 0。読み取りは監査(ICD-005)と同じ共有コア(`plugin/scripts/_intake.py`)を使う。
- `scripts/consistency-reminder.py`: UserPromptSubmit のエンベロープを読み捨て、`.claude/.consistency-counter` の会話カウンタを 1 増やす。10 回ごとに、整合点検の実行(`/consistency-check` またはスクリプト直接)を促す助言を注入する。点検自体は実行しない。

## 制約

- 本リポジトリ専用の自己適用(`.claude/settings.local.json` の UserPromptSubmit 配線。ADR-028 の 7 イベントとは別の、リポジトリ直付けの配線)。プラグインの配布物には含めない。
- 標準ライブラリのみ(ADR-031)。リマインダは何が起きても後続フックを壊さない(終了コード常に 0)。

## エラー時挙動

- 統治木・plugin/scripts が見つからないときは、点検は理由を出して終了コード 2。リマインダはカウンタが読めなくても 0 から数え直して続行する。
- リンタの起動に失敗したファイルは「点検不能」として食い違い側に倒す(黙って飛ばさない)。

## 実装の指紋

対象は契約の要約(モジュール冒頭)。更新は `trace-index.py --id SPEC-023` が返す行を写す（ADR-061）。

- sha256:0ae10986ff71977e790ffaad3cb1e174055efd09a4019c2d8ee3a7d282c92ce1
- sha256:a4fd6eb3d2a9eab88c083ec2f677bbefb83746bfdce38cf8bf785ddb0fb63622

## 受入基準

- 登録済みの非文書へリンタが ERROR を出したら赤(終了コード 1)で、対象と ERROR コードを列挙する。
- 食い違いゼロなら「一致」を報告して 0。
- リマインダは 10 回目ごとの会話でだけ助言を出す。
- 受入は TEST-023 が凍結する。
