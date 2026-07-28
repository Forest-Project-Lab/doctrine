---
id: WATCH-001
title: 横断の退行監視（7項）
type: WATCH
domain: _system
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-28
sources: [spec/doctrine.ja.md]
review_by: 2026-09-28
llm_context: always
---

# 横断の退行監視（7項）

本文書は、一度直した欠陥を再び戻さないための正本である（[R5]）。各項は、撤回した実装方針を要点だけで残し、根拠となる実コードの位置をIDで示す。同じ方針の再採用を防ぐ。

## 戻してはならない事項

1. PostToolUse（編集後に起動するHook）で削除してよいかを、編集後の状態だけを見て決めてはならない。`_invert_edits` で編集前の全文を復元し、編集前から編集後への遷移で判じる。これは `plugin/scripts/policy-guard.py` の `_handle_post_edit` と `_post_delete_safety`（`_reconstruct_pre_edit_state`・`_invert_edits`）が担う。根拠: ADR-004。
2. 用語チェッカーは、承認複合語『入出力』に含まれる部分文字列を、投影（モデルから描画した派生表示）の禁止同義語と取り違えてはならない。`plugin/scripts/_termcheck.py` の `_mask_approved_compounds` が、承認複合語を長さを保ったまま覆って取り違えを防ぐ。
3. 用語チェッカーの承認辞書を、モジュールの中で二重定義してはならない。`plugin/scripts/_termcheck.py` の `load_glossary`／`parse_glossary` が、GLOSSARY 正本（または同梱テンプレート）から読み込む。
4. リンタ（`plugin/scripts/docs-linter.py`）は、decision／permissionDecision を出してはならない。助言（additionalContext）だけを返し、拒否はガードに委ねる。
5. リンタ（`plugin/scripts/docs-linter.py`）は、監査が『非文書／投影』と認めたファイル、および統治木の根に到達できない体系外のファイルに、schema/frontmatter の ERROR（`MISSING_FRONTMATTER` ほか）を出してはならない。判定の前に統治木を探し、intake の読み取りは監査と共有する `plugin/scripts/_intake.py` を使う。監査（全体を見る）とリンタ（一件を見る）の判定が食い違わないことは、リポジトリ直下の `scripts/consistency-check.py`（SPEC-023。配布物の `plugin/scripts/` とは別の場所）が守る。根拠: ADR-024。
6. 受理した ADR の帰結を、実装と SPEC へ落とさないまま完了と見なしてはならない。決定が現行の文書（ADR と投影を除く）から一度も参照されない状態は「文書上の宣言に留まる」欠陥類型であり（ADR-019・ADR-020・ADR-014 で三度起きた）、監査の adr_not_landed 検査（`plugin/scripts/docs-audit.py`、SPEC-011）が warn で挙げる。
7. ビュー（正本を解釈した体系外の文書）を「非文書」へ再分類して刻印の義務を逃れさせてはならない。正本から導かれた主張を含む .md はビューとする（外部レビューが README の主張3件の古びを指した実害が根拠。ADR-073）。再分類の当否は機械では判定できず、docs-curate の定例が分類の見直しで守る。公開ビュー3件（README.md・plugin/README.md・CONTRIBUTING.md）の刻印は `scripts/release-check.py`（SPEC-027）が門で強制する。この一覧から公開ビューを外すときは ADR を要する。

## 撤回日

- 第1項〜第4項: 2026-06-30
- 第5項: 2026-07-22
- 第6項: 2026-07-26
- 第7項: 2026-07-28

## 根拠

第1項: ADR-004（編集前の状態を全文で復元する）。第2項・第3項: ADR-018（辞書駆動の覆い）・ADR-005（辞書の単一符号化）。第4項: SPEC-007（助言のみ）。第5項: ADR-024。第6項: SPEC-011 の adr_not_landed 検査。第7項: ADR-073（ビューと刻印）・SPEC-027（公開ビューの門）。横断: DECIDED-001（横断の確定方針）。各項の実コードの位置は、本文に示したIDのとおり。

## 再点検期限

review_by: 2026-09-28

<!-- 入れない: 安定機能 -->
