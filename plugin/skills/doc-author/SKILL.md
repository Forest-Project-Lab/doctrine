---
name: doc-author
description: 'Creates and updates typed governance documents — SPEC, REQ, ADR, DATA, API, IMPL, TEST, DECIDED, NONGOAL, RESEARCH, ARCHIVE, and ICD — placing each in the correct location with correct frontmatter (id matching filename, type, domain, status, owner, dates, sources), and generating the domain folder and its layer subfolders the first time a document of that type is written. Use this skill when the user wants to "write a spec", "add an ADR", "create an ICD", "author a requirement", "add a doc", "document this decision", "record a data model", "start a new domain", or says "I need a SPEC/REQ/ADR/TEST for ...".'
---

# doc-author

## 役割

型付き文書（ICD を含む）を作り、更新する。型・置き場所・フロントマターを正す。満たす要求は §2 の `R1`・`R3`・`R6`・`R7`（要求番号は §2 の登録簿で定める）。

ICD もこのスキルが書く（ICD 専用スキルは作らない）。ドメインのフォルダと各層は、その型の文書を最初に書くときに、ここで生成する（§3.7「空の足場を先に作らない」）。

## 委ねる先（決定論は scripts と登録簿へ）

- `templates/` のテンプレート。ICD は `templates/icd.md.tmpl`、他の型も付録Bのテンプレートを使う。
- `${CLAUDE_PLUGIN_ROOT}/scripts/_frontmatter.py` — フロントマターの形を読んで確かめる。
- §3.2（型→置き場所→既定 `status`→`llm_context`）・§3.3（`status` の語彙）・§3.4（メタデータ）の登録簿が唯一の正本である。規則をスキル本文やコードに二重定義しない（§3）。
- 書いたあと PostToolUse のリンタ（`docs-linter.py`）が動く。その `additionalContext` の指摘に従って自己修正する。
- `doc-review`（スキル）— 文章規範と一覧外カルクの判断。文書を著したら回す（手順 11）。

## 手順

1. 文書の型を決める（§3.2）。既存の型で表せるなら、新しい型を作らない（「空の型を先に作らない」）。
2. ドメインを決める。フォルダが無ければ、ここで遅延生成する（§3.7）。`docs/<domain>/` と、この型が要る層のフォルダ（`spec/`・`decisions/`・`implementation/`・`test/`・`research/`・`archive/`）だけを作る。空の層を先に作らない。
3. ファイル名を `<型コード>-<連番>-<短い主題>.md` で決める（日付は `ISO 8601`、日本語ファイル名・空白・版番号の埋め込みは禁止、§3.7）。`id` をファイル名と一致させる。
4. フロントマターを §3.4 で埋める。Level 2 以降の必須は `id・title・type・domain・status・owner・updated・sources`。既定の `status` と `llm_context` は §3.2 から引く。`DECIDED`・`WATCH` には必須の `review_by` を足す。`depends_on`・`impacts` は Level 3 以降、`canonical_for` は Level 4 以降。
5. ICD を書く経路（§3.5／付録A）。一ドメインに `<domain>/ICD.md` 一つ、型は `ICD`。宣言するのは三つだけ。公開する用語（用語辞書への参照）・正本である事実（`canonical_for` のトピック）・データ契約。ICD に内部実装は書かない。ICD を変えるときは、依存する全ドメインの合意が要ると利用者に伝える。
6. 依存の規律（`R7`／§3.6）。`depends_on` を付けるとき、ドメイン間の依存は相手ドメインの ICD 宛だけ許す。ドメイン外の非 ICD 宛が要るなら、その相手の ICD 宛へ張り替える。Edit や MultiEdit より Write 経路を選ぶ。そうすればガードが実行前に拒否できる（§3.8／§7。Edit 違反は事後検出で、修正までディスクが一時的に不整合になる）。
7. `SPEC` には必須の4節を持たせる（§3.2／§4.2）。`入出力`・`制約`・`エラー時挙動`・`受入基準`。テンプレートの見出しを使い、空のまま残さない（空節はリンタが指摘する）。
8. 追跡性（`R3`）。`SPEC`・`IMPL`・`TEST` には要求または依存のリンクを持たせる（リンタが点検する）。`REQ`→`SPEC`→`IMPL`→`TEST`→`ADR` の順で前向きに結ぶ。
9. 本文を書く（語彙を正し、一文一義で、§1 の文章の規則に従う）。本文に変更の理由（履歴）を書かない。理由は `ADR` の `id` で引く（§3.8 現行と履歴の分離）。
10. リンタを動かし、指摘された項目を直す。
11. 文書を著したら doc-review を回す（§4.1）。文章規範と位置づけを見直し、用語チェッカーが拾えない一覧外のカルクを逆翻訳テルで判定する。これは著述・編集のたびに行い、定例だけに頼らない。見つけた一覧外のカルクは用語辞書の正本（§1 のカルク表）に一行足す。新しい承認語が要るなら、ADR と用語辞書の更新をもって加える。型コードと要求タグの定義の在処は登録簿（§3.2）と §2 であり、辞書に二重定義しない。

## 詳細（references/）

- `references/type-registry.md` — §3.2 への案内（表を写さず、正本を参照する）。
- `references/icd-authoring.md` — ICD の書き方、付録Aの使い方、「依存する全ドメインの合意」規則。
- `references/frontmatter.md` — §3.4 の各欄、Level の段差。
- `references/lazy-domain-gen.md` — §3.7 のフォルダと層の遅延生成、命名規則。
- `references/dependency-rules.md` — §3.6 ドメイン内とドメイン間、Write を Edit より選ぶ理由。

## 保証限界

- **予防**: このスキル自身は、悪い依存や削除を予防しない。それはガードの役目である。Write 経路へ寄せ、フロントマターを先に正しく埋めることで違反を減らす。
- **検出**: PostToolUse のリンタ（必須キー・`status`・`id` とファイル名・型と置き場所・`SPEC` の4節・用語チェッカー・ICD 照合・追跡性）に頼り、自己修正する。
- **委ねる**: `canonical_for` の付与（人間、§7）。新しい型が本当に要るか。ICD 変更時のドメイン間合意（人間）。
