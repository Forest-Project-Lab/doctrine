---
id: ADR-011
title: 段階導入とBash matcherの拒否限定
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.4, §7]
review_by: 2026-12-30
depends_on: [SPEC-019]
llm_context: task
---

# 段階導入とBash matcherの拒否限定

配線についての二つの判断を、一つの ADR（Architecture Decision Record、設計判断の記録）にまとめる。

## 背景

体系の重さは、利用者の規模に合わせたい。すべてを最初から置くと、小さな利用者には過剰になる `[R9]`。一方、`Bash` matcher の枝では、Claude Code の制約により `additionalContext` も `decision:block` もモデルへ届かない `[R7]`。

## 却下した選択肢

- **常に全構成を置く案**: 監査と依存グラフを Level 2 でも走らせると、一手番ごとの体感が重くなり、最小に保つ方針に反する。よって却下する。
- **Bash で助言文を返す案**: 助言文はモデルへ届かないので役に立たない。しかも、それで防げたと運用が誤解する余地を残す。よって却下する `[R8]`。

## 決定

段を Level 2/3/4 とする。Level 2 では縮小構成 `hooks/hooks.level2.json` を置く。これは、SessionEnd の監査と PostToolUse の `policy-guard.py` を外したものである。`Bash` matcher の `policy-guard.py` は deny だけを返し、起動後に判定を返す経路を持たない。

## 帰結

Level 2 の利用者は、監査なしで軽く運用できる。Level 3 以降で、監査・依存グラフ・投影を足せる。`Bash` の境界は予防（deny）だけに絞り、検出は他の経路に委ねる。

<!-- 入れない: 複数決定、現行仕様の全文 -->
