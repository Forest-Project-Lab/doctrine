---
id: IMPL-019
title: gov-heartbeat.py（統治ハートビート）の実装メモ
type: IMPL
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-14
sources: [plugin/scripts/gov-heartbeat.py]
depends_on: [SPEC-021]
llm_context: task
---

# gov-heartbeat.py（統治ハートビート）の実装メモ

SPEC-021 の実装注記である `[R11]`。

## 対象部品

- `build_message(docs_root, today, config)`: 判定の核。重い順に一件だけの警告文を返す(監査の要約なし→鮮度超過→定例の記録なし→定例超過)。純粋関数に近く、テストが直接呼べる。
- `read_state(docs_root)`: `_system/.governance-state`(`キー: 値` の平文)の読み取り。
- `_audit_summary(docs_root)`: 前回監査の要約。inject-contract と同じ候補順(plugin cache → `.claude/.cache`)と同じ root 照合(越境注入の防止)を使う。
- `_once_per_session(sid)`: セッション別の印(`hb-<セッションid>`)で一度きりを守る。
- 助言へ足す行(main の終盤): 拒否経路の疑い(ADR-062)・版の切替(ADR-066)・版の遅れ(ADR-070)。判定はいずれも共有コア(`_auditcache.liveness_gap`/`version_drift`/`version_lag`)に一度だけ在り、鼓動は呼んで一行を足すだけ。
- 不具合の兆候の促し(ADR-074): 梯子の一項(`error_report_line`)。エラージャーナルの読み書きは共有コア(`_auditcache.record_error`/`read_errors`。許可制・上限20件)に一度だけ在り、鼓動は読んで報告の手順(下書き→承認→gh→感謝)の自己完結文を出すだけ。記録は入口5本(ガード・リンタ・注入・鼓動・監査)の例外処理が書く。

## 実装制約

- 毎会話走るため、全木走査をしない。読むのは小ファイル三つだけ。
- 段差(`.docs-level`)を読まない(ADR-030)。統治木が無ければ無音。
- `--today` で決定的に検査できる。与えないときだけ壁時計(監査と同じ規約)。
- 印の置き場は capture の印と同じ `session-flags`(プラグイン cache 配下)。

## 注意点

- 要約の候補パスと root 照合の規則を inject-contract と別実装で持っている。規則を変えるときは両方を同じ変更で直す(食い違いは WATCH-001 第5項と同型の欠陥になる)。
- 警告文は自己完結(何が起きたか・どう言えば実行されるか・どこへ記録するか)を保つ。技能名や型コードの知識を利用者に求めない。
