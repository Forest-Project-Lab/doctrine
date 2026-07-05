---
id: OVERVIEW-001
title: 現行文書の一覧
type: OVERVIEW
domain: _system
status: current
owner: render-projection
updated: 2026-07-02
llm_context: always
sources: []
---

描画される。手で編集しない。

# Overview

| id | type | domain | title |
|---|---|---|---|
| GLOSSARY-001 | GLOSSARY | _system | 用語辞書の正本 |
| DECIDED-001 | DECIDED | _system | 横断の確定方針（8事実） |
| NONGOAL-001 | NONGOAL | _system | 横断のやらないこと（6項） |
| WATCH-001 | WATCH | _system | 横断の退行監視（4項） |
| ICD-005 | ICD | audit | audit のインターフェース（全件監査の境界） |
| REQ-008 | REQ | audit | 最小性の監査（過剰と不足の両側を全件検出） |
| SPEC-011 | SPEC | audit | 全件監査の検査群・要約スキーマ・決定性 |
| ADR-008 | ADR | audit | 孤児を三条件の連言で定義する |
| IMPL-011 | IMPL | audit | docs-audit.py の実装メモ |
| TEST-011 | TEST | audit | 監査の検査群テスト計画 |
| ICD-007 | ICD | authoring | authoring のインターフェース（作成・初期化・支援） |
| REQ-011 | REQ | authoring | 型付き文書を正しい場所と様式で作り初期化は非破壊・最小に保つ |
| REQ-012 | REQ | authoring | 判断の層（技能と候補語抽出）が決定論を補い保証限界を明示する |
| SPEC-015 | SPEC | authoring | scaffold（_system 非破壊シード） |
| SPEC-016 | SPEC | authoring | skills（7技能を一仕様で） |
| SPEC-017 | SPEC | authoring | templates（19型＋icd-index） |
| SPEC-018 | SPEC | authoring | term-extract（c-TF-IDF 候補語抽出） |
| ADR-010 | ADR | authoring | 作成・初期化の設計判断（7技能固定・遅延生成・テンプレが語彙符号化） |
| IMPL-015 | IMPL | authoring | scaffold/term-extract の実装注記 |
| IMPL-016 | IMPL | authoring | skills/templates の実装注記 |
| TEST-015 | TEST | authoring | scaffold の検証 |
| TEST-016 | TEST | authoring | skills の検証 |
| TEST-017 | TEST | authoring | templates の検証 |
| TEST-018 | TEST | authoring | term-extract の検証 |
| ICD-006 | ICD | context | context のインターフェース（注入・パック・投影描画の契約） |
| REQ-009 | REQ | context | 見つけやすさ（投影を正本から決定論で描画） |
| REQ-010 | REQ | context | LLM適合（常時投入を最小に・never群を渡さない） |
| SPEC-012 | SPEC | context | SessionStart 最小契約の注入 |
| SPEC-013 | SPEC | context | タスク別最小被覆パック |
| SPEC-014 | SPEC | context | 投影の決定論描画 |
| ADR-009 | ADR | context | 注入とパックで二つの別上限を持つ（C10） |
| ADR-014 | ADR | context | DECIDED へ写すのは横断の確定事実だけとする |
| ADR-016 | ADR | context | 投影を正本から描画し直せる派生表示に限り、刊行物は投影一覧に含めない |
| IMPL-012 | IMPL | context | `inject-contract.py` の実装メモ |
| IMPL-013 | IMPL | context | `collect-context.py` の実装メモ |
| IMPL-014 | IMPL | context | `render-projection.py` の実装メモ |
| TEST-012 | TEST | context | inject-contract のテスト計画 |
| TEST-013 | TEST | context | collect-context のテスト計画 |
| TEST-014 | TEST | context | render-projection のテスト計画 |
| ICD-002 | ICD | graph | graph のインターフェース（依存グラフ問い合わせ契約） |
| REQ-002 | REQ | graph | 追跡性（要求→仕様→実装→テスト→決定をたどる） |
| REQ-003 | REQ | graph | 変更耐性（影響集合を依存から列挙する） |
| SPEC-006 | SPEC | graph | 依存グラフの契約（forward/reverse/classify/reverse-orphans） |
| ADR-006 | ADR | graph | cross_domain_violation は depends_on 端のみに付ける |
| IMPL-006 | IMPL | graph | `_depgraph.py`＋`dep-graph.py` の実装メモ |
| TEST-006 | TEST | graph | 依存グラフのテスト計画 |
| ICD-003 | ICD | guard | guard のインターフェース（三ガードの公開境界） |
| REQ-004 | REQ | guard | 境界明瞭（越境依存は相手ICD宛のみ許す） |
| SPEC-003 | SPEC | guard | 三ガードの判定規則（不変・ICD依存・削除安全） |
| ADR-003 | ADR | guard | C13 の分岐（dangling 許容／分類不能 拒否） |
| ADR-004 | ADR | guard | PostToolUse の事前状態を raw 全文で復元する |
| IMPL-003 | IMPL | guard | `policy-guard.py` の実装メモ |
| TEST-003 | TEST | guard | 三ガードの受入試験 |
| ICD-004 | ICD | lint | lint のインターフェース（リンタと用語チェッカーの公開契約） |
| REQ-005 | REQ | lint | 現行性（型↔status・id↔ファイル名・型↔置き場所を機械点検） |
| REQ-006 | REQ | lint | 用語統一（未承認語・禁止同義語を弾く） |
| REQ-007 | REQ | lint | 明快な日本語（カルクを照合する） |
| SPEC-007 | SPEC | lint | 単一文書リンタの全 PostToolUse 点検 |
| SPEC-008 | SPEC | lint | 用語チェッカーの照合規則 |
| ADR-005 | ADR | lint | 承認辞書を体系内で一度だけ符号化する |
| ADR-007 | ADR | lint | 禁止同義語セルの末尾注記の扱い |
| ADR-012 | ADR | lint | 構造語彙を正本で定義済みと認め、doc-reviewを著述時の閉じた輪にする |
| ADR-017 | ADR | lint | 外部の公式名を固有名として辞書に登録し照合から外す |
| IMPL-007 | IMPL | lint | `docs-linter.py` の実装メモ |
| IMPL-008 | IMPL | lint | `_termcheck.py` の実装メモ |
| IMPL-009 | IMPL | lint | `term-check.py` の実装メモ |
| TEST-007 | TEST | lint | リンタのテスト計画 |
| TEST-008 | TEST | lint | 用語チェッカーのテスト計画 |
| ICD-001 | ICD | model | model のインターフェース（登録簿と解析の公開契約） |
| REQ-001 | REQ | model | 構造規則とメタデータ様式を単一の正本として定義する |
| SPEC-001 | SPEC | model | 登録簿の契約（registry contract） |
| SPEC-002 | SPEC | model | フロントマター解析の契約 |
| DATA-001 | DATA | model | 登録簿とフロントマターのスキーマ |
| ADR-001 | ADR | model | 構造規則の単一正本化（C2） |
| ADR-002 | ADR | model | フロントマター解析の3要素戻り値（C1） |
| ADR-013 | ADR | model | 手順を運ぶ型 PROC を一つだけ新設する |
| ADR-015 | ADR | model | 統治の対象を知識と決定の層に限る |
| IMPL-001 | IMPL | model | `_registry.py` の実装メモ |
| IMPL-002 | IMPL | model | `_frontmatter.py` の実装メモ |
| TEST-001 | TEST | model | 登録簿契約のテスト計画 |
| TEST-002 | TEST | model | フロントマター解析契約のテスト計画 |
| ICD-008 | ICD | packaging | packaging のインターフェース（配布物の形・Hook配線・段差） |
| REQ-013 | REQ | packaging | 保証限界の明示（各成果物が予防・検出・委ねるを書く） |
| SPEC-019 | SPEC | packaging | Hook配線（4イベント／matcher／解決／縮小構成／スナップショット） |
| SPEC-020 | SPEC | packaging | パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ） |
| ADR-011 | ADR | packaging | 段階導入とBash matcherの拒否限定 |
| IMPL-017 | IMPL | packaging | パッケージ・Hook配線の実装注記 |
| TEST-019 | TEST | packaging | Hook配線・e2e連鎖の受入 |
| TEST-020 | TEST | packaging | 配布・標準ライブラリの受入 |
