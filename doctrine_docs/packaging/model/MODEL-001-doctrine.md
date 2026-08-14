---
id: MODEL-001
title: doctrine 自身の意味モデル（最小の下書き）
type: MODEL
domain: packaging
status: proposed
owner: doctrine-maintainers
created: 2026-08-14
updated: 2026-08-14
sources: [doctrine_docs/model/decisions/ADR-163-model-type-design.md]
llm_context: task
---

# doctrine 自身の意味モデル（最小の下書き）

MODEL 型の最初の実例である。**網羅を主張しない** —— 型と門が端から端まで働くことを示すための
最小の模型であり、要素も流れも契約も、doctrine の全体を写していない。全ての値は
`review_status: proposed` の候補であり、確定（`confirmed` と `status` の一押し）は人が行う。

値の正本はこの本文の塊である。JSON は `render-projection.py model --id MODEL-001` が隣へ描く。

## 系の概要

doctrine は、文書の統治（型・出所・依存・鮮度）を機械で支える体系である。境界の内側は
配布物と統治木、外側は利用者と実行環境である。

```json
{
  "target": "doctrine",
  "purpose": "古びた仕様がコードになるのを防ぐため、文書の型・出所・依存・鮮度を機械で見張る。",
  "boundary": "境界の内側は配布物(plugin/)と統治木(doctrine_docs/)。利用者・実行環境(Claude Code)・外部の表示製品は境界の外に居る。",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/model/decisions/ADR-163-model-type-design.md",
      "locator": "「意味モデルの型 MODEL（系の意味モデルを持つ文書の型）の設計」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

## 要素の一覧

### d-model — 登録簿（構造規則の正本）

```json
{
  "id": "d-model",
  "name": "登録簿（構造規則の正本）",
  "kind": "subsystem",
  "purpose": "型・status・置き場所・必須キー・必須節の規則を、体系の中で一度だけ持つ。",
  "responsibilities": ["type-registry の正本", "frontmatter-schema の正本"],
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/model/ICD.md",
      "locator": "「構造規則とフロントマターの解析を、体系の唯一の正本として公開する」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### d-lint — リンタ（編集ごとの点検）

```json
{
  "id": "d-lint",
  "name": "リンタ（編集ごとの点検）",
  "kind": "subsystem",
  "purpose": "編集された一つの文書だけを点検し、助言を返す。拒否はしない。",
  "responsibilities": ["document-lint", "term-check"],
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/lint/spec/SPEC-007-document-linter.md",
      "locator": "L27",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### d-audit — 監査（全件の走査）

```json
{
  "id": "d-audit",
  "name": "監査（全件の走査）",
  "kind": "subsystem",
  "purpose": "統治木の全件を走査し、所見と要約を出す。セッション境界と CI で走る。",
  "responsibilities": ["corpus-audit", "audit-summary-schema"],
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/audit/spec/SPEC-011-corpus-audit.md",
      "locator": "L22",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### d-graph — 依存グラフと追跡索引

```json
{
  "id": "d-graph",
  "name": "依存グラフと追跡索引",
  "kind": "subsystem",
  "purpose": "文書の依存の辺と、注釈の対が囲むコード範囲を、問い合わせのたびに導出して返す。",
  "responsibilities": ["dependency-graph-api", "trace-index-api"],
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/graph/ICD.md",
      "locator": "「追跡索引への問い合わせの入口をここで唯一定める」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### d-hooks — 配線（実行環境との接点）

```json
{
  "id": "d-hooks",
  "name": "配線（実行環境との接点）",
  "kind": "component",
  "purpose": "実行環境の七つの出来事を、各スクリプトへ配線する。",
  "responsibilities": ["hook-wiring"],
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/packaging/spec/SPEC-019-hooks.md",
      "locator": "「7 つのイベントを各スクリプトへ配線する仕様である」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

## 流れの一覧

### f-hook-lint — 編集の後にリンタを起こす

```json
{
  "id": "f-hook-lint",
  "from": "d-hooks",
  "to": "d-lint",
  "label": "編集の後にリンタを起こす",
  "kind": "command",
  "payload_or_action": "PostToolUse の封筒（編集された道を含む）",
  "condition": "Edit・Write・MultiEdit のいずれかが走ったとき",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/packaging/spec/SPEC-019-hooks.md",
      "locator": "「PostToolUse / matcher」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### f-lint-registry — 規則を登録簿へ問い合わせる

```json
{
  "id": "f-lint-registry",
  "from": "d-lint",
  "to": "d-model",
  "label": "規則を問い合わせる",
  "kind": "data",
  "payload_or_action": "必須キー・status の許可表・置き場所・必須節の問い合わせ",
  "condition": "点検のたび",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/lint/spec/SPEC-007-document-linter.md",
      "locator": "L29",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### f-audit-graph — 依存グラフを組ませる

```json
{
  "id": "f-audit-graph",
  "from": "d-audit",
  "to": "d-graph",
  "label": "依存グラフを組ませる",
  "kind": "data",
  "payload_or_action": "統治木の全 .md からの依存の辺",
  "condition": "全件監査のたび",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/audit/spec/SPEC-011-corpus-audit.md",
      "locator": "L22",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

## 契約の一覧

### c-lint-advises-only — リンタは拒否しない

```json
{
  "id": "c-lint-advises-only",
  "subject": "d-lint",
  "assumptions": ["点検は編集の後に走る", "拒否はガードが担う"],
  "guarantee": "リンタは decision を返さず、助言だけを出す。",
  "response_measure": "定性的である（返り値に decision の鍵が無いこと）",
  "verification_status": "planned",
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/lint/spec/SPEC-007-document-linter.md",
      "locator": "L51",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

### c-stdlib-only — 標準ライブラリだけで動く

```json
{
  "id": "c-stdlib-only",
  "subject": "doctrine",
  "assumptions": ["利用者の実行環境に python3 が在る"],
  "guarantee": "すべてのスクリプトは標準ライブラリだけで動き、pip にも通信にも依存しない。",
  "response_measure": "定性的である（外部の取り込みが無いこと）",
  "verification_status": "claimed",
  "owner": "doctrine-maintainers",
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/_system/decided-facts.md",
      "locator": "「すべてのスクリプトは、標準ライブラリだけで動く」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

## シナリオの一覧

### s-edit — 文書を一つ編集したとき

```json
{
  "id": "s-edit",
  "name": "文書を一つ編集したとき",
  "kind": "normal",
  "steps": [
    { "actor": "d-hooks", "receiver": "d-lint", "flow": "f-hook-lint" },
    { "actor": "d-lint", "receiver": "d-model", "flow": "f-lint-registry" }
  ],
  "provenance": [
    {
      "source": "doctrine: doctrine_docs/packaging/spec/SPEC-019-hooks.md",
      "locator": "「PostToolUse / matcher」",
      "checked_at": "2026-08-14",
      "verdict": "present"
    }
  ],
  "review_status": "proposed"
}
```

## アンカーの一覧

### a-spec-007

```json
{
  "id": "a-spec-007",
  "target_kind": "document",
  "target": "doctrine: doctrine_docs/lint/spec/SPEC-007-document-linter.md",
  "source_revision": "4d00eed7548275197289af796a13c222ac529da8",
  "observed_at": "2026-08-14",
  "authority": "doctrine"
}
```

### a-spec-011

```json
{
  "id": "a-spec-011",
  "target_kind": "document",
  "target": "doctrine: doctrine_docs/audit/spec/SPEC-011-corpus-audit.md",
  "source_revision": "4d00eed7548275197289af796a13c222ac529da8",
  "observed_at": "2026-08-14",
  "authority": "doctrine"
}
```

<!-- 入れない: 描いた JSON の写し、確定の判断そのもの、網羅の主張 -->
