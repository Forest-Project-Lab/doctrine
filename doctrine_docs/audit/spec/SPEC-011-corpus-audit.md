---
id: SPEC-011
title: 全件監査の検査群・要約スキーマ・決定性
type: SPEC
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-27
sources: [spec/doctrine.ja.md#4.2]
depends_on: [REQ-008, ICD-008, ICD-001, ICD-002]
llm_context: task
---

# 全件監査の検査群・要約スキーマ・決定性

`docs-audit.py` がコーパス全件を走査し、所見と要約を出すための契約を定める。文書集合が過不足なく最小であることを過剰側と不足側の両方から検査し、あわせて古びも検出する。`[R1][R3][R4][R8]`

## 入出力

- 入力: コマンドライン引数 `[--root PATH | --root-from PROJ] [--json] [--summary-out PATH] [--fail-on error|never] [--config PATH] [--today YYYY-MM-DD] [--respect-docs-level]`。`--root-from` はプロジェクト根を取り、統治木を ADR-022 の優先順で解決する（統治木が無ければ飛ばして 0）。標準入力は読まない。入力内容に結果が左右されないからであり、対話端末から起動しても入力待ちで止まらない。
- 処理: 統治木のルート配下のすべての .md について、graph（ICD-002）が依存グラフを組み、登録簿（ICD-001）が各文書の型・`status`・`llm_context` を解決する。本文は一度だけ読んでノードに付ける。
- 返す値: 要約スキーマ `docs-audit/1`。形は `{schema, generated_at, today, root, totals:{error,warn,advisory}, counts_by_check, checks_run, top_findings, findings}`。`root` は絶対パスに正規化して書く（注入側が相対 root を照合不能として捨てるため。SPEC-012）。`--json` を付けると機械向けの JSON を、付けなければ人間向けの平文を出す。`--summary-out` を指定すると、要約を一時ファイルに書いてから改名して差し替え、途中状態を残さない。

## 制約

- 標準ライブラリだけを使う。pip での外部パッケージ取得も、ネットワーク通信もしない。返す値は毎回同じになる（所見を check・doc_id・message の順で整列する）。
- 29 検査の重大度は固定とする（ICD-005 の表のとおり。`AUDIT_CHECKS` の名前は 31 個で、逆孤児の二種と未登録/影がそれぞれ一つの検査を二つの名前で持つ）。`top_findings` は error を優先し、上限 20 件とする。
- 要約に `checks_run`（この版が走らせた検査名の一覧。`AUDIT_CHECKS`）を載せる（#95）。`counts_by_check` は所見のある検査しか載らないため、0 件の検査と走らなかった検査を区別できない。`checks_run` で走った検査集合を明示し、黙って消えた検査を読み手が見つけられるようにする（沈黙する検証器の禁止。`[R11]`）。
- 依存の循環（dep_cycle、ADR-038）: `depends_on` 端の循環（自己依存 A→A、多頂点循環 A→B→C→A）を graph の `find_cycles`（Tarjan、サイクル安全）で求め、warn で挙げる。循環の全構成員は削除安全ガードの「現行の依存が残る」判定に永久に該当し降格できなくなる論理的デッドロックになる。dead link 検査の自己参照除外はそのまま（自己依存は dep_cycle が受け持つ）。`[R3][R8]`
- 語彙的酷似（near_duplicate）の対走査は O(n^2) であり、規模上限 `near_dup_max_docs`（既定 800、`--config` で上書き）を設ける。現行文書数がこの上限を超えた場合は対走査を省き、省いた事実を near_duplicate の助言一つで正直に告げる（黙って切り詰めない）。重大度は advisory のまま（ICD-005 不変）。`[R8]`
- `generated_at` は `today` から決める（`today.isoformat()+"T00:00:00Z"`）。テストが制御できないシステム時刻は参照しない。`[R1]`
- 孤児は三条件すべてを満たす文書とする（どの現行文書からも依存されない、かつ陳腐化している、かつ再現可能。ADR-008）。投影・`llm_context`==always・ICD・`status`==archived は孤児にしない（archived の除外は ADR-027。倉庫の証跡を削除候補へ昇格させない）。`[R8]`
- 逆孤児は現行文書だけを対象とする（判定は graph の `reverse_orphans` に委ねる）。`[R3]`
- ドメインをまたぐ `depends_on` の違反だけを icd_dependency_violation として上げる。ドメインをまたぐ impacts は違反としない。`[R4]`
- 未登録/影文書は、`build_graph` が既に集める `parse_warnings`（frontmatter か id が無い .md）と `dup_ids`（id 衝突で影に隠れた別ファイル）を読むだけで検出する。新たな走査はしない。他の全検査は登録簿ノード上の述語なので、ノードにならないファイルはこの検査だけが拾える。取り除きではなく、型を与えて登録するか archive/ へ退避する候補として error で挙げる。影に隠れた側の判定と、所見が告げる採用先は、登録簿の `resolve_duplicate_id`（ADR-049）から引く。監査が告げる採用先と、注入が実際に運ぶ文書を一致させるためである。`[R1][R8]`
- 投影ドリフトは三つの投影を対象とする。Overview と ICD-index は id 集合の差（error）。Context Map は印の区間の骨格を内部で再導出して突き合わせ、構造の差（ドメインの過不足・ドメイン越え依存端の過不足・印の区間が無い）を error、ラベルの差（ドメイン行の ICD 列挙・境界違反マーク）を warn とする（ICD-005 の表のとおり）。`[R1][R8]`
- テスト不能記述は検査しない。意味の判断であり、doc-review が担う（ADR-020）。
- 体系外 .md（stray_document、ADR-021）: 統治木のルートの親から .md を整列走査し（dot ディレクトリ・node_modules・監査対象の統治木自身は見ない）、`doctrine_docs/_system/.md-intake`（分類の記録。`パス: 非文書|投影|保留 日付`、末尾 `/` は配下全体。書式の正本は ICD-005）と突き合わせる。登録簿の型を持つ .md は warn、記録に無い .md は advisory（上限 50 件で正直に切り詰める）、期限を過ぎた保留は warn、実在しないパスを指す記録の項目と読めない行は advisory。記録の分類の当否は判断であり docs-curate に委ねる。`[R1][R8]`
- 陳腐化の疑い（stale_current、ADR-025）: 明示の `review_by` を持たない現行文書に、型の既定点検周期（登録簿の `TYPE_REVIEW_CYCLE_DAYS`）で実効期限を張り、`updated`＋周期の超過を warn で挙げる。明示の `review_by` は既定より優先し、review_by_overrun 検査が見る。周期の無い型（投影・ADR・DECIDED・WATCH・CHANGE・IMPACT・RESEARCH・ARCHIVE）は対象外。`[R2]`
- 上流更新の伝播（source_drift）: 現行文書（ADR と投影を除く）の `depends_on` 先の `updated` が自分の `updated` より新しいとき、追随の疑いとして advisory で挙げる。確かめたら自分の `updated` を上げれば消える。`[R2][R4]`
- アーカイブ整合（archive_integrity、ADR-027）: `status`==archived なのに `<domain>/archive/` の外に在る文書を error で挙げる。archived の非 RESEARCH に `superseded_by` が無ければ advisory。`[R8]`
- 決定の着地（adr_not_landed）: accepted の ADR を、現行の文書（ADR と投影を除く）の `depends_on`・`impacts`・`superseded_by`・本文の id 参照のどれも指していないとき、「文書上の宣言に留まる」欠陥類型の疑いとして warn で挙げる（WATCH-001 第6項の機械化）。`[R3][R8]`
- 辞書シードの退行（glossary_seed_drift、ADR-005）: 運用正本（`_system/glossary.md`）が同梱シードの承認語・カルク行を落としていたら warn（シードからの成長は正しい。欠落は退行）。運用正本が無ければ検査しない。`[R6]`
- 外部アンカーの存在（ext_anchor_broken、ADR-026）: 現行 EXT の「対象」のうち検査が exists または hash のものについて、プロジェクト根からの相対で実在を確かめ、無ければ error。「対象」の行が無い EXT は warn。URL と「review_by のみ」は機械検査しない（通信はしない）。検査が hash のとき（ADR-039）: 本文の `- 指紋: sha256:<64桁>` と対象の `sha256` を照合し、不一致は warn、指紋の行が無ければ warn（沈黙で素通りしない。hash は exists を無効化しない）。指紋の期待値の更新は人手。`[R11]`
- コードと仕様の追跡（trace_*、ADR-056）: `## 実装の指紋` の節に `- sha256:<64桁>` を持つ文書が一つでもあるときだけ効く。門は節の有無だけで判じ、状態を問わない（ADR-060。廃止された仕様だけが opt-in する木でも、その注釈への warn は生きる）。節を持つ文書が一つも無ければ、コードの走査そのものを行わない（使っていない機能の費用を払わせない）。上向きの検査（注釈→文書）は走査が走れば常に効き、下向きの照合（記録した指紋）は現行の文書だけに掛ける。走査は `_tracescan`（SPEC-026）に委ね、統治木の親を根とする。挙げるのは九つ — 印の対応付けの誤り（error）・実在しない id を指す注釈（error）・現行でない id を指す注釈（warn）・記録した指紋との食い違い（warn）・記録があるのに範囲が無い（warn）・「コード対応なし」の宣言に反して範囲がある（warn。ADR-061）・節の無い現行 SPEC を範囲が指す（advisory。欠陥Dの可視化。ADR-061）・印に見えるが読めない行（advisory。綴りの揺れの兆候。ADR-059）・走査が告げた切り詰めの転記（advisory。走査の所見を読み手が握らない。ADR-059）。節には指紋の記録の代わりに `- コード対応なし: <理由>` の明示宣言を書ける（ADR-061。宣言した仕様は下向きの照合の対象にしない）。あわせて、走査が走ったときは勘定（`trace_coverage`。ADR-058）と現行 SPEC の三分類（`spec_coverage`: traced・no_code・undeclared。ADR-061）を要約に載せる。「根拠を持たないコード」は挙げない（注釈は任意であり原理的に判じられない。ADR-054 の既知の限界）。`[R3][R4]`
- 拒否経路の欠落の疑い（guard_liveness_gap、ADR-062）: フックの発火の印（`.claude/.cache/hook-stamps`）を読み、リンタ（PostToolUse）の印があるのにガード（PreToolUse）の印が無い・60 秒超古いとき advisory で挙げる。判定は `_auditcache.liveness_gap` に一度だけ在り、鼓動（SPEC-021）と同じ答えになる。印が無ければ黙る（CI・更新直後の前方寛容）。`[R11]`
- メモリの影（memory_shadow、ADR-035）: ハーネスのメモリ（`CLAUDE_CONFIG_DIR`（無ければ `~/.claude`）`/projects/<プロジェクト根の絶対パスの / を - に置換した名前>/memory/` の .md。索引 `MEMORY.md` を除く）が統治文書の id に言及していたら advisory で挙げ、正本との矛盾の点検を促す。置き場が無ければ検査しない（CI では通常無い）。中身の真偽・矛盾は判定しない（§7）。`[R8]`

## 実装の指紋

この節がある文書だけが、コードとの追跡の対象になる（ADR-056 の opt-in、ADR-061 の宣言）。対象は検査一覧（`AUDIT_CHECKS`）を囲む範囲。更新は `trace-index.py --id SPEC-011` が返す行を写す。

- sha256:32fb09156790002f457950426c68032c509d0a9db41e2880c43499fa4b968bf3

## エラー時挙動

- ルートが見つからない場合: 所見ゼロと同じ扱いにして終了コード 0 を返す。CI も SessionEnd もここで止めない。
- `--respect-docs-level` 付きで、対象の `doctrine_docs/_system/.docs-level` が `level: 2` の場合: 監査を飛ばした旨を出して終了コード 0 を返し、要約は書かない（ADR-019。全件監査は Level 3 から）。この旗は SessionEnd の配線だけが付ける。CI は付けず、Level に依らず監査する。
- 与えられた `--today` または config.today を日付として解釈できない場合: 使い方の誤りとして終了コード 2 を返す。黙ってシステム時刻に切り替えることはしない。
- 監査本体がクラッシュした場合: stderr に記録して終了コード 0 を返し、Hook の連鎖を妨げない。要約の書き込みに失敗した場合も 0 を保つ。

## 受入基準

TEST-011 で確認する。受入シナリオ TC（TC-082〜130 系）で各検査の pass/fail、要約の受け渡し、結果が毎回同じになること、不正な基準日で終了コード 2 になることを検証する。各検査は pass と、fail または上限到達の両側を持つこと。
