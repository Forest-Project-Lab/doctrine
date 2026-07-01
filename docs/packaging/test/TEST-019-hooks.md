---
id: TEST-019
title: Hook配線・e2e連鎖の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_packaging.py, plugin/tests/test_integration_e2e.py]
depends_on: [SPEC-019]
llm_context: task
---

# Hook配線・e2e連鎖の受入

## 受入基準への対応

SPEC-019 の受入基準を確認する。

- `hooks.json` が 4 つのイベント（SessionStart・PreToolUse・PostToolUse・SessionEnd）を持つ。
- 各 `command` が `${CLAUDE_PLUGIN_ROOT}/scripts/` 配下の `.py` を指す。
- PostToolUse の `Edit|Write|MultiEdit` が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順である `[R7][R10]`。
- `Bash` matcher が `policy-guard.py` へ配線されている。
- `hooks.level2.json` が、SessionEnd と、PostToolUse の `policy-guard.py`・`review-nudge.py` を外して `docs-linter.py` だけにした縮小差分である。
- 実スクリプトを標準入力のエンベロープで起動し、scaffold→ガード→リンタ→監査→注入の連鎖がつながる `[R9]`。

## 退行観点

- PostToolUse の配列順が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` から崩れていないこと（WATCH と突き合わせる）。
- 縮小構成が、起動後の `policy-guard.py` を取り戻していないこと。

## 合否基準

`plugin/tests/test_packaging.py`（`TestHooksFullProfile`・`TestHooksLevel2Profile`）と `plugin/tests/test_integration_e2e.py`（実プロセスの連鎖）が、すべて成功すれば合格とする。

<!-- 入れない: 無関係な要求 -->
