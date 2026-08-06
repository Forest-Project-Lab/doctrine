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
   死んでいる（R11）。**報せたうえで止まる。**注入の無いセッションで統治木を編集しない
   （ガードもリンタも効いていない可能性がある）。レーンの読み取りだけなら続けてよい。
2. `git fetch origin` と open Issue / open PR / CI の再取得。過去の報告を現状として信用しない。
3. `python3 assurance/harness/doctor.py --json` — UNASSESSED ならレーン前提が欠けている。
   SDK 実行はせず決定論試験だけで続行し、その旨を台帳と報告へ残す。
4. `python3 plugin/scripts/docs-audit.py --root doctrine_docs --json --today <今日>` —
   error か warn が 1 件でもあれば、他の何より先に扱う。**`--today` は必ず渡す**
   （渡さないと壁時計を読み、日付が変わっただけで結果が変わる。WATCH-001 第11項と同じ形）。

## 1. 次にやることの正本

**手で選ばない。** `assurance/.venv/bin/python assurance/harness/orchestrator.py status` の
`next_actions` が決定論で導く（ADR-115）。

**着手は先頭の一件から。** 一回の反復で何件消化してもよいが、飛ばしてはならない。
先頭を飛ばしたくなったら、それは正本の優先順が誤っている疑いなので、飛ばさずに
正本の側を直す（実際に INC-006・INC-012・INC-015 がその形で見つかった）。

優先の意味論:

- 事象（incidents）の CAST_ANALYSIS が pending なら、それが新規 DISCOVER より先。
  修正済みの欠陥も「なぜ既存の保証が見逃したか」の分析が済むまで閉じない。
- カタログが UNASSESSED / PARTIAL なら INGEST_NORMS（抽出・再開）。順序は jerg→stpa→cast。
- カタログが揃い網羅台帳が UNKNOWN のままなら MAP_COVERAGE（jerg レーンが doctrine の
  現状と突き合わせ、五値へ割り当てる。証拠ポインタの無い「実装・試験・証拠あり」は書かない）。

## 2. 状態機械（外側は決定論。LLM の気分で遷移しない）

INGEST_NORMS → MAP_COVERAGE → DISCOVER → CHALLENGE → FORMALIZE → REPRODUCE_RED →
FIX → VERIFY → ATTACK_EVALUATOR → RECORD → CURATE（正本: `harness/orchestrator.py`）

- 状態は二つに分かれる（ADR-120）。**名指しされる**（INGEST_NORMS・MAP_COVERAGE・
  CAST_ANALYSIS・DISCOVER・FORMALIZE・ATTACK_EVALUATOR）と、**名指しされないと
  明記されている**（CHALLENGE・REPRODUCE_RED・FIX・VERIFY・RECORD・CURATE）。
  後者は「やらなくてよい」ではなく「帳簿だけからは指せない」の意味で、反復の中で
  順に踏む。**どちらにも属さない状態を作らない** —— 黙って名指しされない状態は
  決して起きない（ATTACK_EVALUATOR が5反復飛ばされた形）。
- **走らせ手を足すときは、その成果を正本が読む段も同時に足す。**片方だけだと、
  同じ行動を毎回買い直す「消えない行動」になる（INC-012・INC-015）。
- FAIL・事象はどの状態からでも CAST_ANALYSIS へ。
- REPRODUCE_RED: 修正前に FAIL する試験を先に作り証拠を保存。最初から緑は再現と認めない。
  再現不能は UNKNOWN として RECORD へ（実装へ進まない）。
- FIX は一度に一つ。破壊的注入は一時ディレクトリ・使い捨て fixture・worktree だけ。

## 3. model 方針（ADR-116。コードが強制）

- 評価役（規範抽出・創出・独立批判・検証計画・事故分析）= `claude-opus-5` × effort `high` 以上。
  `harness/model_policy.py` が未満を拒否。fallback は渡さない。opus 不在なら UNASSESSED。
- `claude-haiku-4-5` は配管確認（煙試験）と劣化プローブ（弱い model で意味が保たれるかの
  測定。役割名 degradation-probe を明示）だけ。
- effort の**引き上げ**（xhigh・max）は自律判断でよい。**引き下げは所有者判断**（ADR-116）。

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
- `incidents.json` — 事象の列。cast 分析が済むまで閉じない。「済んだ」の四条件は
  ADR-117 と ADR-121（schema 適合・出典に欠陥の無い統制欠陥が1件以上・先行指標の定義・
  事象の証拠が確かめられること）。新しい事象には `evidence_refs`（索引か実ファイル系で
  解決する参照）か `evidence_kind`（external / conversational / measurement）を必ず持たせる。
- `cast/<事象 id>.json` — 分析の結果（統制欠陥・先行指標・却下された欠陥つき）。
- `red/<事象 id>.json` — 修正前に FAIL した証拠（最初から緑は再現と認めない）。
- `scenarios/<日付>.json` — 創出した候補と独立批判の判定。生き残りが在れば正本が
  FORMALIZE を挙げる（沈黙は ACCEPT と読まない。判定の無い候補は missing に残る）。
- `smoke-latest.json` / `mutations-*.json` — 煙試験と故障注入の証拠。
  評価器の成果物が `mutations-*.json` の日付より新しければ、正本が ATTACK_EVALUATOR を
  次の行動に挙げる（ADR-120）。攻撃の設計に「これは捏造だ」と読める手掛かりを残さない。
- **事象に id を与えた瞬間に台帳へ積む。**報告や ADR で名指ししてから積むのを
  後回しにしない（INC-012 は ADR と試験から参照されながら台帳に無かった）。
  採番は `INC-<通し番号>-<短い英字の要約>`。番号は台帳の最大値の次を使う。
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
assurance/.venv/bin/python assurance/harness/discover.py                      # 創出と独立批判
assurance/.venv/bin/python assurance/harness/attack_evaluator.py               # 評価器への故障注入 (ADR-120)
assurance/.venv/bin/python assurance/harness/smoke.py            # 実 SDK 煙試験 (0/2/3/4)
python3 -m unittest discover -s assurance/tests                  # レーン決定論試験
python3 plugin/run_tests.py                                      # 本体試験
python3 plugin/scripts/docs-audit.py --root doctrine_docs --json # 監査
```

## 7. してはならないこと

- 配布 Skill 7個の増減・変更。PAUSED Issue の再開。Lens Phase 2 / overlay / System Map への拡張。
- 統治木の決定・仕様・用語をハーネスのメモリへ書くこと（正本は統治木。ADR-035）。
- 模擬（stub）実行を実 Claude の保証として記録すること（execution_kind で区別）。
- 所有者判断（**下の常設許可の外側**。勝手に進めず、判断を仰いで止まる）: 互換性を壊す
  変更・配布境界や保証範囲の変更・復旧不能な削除・外部費用や credential・評価 model
  最低線の引き下げ（ADR-116）・配布物の版番号の変更とリリース。

## 7.1 常設の許可（所有者の指示 2026-08-06。会話の記憶に依存しない）

**branch → commit → push → PR → squash merge までを、反復ごとに自律で行ってよい。**
毎回口頭で許可を取り直さない。ただし次をすべて満たすときだけ:

1. 変更が本反復の一つの主題に収まっている（`CONTRIBUTING.md`「一つの主題に絞る」）。
   主題が二つ終わったら **PR を二つ**に分ける。一つの反復で複数 PR を出してよい。
2. §8 の全門が緑（レーン試験・本体試験・linter 一括・監査・投影・release-check・
   consistency-check・code-audit）。
3. PR の CI が pass。**赤いまま merge しない。赤を避けるために門を緩めない。**
4. 上の所有者判断に触れていない。触れるなら PR は作ってよいが **merge せず**、
   判断を仰ぐ。
5. 自分が作った PR だけを merge する。他者の PR には触れない。
6. merge 後に `main` を引き直し、レーン試験と監査が緑であることを確かめて報告する。

`gh` は未認証なので、token は git の credential helper から取る:
`TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')`
を `GH_TOKEN` に渡す。ネットワークは時折切れる。**切れたら再試行し、最終状態
（`git status -sb` と `origin/main` との差分）を確かめてから報告する。**

## 8. 反復の終端と報告

**一反復の単位**: `next_actions` の先頭に着手し、主題が一つ片づいた時点で門を緑にして
PR を出し、merge して閉じる。分量の目安は**評価セッション 10 本以内・所要 60 分以内**。
超えるなら途中で切って PR を出す（台帳は再開を持つので進捗は失われない）。

- CURATE: 重複 scenario・重複原則の統合、superseded の整理、平時コンテキストの最小化。
  各ループ終端で全門（レーン試験・本体試験・linter 一括・監査・投影・release-check・
  consistency-check・code-audit）を緑にする。
- **「テストが緑」を理由に止まらない。**次の反復で扱うことを台帳へ積んでから閉じる。

### 反復を閉じてよい条件（どれか一つ）

- 主題が一つ片づき、門が緑で、PR が merge された。
- `next_actions` の先頭が**所有者判断**に当たり、判断を仰いで止まっている。
- レーン前提が欠けて（doctor が UNASSESSED・opus 不在）評価が走らせられない。
- 上の分量の目安を超えた（途中まででも PR を出して閉じる）。

**思いつかなくなったことを終端の理由にしない。** 正本の `next_actions` は空にならない。

### 報告（規定形式・順序も固定）

SHA・新規欠陥・規範・修正前再現・変更・環境別証拠・evaluator 攻撃結果・閉じた claim・
UNKNOWN/UNASSESSED・整理した重複・次の最危険仮説・人間判断事項。

- 実施しなかった項目は省略せず「未実施」と書く（空欄は「無かった」と読まれる）。
- 自分の誤り・falsify された自分の仮説・汚染された測定は、**隠さずその項へ書く**。
- 費用は換算値であり請求額ではない（サブスクリプション認証。従量課金は発生しない）。
  制約は金額ではなく所要時間と利用枠である。
