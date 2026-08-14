---
id: SPEC-007
title: 単一文書リンタの全 PostToolUse 点検
type: SPEC
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
sources: [plugin/scripts/docs-linter.py]
depends_on: [REQ-005, REQ-006, REQ-007, ICD-001, ICD-002, ICD-005]
llm_context: task
---

# 単一文書リンタの全 PostToolUse 点検

`docs-linter.py`（リンタ）は、編集された一つの文書だけを点検する。現行性[R2]と境界のずれを助言として知らせるだけで、編集を拒否することはない。拒否はガードに委ねる[R7]。

## 入出力

- 入力: PostToolUse の Hook（編集などのイベントで起動するスクリプト）が渡す JSON を標準入力で受け取る。点検する対象パスは、`tool_input.file_path`、`tool_input.path`、`tool_response.filePath`、最上位の `file_path` の順に探し、どれも無ければ `argv[1]` を使う。
- 返す値: 何か見つかれば、`hookSpecificOutput.additionalContext` に `[severity] CODE: message` の行を並べた助言 JSON を返す。何も無ければ空を返す。終了コードは常に 0 にする。
- CI 用バッチモード（`--batch <root>`。#91）: 統治木の全 .md に per-file の点検を当て、ERROR があれば ERROR を一覧して終了コード 1 を返す（ERROR なしは 0）。フックを迂回した経路（GitHub の Web UI・別エージェント・一括スクリプト）で入った不正文書を、マージ前に止める。点検ロジックは per-file と同一で、規則の正本（登録簿）は一つのまま。**`--batch` の後ろは使い方として解く**（ADR-110）—— 知らない旗と余分な語は場所として飲まず、使い方を出して終了コード 2 を返す（兄弟の門と同じ規約）。**場所が実在しなければ終了コード 3。**実在するが統治木でない場所だけが 0（素の docs/ を CI で誤って落とさない）。**点検した文書の数を必ず文面に出す** —— 見ていない門を緑と読む余地を減らすためである。CI はフックのスナップショットに依らず走るので、この経路だけがマージ前の schema 検査を担う。

## 制約

- 標準ライブラリだけを使う。文書は編集された一つだけを読み、全件は走査しない。`decision` は決して返さず、助言だけを出す[R7]。
- 各点検の重大度は次のとおり。`MISSING_KEY`・`EMPTY_KEY`・`BAD_STATUS`・`UNKNOWN_TYPE`・`ID_FILENAME_MISMATCH`・`BAD_FILENAME`・`TYPE_LOCATION_MISMATCH`・`DOMAIN_PATH_MISMATCH`は ERROR（重大度・誤り）。`BAD_LLM_CONTEXT`は、値が不正なら ERROR、既定値の上書きなら WARN（重大度・警告）。`BAD_SUBDOMAIN`は、値が語彙（model の `SUBDOMAIN_KINDS`）に無ければ ERROR（ADR-092）。`BAD_DATE`は、日付の鍵が解せなければ挙げる（ADR-100。解釈の正本は model の `parse_date`）—— `updated`・`review_by` は ERROR、`created` は WARN（必須キーではない）。**この配分は見立てであり、測って出した数ではない。** 不在は必須キーの検査の領分で、二重に鳴らさない。`PLACEHOLDER_VALUE`は、フロントマターの値（一覧の要素を含む）に雛形の指示文（山括弧の形）が残っていれば ERROR（ADR-098）。**判定は共有コア `_frontmatter.placeholder_fields` に一度だけ在り、全件監査も同じコアを呼ぶ**（読み手ごとに答えが割れない。ADR-053 と同じ原理）。**雛形も語彙の表も読まない** —— 雛形は配布物で導入先で差し替えられるため、正本が動くものになる（ADR-090 が同じ理由で「節の一覧を雛形から読む」案を却下した）。形そのものが指示文の印である。**本文は見ない** —— 本文には `<svg>`・置き場所の記法・id の書式が正当に出るので誤検知が多すぎる。値の一部でも咎める（雛形は `id: ADR-<連番>` のように値の一部へ指示文を置く）。**省略と空は「未分類」であり所見を出さない** —— 既存の木で所見が一件も増えないためである。この項に既定は無いので、`BAD_LLM_CONTEXT` のような「既定の上書き」の WARN は持たない。解析器が文字列以外に解す値（真偽値・一覧）も未分類として黙る（判定を書けないものを咎めない）。**同じ `domain` の中で種類が食い違っても咎めない** —— 一つの区画に中核・補完・一般が同居するのは普通の姿であり（呼び手の木はドメインが一つで三種類を含む）、咎めれば正しい状態を疑わしいと言うことになる。`MODEL_*`（意味モデルの本文の構造。規則の実体は共有コア `_model`。SPEC-031・ADR-163）は ERROR で、MODEL 型の文書にだけ掛かる —— **JSON の側が要する構造を .md の側で機械的に担保する口である**。検めるのは形だけで、意味の正しさ（その要素が本当に在るか）は見ない。`RESEARCH_HAS_DECISION`は WARN（見出しに『決定』を含むかで判ずるが、語を別語にする接尾『決定的』『決定論』は除く。ADR-082）。`MISSING_SECTION`・`EMPTY_SECTION`・`MISSING_TRACE`は ERROR。**節の検査は全型に効く**（ADR-090）—— 型ごとの必須節の正本は登録簿の `REQUIRED_SECTIONS` が持ち（確定事実1。以前は SPEC の四節だけがリンタの中に在った）、`RESEARCH` と投影には課さない（調査は探索で形が先に決まらず、投影は機械が描く）。一覧は実態を測って決めてある —— ある型の文書が 100% ずれているなら雛形が誤りと判じる（CHANGE は『理由』と『要求元』を一節に統合し、RESEARCH は節を課さない形へ改めた）。節の名の一致で判ずるので、言い換えた見出しは欠けと読む。**節が在ることは中身が正しいことではない**（空の節は咎めるが、一文字あれば通る。中身の当否は doc-review と人が見る）。（本文の `[R番号]` タグは doctrine 自己適用の約束で、上位設計書 §2 を引く。追跡の正路は REQ への `depends_on` である。ADR-045、#87）`STRAY_DOCUMENT`（登録簿の型を持つ文書が doctrine_docs/ の木の外に在る。ADR-021）は ERROR。`ARCHIVED_LOCATION_MISMATCH`（`status`==archived なのに `<domain>/archive/` の外に在る。ADR-027。archived ではこの規則が型の置き場所規則より優先する）は ERROR。型なしの .md には出さない（README 等の非文書の分類は external-md-intake に委ねる）。点検の前にまず統治木を探し、根に到達できない体系外のファイルは点検しない。型なしで intake（`_system/.md-intake`）に『非文書』『投影』『ビュー』と登録されたファイルは、schema/frontmatter の点検を飛ばし、用語助言だけを WARN で残す（ADR-024）。『ビュー』のファイルに刻印（書式の正本は audit の ICD-005 の `view-stamp-format`）が無ければ、`VIEW_MISSING_STAMP`（WARN）で刻印を促す（ADR-073。助言のみ。拒否はしない）。intake の読み取りは監査と同じ共有コア（`_intake`。書式の正本は audit の ICD-005）を使い、同じファイルへの分類が食い違わないようにする。
- 必須キーの 8 つも、`status` の型別許可表も、登録簿（model）に問い合わせる。`_system` の固定ファイル名は、`id` とファイル名の一致点検を免除する。
- 依存先がどのドメインに属するかは dep-graph に解決を委ねる。解決できない依存は、ERROR で止めず `ICD_DEP_UNVERIFIED`（WARN）に落とす。別ドメインの ICD 以外を横断して依存していれば `ICD_DEP_VIOLATION`（助言の ERROR）を出すが、それでも編集は拒否しない[R7]。
- 統治の走査から外す範囲（根の案内と dot ディレクトリ配下）は `_registry.is_outside_governance` に一本化し、監査と共有する。ここへは何も出さない（ADR-075）。
- 依存先のドメインは置き場所の名前だけから解く。兄弟文書を読まない（per-turn は編集された一件だけ。NONGOAL 第5項）。解けなければ未検証の助言へ落とす（ADR-075）。
- 助言の描画は `sanitize_inline` を通す。パスと所見の文が攻撃者制御になりうる（ADR-040 の射程拡張。ADR-075）。
- SPEC の必須節の中身は、同レベル以下の次の見出しまでとする。小見出しで途切れさせない（ADR-075）。
- 発火の印は `hook_event_name` が PostToolUse のときだけ残す（ADR-075）。

## エラー時挙動

- 例外は投げない。内部で例外が起きたときは、その旨の注記を助言に出し、終了コード 0 を返す。こうして後続の Hook の連鎖を壊さない。あわせて実行時例外の要約をエラージャーナル（書式の正本は SPEC-021）へ最善努力で残す（ADR-074）。
- 統治木の根に到達できない体系外のファイル、および intake に『非文書』『投影』『ビュー』と登録された型なしファイルには、`MISSING_FRONTMATTER` を出さない（前者は何も出さず、後者は用語助言のみ WARN（『ビュー』は刻印の欠落の WARN も出す）。ADR-024・ADR-073）。それ以外で、フロントマターが無い、または読み取れないときは、`MISSING_FRONTMATTER`（ERROR）一件だけを出して止める。他の点検はいずれも型の情報を要するためである。
- 既に削除されてディスク上に無いファイルには、何も出さない。

## 実装の指紋

対象はSPEC 必須節の正本。更新は `trace-index.py --id SPEC-007` が返す行を写す（ADR-061）。

- sha256:f968f3d4c173baddd64d95b0642d89c78ea6e5628c3de5f543493f2781678413

## 受入基準

- `tests/test_linter.py` の各点検が、発火すべき入力と発火すべきでない入力の両方で期待どおりに動く。観点ごとの対応は TEST-007 に示す。`decision` は決して出さない。

<!-- 入れない: 廃止、検討、実装コードの写し -->
