---
name: change-impact
description: 'Runs the 14-step change flow for a proposed change: traces dependencies to enumerate every document, implementation, and test affected, then drives the updates in the mandated order — decision (ADR) first, then current spec (SPEC), then implementation, then test, then LLM context, then deprecation cleanup — keeping "what changed" (CHANGE/git) separate from "why decided" (ADR). Grades the flow by whether the change contains a decision, never by its size: a change with no decision (typo, wording, formatting, link repair, projection re-render) keeps only the impact enumeration and the update order, and needs no CHANGE/IMPACT/ADR. Use this skill when the user wants to "assess the impact of a change", "what does changing X break", "plan a change", "run the change flow", "trace impact", "what needs updating if I change this spec/ICD", "影響範囲を洗い出して", "この変更で何が壊れるか", "変更フローを回して", "この仕様を変えたらどこを直すか", or "propose and roll out a change".'
---

# change-impact

## 役割

提案された変更について、14ステップの変更フローを走らせる。依存をたどり、影響する文書・実装・テストを列挙する。更新の順序を守る。満たす要求は §2 の `R3`・`R4`（要求番号は §2 の登録簿で定める）。

## 委ねる先（決定論は scripts へ）

- `${CLAUDE_PLUGIN_ROOT}/scripts/dep-graph.py` — 依存の有向グラフ。前向きに波及先（`impacts`）を、逆向きに依存元（逆参照）を列挙する。ドメイン跨ぎの境界を分類する。逆向きで逆孤児を出す。
- `doc-author`（順序どおりの編集を作る）・`regression-guard`（廃止の段で突き合わせる）・`llm-context-pack`（LLM（大規模言語モデル）へ渡す情報の更新の段で使う）。

## 経路を選ぶ（最初にここで分ける。ADR-051）

段数は変更の規模ではなく、**決定を含むか否か**で分ける。

- **決定を含む** → 下の14ステップを全て回す。規模は問わない。選べる案が複数あり、その一つを選んだなら決定である。既定値・上限・順序・型・境界の変更は、一行でも決定を含む。
- **決定を含まない**（誤字・言い回し・書式・リンクの張り替え・投影の描き直し・`updated` の更新）→ 軽い経路を通る。ステップ 2・3（影響の列挙）と、更新の順序（現行 `SPEC` → 実装 → テスト → 投影）だけを守る。`CHANGE`・`IMPACT`・`ADR` は要らない。
- 途中で決定を含むと分かったら、その場で14ステップへ戻す。軽い経路を通ったこと自体は記録しない。

どちらの経路でも、不変条件の強制は変わらない（削除安全ガード・ICD 依存ガード・全件監査はフックと CI の層にあり、経路を見ていない）。軽い経路が省くのは記録の段であって、強制ではない。

## 更新の順序（§3.8、必ず守る）

`ADR` → 現行 `SPEC` → 実装（`IMPL`）→ テスト（`TEST`）→ LLM へ渡す情報 → 廃止整理。順序を守る。「何を変えたか」（`CHANGE`／git）と「なぜ決めたか」（`ADR`）を分ける。

## 14ステップ

1. 変更を `CHANGE`（`status: proposed`）として捕まえる。変更内容・理由・要求元・影響の初期見積（§3.2）。
2. `dep-graph.py` を対象から前向きに走らせ、波及する文書・実装・テストを列挙する。
3. `dep-graph.py` を逆向きに走らせ、逆参照（その対象に依存する文書）を列挙する。後の安全な廃止に要る。
4. `IMPACT`（`status: current`）を作る。影響する文書・実装・テスト・工数見積（§3.2）。感想は書かない。
5. ドメイン跨ぎの境界を分類する。境界を越える影響は、相手ドメインの ICD を通す（`R7`）。ICD が変わるなら、依存する全ドメインの合意が要ると示す（§3.5）。
6. `ADR` を先に作る（§3.8）。決定を捕まえる（背景・却下した選択肢・決定・帰結、1文書1決定）。これが根拠である。
7. 次に現行 `SPEC` を更新し、決定に合わせる。必須の4節を保つ。
8. データ契約や接点が変わったら、`DATA`・`API` を更新する。
9. 実装。`IMPL` の注記を更新し、影響する部品を指す。
10. テスト。`TEST` を更新する（受入基準への対応・退行観点・合否基準）。新しい受入基準にテストを付け、逆孤児を避ける。
11. LLM へ渡す情報。注入する事実を更新する（`DECIDED`・`NONGOAL`・`WATCH`）。`llm-context-pack` で詰め直す。投影（Overview・Context Map・ICD 一覧）を描き直す。これらはモデルからの投影である。
12. 「戻してはならない」事項が生まれたら `WATCH` を更新し、`review_by` を付ける（`regression-guard` と突き合わせる）。
13. 廃止整理（最後、§3.8）。置換された文書を一段だけ降ろす（現行→廃止→アーカイブ、§3.8 降格）。`superseded_by` を付け、事実は `DECIDED` の対の記録に残し、本文は LLM に渡さない。**不変条件**: 現行の依存が残るうちは降ろさない。同じ変更で、依存元を後継へ張り替えてから降ろす（削除安全ガードが強制する）。
14. 仕上げる。`CHANGE` を閉じる。「何を変えたか」は `CHANGE`／git に、「なぜ」は `ADR` に置く。本文で混ぜない。

## 詳細（references/）

- `references/change-flow.md` — 14ステップを全文で、各段が生む成果物。
- `references/dep-graph-usage.md` — 前向き・逆向き・境界の分類、逆孤児の出方。
- `references/deprecation.md` — §3.8 のライフサイクルの段、依存元の張り替え。
- `references/icd-change.md` — ドメイン間で合意が要る場面。

## 保証限界

- **予防**: 降格の不変条件は削除安全ガード（Hook）が強制する。このスキルは作業を並べ、ガードが発火せずに済むようにする。
- **検出**: 前向きの影響集合と逆向きの依存を dep-graph で出す。逆孤児（要求に対応する仕様の不在、受入基準に対応するテストの不在）を表に出す。dead link と全件の逆方向の追跡性は全件走査が要るので監査に委ねる（§4.2）。
- **委ねる**: 工数見積。その変更が決定を含むかの判定（意味の判断であり、機械では閉じない。ADR-051）。ドメイン間の ICD 合意（人間）。なお、決定を含む変更で順序を省けるかは委ねない（省けない。順序は必須）。
