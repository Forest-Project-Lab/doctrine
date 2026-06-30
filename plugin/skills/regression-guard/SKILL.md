---
name: regression-guard
description: Guards against regressions: prevents reviving deprecated approaches or re-adopting a withdrawn decision by cross-checking the proposed change against Decided Facts (DECIDED) and the Regression Watchlist (WATCH), flagging any change that contradicts a current decided fact or reintroduces something the watchlist says must not come back. Use this skill when the user wants to "check for regressions", "are we re-adding something we removed", "does this contradict a decided fact", "check the watchlist", "guard against backsliding", or before re-introducing a previously-rejected approach.
---

# regression-guard

廃止した方針の復活と、撤回した決定の再採用を防ぐ。提案された変更を DECIDED（決定事実）と WATCH（戻してはならない一覧）の正本に突き合わせ、現行の決定事実に反する変更や、戻してはならない項目を再び持ち込む変更を指摘する。主な要求は R5。

この技能は判断の層であり、機械的な拒否は行わない。拒否はガード（不変性・削除安全）の役目である。ここでは検出と助言だけを行い、正しく決定を覆す道筋（新しい ADR）を示す。

## 何に頼るか

- DECIDED 正本（`_system/decided-facts.md`）と WATCH 正本（`_system/watchlist.md` または各ドメインの `test/`）を読み、変更と突き合わせる。
- `dep-graph.py` を逆方向で呼び、廃止・置換した文書へ現行の依存が再び付かないか確かめる。
- `change-impact` の降格・WATCH 更新の段で呼び出される。

## 手順

1. 変更が持ち込む対象（方針・事実・依存）を特定する。
2. DECIDED と突き合わせる。現行の決定事実に反するなら指摘し、覆すには新しい ADR を要ると伝える。決定は ADR でしか変えられない。
3. WATCH と突き合わせる。戻してはならない項目を再び持ち込むなら、元の根拠とともに退行として指摘する。
4. 状態の復活を点検する。廃止・置換・アーカイブの文書を現行へ戻していないか、その本文を再び文脈へ載せていないかを見る（§3.8 はこれを禁じる。廃止本文は LLM へ渡さない。R5）。
5. `review_by` を点検する。変更が触れる DECIDED・WATCH 項目が `review_by` を過ぎているなら、再検討の時期だと記す。期限切れの事実に黙って頼らない。
6. 結果を報告する。見つかった退行、元の決定・WATCH 記録（id と根拠 ADR）、正しく変えるための道筋（新しい ADR と WATCH 更新）を示す。

## 参照

詳細は `references/` に分ける。

- `references/decided-watch-crosscheck.md` — 提案を DECIDED・WATCH 記録へ突き合わせる手順、`review_by` の扱い。
- `references/revival-rules.md` — §3.8 の状態の階段。アーカイブ・廃止が現行や LLM へ戻ってはならない理由。

## 保証限界

R9 の予防／検出／委ねるの切り分けを宣言する。

- 予防: 自身では機械的に予防しない。アーカイブと ADR への編集を止めるのは削除安全ガードと不変性ガードである。この技能は検出して助言する。判断の層であり、Hook ではない。
- 検出: DECIDED への矛盾、WATCH 項目の再導入、状態の不正な復活、`review_by` を過ぎた古い事実を検出する。
- 委ねる: 決定を覆すべきか否かの最終判断は人間に委ねる（ADR で決める）。同じ撤回方針かどうかを言い回しを変えて表したときの意味の一致は §7 の限界であり、語の一致だけでは言い換えを取りこぼす。人間の判断に委ねる。
