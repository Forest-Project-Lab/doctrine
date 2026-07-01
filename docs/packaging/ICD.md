---
id: ICD-008
title: packaging のインターフェース（配布物の形・Hook配線・段差）
type: ICD
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.3]
canonical_for: [plugin-packaging, hook-wiring, level-staging]
llm_context: task
---

# packaging ICD

packaging ドメインは、配布物の形（`plugin.json`）、Hook の配線（`hooks/hooks.json`）、段階導入の各段（Level 2/3/4）を所有する。この ICD は、他ドメインが依存してよい唯一の入口である。

## 公開する用語

- **Hook**: イベントが起きたときに Claude Code が起動する外部スクリプト。
- **`${CLAUDE_PLUGIN_ROOT}`**: プラグインの配置先を指す環境変数。Hook は、起動するスクリプトのパスをこの変数から組み立てる。
- **段（Level 2/3/4）**: 体系の重さを利用者の規模に合わせる段階。段ごとに、使える型・スクリプト・Hook が変わる。
- **縮小構成**: Level 2 向けに Hook を減らした配線。正本は `hooks/hooks.level2.json`。
- **スナップショット**: セッション開始時に Hook 設定を読み取って固定し、そのセッションの間は変えないこと。

## 正本である事実

このドメインだけが正本である事実は、次の三つである（canonical_for と一致する）。

- **plugin-packaging**: 配布は `/plugin install` で行う。プラグインを配置できないときは `.claude/` へ退避する。スクリプトは標準ライブラリだけで動く。`plugin.json` の最小キーは、name=`doctrine`、version=`0.1.0`、license=MIT の三つである。
- **hook-wiring**: 4 つのイベント（SessionStart・PreToolUse・PostToolUse・SessionEnd）を各スクリプトへ対応づける。matcher は `Edit|Write|MultiEdit` と `Bash` の二系統に分ける。PostToolUse では `policy-guard.py`・`docs-linter.py`・`review-nudge.py` をこの順に起動する。
- **level-staging**: Level 2 では縮小構成として `hooks/hooks.level2.json` を置く。Level 3 で監査と依存グラフを、Level 4 で投影の一式を足す。Hook 設定は、セッション開始時にスナップショットして固定する。

## データ契約

他ドメインが依存してよい事実は、次のとおりである。

- **配置規約**: Hook の `command` は、すべて `${CLAUDE_PLUGIN_ROOT}/scripts/<名>.py` の形で書く。
- **PostToolUse の起動順**: matcher `Edit|Write|MultiEdit` では、拒否しうる `policy-guard.py` を先に、助言だけを返す `docs-linter.py`・`review-nudge.py` を後に、この順で並べる。
- **縮小差分**: `hooks.level2.json` は、全構成から SessionEnd の `docs-audit.py` と、PostToolUse の `policy-guard.py`・`review-nudge.py` を外し、PostToolUse を `docs-linter.py` だけにしたものである。
- **段マーカー**: 現に選んでいる Level は、`docs/_system/.docs-level`（`level: N` の一行）に書き、他のスクリプトがここから読む。

## 依存してよい入口

他ドメインは、この ICD（ICD-008）だけを depends_on に書ける。packaging 内部の SPEC・IMPL・TEST を直接 depends_on に書いてはならない。

<!-- 入れない: 内部実装、内部の検討 -->
