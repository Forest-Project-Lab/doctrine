---
id: ICD-003
title: guard のインターフェース（三ガードの公開境界）
type: ICD
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.2]
canonical_for: [policy-guards]
llm_context: task
---

# guard ICD

## 公開する用語
ガード（違反を機械的に拒否するHook。Hook=ツール実行の前後で走るスクリプト連携点）、境界、ICD、現行、依存。語の意味は用語辞書の正本（GLOSSARY-001）に従う。

## 正本である事実
本ドメインは `policy-guards` の唯一の正本である。三ガード（不変・ICD依存・削除安全）の判定規則、各ガードの Hook JSON 契約、R7 拒否文の文面を、すべてここが正本として持つ。

## データ契約
他ドメインが依存してよい接点は次の三つである。

- 判定の入口は Hook の標準入力 JSON（フロントマター=文書冒頭のメタデータ。トークン=LLMが扱う語のおおよその数）である。`hook_event_name` と `tool_name` を見て、どの処理に振り分けるかを自分で決める。
- PreToolUse には `permissionDecision`（`allow` または `deny`）を返す。違反を止める手段は `deny` だけで、その理由に日本語のガード文を載せる。
- PostToolUse には `decision: "block"` を返す（Edit・MultiEdit を書き込んだ後に違反を見つけたとき）。Bash 経路は deny だけを使い、文脈の注入はできない。
- ICD依存違反の拒否文は次の形に固定する: `<dep> は <相手ドメイン> の内部です。<相手ドメイン> の ICD 宛にしてください。`

## 依存してよい入口
他ドメインは本文書（ICD-003）だけを `depends_on` できる。`policy-guard.py` の内部関数や IMPL-003 を直接指してはならない。

## 保証限界
- 予防: 相手の ICD 以外を指す越境依存、既存 ADR の改変、現行の逆依存が残ったままの降格や削除を、書き込む前に deny で止める。
- 検出: Edit・MultiEdit は書き込む前に全文を組み立てられない。そのため PostToolUse で読み直し、違反なら block する。
- 委ねる: 死リンク・逆孤児・古びの全件監査は audit（ICD-005）に委ねる。ドメインの解決は graph（ICD-002）に委ねる。

<!-- 入れない: 内部実装、内部の検討 -->
