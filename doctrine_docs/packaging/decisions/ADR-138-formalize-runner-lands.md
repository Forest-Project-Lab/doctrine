---
id: ADR-138
title: FORMALIZE（定式化）は jerg レーンの検証計画審査として走らせ手を持ち、判定はどれも消化と数える
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-07
sources: ["所有者裁定（2026-08-07。INC-021 推奨#3 を両方実装と決めた）", doctrine_docs/packaging/decisions/ADR-121-claim-level-evidence-rule.md, doctrine_docs/packaging/decisions/ADR-116-evaluation-model-floor.md, assurance/ledger/cast/INC-021-lane-fires-on-declared-without-a-runner.json]
depends_on: [ADR-116, ADR-121, ADR-128]
llm_context: task
---

# FORMALIZE（定式化）は jerg レーンの検証計画審査として走らせ手を持ち、判定はどれも消化と数える

## 背景

ADR-128 は、宣言された評価の発火点に「走らせ手の三点（実行器・prompt 組み立て
関数・台帳の成果物種別）」か「未実装である旨と理由」のちょうど一方を持たせた。
FORMALIZE（批判を生き残った失敗仮説の検証計画を審査する段）は後者の側に
置かれ、是正は事象 INC-021 が持っていた。

実害は具体である。批判を生き残った候補 6 件が 2026-08-06 の創出記録に在るのに、
検証計画を審査する段の実体が無く、状態機械の `CHALLENGE_DONE → FORMALIZE →
REPRODUCE_RED` は踏む先を持たなかった。生き残りは台帳に滞留し、修正前再現へ
渡る道が無い。

所有者は 2026-08-07 に、INC-021 推奨#3 —— FORMALIZE と VERIFY（修正の独立検証）
の二段の実装 —— について「両方実装する」と裁定した。本 ADR はその FORMALIZE 側である。これは ADR-128 の
置換ではない —— 倒すのはエントリの側（未実装の明記 → 三点そろい）であって、
二分の不変条件そのものは維持する。

## 却下した選択肢

- **FORMALIZE を `fires_on` から外す**: ADR-128 が同じ選択肢を却下している。
  外すと、独立した審査を経ずに実装へ進んでいる事実も一緒に消える。
- **APPROVE（承認）だけを消化と数える**: REJECT（却下）された scenario を挙げ続けると、
  審査の結論が出た物を毎回買い直す「消えない行動」になる —— 評価済みの
  UNKNOWN（判定不能）を未評価と混ぜた INC-006 と同じ取り違えである。判定は評価の結論で
  あり、どの判定（APPROVE / REJECT / UNKNOWN）も割当済みである。
- **承認の可否を評価者の自由文から読む**: 意味の判断であり機械では閉じない。
  承認の床は決定論の guard（欄の非空と verdict）で引き、意味の質は憲章の文が
  受け持つ（ADR-133 と同じ二層）。
- **解決しない出典を持つ計画を主張ごと却下する**: ADR-121 が既に規則を主張
  単位に揃えている。ここだけ厳格側に割ると、照合規則がまた二つに割れる。

## 決定

FORMALIZE は走らせ手の三点を持つ —— 実行器 `assurance/harness/formalize.py`・
組み立て関数 `prompts.build_formalize_prompt`（構造化された生き残り scenario と
jerg カタログだけを受け取る。会話の口は無い）・台帳の成果物種別
`formalize/<日付>.json`。あわせて次を定める:

1. 審査役は評価役であり、最低線は ADR-116 のまま（opus × effort high。
   引き下げは所有者判断）。
2. 出典の照合は ADR-121 の主張単位の規則 —— 解決する jerg の鍵を一つでも保つ
   計画は残して `citation_defect` を刻み、ゼロの計画は受け取らない。
3. **どの判定も消化と数える。**正本が挙げ続けるのは、計画が返らなかった沈黙
   （`missing`）だけである（沈黙を APPROVE と読まない）。
4. `REPRODUCE_RED` へ進んでよいのは、決定論の guard `prompts.oracle_observable`
   を通った APPROVE の計画だけ —— 再現手順・注入点・隔離・両方の受入条件・
   証拠仕様のすべてが空白でないこと。空欄の形式的な充足は通さない。

## 帰結

- 正本の三点（`FIRING_POINTS` の実装側への倒し・`LEDGER_KINDS` への種別追加・
  `unformalized_survivors` という読む段と `next_actions` の挙げ方）は同じ変更で
  入り、`validate()` とレーンの決定論試験が凍結する。走らせ手だけを足す形
  （INC-012・INC-015 の同型）を最初から作らない。
- `status` の `firing_points.unimplemented` から FORMALIZE が消える。
  次の行動には「計画審査の判定が無い生き残り」の件数と id が挙がる。
- 審査の成果物は `evaluator_outputs_latest` に数えられ、故障注入の鮮度判定
  （ADR-120）の対象に入る。審査器だけが攻撃の外に立つ形を作らない。
- 得られる独立はセッションの独立までである（ADR-128 の帰結のまま。
  NONGOAL-001 第17項）。

<!-- 入れない: 複数決定、現行仕様の全文 -->
