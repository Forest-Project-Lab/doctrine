---
id: ADR-140
title: 事故分析の新規仮説は DISCOVER（失敗仮説の創出）の口から独立批判を経て取り込み、消化は scenarios 台帳の出自欄で記帳する
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-07
sources: [assurance/ledger/cast/INC-016-cast-analysis-content-unread-by-canon.json, doctrine_docs/packaging/decisions/ADR-125-cast-recommendations-need-a-disposition.md, doctrine_docs/packaging/decisions/ADR-115-viewpoint-lane-orchestration.md, doctrine_docs/packaging/decisions/ADR-134-staleness-is-scoped-to-what-the-judgement-cited.md]
depends_on: [ADR-115, ADR-125, ADR-131, ADR-134]
llm_context: task
---

# 事故分析の新規仮説は DISCOVER（失敗仮説の創出）の口から独立批判を経て取り込み、消化は scenarios 台帳の出自欄で記帳する

## 背景

事故分析の記録は、統制欠陥・先行指標・推奨のほかに `new_scenario_candidates`
（新規仮説の候補）の欄を持つ。INC-016 は「分析の中身が正本へ一度も届いていない」
という統制欠陥を立て、その是正のうち推奨の側は ADR-125 が処遇の台帳で受けた。
**仮説の側は受け皿を持たないまま残った** —— 26 件の事故分析が残した候補は
計 134 件（重大度の四段で P0（最重大）12・P1（重大）62・P2（中位）53・
P3（軽微）7）で、正本はその欄を一度も読んでいない。
分析のたびに増える欄が、読まれない場所へ積もり続ける形は、INC-016 が名指しした
統制欠陥そのものの残余である。

候補の性質は推奨と違う。推奨は「何をするか」の提案であり、要るのは処遇（人の
判断の記録）である。候補は失敗**仮説**であり、要るのは判定 —— 反証可能な形への
定式化と、CHALLENGE（独立批判）である。仮説を判定済みの scenario として扱えば、
批判を経ない候補が定式化・実装へ流れる（ADR-115 が構造で禁じた形）。

## 却下した選択肢

- **候補をそのまま scenario として台帳へ積む**: 候補は仮説であり、判定済みでは
  ない。独立批判を経ない受け入れは、DISCOVER→CHALLENGE の独立構造（ADR-115）の
  迂回路になる。
- **推奨と同じ処遇の台帳（第二の待ち行列）を作る**: 候補に要るのは処遇ではなく
  判定である。台帳を二つ持つと、同じ「読まれたか」の検査・集計・凍結試験を
  二重に保守することになり、片方だけが変わったときに割れる。消化の記帳は
  scenarios 台帳の出自欄で足りる。
- **閾値なしで全件を次の行動に挙げる**: 一束に満たない件数で評価を買いに行くと
  単価に対して割に合わない（ADR-134 が古びで確定した判断と同じ）。閾値は新しく
  発明せず ADR-134 の一束（25 件）を再利用する。
- **優先順の表に候補専用の段を足す**: 表の書き換えは所有者判断である（ADR-131）。
  候補の取り込みは既存の DISCOVER の段（既定の入口）に載せ、表は変えない。

## 決定

事故分析の新規仮説候補は、DISCOVER の口から独立批判を経て取り込む。

1. **正本が候補を読む。** `cast_scenario_candidates()`（鍵は事象 id と番号。
   ADR-125 の推奨の読み方と同型）と `triaged_candidate_keys()`（消化済みの鍵の
   集合）を読む段として持ち、`status` は重大度別と未批判の件数を常に出す。
2. **消化の記帳は scenarios 台帳の出自欄が持つ。** 取り込みの記録は既存の
   `scenarios/<日付>.json` の形に `kind: candidate-triage`・
   `candidates_considered`（一括の**全候補**の鍵）・`dropped`（定式化不能と
   重複の候補。理由つき）を足した物とする。considered = 定式化済み + dropped が
   常に成り立ち、第二の待ち行列は作らない。
3. **走らせ手は `triage_candidates.py`。** session 1（定式化。評価役の最低線
   ADR-116 のまま）が候補を SCENARIOS_SCHEMA へ定式化する。憲章は、渡していない
   仮説の発明を禁じ、既存 scenario と実質同一の候補には `duplicate_of` を要す。
   出自（`source_candidate`）と出典（規範の鍵）は機械照合し、通らない scenario
   は外す。`duplicate_of` を持つ scenario は記録するが批判へ渡さない。session 2
   （独立批判）は既存の `build_challenge_prompt` をそのまま使う —— 構造化 JSON
   だけが渡り、会話の口は無い。
4. **次の行動に挙げるのは、未批判の P0・P1 が一束（ADR-134 の閾値の再利用）に
   達したときだけ。** 挙げる段は DISCOVER で、優先順の表は変えない。閾値未満でも
   必ず数えて出す —— 挙げないことと隠すことは違う（INC-006）。

## 帰結

- 批判を生き残った候補は、既存の読む段（`unformalized_survivors`）がそのまま
  FORMALIZE（検証計画の審査）へ渡す。取り込み専用の後工程は増えない。
- 候補の取り込みを APPLY_FINDINGS より前に置くかどうかは、優先順の表の書き換えに
  当たるので所有者の表の領分である（ADR-131）。本決定は DISCOVER の段（表の末尾）
  のまま使い、表に触れない。
- 記帳は結果を選ばない —— 定式化済みも重複も定式化不能も、出自欄に載った候補は
  二度と数え直されない（評価済みの判定不能を引き直さないのと同じ規則。INC-006）。
- 得られる独立はセッションの独立までである（NONGOAL-001 第17項。同系 model の
  共通原因故障は残余リスク）。

<!-- 入れない: 複数決定、現行仕様の全文 -->
