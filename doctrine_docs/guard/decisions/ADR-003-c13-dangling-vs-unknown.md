---
id: ADR-003
title: C13 の分岐（dangling 許容／分類不能 拒否）
type: ADR
domain: guard
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/policy-guard.py]
depends_on: [SPEC-003]
llm_context: task
---

# C13（整合判断id）の分岐（dangling 許容／分類不能 拒否）

ADR（Architecture Decision Record=設計判断の記録）。1 文書 1 決定。

## 背景
ICD依存ガードは、`depends_on` の dep を索引（依存グラフ）で引けないことがある。引けない dep をすべて同じに扱うと、二つの失敗のどちらかに倒れる。死リンクを境界違反と取り違えて拒否してしまうか、逆に本物の境界違反を見逃してしまうかである。`[R7]`

## 却下した選択肢
- 引けない dep をすべて許す: 接頭辞からして型を読めない不正な dep まで通してしまい、R7 の境界明瞭が崩れる。
- 引けない dep をすべて拒否する: 索引に載っていないだけの死リンク（構文としては正しい dep）まで拒否してしまう。死リンクを見つけるのは監査の役目なのに、それをガードが奪う。

## 決定
引けない理由で二つに分ける。構文は正しく索引に載っていないだけの dep（dangling）は、ガードが許す（死リンクは監査が見つける）。接頭辞から型を読めない dep（型が UNKNOWN（不明））は、ガードが安全側に倒して拒否する。

## 帰結
`_icd_judge_dep` がこの二分を実装する。将来の改変で、この判定が知らぬ間に「危険でも通す」側へ倒れないよう、判定の中身をスクリプト冒頭の docstring と本 ADR の両方に書き残す。死リンクは audit（ICD-005）が後から見つけて補う。

<!-- 入れない: 複数決定、現行仕様の全文 -->
