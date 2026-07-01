---
id: ICD-007
title: authoring のインターフェース（作成・初期化・支援）
type: ICD
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.1]
canonical_for: [scaffolding, term-extraction, skills, templates]
---

# authoring ICD

authoring ドメインは、型付き文書を正しい置き場所と様式で作る。体系を最小に初期化し、機械では割り切れない判断を人が下すのを支援する。他ドメインに公開する接点は、すべて本文書にまとめる。

## 公開する用語

ここに挙げる語は本ドメインが所有する。意味は用語辞書（正本は `docs/_system/glossary.md`）の該当分を引く。

- 足場（初期化が `_system` に置く最小限のファイル）。
- 候補語抽出（ドメインごとの特徴語の候補を c-TF-IDF で出す処理。ファイルは読むだけで書き込まない。c-TF-IDF は、各ドメインを一つのまとまりとみなして特徴語を測る指標で、SPEC-018 で定義する）。
- 技能（人の判断を支援する Skill。本ドメインは7つの技能を所有する）。
- テンプレート（型ごとに様式をかたどった雛形。全19個）。

## 正本である事実

次の事実は本ドメインだけが正本として持つ（`canonical_for` と一致させる）。

- scaffolding: 初期化は既存を壊さず、置くものを最小限にとどめる。glossary・decided-facts・non-goals・overview の投影からなる `_system` の最小集合、ルートの案内、`.docs-level` だけを置く。ドメインのフォルダ・各層・hooks・skills は先に作らない。
- term-extraction: ドメインごとの特徴語の候補を c-TF-IDF で出す。ファイルには書き込まず、どれを採るかは人が決める。
- skills: 技能は7つに固定する。機械で割り切れる処理は scripts と登録簿に任せ、各技能は何をどこまで保証するかを明記する。
- templates: テンプレートは、18種の型と1種の投影（icd-index）で計19個。§1 の語彙を体系の中でテンプレートが一度だけ書き写し、ほかには持たせない。

## データ契約

他ドメインが頼ってよい様式と、本ドメインが書き出す内容を定める。

- doc-author が作る文書の様式: すべての文書は §3.4 のフロントマター（文書先頭の YAML メタデータ）を持つ。`id` はファイル名と一致させ、型ごとに決められた置き場所に従う。
- scaffold が置く最小集合: `docs/_system/{glossary,decided-facts,non-goals,overview}.md`、`AGENTS.md`・`CLAUDE.md`、`docs/_system/.docs-level`（`level: N` の一行で、いま使われている Level を公開する）。
- term-extract が出す候補表: `text`・`json`・`csv` の3様式。いずれにも、これは候補にすぎず採否は人が決める旨の注記を付ける。

## 依存してよい入口

他ドメインは本文書（ICD-007）だけを `depends_on` できる。内部文書（SPEC・IMPL・TEST）を名指しで依存することはできない。

<!-- 入れない: 内部実装、内部の検討 -->
