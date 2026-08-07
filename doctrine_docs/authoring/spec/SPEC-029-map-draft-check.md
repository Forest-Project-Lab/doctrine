---
id: SPEC-029
title: map-draft-check（意味モデル下書きの出所検証）
type: SPEC
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-07
sources: [plugin/scripts/map-draft-check.py]
depends_on: [SPEC-016]
llm_context: task
---

# map-draft-check（意味モデル下書きの出所検証）

`system-map-draft` 技能（ADR-136）が起草する意味モデルの下書き（lens 側の検証用スキーマ `system-map/gold-model/0.1`）を、確定（`confirmed` への昇格）の前に機械で検める門である。固有の務めは出所の実在（捏造出所ゼロ）。起草の意味の正しさは検めない（昇格は人の仕事のまま）。

## 入出力

- 引数: `--model PATH`（検査対象の JSON）、`--repo PATH`（出所を解決するリポジトリの根）、`--docs-root PATH`（任意。無指定なら `--repo` 直下の `doctrine_docs` を使う）、`--repo-prefix NAME`（任意。この接頭の出所だけを `--repo` で解決し、別の接頭は機械検証不能の一覧へ回す）、`--today YYYY-MM-DD`（任意。日付の上限。無指定なら形だけ検める）、`--trace-json PATH`（任意。`trace-index/1` の JSON を注入する。無指定なら同じディレクトリの `trace-index.py` を子プロセスで実行する）、`--json`。
- 返す値: 人が読む日本語の報告。`--json` は `{"schema": "map-draft-check/1", "model": 名前, "findings": [...], "unverifiable": [...], "totals": {...}}` を返す。所見（findings）と機械検証不能（unverifiable）は別の一覧であり、混ぜない。
- 終了コード: 0 所見なし / 1 所見あり / 2 使い方の誤り / 3 対象（モデル・リポジトリの根・`--trace-json` の実体）が無い。ICD-002 の 0/2/3 の規約に、所見あり=1（`docs-linter --batch` と同じ）を加えた形である。

## 制約

- 標準ライブラリだけで実装し、同じ入力には常に同じ答えを返す。壁時計を読まない（日付の上限は `--today` で受け取る）。
- ネットワークを使わない。URL は取得せず、機械検証不能として列挙する。検証できないものを検証済みとは言わない（検証可能性を偽らない）。例外は一つだけ: GitHub の blob URL が `SHA` とパスを含み、その `SHA` を `--repo` の git が知るときは、履歴の中だけで検める。
- git が使えない木・履歴に無い rev（浅い複製を含む）は、所見ではなく機械検証不能へ回す。門は確かめていない赤を出さない。
- 検査は次の七つとする。

| code | 検める内容 |
|---|---|
| `D1_NOT_PROPOSED` | `review_status` を持つ実体（`system`・`elements`・`flows`・`contracts`・`scenarios`・`anchors`）は `proposed` に限る。下書きは自分を確定しない |
| `D2_SOURCE_UNRESOLVED` | リポジトリ接頭付きパスの出所が `--repo` の作業木に実在する。`@rev` 付きは `git cat-file -e rev:path` を通る。`locator` の行番号（`L番号`・`番号行`）が行数以内で、鉤括弧の引用が本文に実在する（`verdict: silent` の引用は照合しない） |
| `D3_BAD_DATE` | `checked_at` / `observed_at` が実在する `YYYY-MM-DD` で、`--today` より未来でない |
| `D4_ANCHOR_UNMATCHED` | `target_kind: code_range` かつ `authority: doctrine` のアンカーの `target` が、追跡索引の返すいずれかの範囲の `path` を含む。`source_revision` の commit が `--repo` の履歴に実在する |
| `D5_FLOW_FROM_DEP_EDGE` | Flow の出所（`source`・`locator`）が `dep-graph`・`depends_on`・`impacts` を名指ししない。文書辺の自動 Flow 化の早期信号（lens 側 validator と同じ照合の族） |
| `D6_UNKNOWN_WITHOUT_NEGATIVE` | `verification_status: unknown` の Contract は、`verdict: silent` かつ `checked_at` 付きの負の出所を最低 1 件持つ |
| `D7_SHAPE` | 最上位の必須キー（`schema`・`target`・`system`・`elements`・`flows`・`contracts`・`scenarios`・`anchors`）、語彙（列挙）の当否、`elements` の `id`/`name`/`kind` と `flows` の `from`/`to` |

- 語彙（列挙）の正本は lens 側 gold-model の `schema.json`（0.1）であり、実装はそれを写して名指しする。
- M 層（lens 側 INVARIANTS.md）との分担: ここで早期に検めるのは M-07 の一部（`D1`）・M-08（`D5`）・M-11（`D6`）だけである。M-02/03/04/05/06/09/12/15/16 は lens 側 validator の受け持ちであり、この門は validator の置き換えではない。
- 入口スクリプトは入口スクリプトを取り込まない。追跡索引は `--trace-json` で注入するか、`trace-index.py` を子プロセスで実行して読む（`.claude/.cache` は読まない。ADR-136）。

## エラー時挙動

- 使い方の誤り（未知の引数・必須の欠落・`--today` の形の誤り）は usage を告げて 2 で終わる。
- モデル・リポジトリの根・`--trace-json` の実体が無ければ 3 で終わる。
- モデルが JSON として読めないときは、`D7_SHAPE` の所見一件として挙げて 1 で終わる（門は黙って通さない）。
- 追跡索引が得られないとき（子プロセスの失敗など）は、`D4` の対象アンカーを機械検証不能へ回して続行する。
- 想定外の例外は握りつぶさない。internal error として告げ、非零で終わる。

## 実装の指紋

対象は検査の本体。更新は `trace-index.py --id SPEC-029` が返す行を写す（ADR-061）。

- sha256:4971049f2ec234079a28d0f1ae132e13f67452a7af39c5aa82dd57de938b91f0

## 受入基準

- 正しい最小モデルが所見 0 で 0 終了すること。
- 実在しないパスの出所が `D2` で挙がること。`locator` の行番号が行数を超えるとき・引用が本文に無いときに挙がり、実在する引用と `verdict: silent` の引用では挙がらないこと。
- `--today` を固定して、未来の `checked_at` と形の崩れた日付が `D3` で挙がること。
- 注入した追跡索引に無い `target` のアンカーが `D4` で挙がり、在る `target` では挙がらないこと。
- 依存辺を名指しした Flow の出所が `D5` で挙がること。
- 負の出所を欠く `unknown` の Contract が `D6` で挙がり、持つものは挙がらないこと。
- `confirmed` を名乗る実体が `D1` で挙がること。
- 最上位の必須キーの欠落・語彙の外れ値・`from`/`to` の欠落が `D7` で挙がること。
- URL・会話・別接頭の出所が所見にならず、機械検証不能の一覧に載ること。git の無い木で `@rev` と `source_revision` の検査が機械検証不能へ退くこと。
- 終了コードが 0/1/2/3 になること。`--json` が宣言の形を返すこと。
- 観点ごとの対応は TEST-029 に示す。

<!-- 入れない: 廃止、検討、実装コードの写し -->
