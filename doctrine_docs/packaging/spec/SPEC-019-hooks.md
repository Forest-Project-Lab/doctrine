---
id: SPEC-019
title: Hook配線（7イベント／matcher／解決／縮小構成／スナップショット）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/hooks/hooks.json]
depends_on: [ICD-008, ICD-001, ICD-002, ICD-003, ICD-004, ICD-005, ICD-006, ICD-007]
llm_context: task
---

# Hook配線（7イベント／matcher／解決／縮小構成／スナップショット）

`hooks/hooks.json` が、7 つのイベントを各スクリプトへ配線する仕様である（ADR-028）。各スクリプトの中身は相手ドメインの ICD（ICD-001 から ICD-007）に委ね、この仕様は配線だけを所有する `[R9]`。

## 入出力

入力は、Claude Code が各イベントで標準入力に渡すエンベロープ（JSON、構造化データのテキスト表現）である。**エンベロープの読み取りは共有コア `_hookio.read_payload` に一本化する**（ADR-108）—— **上限（既定 8 MB）は正本が持ち、呼び手は上限の数を書かない。** 以前は三本の Hook が自前で標準入力を読み、**上限を落としていた**（実測: 9 MB のエンベロープを三本とも全部読んだ。変更後は上限で切られ、封筒に依る助言が出なくなる）。読めない・大きすぎるときは空の写像を返し、Hook は封筒が無いときと同じ振る舞いへ退く。**上限に達して切り詰めたときは黙らない**（ADR-109）—— 標準エラーへ一行だけ、部品の名と上限を添えて告げる（Hook が返す JSON の経路は汚さない）。切り詰めの判定は、上限まで読んだあと一文字だけ余分に読んで残りが在るかで行う（**上限ちょうどで残りが無ければ告げない** —— 偽の警告を出さない）。**不具合のジャーナルへは記録しない** —— あれは「部品が実行時に倒れた」記録であり（ADR-074）、**切り詰めは倒れではない**（名が事実を語らなくなる）。**標準エラーが使う人に見えるかは実行環境が決める** —— 保証するのは「書くこと」までである。**封筒を自前で読む Hook が現れたら、メタの受入が落ちる。**返す値は、`command` に書いたスクリプトの起動である。配線は次のとおり。

- **SessionStart**: `inject-contract.py` を起動し、最小契約を注入する（context ドメインの ICD-006）。
- **PreToolUse / matcher `Edit|Write|MultiEdit`**: `policy-guard.py` を起動し、三つのガードをかける（guard ドメインの ICD-003）。
- **PreToolUse / matcher `Bash`**: `policy-guard.py` を起動し、削除の安全だけを deny で見る。
- **PostToolUse / matcher `Edit|Write|MultiEdit`**: `policy-guard.py`・`docs-linter.py`・`review-nudge.py` をこの順に並べる（lint ドメインの ICD-004）`[R7][R10]`。`review-nudge.py` は型付き文書の編集に doc-review を促す助言である。
- **SessionEnd**: `docs-audit.py` を起動し、全件を監査する（audit ドメインの ICD-005）。要約を次セッションの注入へ渡すため、`--json --summary-out "${CLAUDE_PROJECT_DIR}/.claude/.cache/last-audit.json" --fail-on never --respect-docs-level` を付け（プロジェクトスコープ: プラグインの更新で失われず、別プロジェクトと衝突しない）、`--root-from "${CLAUDE_PROJECT_DIR}"` でプロジェクト根を渡す（統治木の解決は docs-audit 側が ADR-022 の優先順で行う。統治木が無ければ静かに飛ばす）。`--fail-on never` で後始末を妨げず、`--respect-docs-level` で Level 2 の体系では監査を飛ばす（ADR-019。CI はこの旗を付けない）。

`command` は、すべて `"${CLAUDE_PLUGIN_ROOT}/scripts/<名>.py"` の形で解決する。`command` はシェル経由で走るため、`${CLAUDE_PLUGIN_ROOT}`・`${CLAUDE_PROJECT_DIR}` を含むパスは必ず二重引用符で囲む。囲まないと、空白を含むパスで語が割れ、フックが起動しないか誤った場所を指す。引数を付ける場合はスクリプトのパスに続けて書く（SessionEnd の `docs-audit.py` だけが、要約の成果物を書くため引数を持つ）。

## 制約

- `command` には、`${CLAUDE_PLUGIN_ROOT}/scripts/` 直下の `.py` だけを書く。第三者のパスは書かない。
- 変数を含むパスは二重引用符で囲む。空白を含むパスでも語が割れないためである。
- スクリプトは直接起動する（`python3` を前置しない）ため、全スクリプトは実行ビットと `python3` のシバンを持つ。実行ビットは git の登録簿（インデックス）に 100755 で記録する。作業ツリーの `chmod` だけでは配布物に載らない。
- matcher は、`Edit|Write|MultiEdit` と `Bash` の二系統だけにする。ツール名は実行環境の仕様への依存であり、EXT-001 のアンカーが `review_by` で定期再検証する（書き込み系ツールの追加・改名は matcher を黙って素通りするため）。
- PostToolUse は `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順を守る `[R7]`。先に走る `policy-guard.py` は起動後の違反を拒否しうる。これを、助言だけを返す `docs-linter.py`・`review-nudge.py` より前に判定する。
- 生存性と捕捉の三イベント（ADR-028）: UserPromptSubmit は `gov-heartbeat.py`（統治の生存と定例の期限。SPEC-021）、Stop は `capture-nudge.py`（記録の確認の一度きりの差し止め。SPEC-022）、PreCompact は `precompact-dump.py`（圧縮前の退避指示。SPEC-022）を起動する。三つとも `.docs-level` に依らず動く（ADR-030）。
- 縮小構成 `hooks/hooks.level2.json` は、全構成から SessionEnd の `docs-audit.py` と、PostToolUse の `policy-guard.py`・`review-nudge.py` を外し、PostToolUse を `docs-linter.py` だけにしたものである。監査と依存グラフは Level 3 以降に置く。起動後のブロックには依存グラフが要るからである `[R5]`。
- 段差の実現は配線の差し替えではなく自主停止である（ADR-019）: 配線は常に全構成 `hooks.json` とし、SessionEnd の監査・PostToolUse の `policy-guard.py`・`review-nudge.py` が `doctrine_docs/_system/.docs-level` を読み、Level 2 では静かに済ませる。`hooks.level2.json` は、プラグインを使わず手で配線する場合の代替として同梱を続ける。手で配線するときは、`${CLAUDE_PLUGIN_ROOT}/scripts/` を実際のスクリプトの場所（退避配置なら `.claude/scripts`）へ書き換えること。書き換えないと変数が未定義のため各 `command` が失敗し、予防が黙って無効になる（fail-open）。手順は `docs-system-init` の `references/fallback.md` に置く（#75）。
- Hook 設定はセッション開始時にスナップショットして固定する。配線を変えても、そのセッションには反映されず、新しいセッションから反映する。
- per-turn のフック（PreToolUse・PostToolUse・UserPromptSubmit・SessionStart）は体感速度を壊さない。実測（1414 文書）で 1 編集あたり合計およそ 0.4 秒。目安は 1 編集あたり 1 秒以内（1500 文書規模）で、数値の確定は受入テストで詰める（開発方法論と性能の上限は ADR-047）。全件監査はセッション境界と CI に隔離し、per-turn では走らせない。
- 縮小構成のイベント集合は「全構成 −{SessionEnd}」とする。生存性（R11）と捕捉（R12）は段差に依らず動く（ADR-030 決定2。ADR-075）。
- フック境界の入出力は共有コア `_hookio` に一本化する。標準の入出力を UTF-8 へ張り替え、書けなければ英数字だけの符号化へ退避し、PreToolUse で書けなければ終了コード 2 へ倒す（ADR-075）。
- 統治木の解決は親をたどる（`walkup_docs_root`）。環境変数が欠けても部分ディレクトリから届く（ADR-075）。

## エラー時挙動

- 各スクリプトは、通常の運用では終了コード 0 を返し、判定は JSON に載せる。スクリプト自身が異常を起こしたときだけ、非ゼロを返す。
- `Bash` matcher の枝は deny だけを返す（ADR-011）。`additionalContext` も `decision:block` もモデルへ届かないからである。段階導入の縮小構成の由来も ADR-011 が定める。

## 実装の指紋

配線そのものは JSON(hooks.json)であり注釈の行を持てないため、設定側の `trace_exempt` が
理由と共に載せる(ADR-072)。一方、フック境界の入出力の契約は共有コアに実体を持つ(ADR-075)。

- sha256:2cde36ea62fbb0b0d2b5888464f14922ce876057327ba00a9696f2ab71cd0a1f

## 受入基準

`hooks.json` が 7 つのイベント（SessionStart・UserPromptSubmit・PreToolUse・PostToolUse・Stop・PreCompact・SessionEnd。ADR-028）を持ち、各 `command` が `${CLAUDE_PLUGIN_ROOT}/scripts/` 配下の `.py` を指し、PostToolUse が `policy-guard.py` → `docs-linter.py` → `review-nudge.py` の順であり、`hooks.level2.json` が縮小差分であること。空白を含むパスへ置換しても `command` の語数が変わらないこと。全スクリプトが実行ビットとシバンを持つこと。イベント集合と要求の対応は被覆マトリクス（SPEC-025）が持つ。対応テストは TEST-019 と TEST-020 と TEST-025。

<!-- 入れない: 廃止、検討、実装コードの写し -->
