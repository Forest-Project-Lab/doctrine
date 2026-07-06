---
id: ADR-009
title: 注入とパックで二つの別上限を持つ（C10）
type: ADR
domain: context
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §3.9]
depends_on: [SPEC-012, SPEC-013]
llm_context: task
---

# 注入とパックで二つの別上限を持つ

ADR とは設計上の一つの決定を背景・選択肢・帰結とともに記録する文書をいう。C10とは、凍結した契約の整合を見る判断項目の番号をいう。この決定はその一つである。

## 背景

注入は SessionStart で常時集合を渡し、パックはタスクごとに最少集合を集める。この二つは、扱う量の性質が異なる。常時集合は毎セッションにかかる固定費であり、パックの量はタスクごとに変わる。両方を一つの上限で縛ると、片方を調整したときにもう片方まで影響を受ける `[R5]`。

## 却下した選択肢

- 一つの上限を両者で共有する案。注入を絞るとパックまで痩せ、タスクの被覆が落ちる。却下する。
- パックを無制限にする案。文脈窓のふくらみ（context-rot）に歯止めがかからない。却下する。

## 決定

`_system/.context-config.json` に、別々のキーを二つ置く。注入は `injection_token_cap`（既定 12000）を、パックは `task_pack_token_cap`（任意）を使う。注入スクリプトは前者だけを、パック・スクリプトは後者だけを読む。

## 帰結

`inject-contract.py` と `collect-context.py` は、上限をそれぞれ独立に調整できる。一方の運用を変えても、もう一方には影響しない。受入は、TEST-012 と TEST-013 で二つの上限が独立に効くことを確かめる。
