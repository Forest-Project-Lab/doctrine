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

実行環境(Claude Code)の Hook 仕様。依存しているのは**能力**であって、事象名の一覧ではない(ADR-078)。名前の列挙は `review_by` の周期より速く動くので、ここには持たない。

| 依存している能力 | いま使っている入口 |
|---|---|
| セッション冒頭に文脈を注入できる | `SessionStart`(`source` を運ぶ。`compact` を含む) |
| 会話ごとに文脈を注入できる | `UserPromptSubmit` |
| ツール実行の前に拒否できる | `PreToolUse` の `permissionDecision` |
| ツール実行の後に差し止められる | `PostToolUse` の `decision` |
| ターンの終端で差し止められる | `Stop`(`stop_hook_active` の旗で無限ループを防ぐ) |
| 圧縮が起きたことを知れる | `PreCompact`(**文脈は運ばない**。ADR-077) |
| セッション終了で後始末できる | `SessionEnd` |
| matcher でツールを絞れる | `Edit`・`Write`・`MultiEdit`・`Bash` |

`additionalContext` を運ぶ事象は限られており、`PreCompact` は含まれない(ADR-077)。
`SubagentStart` は運ぶ(ADR-079。配線するかは未決)。

設定の反映は**層で違う**(ADR-080。ADR-032 を置換):

| 層 | 挙動 |
|---|---|
| settings 由来の hooks(user・project・local・managed) | セッション中に live reload される。変更ごとに `ConfigChange` が発火する |
| インストール済み plugin の hooks | セッション中は保持され、`/reload-plugins` で再読込される |

## 期待

- 対象: `実行環境の仕様(ファイルではない)`
- 検査: review_by のみ(指紋で追えないため、期限で定期再検証する)
- 期待する状態: 上のイベント名・ツール名・意味論が保たれている。書き込み系ツールの追加・改名があれば matcher が黙って素通りするため、再検証で拾う

## 動いたら何が壊れるか

ツール名の改名・追加でガード(SPEC-003)とリンタの発火面が黙って欠ける。イベントの廃止で SPEC-019/SPEC-021/SPEC-022 の配線が沈黙する。挙動が変わったら本アンカーを更新し、SPEC-019 と関係する ADR を置換する。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
