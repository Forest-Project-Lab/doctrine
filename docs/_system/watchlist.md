---
id: WATCH-001
title: 横断の退行監視（4項）
type: WATCH
domain: _system
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
review_by: 2026-09-28
llm_context: always
---

# 横断の退行監視（4項）

本文書は、一度直した欠陥を再び戻さないための正本である（[R5]）。各項は、撤回した実装方針を要点だけで残し、根拠となる実コードの位置をIDで示す。同じ方針の再採用を防ぐ。

## 戻してはならない事項

1. PostToolUse（編集後に起動するHook）で削除してよいかを、編集後の状態だけを見て決めてはならない。`_invert_edits` で編集前の全文を復元し、編集前から編集後への遷移で判じる。これは `scripts/policy-guard.py` の `_handle_post_edit` と `_recheck_delete_safety` が担う。根拠: ADR-004。
2. 用語チェッカーは、承認複合語『入出力』に含まれる部分文字列を、投影（モデルから描画した派生表示）の禁止同義語と取り違えてはならない。`scripts/_termcheck.py` の `_mask_approved_compounds` が、承認複合語を長さを保ったまま覆って取り違えを防ぐ。
3. 用語チェッカーの承認辞書を、モジュールの中で二重定義してはならない。`scripts/_termcheck.py` の `load_glossary`／`parse_glossary` が、GLOSSARY 正本（または同梱テンプレート）から読み込む。
4. リンタ（`scripts/docs-linter.py`）は、decision／permissionDecision を出してはならない。助言（additionalContext）だけを返し、拒否はガードに委ねる。

## 撤回日

2026-06-30

## 根拠

ADR-004（編集前の状態を全文で復元する）・DECIDED-001（横断の確定方針）。各項の実コードの位置は、本文に示したIDのとおり。

## 再点検期限

review_by: 2026-09-28

<!-- 入れない: 安定機能 -->
