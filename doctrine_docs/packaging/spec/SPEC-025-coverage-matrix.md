---
id: SPEC-025
title: 被覆マトリクス（統治要求×発火経路×証跡）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-27
sources: [plugin/hooks/hooks.json, .github/workflows/checks.yml]
depends_on: [REQ-014, ICD-008]
llm_context: task
---

# 被覆マトリクス（統治要求×発火経路×証跡）

各統治要求が、どの発火経路(いつ動くか)に結線され、どんな証跡(動いた事実の残滓)を残すかの一覧である。空白のセルが構造的に存在できない状態を保つ — 全ての行は「結線済み」か「明示の非目標(NONGOAL)」のどちらかである。発火経路を足す・消すときは本表を更新し、受入(TEST-025)が hooks.json のイベント集合との一致を凍結する `[R11][R9]`。

## 入出力

- 入力: 統治要求(R1〜R12)と発火経路(7 イベント・CI・技能)。
- 返す値: 下の表。行の追加・変更は本文書の編集であり、配線の変更(hooks.json)と同じ変更で行う。

| 要求 | 発火経路(いつ) | 実行するもの | 証跡 | Level 2(既定)での担保 |
|---|---|---|---|---|
| R1 見つけやすさ | SessionEnd/CI(監査)・docs-curate | docs-audit(投影ドリフト・孤児)・render-projection | 監査要約・投影の updated | CI 委任(全件監査は Level 3 以降) |
| R2 現行性 | PostToolUse(リンタ)・SessionEnd/CI(監査)・UserPromptSubmit(督促) | docs-linter(`status`)・docs-audit(review_by 超過・stale_current)・gov-heartbeat | リンタ助言・監査要約・督促 | 在席(リンタの `status`)＋古びは CI 委任 |
| R3 追跡性 | PostToolUse(リンタ)・SessionEnd/CI(監査) | docs-linter(MISSING_TRACE)・docs-audit(逆孤児・adr_not_landed・trace_*) | 同上 | 在席(リンタ)＋逆孤児と追跡は CI 委任 |
| R4 変更耐性 | PreToolUse(ガード)・SessionEnd/CI(監査)・change-impact | policy-guard(削除安全)・docs-audit(dead link・source_drift・trace_stale) | deny 理由・監査要約 | 在席(予防)＋dead link と追跡は CI 委任 |
| R5 LLM適合 | SessionStart(注入)・llm-context-pack | inject-contract(上限・never 除外)・collect-context | 注入の contract・超過通知 | 在席(注入は全 Level) |
| R6 用語統一 | PostToolUse(リンタ)・CI | term-check(_termcheck)・glossary_seed_drift(監査) | リンタ助言・CI ログ | 在席(リンタ)＋シード退行は CI 委任 |
| R7 境界明瞭 | PreToolUse(ガード)・PostToolUse(block)・SessionEnd/CI(監査) | policy-guard(ICD 依存)・docs-audit(ICD 違反) | deny/block 理由・監査要約 | 在席(予防)＋事後 block・違反検出は CI 委任 |
| R8 最小性 | SessionEnd/CI(監査)・docs-curate | docs-audit(孤児・canonical 衝突・未登録/影・体系外 .md) | 監査要約・.md-intake | CI 委任(全件監査) |
| R9 保証限界 | CI(受入) | run_tests(保証限界節の存在) | テスト結果 | CI 委任 |
| R10 明快な日本語 | PostToolUse(リンタ+ナッジ)・doc-review 定例 | term-check(カルク)・review-nudge・gov-heartbeat(定例督促) | リンタ助言・governance-state | 在席(リンタ)＋ナッジは Level 3 以降 |
| R11 統治の生存性 | UserPromptSubmit(毎会話)・SessionStart(注入)・CI | gov-heartbeat(鮮度)・inject-contract(死活警告)・docs-audit(EXT 存在) | 督促・警告・監査要約 | CI 委任(死活は Level 3 以降。ADR-046) |
| R12 会話知識の捕捉 | Stop(終端)・PreCompact(圧縮の印)・SessionStart(圧縮後の合図・選別義務)・PostToolUse(印) | capture-nudge・precompact-dump(印のみ)・inject-contract(圧縮後の節・未選別節)・review-nudge(印) | 差し止め理由・圧縮の印・.session-notes・印 | 在席(段差に依らず動く。ADR-030) |

明示の非目標: 根拠を持たないコードの検出(注釈は任意であり原理的に判じられない。ADR-054 の既知の限界)・会話の決定の見落としゼロの検出(NONGOAL 第7項)・フックが起動しない経路の予防(NONGOAL 第4項。監査と CI が補う)・ガードが拒否できる状態かの検出(NONGOAL 第9項。ADR-050。R11 の証跡は監査の要約の鮮度までで、ガードの往復は覆わない)。

コードと仕様の双方向トレースを将来この被覆の可視へ接続する構想は、条件付きの段階拡張として ADR-048 が方向を定める(統治範囲の拡張は別 ADR で裁く・試験結果の本文は取り込まない・既存の機構の拡張として設計する)。本表はその接続先の土台である。段1〜4 は実装済みで、追跡の検査(trace_*)は R3 と R4 の行に結線した。ただし効くのは仕様が `## 実装の指紋` の節を持つときだけであり(ADR-056 の opt-in)、節を持つ仕様が無ければ走査そのものを行わない(使っていない機能の費用を払わせない)。索引を人へ見せる編集画面の表示層については、実装より先に制約だけを ADR-052 が凍らせる(表示層に限る・索引が無ければ黙る・中核は CLI が持つ)。表示層は本表に行を足さない。統治判断を持たないため、担保する要求を持たないからである。

「Level 2 での担保」の列は、各要求が既定の Level 2 でセッション内に効くか、CI に委ねるかを示す(#94。ADR-046 の境界を要求ごとに可視にする)。空白のセルを許さない原則は全列に及ぶ。NASA（米国航空宇宙局）の NPR（手順要求。Procedural Requirements）が定める保証マトリクス(全セルを Full/Tailored/N-A で埋め空欄を許さない)に対応する最小の形であり、Level の列が Tailored(段階導入で縮む)を、明示の非目標が N-A を、残りが Full を表す。

## 制約

- 表の発火経路は hooks.json の 7 イベント(ADR-028)+ CI + 技能の招集だけを使う。ここに無い経路を前提にしない。
- 行を消してよいのは、対応する NONGOAL を足すときだけ。

## エラー時挙動

- hooks.json のイベント集合が本表とずれたら、受入(TEST-025)が赤になる。配線か本表のどちらかを直す。

## 実装の指紋

- コード対応なし: 本文書の表そのものが実装である

## 受入基準

- hooks.json のイベント集合 = {SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, PreCompact, SessionEnd}。
- R1〜R12 の全行に発火経路・証跡・「Level 2 での担保」がある(空白セルなし。#94)。
- 受入は TEST-025 が凍結する。
