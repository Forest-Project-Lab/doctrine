---
id: DECIDED-001
title: 横断の確定方針（8事実）
type: DECIDED
domain: _system
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md]
review_by: 2026-09-28
canonical_for: [cross-cutting-frozen-decisions]
llm_context: always
---

# 横断の確定方針（8事実）

本文書は、体系全体に効く確定事実の正本である。各事実は一文一義で書き、根拠ADR（ADR: 設計判断を一件ずつ記録する文書）のIDを示す。決定を変えるときは、根拠ADRを置換してから本表を更新する。各根拠はあくまで参照であって、依存ではない。

## 確定方針

1. 構造規則（型・`status`・置き場所・必須キー）は、`scripts/_registry.py` の中に一度だけ正本化する。他のスクリプト（実行可能な処理単位）は、この表を二重定義しない。
2. フロントマター（YAMLで書く文書先頭のメタデータ）の解析では、`parse(text)` が `(frontmatter, body, errors)` の3要素を返す。本文の内容を理由に例外を投げることはない。
3. 必須キーはちょうど8個（id・title・type・domain・`status`・owner・updated・sources）とする。`created` は必須に含めない。DECIDED と WATCH は、これに加えて `review_by` も必須とする。
4. ドメインを越える依存は、相手ドメインのICD宛だけを許す。相手ドメインの内部文書を直接の依存先にはしない。
5. 文書を削除・降格してよいのは、現行の逆依存がゼロのときだけとする。逆依存は dep-graph の `reverse_current_dependents(id)` で引く。
6. 常時投入の上限は、既定で 12000 トークン（LLMが一度に読み込む語の単位）とする。注入の上限とタスクパックの上限は、別々の二つのキーで持つ。
7. すべてのスクリプトは、標準ライブラリだけで動く。pipにも通信にも依存しない。
8. 技能は7個に固定する。Hook（特定の出来事で起動する処理）の設定は、セッション開始時に読み込んで以後固定する。

## 決定日

2026-06-30

## 根拠ADR

- 事実1: ADR-001（構造規則の単一正本化）
- 事実2: ADR-002（フロントマター解析の3要素戻り値）
- 事実3: ADR-001
- 事実4: ADR-003・ADR-006（ICD宛のみ・違反は depends_on 端のみ）
- 事実5: ADR-004（PostToolUse の事前状態を全文で復元）
- 事実6: ADR-009（注入とパックで二つの別上限）
- 事実7: ADR-011（段階導入と標準ライブラリのみ）
- 事実8: ADR-010・ADR-011（7技能固定・Hookスナップショット）

## 再点検期限

review_by: 2026-09-28（この期限で再点検する。置換済みの決定は、要点だけを残して一本に統合する）

要求の対応: 本確定群は [R2]・[R5]・[R6]・[R7]・[R8] を横断して固定する。

<!-- 入れない: 迷い、調査、提案中 -->
