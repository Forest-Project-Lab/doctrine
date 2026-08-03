---
id: CHANGE-007
title: 追跡索引の読み口を ICD へ宣言する（issue #204 合意の doctrine 側実装）
type: CHANGE
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-08-03
updated: 2026-08-03
sources: [https://github.com/Forest-Project-Lab/doctrine/issues/204, plugin/scripts/trace-index.py]
depends_on: [ICD-002, SPEC-026]
llm_context: task
---

# 追跡索引の読み口を ICD へ宣言する（issue #204 合意の doctrine 側実装）

## 変更内容

graph の ICD（ICD-002）へ、追跡索引の問い合わせ契約 `trace-index-api` を宣言する（JSON の形 `trace-index/1`・ranges の五項・終了コード。詳細の正本は SPEC-026 のまま動かさない）。あわせて、規範文書の複製 `Reference_material/` を `.gitignore` に足す（再配布条件を確認するまでコミットしない）。決定を含まない同乗として、DECIDED-001 の見出しの件数表記（11→12）の古びを直す。

## 理由（要求元）

issue #204 の合意台帳 v2（2026-08-03。v2-13・v2-11′・v2-14）。表示製品（doctrine-lens）は `trace-index/1` の五項を既に消費しているのに、ドメインの入口（ICD）に宣言が無い。越境の依存は ICD 宛だけという規律（DECIDED-001 事実4）に照らすと、「実装と仕様はあるが入口の宣言が無い」状態であり、実装の内部形が黙った契約になっている。

## 影響の初期見積

- 文書: ADR（新規1件）・ICD-002（宣言の追加。既存の依存グラフ契約は不変）・投影（ICD一覧・Overview）・DECIDED-001（見出しのみ）。
- 実装: なし（`trace-index/1` は実装済み。SPEC-026 §問い合わせが形の正本）。
- テスト: なし（挙動の変更が無い。受入は TEST-026 が凍結済み）。
- ドメイン跨ぎ: なし（宣言の追加は前方寛容。ICD-002 の現行逆依存 5 件は既存契約だけを読む）。

## 実施の記録

2026-08-03 に完了。決定は ADR-111、影響の列挙は IMPACT-007。ICD-002 へ `trace-index-api` を宣言し、`.gitignore` と分類の記録（`.md-intake`）へ `Reference_material/` を登録し、DECIDED-001 の見出しの件数表記を直した。上流の更新に伴う source_drift は 26 件——各件、追随不要（追加のみの変更）を確かめて `updated` を上げ、固定点で advisory 0 に収束した。全件監査 error 0 / warn 0 / advisory 0、試験・投影の照合・release-check の全ゲート通過を確認した。

2026-08-03 追補: 合意台帳が v3（第3版。「v」は版）を経て v3.1（自己完結版）へ置換され、所有者が P1（画面区分）・P2（実験ブランチ方式）・台帳 v3 を明示 ACK（承諾の表明）したため、正規の道（ADR-044）に従い ADR-112 で ADR-111 を置換し、記録を追随させた（三層ゲートと `UNASSESSED`（未評価）の記録・`planned` ↔ 検証戦略の対応・所有者 ACK の記録）。ICD-002 の根拠参照を ADR-112 へ更新。操作的内容（ICD 宣言・`.gitignore`・分類の記録）は無変更。全ゲートの通過を再確認した。
