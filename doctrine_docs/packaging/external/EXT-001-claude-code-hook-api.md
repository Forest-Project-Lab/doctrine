---
id: EXT-001
title: Claude Code の Hook 仕様とツール名への依存
type: EXT
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [https://docs.anthropic.com/claude-code]
review_by: 2026-10-26
llm_context: task
---

# Claude Code の Hook 仕様とツール名への依存

統治木の外への依存を登録するアンカーである(ADR-026)。中身は写さない。

## 何に依存しているか

実行環境(Claude Code)の Hook 仕様。イベント名(SessionStart・UserPromptSubmit・PreToolUse・PostToolUse・Stop・PreCompact・SessionEnd)、matcher のツール名(`Edit`・`Write`・`MultiEdit`・`Bash`)、`permissionDecision`/`decision` の意味、`stop_hook_active` の旗、設定がセッション開始時に固定される挙動(ADR-032)。

## 期待

- 対象: `実行環境の仕様(ファイルではない)`
- 検査: review_by のみ(指紋で追えないため、期限で定期再検証する)
- 期待する状態: 上のイベント名・ツール名・意味論が保たれている。書き込み系ツールの追加・改名があれば matcher が黙って素通りするため、再検証で拾う

## 動いたら何が壊れるか

ツール名の改名・追加でガード(SPEC-003)とリンタの発火面が黙って欠ける。イベントの廃止で SPEC-019/SPEC-021/SPEC-022 の配線が沈黙する。挙動が変わったら本アンカーを更新し、SPEC-019 と関係する ADR を置換する。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
