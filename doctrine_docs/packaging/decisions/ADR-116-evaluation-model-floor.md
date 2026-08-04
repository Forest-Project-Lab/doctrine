---
id: ADR-116
title: 評価役の実行条件は opus の effort high を最低線とし、弱い model への黙った縮退を禁ずる
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-04
updated: 2026-08-04
sources: ["所有者指示（2026-08-04 の会話）", assurance/harness/model_policy.py, assurance/external-specs.md]
depends_on: [ADR-114, ADR-115]
llm_context: task
---

# 評価役の実行条件は opus の effort high を最低線とし、弱い model への黙った縮退を禁ずる

## 背景

規範の抽出・観点の創出・独立批判・検証計画・事故分析の質は、使う model と
思考の割り当てに強く依存する。弱い model の評価は観点を薄め、その劣化は応答の
形からは見えない。所有者は 2026-08-04 に「評価は最低でも opus の high。弱い
model を使ってよいのは、意味が保たれるかを測る用途だけ」と指示した。実行系の
Claude Agent SDK（0.2.129）には effort（low〜max の五段）がもともと在り、
条件は機械で固定できる（確認記録第8項）。

## 却下した選択肢

- `claude-haiku-4-5` での評価の常用: 費用は安いが、規範評価の意味の密度が保てない。
- fallback（代替 model への自動切替）の設定: 判定の劣化が記録に残らないまま起きる。
- effort の無指定: 既定値がどの段かは外部仕様であり、版の更新で黙って変わり得る。

## 決定

評価役（規範抽出・創出・独立批判・検証計画・事故分析）の実行条件は
`claude-opus-5` × effort `high` を最低線とし、これ未満の組をコード
（`assurance/harness/model_policy.py`）が拒否する。

## 帰結

- 役割は三つに固定する: 評価役（最低線あり）・配管確認（意味を要さない煙試験。
  `claude-haiku-4-5` でよい）・劣化プローブ（弱い model で意味が保たれるかを
  測る比較専用。弱い model の使用を役割名で明示する）。
- opus が使えない環境では、評価は UNASSESSED（前提欠如で未評価）へ倒す。
  黙って弱い model で代行しない（fallback は渡さない実装のまま）。
- effort の引き上げ（xhigh・max）は自律判断でよい。最低線の引き下げは所有者判断。
- 最低線は決定論試験が凍結する（評価役へ `claude-haiku-4-5` や effort medium を
  渡す組は試験が拒否する）。

<!-- 入れない: 複数決定、現行仕様の全文 -->
