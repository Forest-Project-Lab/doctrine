---
name: assurance-loop
description: >-
  Doctrine 継続保証キャンペーンの運転手順。保証ループを回す・DISCOVER/CHALLENGE を実行する・
  規範カタログや網羅台帳を進める・カオス試験や故障注入を計画する・事象を分析する・
  「保証キャンペーンを進めて」「保証ループを回して」「観点を創出して」「独立検証して」と
  言われたときに使う。セッションを跨いだ再開は台帳と状態機械が持ち、会話の記憶に依存しない。
  開発専用（assurance/ レーン）。配布物・配布 7 Skill には触れない。
---

# assurance-loop — 保証キャンペーンの運転手順

開発専用スキル。規範は campaign 指示（CLAUDE.md 経由の会話）・ADR-114/115/116・
PROC-001・`assurance/README.md`・規範3冊（JERG=検証計画と証拠・STPA=創出・CAST=失敗後更新）。

## 0. 前提確認（毎回・省略禁止）

1. セッション冒頭に「セッション開始（要点復唱）」の契約注入があるか。無ければ統治フックが
   死んでいる（R11）。作業前にユーザーへ報せる。
2. `git fetch origin` と open Issue / open PR / CI の再取得。過去の報告を現状として信用しない。
3. `python3 assurance/harness/doctor.py --json` — UNASSESSED ならレーン前提が欠けている。
   SDK 実行はせず決定論試験だけで続行し、その旨を台帳と報告へ残す。
4. `python3 plugin/scripts/docs-audit.py --root doctrine_docs --json` — 監査が古い・赤なら先に扱う。

## 1. 次にやることの正本

**手で選ばない。** `assurance/.venv/bin/python assurance/harness/orchestrator.py status` の
`next_actions` が決定論で導く（ADR-115）。優先の意味論:

- 事象（incidents）の CAST_ANALYSIS が pending なら、それが新規 DISCOVER より先。
  修正済みの欠陥も「なぜ既存の保証が見逃したか」の分析が済むまで閉じない。
- カタログが UNASSESSED / PARTIAL なら INGEST_NORMS（抽出・再開）。順序は jerg→stpa→cast。
- カタログが揃い網羅台帳が UNKNOWN のままなら MAP_COVERAGE（jerg レーンが doctrine の
  現状と突き合わせ、五値へ割り当てる。証拠ポインタの無い「実装・試験・証拠あり」は書かない）。

## 2. 状態機械（外側は決定論。LLM の気分で遷移しない）

INGEST_NORMS → MAP_COVERAGE → DISCOVER → CHALLENGE → FORMALIZE → REPRODUCE_RED →
FIX → VERIFY → ATTACK_EVALUATOR → RECORD → CURATE（正本: `harness/orchestrator.py`）

- FAIL・事象はどの状態からでも CAST_ANALYSIS へ。
- REPRODUCE_RED: 修正前に FAIL する試験を先に作り証拠を保存。最初から緑は再現と認めない。
  再現不能は UNKNOWN として RECORD へ（実装へ進まない）。
- FIX は一度に一つ。破壊的注入は一時ディレクトリ・使い捨て fixture・worktree だけ。

## 3. model 方針（ADR-116。コードが強制）

- 評価役（規範抽出・創出・独立批判・検証計画・事故分析）= `claude-opus-5` × effort `high` 以上。
  `harness/model_policy.py` が未満を拒否。fallback は渡さない。opus 不在なら UNASSESSED。
- `claude-haiku-4-5` は配管確認（煙試験）と劣化プローブ（弱い model で意味が保たれるかの
  測定。役割名 degradation-probe を明示）だけ。

## 4. 独立性の規律（構造で守る）

- DISCOVER と CHALLENGE は別々の一回限り SDK セッション。会話・計画・弁明を共有しない。
  プロンプトは `harness/prompts.py` の組み立て関数だけを使う（CHALLENGE は構造化 JSON しか
  受け取れない）。実行は `sdk_lane.run_one_shot`（`setting_sources=[]` 固定・空の一時 cwd）。
- 規範抽出の引用はチャンク本文と機械照合（`prompts.verify_principles`）。出典なき候補は却下。
- 実装者は評価者の最終判定を書き換えない。評価者不在は PASS でなく UNASSESSED。
- AI の一致は客観的証拠でない。同系 model の共通原因故障は残余リスクとして台帳に保つ。

## 5. 証拠と台帳（`assurance/ledger/`）

- `catalogs/<book>-principles.json` — 検証原則カタログ（引用・行番号・費用・指紋つき）。
- `catalogs/<book>-coverage.json` — 五値の網羅台帳。再生成は評価済み割当を保持する。
  割当は現状の索引（`harness/system_index.py`）に対して行い、証拠ポインタは機械照合。
  解決しないポインタしか無い「実装・試験・証拠あり」は UNKNOWN へ落ちる（ADR-118）。
- `incidents.json` — 事象の列。cast 分析が済むまで閉じない。「済んだ」の三条件は
  ADR-117（schema 適合・照合を通った統制欠陥が1件以上・先行指標の定義）。
- `cast/<事象 id>.json` — 分析の結果（統制欠陥・先行指標・却下された欠陥つき）。
- `red/<事象 id>.json` — 修正前に FAIL した証拠（最初から緑は再現と認めない）。
- `smoke-latest.json` / `mutations-*.json` — 煙試験と故障注入の証拠。
- 状態語彙: PASS / FAIL / UNKNOWN / UNASSESSED / DEGRADED / NOT-APPLICABLE。
  根拠なき PASS を書かない。証拠が消えた PASS は UNKNOWN へ戻す。
  「完璧」「網羅済み」「保証済み」を無根拠に宣言しない（思いつかない≠網羅）。

## 6. コマンド

```bash
python3 assurance/harness/doctor.py --json                       # 前提診断 (0/3)
assurance/.venv/bin/python assurance/harness/orchestrator.py status    # 次の行動の正本
assurance/.venv/bin/python assurance/harness/orchestrator.py validate  # 正本の自己整合
assurance/.venv/bin/python assurance/harness/extract_principles.py --book jerg  # 抽出(再開可能)
assurance/.venv/bin/python assurance/harness/coverage.py init --book jerg      # 台帳骨組み
assurance/.venv/bin/python assurance/harness/coverage.py stats                 # 五値の集計
assurance/.venv/bin/python assurance/harness/cast_analysis.py --all            # 事象の分析 (ADR-117)
assurance/.venv/bin/python assurance/harness/map_coverage.py --book jerg       # 五値の割当 (ADR-118)
assurance/.venv/bin/python assurance/harness/smoke.py            # 実 SDK 煙試験 (0/2/3/4)
python3 -m unittest discover -s assurance/tests                  # レーン決定論試験
python3 plugin/run_tests.py                                      # 本体試験
python3 plugin/scripts/docs-audit.py --root doctrine_docs --json # 監査
```

## 7. してはならないこと

- 配布 Skill 7個の増減・変更。PAUSED Issue の再開。Lens Phase 2 / overlay / System Map への拡張。
- 統治木の決定・仕様・用語をハーネスのメモリへ書くこと（正本は統治木。ADR-035）。
- 模擬（stub）実行を実 Claude の保証として記録すること（execution_kind で区別）。
- 所有者判断: 互換性を壊す変更・配布境界や保証範囲の変更・復旧不能な削除・外部費用や
  credential・評価 model 最低線の引き下げ（ADR-116）。push / PR / merge は所有者が
  許可した範囲だけ（許可は会話で確認された事実に限る。推定しない）。

## 8. 反復の終端と報告

- CURATE: 重複 scenario・重複原則の統合、superseded の整理、平時コンテキストの最小化。
  各ループ終端で全門（レーン試験・本体試験・linter 一括・監査・投影・release-check）を緑にする。
- 「テストが緑」を理由に止まらない。campaign の一時停止条件を満たしたときだけ反復を閉じる。
- 進捗報告は規定形式: SHA・新規欠陥・規範・修正前再現・変更・環境別証拠・evaluator 攻撃
  結果・閉じた claim・UNKNOWN/UNASSESSED・整理した重複・次の最危険仮説・人間判断事項。
