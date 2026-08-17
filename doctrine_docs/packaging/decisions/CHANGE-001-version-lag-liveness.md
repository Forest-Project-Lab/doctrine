---
id: CHANGE-001
title: 導入済みプラグインの版の遅れを生存性として照合する
type: CHANGE
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-08-16
sources: [plugin/scripts/gov-heartbeat.py, plugin/scripts/_auditcache.py]
depends_on: [SPEC-021]
llm_context: task
---

# 導入済みプラグインの版の遅れを生存性として照合する

## 変更内容

鼓動（`gov-heartbeat.py`）に、実行中のプラグインの版と、このリポジトリ自身が
マーケットプレイスの正本として宣言する版（`.claude-plugin/marketplace.json`）
との照合を足す。食い違えば「導入済みの複製が正本より遅れている。更新して
新しいセッションを開始する」と助言する。マニフェストを持たない通常の導入先
では黙る。判定は共有コア（`_auditcache`）に一度だけ置く。

## 理由（要求元）

版 0.5.0 の公開後も、フックは 0.4.0 の導入済み複製で動き続けた。監査要約に
`trace_coverage` が載らず、紐づけキャンペーン・契約注入の進捗計・編集時の
促しがすべて沈黙した。生存期待 [R11] は「注入があるか」を見るが、「動いて
いる版が体系の正本より古い」は誰も見ていなかった（ADR-066 の版の切替の検出は
セッション途中の切替だけを見る — 遅れたまま切り替わらない場合は死角）。

## 影響の初期見積

- 文書: ADR（新規1件）、SPEC-021（照合の追加）、IMPL-019、TEST-021。
- 実装: `_auditcache.py`（判定の関数）、`gov-heartbeat.py`（助言の一行）。
- テスト: `test_auditcache.py`・`test_liveness_capture.py` に受入を足す。
- ドメイン跨ぎ: なし（packaging の中で閉じる）。

## 実施の記録

2026-07-28 に完了。決定は ADR-070、影響の列挙は IMPACT-001。実装・テスト・
投影まで同じ変更で落とし、全テスト（972件）が緑であることを確認した。
