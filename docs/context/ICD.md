---
id: ICD-006
title: context のインターフェース（注入・パック・投影描画の契約）
type: ICD
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §3.9]
canonical_for: [context-injection, context-pack, projection-render]
llm_context: task
---

# context ICD

## 公開する用語

- 注入: セッション開始時に、常時集合の要点だけを additionalContext として渡す契約。用語辞書の該当語に従う。
- パック: あるタスクを覆う最少の文書集合のこと。様式は `context-pack/1`。
- 投影: モデルから決定論で描画した派生表示で、手では保守しない。ここでモデルとは §3 の登録簿と各文書のフロントマターを指す。フロントマターとは文書冒頭の YAML メタデータをいう。

## 正本である事実

この ICD は、次の三つの事実について唯一の正本となる。

- context-injection: 注入は常時集合（DECIDED・NONGOAL・WATCH・廃止事実・GLOSSARY 見出し）を要点に絞り、上限を守って渡す。文書の本文全量と never 群の本文は、いずれも注入には混ぜない。
- context-pack: タスク別パックは、被覆を計算する前に never 群を取り除く。そのうえで最少集合と、各事実の出所を返す。
- projection-render: 投影（Overview・ICD 一覧・Context Map の骨組み）は正本から描画する。同じ源からは何度描いても同じ結果になり（冪等）、手では書き溜めない。

## データ契約

他ドメインが依存してよい境界は、次のとおりである。

- 注入応答: SessionStart に対する Hook の応答 JSON `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":<文字列>}}`。終了コードは常に 0。Hook とは、Claude Code がツール実行やセッションの節目で呼ぶ外部命令をいう。
- 二つの別々の上限（C10とは凍結した契約の整合を見る判断項目をいい、これはその一つ）: 注入の `injection_token_cap`（既定 12000）と、パックの `task_pack_token_cap`（任意）。どちらも `_system/.context-config.json` の別キーに置く。トークンとは、モデルが文を区切って数える単位をいう。見積もりは文字数からの近似で、多めに見積もる側に倒す。
- 監査要約の受け渡し: 注入は `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（スキーマ `docs-audit/1`）を読む。これは audit（ICD-005）が書いた成果物である。
- パック様式: `context-pack/1`。`docs`・`uncovered`・`uncovered_reasons`・`boundary_violations`・`trimmed` を含む。

## 依存してよい入口

他ドメインは、この文書（ICD）だけを depends_on できる。注入・パック・投影の各スクリプトの内部部品を名指しして依存してはならない。

<!-- 入れない: 内部実装、内部の検討 -->
