---
id: IMPL-017
title: パッケージ・Hook配線の実装注記
type: IMPL
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/hooks/hooks.json, plugin/scripts/scaffold.py]
depends_on: [SPEC-019, SPEC-020]
llm_context: task
---

# パッケージ・Hook配線の実装注記

## 実装制約

- `hooks/hooks.json` の PostToolUse は三つのスクリプトを配列で並べ、その順で起動する。`policy-guard.py`・`docs-linter.py`・`review-nudge.py` の順に書く `[R7][R10]`。配列の並びが起動順を決める。
- `hooks/hooks.level2.json` は縮小差分である。SessionEnd を持たず、PostToolUse は `docs-linter.py` だけにする。
- 配線先の `command` は、すべて `${CLAUDE_PLUGIN_ROOT}/scripts/<名>.py` で書く。
- `plugin.json` は最小キーだけを持つ。スクリプトは、標準ライブラリと、兄弟の `_` コアだけを import する `[R5]`。

## 注意点

- 縮小構成にするか `.claude/` へ退避するかは、`scaffold.py` が決める。`_build_plan` が `--level` と `--fallback` を受け取り、`.claude/` の接頭辞と `.docs-level` マーカーを決める。著述者が Hook を手で並べ替えてはならない。
- PostToolUse の並び順を取り違えると、起動後に見つけた境界違反がブロックされず、助言だけで終わる。この配列順は退行監視の対象とする（WATCH を参照）。
- Hook 設定はセッション開始時にスナップショットして固定するので、配線を変えたら、新しいセッションで検証する。

## 対象部品

- `plugin/.claude-plugin/plugin.json`
- `plugin/hooks/hooks.json`・`plugin/hooks/hooks.level2.json`
- `plugin/scripts/scaffold.py`（`_build_plan`・`_docs_level_marker`、および縮小構成か `.claude/` 退避かの選択）

<!-- 入れない: 仕様の正本 -->
