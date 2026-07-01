---
id: TEST-003
title: 三ガードの受入試験
type: TEST
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_guard.py]
depends_on: [SPEC-003]
llm_context: task
---

# 三ガードの受入試験

## 受入基準への対応
SPEC-003 の受入基準を `plugin/tests/test_guard.py` の各クラスで確認する。`[R7]`

- `TestR7IcdDependency`: 受入シナリオ TC（番号は次のとおり）。TC-070（越境ICD宛=許可）・TC-071（越境非ICD宛=拒否、拒否文を一字一句照合）・TC-072（同ドメイン=許可）・TC-117（相手が deprecated でも許可、`status` 無関係）・TC-123（分類不能=fail-closed 拒否）・dangling 連れ合い（索引に無いが既知型=許可）。
- `TestPostBlock`: TC-073（Edit は PRE（書き込み前）で許し POST（書き込み後）で block）・TC-074（MultiEdit の block）・TC-119（同一違反で Write deny と Edit block）・リンタは decision を出さない。
- `TestImmutability`: TC-075（無関係な現行文書の編集=許可）・TC-076（archive 下の Write/Edit=拒否）・TC-077（既存ADRの改変=拒否、carve-out の `status` 遷移=許可・本文変更=拒否）。
- `TestDeleteSafety`・`TestPostDeleteSafetyTransition`: TC-078..081（降格・本文消し・Bash rm/git rm/mv=拒否、逆参照ゼロ=許可）・TC-118（block→張り替え→許可）・既存 deprecated や既存空本文の無関係な編集は誤って block しない。
- `TestBashOutputGrammar`: TC-132（Bash deny に additionalContext も block も無い）。

## 退行観点
WATCH-001 と突き合わせる。守るべき退行は二つある。一つは、削除安全を PRE から POST への遷移で判じること、すなわち、もとから deprecated だったり本文が空だったりする文書を、無関係な編集で取り違えて block しないことである。もう一つは、Bash の拒否を deny だけで行うことである。

## 合否基準
列挙した全 TC が合格し、R7 拒否文が原文とバイト単位で一致し、取り違えの block と取り違えの deny がともにゼロのとき、合格とする。

<!-- 入れない: 無関係な要求 -->
