---
id: SPEC-013
title: タスク別最小被覆パック
type: SPEC
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/collect-context.py]
depends_on: [REQ-010, ICD-001]
llm_context: task
---

# タスク別最小被覆パック

`collect-context.py` は、あるタスクを覆う最少の文書集合を組み、各事実に出所を付けて渡す `[R5]`。境界違反には印を付けるが、拒否はしない。拒否はガードの職分である `[R7]`。

## 入出力

- 入力: `--task TASKSPEC [--docs-root R] [--domain D] [--require REQ_ID ...] [--format json|md] [--max-tokens N]`。何を覆うかは `--require` が定める。`--require` が無いときは、TASKSPEC（タスク指定の文字列）の語を要求（REQ）の title に照らし、覆う候補を読める範囲で当てる。
- 応答: スキーマ `context-pack/1`、または md 形式。`docs`・`uncovered`・`uncovered_reasons`・`boundary_violations`・`trimmed` を含む。各事実には出所 `〔出所: <id> · <相対パス>〕` を付ける。
- 登録簿の現行判定・型既定・実効 llm_context は、ICD-001 に依存する。

## 制約

- 被覆を計算する前に、never 群を必ず取り除く `[R5]`。never 文書は、たとえ要求を覆っていてもパックに入れない。
- 最少集合の被覆は貪欲法で求め、そのうえで不要になった文書を後ろ向きにそぎ落とす。集合の大きさが同じなら、トークンの少ない方を採る。それも同じなら、id の辞書順で決める（決定的）。
- depends_on をたどって ICD を多段に同梱する。ただし never 文書は、引かないしたどらない。
- 上限は `task_pack_token_cap` を使う（C10とは凍結した契約の整合を見る判断項目をいう）。`injection_token_cap` は読まない。

## エラー時挙動

- 覆えなかった要求は隠さず、uncovered として表に出す。理由（never 群でしか言及されていない／覆う現行文書が無い）も添える。終了コードは 0。
- 引数に不備があるときだけ、終了コード 2 を返す。docs ルートが無くても、空だが妥当なパックを返して 0 とする。
- 境界違反（ドメインをまたぐ依存先が ICD でない）には印を付けるが、拒否はしない。

## 受入基準

TEST-013 に対応する。次の三つを合否とする。never 文書が応答に一切現れないこと。最少集合が決定的に再現すること。`task_pack_token_cap` が `injection_token_cap` と独立に効くこと。

<!-- 入れない: 廃止、検討、実装コードの写し -->
