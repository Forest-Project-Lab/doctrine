---
id: ADR-028
title: Hook を 7 イベントに広げ、生存性と捕捉を発火面に載せる
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [全体批判レビュー 2026-07-26]
depends_on: [ICD-008]
---

# Hook を 7 イベントに広げ、生存性と捕捉を発火面に載せる

## 背景

従来の 4 イベント(SessionStart・PreToolUse・PostToolUse・SessionEnd)は、すべてファイル操作かセッション境界に反応する。会話の中の決定には何も発火せず(記録が取られない)、統治自身の死には何も鳴らず(4 日間の全停止に気づけない)、圧縮による文脈の消失には介入できなかった。加えて本リポジトリは `.claude/settings.local.json` で 5 番目のイベント(UserPromptSubmit)を既に運用しており、仕様(4 イベント)と実態が食い違っていた。

## 却下した選択肢

- 4 イベントのまま運用規約で補う: 「文書上の宣言に留まる」欠陥類型の再生産になる。
- 全イベントを配線する: Notification 等は統治の要求に対応する仕事が無い。空の配線は最小性に反する。

## 決定

`hooks/hooks.json` を 7 イベントにする。追加は三つ。(1) UserPromptSubmit → `gov-heartbeat.py`(統治の生存と定例の期限の照合。R11)。(2) Stop → `capture-nudge.py`(統治文書を編集したのに記録に触れていないセッションの終端を一度だけ差し止めて問う。R12)。(3) PreCompact → `precompact-dump.py`(圧縮前に未記録の決定を `_system/.session-notes` へ退避させる指示。R12)。三つとも Level の段差に依らず動く(ADR-030)。

## 帰結

- SPEC-019 を 7 イベントに改訂する。受入は hooks.json のイベント集合をテストで凍結する。
- 追加イベントは助言と一度きりの差し止めに限り、決定論の拒否(deny)は従来どおり PreToolUse だけが持つ。
- Hook 設定はセッション開始時に固定される前提(ADR-032)は変わらない。反映には新しいセッションが要る。
