---
name: assurance-loop
description: >-
  Doctrine 継続保証キャンペーンの運転手順。保証ループを回す・DISCOVER/CHALLENGE を実行する・
  カオス試験や故障注入を計画する・保証台帳や煙試験を確認する・「保証キャンペーンを進めて」
  「保証ループを回して」「観点を創出して」「独立検証して」と言われたときに使う。
  開発専用（assurance/ レーン）。配布物・配布 Skill には触れない。
---

# assurance-loop — 保証キャンペーンの運転手順

これは Forest-Project-Lab/doctrine の開発専用スキルである。配布物ではない。
規範は CLAUDE.md の campaign 指示・`assurance/README.md`・JERG/STPA/CAST 三冊。

## 0. 前提確認（毎回・省略禁止）

1. セッション冒頭に「セッション開始（要点復唱）」の契約注入があるか。無ければ統治フックが死んでいる（R11）。作業前にユーザーへ報せる。
2. `python3 assurance/harness/doctor.py --json` — UNASSESSED ならレーン前提が欠けている。SDK 実行はせず、決定論試験だけで続行し、その旨を台帳と報告に残す。
3. `python3 plugin/scripts/docs-audit.py --root doctrine_docs --json` — 監査が古い/赤なら先に扱う。
4. remote 再取得（`git fetch origin` / open Issue / open PR）。過去の報告を現状として信用しない。

## 1. 状態機械（外側は決定論・LLM の気分で遷移しない）

DISCOVER → CHALLENGE → FORMALIZE → REPRODUCE_RED → FIX → VERIFY → ATTACK_EVALUATOR → RECORD → CURATE

- 各状態の成果物が schema（`assurance/harness/schemas.py`）に適合しない限り次へ進まない。
- REPRODUCE_RED: 修正前に FAIL する試験を先に作り、FAIL の証拠を保存する。最初から緑の試験は再現と認めない。再現不能は UNKNOWN とし実装へ進まない。
- FIX は一度に一つ。無関係な変更を混ぜない。
- 破壊的注入は一時ディレクトリ・使い捨て fixture・worktree だけ。main checkout と利用者データに触れない。

## 2. 独立性の規律（構造で守る）

- DISCOVER と CHALLENGE は**別々の一回限り SDK セッション**。会話履歴・計画・弁明を共有しない。
  プロンプトは `assurance/harness/prompts.py` の組み立て関数だけを使う（CHALLENGE は構造化 JSON しか受け取れない設計）。
- 実行は `sdk_lane.run_one_shot`（`setting_sources=[]` 固定・空の一時 cwd・読み取り専用）。
- 実装者（このセッション）は評価者の最終判定を書き換えない。評価者不在の主張は PASS でなく UNASSESSED。
- AI の一致は客観的証拠でない。同系 model の共通原因故障は残余リスクとして常に台帳へ残す。

## 3. 状態語彙と証拠

- PASS / FAIL / UNKNOWN / UNASSESSED / DEGRADED / NOT-APPLICABLE を使い分ける。根拠なき PASS を書かない。証拠が消えた PASS は UNKNOWN へ戻す。
- 証拠は `assurance/ledger/` へ（生ログは `ledger/runs/`、コミットしない）。各記録に commit SHA・SDK 版・model・プロンプト指紋・費用を残す。
- 模擬（stub）実行を実 Claude の保証として書かない。記録の execution_kind で区別する。

## 4. してはならないこと

- 配布 Skill 7個の増減・変更（保証エージェントはレーンからプログラム的に定義する）。
- PAUSED と明記された Issue の再開。
- Lens Phase 2 / overlay / System Map 製品化への拡張。
- 統治木の決定・仕様・用語をハーネスのメモリへ書くこと（正本は統治木。ADR-035）。
- 次は所有者判断: 互換性を壊す変更・配布境界の変更・保証範囲の変更・復旧不能な削除・外部費用や credential・main への merge・release・PAUSED 再開。

## 5. コマンド

```bash
python3 assurance/harness/doctor.py --json          # レーン前提診断 (0/3)
assurance/.venv/bin/python assurance/harness/smoke.py  # 実 SDK 煙試験 (0/2/3/4)
python3 -m unittest discover -s assurance/tests     # レーン決定論試験
python3 plugin/run_tests.py                         # 本体試験（現状 1201 件）
python3 plugin/scripts/docs-audit.py --root doctrine_docs --json  # 監査
```

## 6. 反復の終端（CURATE）と停止条件

- 重複 scenario の統合・superseded の整理・台帳から古い実行結果の除外・平時コンテキストの最小化を行う。
- 停止してよいのは campaign の一時停止条件（証拠の揃った claim・放置なき UNKNOWN・修正前 FAIL と修正後 PASS・evaluator への故障注入検出・残余リスクと再評価 trigger の明示 など）を満たしたときだけ。「テストが緑」を理由に止まらない。
- 進捗報告は campaign の規定形式（SHA・新規欠陥・規範・修正前再現・変更・環境別証拠・evaluator 攻撃結果・閉じた claim・UNKNOWN/UNASSESSED・整理した重複・次の最危険仮説・人間判断事項）。
