# モデルの形（各欄の起草の手引き）

スキーマの正本は lens 側の `gold-model/schema.json`（`system-map/gold-model/0.1`）であり、この手引きはその写しではない。起草のとき迷いやすい欄の判断だけを書く。手本は同じ場所の `target-1-doctrine-and-lens.json`。

最上位の必須欄は `schema`・`target`・`system`・`elements`・`flows`・`contracts`・`scenarios`・`anchors` の八つ。件数が 0 でも配列は置く。

## system（必須）

`purpose` は二文以内。`boundary` は境界の内側と外側を一文ずつ。`provenance` と `review_status` を持つ。

```json
"system": {
  "purpose": "統治木を持つ開発を、規則の検査と帰結の表示の一組で支える。",
  "boundary": "境界の内側は二製品。保守者は利用者として、編集器は実行環境として、境界の外に居る。",
  "provenance": [
    { "source": "doctrine: doctrine_docs/_system/REQ-000-what-this-solves.md@<rev>",
      "locator": "要求文", "checked_at": "2026-08-07", "verdict": "present" }
  ],
  "review_status": "proposed"
}
```

## SystemElement

- `id` — 表示名と独立に付け、以後変えない（M-01。表示名を変えても `id` は変わらない）。
- `kind` — `person`・`organization`・`system`・`subsystem`・`component`・`operation`・`external_system`・`device` の八値。
- `purpose` は一〜二文。`responsibilities` は最低 1 件。`owner` を必ず書く。
- `parent` は 0 か 1（M-02）。包含は `parent` で表し、依存や流れは Flow で表す。包含と依存を同じ辺にしない。
- 実現の欄は二者択一。`person` や `external_system` など、コード・試験による実現が意味上当てはまらない要素には `realization: { "status": "not_applicable", "reason": "..." }` を書く。それ以外は `realized_by` で `code_range` / `test` の anchor（開ける `url` を持つもの）へ結ぶ（M-14）。

```json
{
  "id": "doctrine.graph",
  "name": "グラフと追跡索引",
  "kind": "subsystem",
  "purpose": "依存グラフと注釈対のコード範囲を、問い合わせのたびに導出して返す。",
  "responsibilities": ["dependency-graph-api の正本"],
  "owner": "doctrine-maintainers",
  "parent": "doctrine",
  "provenance": [
    { "source": "doctrine: doctrine_docs/graph/ICD.md@8cd29bd",
      "locator": "データ契約", "checked_at": "2026-08-03", "verdict": "present" }
  ],
  "review_status": "proposed",
  "realized_by": ["a-traceindex-py"]
}
```

## Flow

- `from`・`to` は SystemElement の `id` を各 1 個（M-03）。自己ループ（`from` = `to`）には `self_loop_reason` が必須。
- `label` は動詞または交換物で必須（M-09。無名の矢印を作らない）。`kind`（`data`・`command`・`event`・`physical`・`human_action`）・`payload_or_action`・`condition`・`provenance`・`review_status` も必須。
- 根拠の取り方は `flow-evidence.md`。依存の辺からの機械変換は禁止（M-08）。

## Contract

- `assumptions` は最低 1 件（無条件の保証文を許さない）。
- `response_measure` は判定可能な測定基準。無ければ「定性的である」と明示する（M-05）。
- `verification_status` は七状態: `unknown`・`claimed`・`planned`・`verified`・`failed`・`stale`・`not_applicable`。
  - `verified` — 到達可能な `evidence` を最低 1 件持ち、証跡最小形（指紋・実行環境・版・終了状態・時刻）が埋まっている（M-06）。
  - `unknown` — `verdict: silent` の負の出所を最低 1 件持つ（M-11。`provenance-rules.md`）。
  - `not_applicable` — `na_reason` と、理由の在処を示す `present` の出所を持つ（M-15）。

```json
{
  "id": "c-lens-performance",
  "subject": "lens",
  "assumptions": ["定性的である(現時点で測定条件の定義が無い)"],
  "guarantee": "(候補)大きな統治木でも帰結の明細が実用的な時間で出る。",
  "response_measure": "定性的である(判定可能な測定基準は未定義)",
  "verification_status": "unknown",
  "owner": "doctrine-lens-maintainer",
  "provenance": [
    { "source": "doctrine-lens: doctrine_docs/_system/REQ-000-what-this-product-solves.md",
      "locator": "全文(性能への言及なし)", "checked_at": "2026-08-04", "verdict": "silent" }
  ],
  "review_status": "proposed"
}
```

## Evidence（`verified` の証跡）

証跡最小形の五項（`ref`・`environment`・`version`・`exit_status`・`observed_at`）を埋めた上で、`fingerprint` を持つか、`version` にコミットの SHA(内容の指紋を兼ねる等価規則。M-16)を置く。どちらも無いものは `verified` の証跡にならない。黙った省略を許さない。

## Scenario

`steps` の `actor`・`receiver`・`flow` は、静的構造に実在する `id` だけを指す（M-12。幽霊要素の禁止）。例外系は `kind: exception` とし、`exception_of` で正常系 Scenario の `id` を指す。

## TraceAnchor

- 必須は `id`・`target_kind`（`document`・`code_range`・`test`・`external_doc`・`artifact`）・`target`・`source_revision`（tag か SHA）・`observed_at`・`authority`。
- `authority` は `doctrine` か `gold_model` のちょうど一つ（M-10）。doctrine 管理下（統治木の文書・trace-index が指紋を持つコード範囲）の鮮度は doctrine の機構だけで判じ、契約外の鮮度は `observed_at`（必要なら `expires_at`）で見る。同じ anchor に二つの判定器を置かない。
- doctrine 権威の `code_range` anchor は、`source_revision` に完全 SHA を、`url` に SHA 固定の参照（blob の URL）を持つ。`realized_by` から指される anchor は `url` 必須（M-14。開ける参照）。

```json
{
  "id": "a-traceindex-py",
  "target_kind": "code_range",
  "target": "doctrine: plugin/scripts/trace-index.py(SPEC-026 の注釈対)",
  "source_revision": "8cd29bd0f2a94c31be6f4c0d9a7e5b12c3d4e5f6",
  "observed_at": "2026-08-04",
  "authority": "doctrine",
  "url": "https://github.com/Forest-Project-Lab/doctrine/blob/8cd29bd0f2a94c31be6f4c0d9a7e5b12c3d4e5f6/plugin/scripts/trace-index.py"
}
```
