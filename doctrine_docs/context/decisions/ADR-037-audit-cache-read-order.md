---
id: ADR-037
title: 監査要約キャッシュはプロジェクトスコープを先に読み、旧プラグインroot配置は後方互換のフォールバックに限る
type: ADR
domain: context
status: accepted
owner: doctrine-maintainers
created: 2026-07-27
updated: 2026-07-27
sources: [plugin/scripts/inject-contract.py, plugin/scripts/gov-heartbeat.py]
depends_on: [SPEC-012]
llm_context: task
---

# 監査要約キャッシュはプロジェクトスコープを先に読み、旧プラグインroot配置は後方互換のフォールバックに限る

## 背景

v0.4.0 で監査要約の書き込み先を、旧 `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（全プロジェクト共有）から、プロジェクトスコープ `${CLAUDE_PROJECT_DIR}/.claude/.cache/last-audit.json` へ移した。しかし読み取り側（`inject-contract.py`・`gov-heartbeat.py`）は旧配置を**第一候補**のまま残していた。

このため、移行前の残骸が同じプロジェクトルートを指して残っていると、次の恒久的な故障が起きる（#69、実機で再現）。SessionEnd 監査が毎回正しく新しい要約をプロジェクトスコープへ書いても、読み取りは root が一致する旧配置を先に採るため、古い要約を読み続ける。結果、`inject-contract` と `gov-heartbeat` の双方が「前回監査から N 日」という偽の R11 死活警報を毎セッション出す。自己修復の経路が無い。通常の marketplace 更新では `${CLAUDE_PLUGIN_ROOT}` ごと消えて起きにくいが、自己適用環境やローカル開発では残る。

## 却下した選択肢

- **旧配置の残骸を削除・改名する自己修復**: 書き込み権限や競合の考慮が要り、読み取り側が破壊的操作を持つのは責務違反。過剰であり、却下する。
- **`generated_at`/`today` が最も新しい候補を選ぶ**: 頑健だが、正常運用では書き込み先が一つ（プロジェクトスコープ）なので不要。最小の修正で足りる。

## 決定

読み取りの候補順を**プロジェクトスコープ優先**にする。`${CLAUDE_PROJECT_DIR}/.claude/.cache` → `cwd/.claude/.cache` → `${CLAUDE_PLUGIN_ROOT}/.cache`（後方互換の読み取りフォールバックとしてのみ最後）。現行の書き込み先を先に読むため、フレッシュな要約が常に勝ち、旧残骸は root が一致しても選ばれない。`inject-contract.py` と `gov-heartbeat.py` の両方に同じ順序を課す（握手の両端を一致させる）。root 照合（`_same_docs_root`）による越境汚染ガードは従来どおり全候補に効く。

## 帰結

- 移行前の残骸が在っても、偽の R11 死活警報が出なくなる（#69 の恒久故障を断つ）。
- 旧配置しか無い（移行前の）環境では、最後の候補として引き続き読めるので後方互換を保つ。
- SPEC-012 の受入基準（監査要約の受け渡し）を、候補順まで含めて明示する。
- root 照合は不変。別プロジェクトの所見は引き続き注入されない。
