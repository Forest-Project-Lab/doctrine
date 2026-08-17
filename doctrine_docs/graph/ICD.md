---
id: ICD-002
title: graph のインターフェース（依存グラフと追跡索引の問い合わせ契約）
type: ICD
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-16
sources: [plugin/scripts/_depgraph.py, plugin/scripts/trace-index.py, plugin/scripts/dep-graph.py]
canonical_for: [dependency-graph-api, trace-index-api]
llm_context: task
---

# graph ICD

## 公開する用語

- 依存（depends_on）: ある文書が他文書を前提とする関係。
- 参照: 文書から別文書への指し示し。依存とは限らない。
- 孤児: どの現行文書からも依存されない文書。
- 逆孤児: あるべき文書の不在（対応する仕様を持たない要求、対応するテストを持たない受入基準）。
- 投影: モデルから描画した派生表示。本ドメインが返すのは投影そのものではなく、投影を描くための素材である。
- 追跡索引: 注釈の対が囲むコードの範囲を、問い合わせのたびに導出する索引。保存しない（ADR-055）。
- 勘定: 走査が触れたファイルの、保存則つきの件数（SPEC-026）。

## 正本である事実

本ドメインは `dependency-graph-api` の正本である。統治木の配下の全文書から組み立てた有向グラフに対し、どう問い合わせられるかをここで唯一定める。

あわせて `trace-index-api` の正本でもある。追跡索引への問い合わせの入口をここで唯一定める（ADR-112）。書式と勘定の詳細な正本は SPEC-026 であり、本宣言は二重定義しない。

## データ契約

他ドメイン（guard・lint・audit・packaging）が依存してよい問い合わせは次の通り。戻り値は整列済みで、同じ入力には同じ結果を返す。所見が一つでも見つかったときも、拒否や警告は返さず結果を返すだけにとどめる（検出に徹し、判定はしない）。[R3][R4][R7]

- `forward_impacts(id)`: impacts 端をたどった推移閉包を返す（id 自身は含めない）。変更耐性が使う影響集合がこれである。[R4]
- `reverse_dependents(id, current_only=False, transitive=False)`: depends_on で id を指すノードをすべて返す。`reverse_current_dependents(id)` は `current_only=True` を呼びやすくした短縮形で、削除安全の判定が使う。[R3]
- `resolve(id)`: その id の `{path, domain, type, status}` を返す。見つからなければ None を返す。ガード・リンタ・監査は、id からドメイン・型・位置づけを引くときこれを使う。
- `classify_edges()`: すべての端を `kind`（intra_domain / cross_domain_icd / cross_domain_violation / cross_domain_impact / dangling）に分類して返す。`cross_domain_violation` が付くのは depends_on 端だけである。[R7]
- `reverse_orphans()`: `{req_without_spec, spec_without_test}` を返す（対象は現行文書のみ）。
- CLI `dep-graph.py` の終了コード: 問い合わせが成立すれば、所見の有無にかかわらず 0。使い方を誤れば 2、ルートが見つからなければ 3。

### 依存グラフの問い合わせ（CLI。dep-graph/1。ADR-153）

外部の消費者（リポジトリの外の表示製品を含む）が依存してよいのは、CLI `dep-graph.py` が返す値だけである。

- JSON の形は `{"schema": "dep-graph/1", "root": <名前だけ>, "source_revision": <完全SHA|null>, "source_dirty": <真偽|null>, "generator": {...}, "mode": <モード名>, "nodes": [...], "edges": [...], "result": ...}`（モードによっては `id`・`count` が加わる）。`root` に絶対パスを載せない（trace-index/1 と同義）。節点の項の正本は SPEC-006（節点は隠さない。ADR-087）。
- モードは `--impacts <id>`・`--dependents <id>`・`--classify-edges`・`--reverse-orphans`・`--reverse-refs <id>`・`--find-root [開始位置]` の六つ。`--json` は修飾子であってモードではない（ADR-110）。
- `--classify-edges` の `result` は `edges` と同じ内容の重複である（互換のため残す。読み手はどちらか一方だけを読む。ADR-153）。
- `--find-root` はグラフを組まずに統治木を探し（規則の正本は ADR-022）、`result` に統治木の絶対パスを返す。見つからなければ `result` は null で終了コード 3。この口だけは絶対パスを返す —— 自分の機械の統治木を見つけるための口であり、機械をまたいで共有する成果物ではない（ADR-154）。
- 診断は標準エラーへ出す。stdout は返す値だけとする（ADR-153）。

### 測った木の版と作り手（ADR-155）

`trace-index/1` と `dep-graph/1` は、最上位に次の三つの鍵を名乗る。鍵の追加は互換であり、読み手は未知の最上位の鍵を読み捨ててよい。互換を壊す変更はスキーマ名の版を上げる（確定事実13。ADR-152）。

- `source_revision`: 測った木の版 —— HEAD（作業木が向いているコミット）の完全 SHA（コミットを一意に指す指紋）。解決できない木（git でない等）では null。
- `source_dirty`: 測った木に未コミットの変更が在れば true、無ければ false、git で解決できなければ null。
- `generator`: `{name, version}`。`name` はスクリプト名、`version` は plugin.json の版（知れなければ null）。
- 複数の返す値の `source_revision` が同値であることを「同じ木を測った」ことの照合に使う。`root` は照合の鍵ではない（口ごとに意味が違ってよい。ADR-155・ADR-156）。
- 鮮度の判定規則（ADR-172 決定3）: 記録時といまの `source_revision` が共に完全 SHA で等しく、かつ、いまの `source_dirty` が false なら「同一」。共に完全 SHA で異なれば「相違」。どちらかが null、または、いまの `source_dirty` が true か null なら「不明」。三値であり、不明を肯定（同一）に丸めない。読み手はこの規則を再定義しない。

### 追跡索引の問い合わせ（trace-index-api。ADR-112）

外部の消費者（リポジトリの外の表示製品を含む）と他ドメインが依存してよいのは、CLI `trace-index.py` が返す値だけである。

- JSON の形は `{"schema": "trace-index/1", "root": <名前だけ>, "source_revision": <完全SHA|null>, "source_dirty": <真偽|null>, "generator": {...}, "ranges": [...], "findings": [...]}`。`root` に絶対パスを載せない。三つの版の鍵の意味は「測った木の版と作り手」の節のとおり（ADR-155）。
- `--id <id>` を与えると、その仕様に対応する範囲だけを返す（仕様の側から見た逆リンク。詳細は SPEC-026）。
- `findings` の各項は `{code, path, line, message}`。重さ（severity）は持たない —— 検出に徹し、判定はしない。判定済みの重さが要る読み手は、監査要約（`docs-audit/1`。ICD-005）の trace 系の所見から severity 付きで読む（ADR-156）。
- `ranges` の各項はちょうど五項 `{id, path, begin_line, end_line, fingerprint}`。`path` は根からの相対で、区切りは `/`。
- `--coverage` は勘定（既定は件数だけ）を返し、`--coverage --term <項>` は当該の一覧を返す。
- 終了コードは dep-graph と同じ規約: 問い合わせが成立すれば 0、使い方を誤れば 2、根が見つからなければ 3。
- 書式・勘定の保存則・除外規則の詳細な正本は SPEC-026。この宣言は入口だけを固定する。
- 実行時の状態（`.claude/.cache` の監査要約など）の直読みは契約外である。読み手は CLI を走らせ、返る値だけを読む。

## 依存してよい入口

他ドメインが depends_on できるのは、この文書（ICD）だけである。`_depgraph.py`・`_tracescan.py` の内部や CLI の実装を直接 depends_on してはならない。
