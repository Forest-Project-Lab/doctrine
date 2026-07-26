---
id: SPEC-025
title: 被覆マトリクス（統治要求×発火経路×証跡）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [plugin/hooks/hooks.json, .github/workflows/checks.yml]
depends_on: [REQ-014, ICD-008]
llm_context: task
---

# 被覆マトリクス（統治要求×発火経路×証跡）

各統治要求が、どの発火経路(いつ動くか)に結線され、どんな証跡(動いた事実の残滓)を残すかの一覧である。空白のセルが構造的に存在できない状態を保つ — 全ての行は「結線済み」か「明示の非目標(NONGOAL)」のどちらかである。発火経路を足す・消すときは本表を更新し、受入(TEST-025)が hooks.json のイベント集合との一致を凍結する `[R11][R9]`。

## 入出力

- 入力: 統治要求(R1〜R12)と発火経路(7 イベント・CI・技能)。
- 返す値: 下の表。行の追加・変更は本文書の編集であり、配線の変更(hooks.json)と同じ変更で行う。

| 要求 | 発火経路(いつ) | 実行するもの | 証跡 |
|---|---|---|---|
| R1 見つけやすさ | SessionEnd/CI(監査)・docs-curate | docs-audit(投影ドリフト・孤児)・render-projection | 監査要約・投影の updated |
| R2 現行性 | PostToolUse(リンタ)・SessionEnd/CI(監査)・UserPromptSubmit(督促) | docs-linter(status)・docs-audit(review_by 超過・stale_current)・gov-heartbeat | リンタ助言・監査要約・督促 |
| R3 追跡性 | PostToolUse(リンタ)・SessionEnd/CI(監査) | docs-linter(MISSING_TRACE)・docs-audit(逆孤児・adr_not_landed) | 同上 |
| R4 変更耐性 | PreToolUse(ガード)・SessionEnd/CI(監査)・change-impact | policy-guard(削除安全)・docs-audit(dead link・source_drift) | deny 理由・監査要約 |
| R5 LLM適合 | SessionStart(注入)・llm-context-pack | inject-contract(上限・never 除外)・collect-context | 注入の contract・超過通知 |
| R6 用語統一 | PostToolUse(リンタ)・CI | term-check(_termcheck)・glossary_seed_drift(監査) | リンタ助言・CI ログ |
| R7 境界明瞭 | PreToolUse(ガード)・PostToolUse(block)・SessionEnd/CI(監査) | policy-guard(ICD 依存)・docs-audit(ICD 違反) | deny/block 理由・監査要約 |
| R8 最小性 | SessionEnd/CI(監査)・docs-curate | docs-audit(孤児・canonical 衝突・未登録/影・体系外 .md) | 監査要約・.md-intake |
| R9 保証限界 | CI(受入) | run_tests(保証限界節の存在) | テスト結果 |
| R10 明快な日本語 | PostToolUse(リンタ+ナッジ)・doc-review 定例 | term-check(カルク)・review-nudge・gov-heartbeat(定例督促) | リンタ助言・governance-state |
| R11 統治の生存性 | UserPromptSubmit(毎会話)・SessionStart(注入)・CI | gov-heartbeat(鮮度)・inject-contract(死活警告)・docs-audit(EXT 存在) | 督促・警告・監査要約 |
| R12 会話知識の捕捉 | Stop(終端)・PreCompact(圧縮前)・PostToolUse(印)・SessionStart(選別義務) | capture-nudge・precompact-dump・review-nudge(印)・inject-contract(未選別節) | 差し止め理由・.session-notes・印 |

明示の非目標: 会話の決定の見落としゼロの検出(NONGOAL 第7項)・フックが起動しない経路の予防(NONGOAL 第4項。監査と CI が補う)。

## 制約

- 表の発火経路は hooks.json の 7 イベント(ADR-028)+ CI + 技能の招集だけを使う。ここに無い経路を前提にしない。
- 行を消してよいのは、対応する NONGOAL を足すときだけ。

## エラー時挙動

- hooks.json のイベント集合が本表とずれたら、受入(TEST-025)が赤になる。配線か本表のどちらかを直す。

## 受入基準

- hooks.json のイベント集合 = {SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, PreCompact, SessionEnd}。
- R1〜R12 の全行に発火経路と証跡がある(空白セルなし)。
- 受入は TEST-025 が凍結する。
