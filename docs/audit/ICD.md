---
id: ICD-005
title: audit のインターフェース（全件監査の境界）
type: ICD
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md#4.2]
canonical_for: [corpus-audit, audit-summary-schema]
llm_context: task
---

# audit ICD

全件監査（corpus-audit）が外部に公開する境界を定める。コーパス全体を一度に走査して所見と要約を出すスクリプト `docs-audit.py` の接点である。`[R1][R3][R8]`

## 公開する用語

- 監査: コーパス全件を走査し、過剰な文書と不足している文書を一覧にする処理。一往復ごと（per-turn）には走らない。セッションの区切りで起動する Hook（プラグインがイベントを受けて起動するスクリプト）と、CI（継続的インテグレーション）の自動実行からだけ走る。
- 孤児: どの現行文書からも依存されない文書。
- 逆孤児: あるべき文書が欠けている状態。対応する仕様を持たない要求や、対応するテストを持たない仕様がこれに当たる。

ICD・正本・投影・現行・依存・参照は用語辞書（`_system/glossary.md`）の正本を参照する。

## 正本である事実

このドメインだけが正本となる事実を挙げる（frontmatter の `canonical_for` と一致する）。

- `corpus-audit`: 全件監査の検査群（9 検査）と、各検査の重大度。
- `audit-summary-schema`: 監査の要約スキーマ `docs-audit/1` の形。

9 検査と重大度（固定）:

| 検査名 | 重大度 |
|---|---|
| dead_link | error |
| review_by_overrun（DECIDED/WATCH の不在も含む） | warn（不在は error） |
| stale_draft | warn |
| orphan | error |
| reverse_orphan_req_no_spec / reverse_orphan_spec_no_test | error |
| canonical_conflict | error |
| near_duplicate（語彙的酷似） | advisory |
| icd_dependency_violation | error |
| projection_drift | error（Context Map のラベル差のみ warn） |

## データ契約

他ドメインが依存してよい入出力を定める。

- 入力: docs ルート、`--config`（調整値）、`--today YYYY-MM-DD`（基準日。同じ値なら毎回同じ結果になる）。
- 返す値: 要約スキーマ `docs-audit/1`。形は `{schema, generated_at, today, root, totals:{error,warn,advisory}, counts_by_check, top_findings, findings}`。`top_findings` は error を先頭に並べ、上限 20 件とする。
- 終了コード: SessionEnd 経路（`--fail-on never`）は常に 0 を返し、セッションの後始末を妨げない。CI 経路（`--fail-on error`）は error 所見が一つでもあれば 1 を返す。
- context ドメインへの注入との受け渡し: 監査は要約を `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（読めない場合は `.claude/.cache/last-audit.json`）へ書く。書き込みは一時ファイルを経て一括で差し替え、途中状態を残さない。次のセッションで context の SessionStart 注入がこの要約を読む。

## 依存してよい入口

他ドメインが `depends_on` できるのは、この ICD だけである。内部の `audit/spec/` や `audit/implementation/` を指す依存は認めない。audit 自身は、登録簿を model の ICD（ICD-001）に、ドメインの解決を graph の ICD（ICD-002）に依存する。
