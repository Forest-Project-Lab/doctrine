---
id: CHANGE-005
title: 不具合の兆候を記録し、承認を経た issue 報告を促す
type: CHANGE
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-28
sources: [plugin/scripts/gov-heartbeat.py, plugin/scripts/_auditcache.py]
depends_on: [SPEC-021, ICD-005]
llm_context: task
---

# 不具合の兆候を記録し、承認を経た issue 報告を促す

## 変更内容

フックの入口スクリプト5本（ガード・リンタ・注入・鼓動・監査）が握りつぶした
実行時例外の要約を、ローカルのエラージャーナル
（`.claude/.cache/doctrine-errors.jsonl`。git の追跡外）へ最善努力で残す。
記録するのは事象だけ — 部品名・例外の型と plugin 内の発生位置・プラグインの
版・時刻。統治対象の内容（リポジトリ名・パス・本文）は原理的に入らない
（例外の自由文を写さない許可制）。鼓動は記録が在るとき、issue への報告を
1セッション1回だけ促す — 下書きの全文を利用者に見せ、承認を得てから利用者の
手元の gh で投稿し、投稿できたら感謝を伝える、までを自己完結文で指示する。
報告は任意で、記録ファイルの削除で促しは消える。受け側として issue の
定型フォームを置く。スクリプトは通信しない（DECIDED 事実7 のまま）。

## 理由（要求元）

利用者の依頼（2026-07-28）: あらゆるリポジトリから使われる本プラグインの
不具合・その兆候を、機密を送らずに、利用者の確認を経て doctrine の issue へ
報告できるようにし、報告への感謝を伝えたい。現状、フックは例外を握りつぶして
会話を守る（正しい）が、握りつぶした事実は stderr にしか残らず、利用者にも
保守者にも届かない。沈黙する故障の禁止（R11）の延長として、倒れた記録を
見えるようにし、報告の経路を人の承認つきで用意する。

## 影響の初期見積

- 文書: ADR（新規1件）、SPEC-021（ジャーナルの契約・促しの梯子）、
  SPEC-011・SPEC-007・SPEC-003・SPEC-012（エラー時挙動の一行）、
  NONGOAL-001（自動送信はしない）、IMPL-019、TEST-021。
- 実装: `_auditcache.py`（ジャーナルの読み書き）、入口5本の例外処理、
  `gov-heartbeat.py`（促しの一項）、`.github/ISSUE_TEMPLATE/`（受け側の
  定型フォーム）、CONTRIBUTING.md（報告の歓迎と感謝）。
- ドメイン跨ぎ: ジャーナルは guard・lint・context・audit の入口が書き、
  packaging（鼓動）が読む。読み書きは共有コア `_auditcache` に一本化し、
  書式の正本は SPEC-021 に置く（発火の印と同じ形）。
- 技能は増やさない（DECIDED 事実8 のまま。促しの自己完結文で賄い、
  頻度の実績を見てから技能化を裁く）。

## 実施の記録

2026-07-28 に完了。決定は ADR-074、影響の列挙は IMPACT-005。ジャーナルの
読み書きを `_auditcache` に一本化し、入口5本を配線、鼓動の梯子に促しを追加、
issue の定型フォームと CONTRIBUTING の一節を置いた。受入はジャーナル6件・
促し4件を新設（全 1028 テスト緑、全件監査 error 0 / warn 0 / advisory 0）。
