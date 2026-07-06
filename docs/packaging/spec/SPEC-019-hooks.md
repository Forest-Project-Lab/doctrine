---
id: SPEC-019
title: Hook配線（4イベント／matcher／解決／縮小構成／スナップショット）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-06
sources: [plugin/hooks/hooks.json]
depends_on: [ICD-008, ICD-001, ICD-002, ICD-003, ICD-004, ICD-005, ICD-006, ICD-007]
llm_context: task
---

# Hook配線（4イベント／matcher／解決／縮小構成／スナップショット）

`hooks/hooks.json` が、4 つのイベントを各スクリプトへ配線する仕様である。各スクリプトの中身は相手ドメインの ICD（ICD-001 から ICD-007）に委ね、この仕様は配線だけを所有する `[R9]`。

## 入出力

入力は、Claude Code が各イベントで標準入力に渡すエンベロープ（JSON、構造化データのテキスト表現）である。返す値は、`command` に書いたスクリプトの起動である。配線は次のとおり。

- **SessionStart**: `inject-contract.py` を起動し、最小契約を注入する（context ドメインの ICD-006）。
- **PreToolUse / matcher `Edit|Write|MultiEdit`**: `policy-guard.py` を起動し、三つのガードをかける（guard ドメインの ICD-003）。
- **PreToolUse / matcher `Bash`**: `policy-guard.py` を起動し、削除の安全だけを deny で見る。
- **PostToolUse / matcher `Edit|Write|MultiEdit`**: `policy-guard.py`・`docs-linter.py`・`review-nudge.py` をこの順に並べる（lint ドメインの ICD-004）`[R7][R10]`。`review-nudge.py` は型付き文書の編集に doc-review を促す助言である。
- **SessionEnd**: `docs-audit.py` を起動し、全件を監査する（audit ドメインの ICD-005）。要約を次セッションの注入へ渡すため、`--json --summary-out "${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json" --fail-on never` を付け、`--root "${CLAUDE_PROJECT_DIR}/docs"` を指す。`--fail-on never` で後始末を妨げない。

`command` は、すべて `"${CLAUDE_PLUGIN_ROOT}/scripts/<名>.py"` の形で解決する。`command` はシェル経由で走るため、`${CLAUDE_PLUGIN_ROOT}`・`${CLAUDE_PROJECT_DIR}` を含むパスは必ず二重引用符で囲む。囲まないと、空白を含むパスで語が割れ、フックが起動しないか誤った場所を指す。引数を付ける場合はスクリプトのパスに続けて書く（SessionEnd の `docs-audit.py` だけが、要約の成果物を書くため引数を持つ）。

## 制約

- `command` には、`${CLAUDE_PLUGIN_ROOT}/scripts/` 直下の `.py` だけを書く。第三者のパスは書かない。
- 変数を含むパスは二重引用符で囲む。空白を含むパスでも語が割れないためである。
- スクリプトは直接起動する（`python3` を前置しない）ため、全スクリプトは実行ビットと `python3` のシバンを持つ。実行ビットは git の登録簿（インデックス）に 100755 で記録する。作業ツリーの `chmod` だけでは配布物に載らない。
- matcher は、`Edit|Write|MultiEdit` と `Bash` の二系統だけにする。
- PostToolUse は `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順を守る `[R7]`。先に走る `policy-guard.py` は起動後の違反を拒否しうる。これを、助言だけを返す `docs-linter.py`・`review-nudge.py` より前に判定する。
- 縮小構成 `hooks/hooks.level2.json` は、全構成から SessionEnd の `docs-audit.py` と、PostToolUse の `policy-guard.py`・`review-nudge.py` を外し、PostToolUse を `docs-linter.py` だけにしたものである。監査と依存グラフは Level 3 以降に置く。起動後のブロックには依存グラフが要るからである `[R5]`。
- Hook 設定はセッション開始時にスナップショットして固定する。配線を変えても、そのセッションには反映されず、新しいセッションから反映する。

## エラー時挙動

- 各スクリプトは、通常の運用では終了コード 0 を返し、判定は JSON に載せる。スクリプト自身が異常を起こしたときだけ、非ゼロを返す。
- `Bash` matcher の枝は deny だけを返す。`additionalContext` も `decision:block` もモデルへ届かないからである。

## 受入基準

`hooks.json` が 4 つのイベントを持ち、各 `command` が `${CLAUDE_PLUGIN_ROOT}/scripts/` 配下の `.py` を指し、PostToolUse が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順であり、`hooks.level2.json` が縮小差分であること。空白を含むパスへ置換しても `command` の語数が変わらないこと。全スクリプトが実行ビットとシバンを持つこと。対応テストは TEST-019 と TEST-020。

<!-- 入れない: 廃止、検討、実装コードの写し -->
