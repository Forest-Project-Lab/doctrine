---
id: TEST-019
title: Hook配線・e2e連鎖の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-07
sources: [plugin/tests/test_packaging.py, plugin/tests/test_integration_e2e.py]
depends_on: [SPEC-019]
llm_context: task
---

# Hook配線・e2e連鎖の受入

## 受入基準への対応

- 切り詰めを告げること（ADR-109）: 上限を超えた封筒で標準エラーに一行が出て、**部品の名**を含むこと。**上限ちょうどで残りが無ければ告げない**こと（偽の警告を出さない）。**不具合のジャーナルへ記録しない**こと（倒れではない）。**歯止め自身の実効を実測してある**（2026-08-03）: 告知を外す／切り詰めていなくても告げる／倒れとして記録する、の三通りで落ち、いずれも戻すと通った。端から端でも測った —— 9 MB の封筒で三本とも自分の名で告げる（変更前は stdout も stderr も空だった）。
- エンベロープの読み取りが共有コア `_hookio.read_payload` に一本化されていること（ADR-108）。**上限が正本に在る**こと（構造）と、**上限を超えた封筒が空になる**こと（振る舞い）。**封筒を自前で読む Hook が無い**こと。**歯止め自身の実効を実測してある**（2026-08-03）: 自前の読み取りへ戻す／正本から上限を外す／写しを一つ作る、の三通りで落ち、いずれも戻すと通った。前後比較も取った —— 9 MB の封筒に文書の道を入れると、変更前は助言が出て（261字）、変更後は出ない（0字）。
SPEC-019 の受入基準を確認する。

- `hooks.json` が必要なイベント（SessionStart・UserPromptSubmit・PreToolUse・PostToolUse・Stop・PreCompact・SessionEnd。ADR-028）を**すべて持つ**（test_packaging の test_required_events_are_all_wired）。集合の上限は凍らせない —— 事象を増やしても落ちず、減らせば落ちる（ADR-078）。
- 各 `command` が `${CLAUDE_PLUGIN_ROOT}/scripts/` 配下の `.py` を指す。
- PostToolUse の `Edit|Write|MultiEdit` が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順である `[R7][R10]`。
- `Bash` matcher が `policy-guard.py` へ配線されている。
- `hooks.level2.json` が、SessionEnd と、PostToolUse の `policy-guard.py`・`review-nudge.py` を外して `docs-linter.py` だけにした縮小差分である。
- 変数を空白入りパスへ置換しても、各 `command` の語数が変わらない（二重引用符の検査）。
- 実スクリプトを標準入力のエンベロープで起動し、scaffold→ガード→リンタ→監査→注入の連鎖がつながる `[R9]`。
- ADR-075: 縮小構成のイベント集合が「全構成 −{SessionEnd}」であること。UserPromptSubmit・Stop・PreCompact が配線されていること。
- ADR-075: 環境変数が欠け、作業ディレクトリが部分ディレクトリでも、統治木へ届くこと。

## 退行観点

- PostToolUse の配列順が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` から崩れていないこと（WATCH と突き合わせる）。
- 縮小構成が、起動後の `policy-guard.py` を取り戻していないこと。

## 合否基準

`plugin/tests/test_packaging.py`（`TestHooksFullProfile`・`TestHooksLevel2Profile`）と `plugin/tests/test_integration_e2e.py`（実プロセスの連鎖）が、すべて成功すれば合格とする。

<!-- 入れない: 無関係な要求 -->
