---
id: PROC-001
title: 開発規範 — 方法論の採用範囲と、機械の検算・人の査読の分担
type: PROC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-28
sources: [doctrine_docs/packaging/decisions/ADR-047-methodology-performance-noimpact.md, doctrine_docs/packaging/decisions/ADR-068-code-audit-residues.md, doctrine_docs/packaging/decisions/ADR-071-release-integrity-gate.md]
depends_on: [ICD-008]
llm_context: task
---

# 開発規範 — 方法論の採用範囲と、機械の検算・人の査読の分担

doctrine 本体を開発するときの規範の正本である。寄稿の案内 CONTRIBUTING（リポジトリ直下の CONTRIBUTING.md）はこの文書を指す（規範を二重定義しない）。`[R8]`

## 方法論の採用範囲（ADR-047 の再掲でなく参照）

- **テスト駆動**: 挙動を変えるときはテストを先に足す（または同じ変更で足す）。バグ修正は再現テストを添えてから直す。列挙を持つ次元の試験は、正本を読み込んだ添字と手書きの期待表で書く（ADR-060 の様式）。
- **ドメイン駆動**: 共有コア（`_` で始まるモジュール）を境界づけられた文脈として扱い、入口スクリプトはその利用者に徹する。規則はコアに一度だけ定義する（DECIDED-001 事実1）。
- **オブジェクト指向**: 重複の削減に効く箇所にだけ使う。抽象の先取り（使わない拡張点）は最小性に反するので作らない。

## 機械の検算（code-audit。ADR-068）

`plugin/scripts/code-audit.py` が、方法論の機械化残差を検める。CI が毎回走らせ、error で門を閉じる。

- import 境界（error）: 入口は入口を取り込まない／共有コアは入口を取り込まない／`_registry` は体系内の何も取り込まない。
- 二重定義リテラル（advisory）: 複数ファイルに同じタプル・集合・長い文字列定数の代入があれば名指しする。統合するかは人が決める。
- 肥大（advisory）: 関数 120 行・ファイル 1,300 行の上限（正本は `LIMITS`）を超えたら名指しする。分割するかは人が決める。
- 解析不能（error）: 構文解析に失敗した対象は黙って飛ばさず告げる。

per-turn の性能は受入の門で凍結する: 合成 1,500 文書で 1 編集のフック対（ガード＋リンタ）が 1 秒以内（ADR-047 の数値の確定。`plugin/tests/test_perf_gate.py`）。

## 追跡の三角（仕様⇔実装⇔試験）

追跡の機構（SPEC-026）は文書型を選ばない。仕様が実装の範囲の指紋を記録するのと同じ形で、**テスト文書（TEST）も、受入を凍結するテストコードの範囲の指紋を記録してよい**。記録すれば、テストの消失・改変が監査（trace_missing_impl / trace_stale）で見える。

## 手順

1. 変更は変更フロー（change-impact。決定の有無で段数が変わる。ADR-051）に載せる。
2. コードを触ったら、CI の前に手元で `python3 plugin/scripts/code-audit.py` を走らせてよい（任意。CI が最終の門）。
3. advisory（重複・肥大）は放置してよいが、同じ箇所へ三度目の指摘が出たら分割・統合を検討する（判断は人）。

## リリース手順（ADR-071）

1. 変更のたびに、CHANGELOG（リリースごとの変更を利用者向けに記す変更履歴
   ファイル。実体は CHANGELOG.md）の常設「未リリース」節へ一行を積む。
   `plugin/` に触れる pull request が積んでいないと、CI の門
   （`scripts/release-check.py`。SPEC-027）が止める。記録に値しない変更は、
   pull request の題名に `[no-changelog]` を書いて明示的に免れる。
2. リリースでは、「未リリース」節へ版番号と日付を付けて版付き節にし、版番号の
   正本（`plugin/.claude-plugin/plugin.json`）と `.claude-plugin/marketplace.json`
   の版を同じ値へ上げる。二つの一致は TEST-020 が、CHANGELOG との整合は
   同じ門が検める。
3. リリースの pull request の題名は `release: vX.Y.Z — 概要 (semver patch|minor|major)`
   の形に揃える（git 履歴が「何を変えたか」の正本。§3.8 の分担どおり）。
4. マージ後、自己適用の導入済み複製を更新し（`claude plugin update`）、新しい
   セッションを開始する。忘れても鼓動が「版の遅れ」で名指しする（ADR-070）が、
   検出はセーフティネットであり、手順の一部はこの段である。

## 保証限界

- **予防**: import 境界と解析不能だけを CI の門が止める。
- **検出**: 上の四種と、文書層の既存検査（逆孤児・着地・追跡）。
- **委ねる**: test-first の「順序」は履歴を持たない体系では検証できない。抽象の先取りかどうか・分割/統合の当否・設計の良し悪しは意味の判断であり、査読に残る（NONGOAL 第1項と同じ形）。

<!-- 入れない: 仕様の正本、ADR の再掲 -->
