---
id: ADR-114
title: 保証キャンペーンの実行系評価は開発専用レーンに隔離する — 配布物へ依存を持ち込まない
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-04
updated: 2026-08-04
sources: ["保証キャンペーン開始指示（2026-08-04 の会話）", assurance/external-specs.md, "Claude Code 公式文書 agent-sdk / authentication（取得記録は assurance/external-specs.md）"]
depends_on: [ICD-008]
llm_context: task
---

# 保証キャンペーンの実行系評価は開発専用レーンに隔離する — 配布物へ依存を持ち込まない

## 背景

継続保証キャンペーン（規範は JERG（宇宙機関のソフトウェア開発標準群）の 2-610C・
STPA（システム理論に基づく危険要因分析）・CAST（システム理論に基づく事故分析））は、
観点の創出と独立批判を実 Claude の一回限りセッションで行う。その実行系 Claude Agent
SDK（エージェント実行の開発キット。以下 SDK）は pip の依存であり、配布物 `plugin/` の
「標準ライブラリだけで動く」（DECIDED-001 事実7）と両立しない。また評価者が実装者の
設定・フック・会話を継ぐと、独立性の主張が崩れる。

## 却下した選択肢

- 配布物へ SDK を同梱する: DECIDED-001 事実7に反し、利用者へ依存と費用を強いる。
- 従量課金の鍵を常用する: サブスクリプションで足りる開発時評価に別の費用構造を持ち込む。
- 評価セッションに設定の読み込みを許す: `setting_sources` の省略は user/project/local を
  読む既定であり（確認記録第4項）、評価者の独立が壊れる。
- 保証用エージェントを配布 Skill として増やす: 技能7個の固定（DECIDED-001 事実8）に反する。

## 決定

保証キャンペーンの SDK 実行系は、リポジトリ直下の開発専用レーン `assurance/` に
隔離し、配布物 `plugin/` の実行時依存・配布内容へ一切入れない。

## 帰結

- レーンは自前の venv（Python の隔離実行環境）と pin した依存
  （`assurance/requirements.lock`）を持つ。配布物の stdlib-only は不変。
- 認証はサブスクリプション資格情報の流用を主とする。対話ログイン保存分の自動流用は
  公式文書に無い実装詳細のため、破れたら `claude setup-token` へ切り替える
  （確認記録第2・3項。資格情報の内容は記録しない）。
- 評価セッションは `setting_sources` を空配列で明示し、空の一時作業場所で動かす。
  独立批判へ渡せるのは構造化された成果物だけとする（レーンの組み立て関数が構造で守る）。
- レーンが使えないときの状態は PASS（適合の証拠あり）でなく UNASSESSED（前提欠如で
  未評価）とし、決定論試験だけで続行する。壊れたとき赤くなることは故障注入の記録
  （`assurance/ledger/`）が証拠を持つ。
- 運転規範は PROC-001 が持つ。レーンの Markdown は体系外分類の記録（.md-intake）で
  非文書またはビューとして登録する。

<!-- 入れない: 複数決定、現行仕様の全文 -->
