---
id: SPEC-012
title: SessionStart 最小契約の注入
type: SPEC
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-06
sources: [plugin/scripts/inject-contract.py]
depends_on: [REQ-010, ICD-001, ICD-005]
llm_context: task
---

# SessionStart 最小契約の注入

`inject-contract.py` は、セッション開始時に常時集合の要点だけを注入する `[R5]`。スクリプトとは、外部から実行する Python 命令をいう。常時集合がふくらめば上限で検出でき、文書の見つけやすさにも役立つ `[R1]`。

## 入出力

- 入力: SessionStart の Hook JSON を標準入力で受け取るが、内容は読み捨てる。引数は `[--docs-root R] [--cap N] [--config PATH] [--format json|text]`。統治木は `--docs-root` → プロジェクト根 → 作業ディレクトリの順に、登録簿の解決（ADR-022: doctrine_docs 優先、docs は `_system` を持つ場合だけ）で決める。日付は受け取らない（古び検出は監査の仕事で、本スクリプトは監査の要約を読むだけ）。未知の引数は無視する。
- 応答: `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":<契約文字列>}}`。
- 契約文字列は次の順に並べる。要点復唱 → 重要文書（冒頭）→ GLOSSARY 見出し → 確定事実（現行の DECIDED）→ NONGOAL → 廃止事実 → WATCH の要点 → 前回監査の要約 → 重要文書（末尾に再掲）→ 超過通知（条件を満たすときだけ）。
- 前回監査の要約は実行可能にする。`top_findings` の同一行は一つにまとめて件数を添える。`counts_by_check` に未登録/影文書（`unregistered_document`・`shadowed_document`）・体系外 .md（`stray_document`）または孤児（`orphan`）が在るとき、あるいは error があるときは、`docs-curate` を名指しで起動する一行を要約に加える（受動の案内に留めない）。この一行は上限超過の有無に依らず出す。
- 登録簿の型既定と現行判定は ICD-001 に、前回監査の要約は ICD-005 の成果物に、それぞれ依存する。

## 制約

- 標準ライブラリだけを使う。pip も通信も使わない。壁時計を読まず、同じ入力には同じ結果を返す（決定的）。
- 上限は `--cap`、`injection_token_cap`、既定 12000 の順に、先に見つかったものを使う。注入とパックは別々の上限を持つ（C10とは凍結した契約の整合を見る判断項目をいう）。
- トークンの見積もりは `ceil(len/4.0)` で計算する。日本語では多めに出る、安全側の近似である。
- 文書の本文全量と never 群の本文は、いずれも含めない `[R5]`。GLOSSARY には承認語と一行の意味だけを載せ、禁止同義語の表は載せない。

## エラー時挙動

- 内容に由来する例外は main の外へ出さない。常に終了コード 0 を返し、セッションを落とさない。何が起きても、空でない妥当な JSON を返す。
- 監査要約が無い、またはスキーマが合わないときは「前回監査なし」と書く。
- 監査要約の `root` が注入先セッションの統治木のルートと一致しない要約は捨て、「前回監査なし」へ劣化する。`${CLAUDE_PLUGIN_ROOT}/.cache` は同じプラグインを使う全プロジェクトで共有されるため、照合しないと別プロジェクトの所見と是正指示を注入してしまう。`root` の無い要約も捨てる（誤注入より無注入が安全側）。
- `_system` が無いときは、ブートストラップの通知だけを返す（空文字列は返さない）。
- `doctrine_docs/` は在るが登録文書（frontmatter に `id` を持つ `.md`）が一つも無いときは、オンボーディングの通知だけを返す。docs-system-init での最小構成の用意と、散在する未登録ファイルの docs-curate での整理・登録を促す（空文字列は返さない）。ブートストラップ（`doctrine_docs/` 自体が無い）とは相互排他である。

## 受入基準

TEST-012 に対応する。次の三つを合否とする。上限を超えたときは要点まで切り詰め、それでも超過通知を必ず出すこと。never 群の本文がどの節にも現れないこと。監査要約の受け渡しが `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（スキーマ `docs-audit/1`）を介して成り立つこと。

<!-- 入れない: 廃止、検討、実装コードの写し -->
