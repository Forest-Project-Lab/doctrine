---
id: CHANGE-009
title: 監査要約の読み口を ICD へ宣言する（issue #212 の overlay 入力への回答）
type: CHANGE
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-13
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/212"]
depends_on: [ICD-005]
llm_context: task
---

# 監査要約の読み口を ICD へ宣言する（issue #212 の overlay 入力への回答）

## 変更内容

audit の ICD（ICD-005）のデータ契約へ、外部利用者の読み口を一行宣言する ——
`docs-audit.py --root <統治木> --json` の返す値（`docs-audit/1`）だけに依存してよい。
`.claude/.cache/last-audit.json` は体系内部の受け渡しのままで契約の外（ADR-137）。

## 理由（要求元）

issue #212（System Map Phase 2）の合意台帳の第4版の案が、overlay の入力の閉じた列挙に
監査要約を挙げ、doctrine 側の意見を求めた。要約スキーマの正本（ICD-005）は在るが、
外部の受け取り経路が宣言されていなかった。宣言なき消費は実装の内部形が黙った契約に
なる（追跡索引で踏んだ形。CHANGE-007）。

## 影響の初期見積

- 文書: ADR-137（新規）・ICD-005（データ契約へ一行）・投影（ICD 一覧・Overview）。
- 実装: なし（`--json` と `--today` は実装済み。SPEC-011 が形の正本）。
- テスト: なし（挙動の変更が無い）。
- ドメイン跨ぎ: なし（宣言の追加は前方寛容。ICD-002 へ相互参照は足さない ——
  二重列挙のドリフトを避ける）。

## 実施の記録

2026-08-07 に完了。決定は ADR-137、影響の列挙は IMPACT-009。
