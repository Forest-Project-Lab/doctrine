---
id: SPEC-022
title: 会話知識の捕捉（終端の確認・圧縮前の退避・次セッションの選別）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-14
sources: [plugin/scripts/capture-nudge.py, plugin/scripts/precompact-dump.py]
depends_on: [REQ-015, ICD-004, ICD-006]
llm_context: task
---

# 会話知識の捕捉（終端の確認・圧縮前の退避・次セッションの選別）

`capture-nudge.py`(Stop)・`precompact-dump.py`(PreCompact)・捕捉の印(lint ドメインの review-nudge が書く。ICD-004)・選別の義務(context ドメインの注入が出す。ICD-006)で、一つの輪を成す仕様である。配線は ADR-028、段差非依存は ADR-030 が定める `[R12]`。

## 入出力

- 捕捉の印: PostToolUse の review-nudge が、型付き文書の編集で `edits-<セッションid>`、記録の型(ADR・DECIDED・WATCH・CHANGE)かセッションメモへの書き込みで `recorded-<セッションid>` の印を残す(置き場はプラグインの cache。Level に依らない)。
- 終端の確認(Stop): `edits` あり ∧ `recorded` なし ∧ 未確認、のときだけ `decision: block` で停止を差し止め、「記録するか、決定なしと明言するか」を問う。それ以外は無音。
- 圧縮の印(PreCompact): 圧縮が起きた時刻を印(`compacted`)として原子的に残すだけとし、モデルへは何も返さない。**この事象は文脈を運ばない**ので、載せても届かない(ADR-077)。会話本文も推論過程も写さない。
- 圧縮の後の合図(SessionStart): この起動が圧縮を跨いでいるとき、保護節で「圧縮前の詳細は失われている。いま思い出せる未記録の決定を `_system/.session-notes` へ一行ずつ(`- <一文の事実> (出所: 会話, YYYY-MM-DD)`)書け」と告げる。跨いだかの判定は二つの入口を持つ —— `source` が `compact`、または圧縮の印が前回の注入の印より後。どちらか一方が生きていれば合図は出る。
- 選別の義務: `_system/.session-notes` に未選別の行があるかぎり、SessionStart の注入が保護節で選別(doc-author で ADR・DECIDED へ、または破棄の明言)を義務として出し続ける。

## 制約

- 差し止めはセッションに一度だけ。`stop_hook_active` と `nudged-<セッションid>` の二重の歯止めで無限ループを防ぐ。印を残せないときは問わない(ループの恐れを避ける)。
- 決定論の拒否ではない。中身(記録する/決定なしと明言する)は判断層と人間に委ねる。
- 7 日より古い印は掃除する(たまり続けない)。
- セッションメモは受信箱であり正本ではない。事実の正本は選別後の ADR・DECIDED である。

## エラー時挙動

- エンベロープが読めない・session_id が無い・印の置き場が作れないときは無音で通す。
- 圧縮の印が書けない環境では、黙って諦める(合図が出ないだけで、何も壊さない)。印が読めない・時刻が壊れているときは、合図を出さない側へ倒す。
- 想定外の例外は握りつぶして静かに終わる。終了コードは常に 0。

## 実装の指紋

対象は記録に数える型(R12)。更新は `trace-index.py --id SPEC-022` が返す行を写す（ADR-061）。

- sha256:aa8a749aed0be9930fc0e8830d6d83165f68dd451ca4190ced352dfda42e4138
- sha256:e1897521264fbda1388f6dfcbe6fb222600ee6dfa4bfa68ce7ce9193084832d3
- sha256:843048301cef4c7da38d3138b12d3ff0cbecad7d9b1af300731059ee8db87894

## 受入基準

- 統治文書を編集し記録に触れないセッションの終端は、一度だけ差し止められる。二度目は無音。
- 記録の型かセッションメモに触れたセッションは差し止められない。
- PreCompact が `additionalContext` を返さず、圧縮の印を残す。
- `source` が `compact` の注入、および印だけが新しい注入で、圧縮の後の合図が出る。前回の注入より古い圧縮では出ない。
- 未選別の行がある注入は選別の義務を出す。
- 受入は TEST-022 が凍結する。
