---
id: SPEC-012
title: SessionStart 最小契約の注入
type: SPEC
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/scripts/inject-contract.py]
depends_on: [REQ-010, ICD-001, ICD-005]
llm_context: task
---

# SessionStart 最小契約の注入

`inject-contract.py` は、セッション開始時に常時集合の要点だけを注入する `[R5]`。スクリプトとは、外部から実行する Python 命令をいう。常時集合がふくらめば上限で検出でき、文書の見つけやすさにも役立つ `[R1]`。

## 入出力

- 入力: SessionStart の Hook JSON を標準入力で受け取るが、内容は読み捨てる。引数は `[--docs-root R] [--cap N] [--config PATH] [--format json|text] [--today YMD]`。
- 応答: `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":<契約文字列>}}`。
- 契約文字列は次の順に並べる。要点復唱 → 重要文書（冒頭）→ GLOSSARY 見出し → 確定事実（現行の DECIDED）→ NONGOAL → 廃止事実 → WATCH の要点 → 前回監査の要約 → 重要文書（末尾に再掲）→ 超過通知（条件を満たすときだけ）。
- 登録簿の型既定と現行判定は ICD-001 に、前回監査の要約は ICD-005 の成果物に、それぞれ依存する。

## 制約

- 標準ライブラリだけを使う。pip も通信も使わない。壁時計を読まず、同じ入力には同じ結果を返す（決定的）。
- 上限は `--cap`、`injection_token_cap`、既定 12000 の順に、先に見つかったものを使う。注入とパックは別々の上限を持つ（C10とは凍結した契約の整合を見る判断項目をいう）。
- トークンの見積もりは `ceil(len/4.0)` で計算する。日本語では多めに出る、安全側の近似である。
- 文書の本文全量と never 群の本文は、いずれも含めない `[R5]`。GLOSSARY には承認語と一行の意味だけを載せ、禁止同義語の表は載せない。

## エラー時挙動

- 内容に由来する例外は main の外へ出さない。常に終了コード 0 を返し、セッションを落とさない。何が起きても、空でない妥当な JSON を返す。
- 監査要約が無い、またはスキーマが合わないときは「前回監査なし」と書く。
- `_system` が無いときは、ブートストラップの通知だけを返す（空文字列は返さない）。

## 受入基準

TEST-012 に対応する。次の三つを合否とする。上限を超えたときは要点まで切り詰め、それでも超過通知を必ず出すこと。never 群の本文がどの節にも現れないこと。監査要約の受け渡しが `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（スキーマ `docs-audit/1`）を介して成り立つこと。

<!-- 入れない: 廃止、検討、実装コードの写し -->
