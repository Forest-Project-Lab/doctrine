---
id: ICD-007
title: authoring のインターフェース（作成・初期化・支援）
type: ICD
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
sources: [spec/doctrine.ja.md §4.1, plugin/scripts/map-draft-check.py, plugin/scripts/scaffold.py]
llm_context: task
canonical_for: [scaffolding, term-extraction, skills, templates]
---

# authoring ICD

authoring ドメインは、型付き文書を正しい置き場所と様式で作る。体系を最小に初期化し、機械では割り切れない判断を人が下すのを支援する。他ドメインに公開する接点は、すべて本文書にまとめる。

## 公開する用語

ここに挙げる語は本ドメインが所有する。意味は用語辞書（正本は `doctrine_docs/_system/glossary.md`）の該当分を引く。

- 足場（初期化が `_system` に置く最小限のファイル）。
- 候補語抽出（ドメインごとの特徴語の候補を c-TF-IDF で出す処理。ファイルは読むだけで書き込まない。c-TF-IDF は、各ドメインを一つのまとまりとみなして特徴語を測る指標で、SPEC-018 で定義する）。
- 技能（人の判断を支援する Skill。本ドメインは8つの技能を所有する）。
- テンプレート（型ごとに様式をかたどった雛形。件数は書かない。在庫は登録簿の型と投影の種が決める）。

## 正本である事実

次の事実は本ドメインだけが正本として持つ（`canonical_for` と一致させる）。

- scaffolding: 初期化は既存を壊さず、置くものを最小限にとどめる。glossary・decided-facts・non-goals・overview の投影からなる `_system` の最小集合、ルートの案内、`.docs-level` だけを置く。ドメインのフォルダ・各層・hooks・skills は先に作らない。
- term-extraction: ドメインごとの特徴語の候補を c-TF-IDF で出す。ファイルには書き込まず、どれを採るかは人が決める。
- skills: 技能の一覧は SPEC-016 を正本とし、増減は根拠ADRの置換によってのみ行う（ADR-136）。機械で割り切れる処理は scripts と登録簿に任せ、各技能は何をどこまで保証するかを明記する。
- templates: テンプレートは、登録簿の各型と1種の投影（icd-index）から成る（ADR-163 で MODEL を追加）。§1 の語彙を体系の中でテンプレートが一度だけ書き写し、ほかには持たせない。

## データ契約

他ドメインが頼ってよい様式と、本ドメインが書き出す内容を定める。

- doc-author が作る文書の様式: すべての文書は §3.4 のフロントマター（文書先頭の YAML メタデータ）を持つ。`id` はファイル名と一致させ、型ごとに決められた置き場所に従う。
- scaffold が置く最小集合: `doctrine_docs/_system/{glossary,decided-facts,non-goals,overview}.md`、`AGENTS.md`・`CLAUDE.md`、`doctrine_docs/_system/.docs-level`（`level: N` の一行で、いま使われている Level を公開する）。
- term-extract が出す候補表: `text`・`json`・`csv` の3様式。いずれにも、これは候補にすぎず採否は人が決める旨の注記を付ける。

### 外部条項（体系の外の消費者が依存してよい口。確定事実13）

- 出所検証の門: `map-draft-check.py --json` の返す値（`map-draft-check/1`）だけに依存してよい（ADR-158）。形と検査の正本は SPEC-029。引数は `--repo <接頭>=<経路>` の反復を受け、同じ接頭の二度渡しと旧形・新形の混在は使い方の誤り（終了コード 2）に倒す。
- 必須節の名の問い合わせ: `scaffold.py --list-sections [--type <型>] --json` の返す値（`scaffold-sections/1`。`{"schema", "sections": {<型>: [<節名>…]}, "generator"}`）だけに依存してよい（ADR-159）。正本は登録簿（ICD-001）のまま動かさず、この口は写しではなく参照である。未知の型は使い方の誤り（終了コード 2）。
- 進化の規約は確定事実13（ADR-152）に従う —— 鍵の追加は互換、読み手は未知の最上位の鍵を読み捨て、互換を壊す変更はスキーマ名の版を上げる。機械向けの JSON は stdout へ、診断は標準エラーへ。

## 依存してよい入口

他ドメインは本文書（ICD-007）だけを `depends_on` できる。内部文書（SPEC・IMPL・TEST）を名指しで依存することはできない。

<!-- 入れない: 内部実装、内部の検討 -->
