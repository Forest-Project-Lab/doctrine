---
id: SPEC-003
title: 三ガードの判定規則（不変・ICD依存・削除安全）
type: SPEC
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [spec/doctrine.ja.md §4.2]
depends_on: [REQ-004, ICD-001, ICD-002]
llm_context: task
---

# 三ガードの判定規則（不変・ICD依存・削除安全）

`policy-guard.py` の判定規則を定める。三ガード（不変=Guard1（不変性ガード）・ICD依存=Guard2（ICD依存ガード）・削除安全=Guard3（削除安全ガード））を不変→ICD依存→削除安全の順に当て、最初に拒否したガードで止める。登録簿の解決は ICD-001 に、ドメインと逆依存の解決は ICD-002 に依存する。`[R4]`（R4=変更耐性）`[R7]`（R7=境界明瞭）`[R8]`（R8=最小性）

## 入出力
入力は Hook の標準入力 JSON（フロントマター=文書冒頭のメタデータ）。`hook_event_name` と `tool_name` を見て、どの処理に振り分けるかを自分で決める。

- PreToolUse `Edit|Write|MultiEdit`: 三ガードを順に当て、`permissionDecision: "allow"` または `"deny"`（理由つき）を返す。
- PreToolUse `Bash`: 削除安全だけを当て、deny または allow を返す（deny だけを使う）。
- PostToolUse `Edit|MultiEdit`: 書き込んだファイルを読み直し、ICD依存または削除安全に違反していれば `decision: "block"` を、なければ空オブジェクトを返す。

各ガードの規則:

- 不変（Guard1, `[R8]`）: `<domain>/archive/` 下の編集を拒否する。既存の `type:ADR` ファイルの改変も拒否する。ただし carve-out だけは許す。carve-out とは、`status` を proposed→accepted・accepted→superseded・accepted→deprecated の範囲で動かし、`superseded_by` と `updated` を付ける編集をいう。
- ICD依存（Guard2, `[R7]`）: Write の content からフロントマターを読み、`depends_on` の各 dep を調べる。相手のドメインが自ドメインと異なり、しかも相手の型が ICD でなければ拒否する。dep の `status` は見ない（C12: 整合判断id）。Edit・MultiEdit は書き込む前に全文を組み立てられないため、PostToolUse の block に回す。
- 削除安全（Guard3, `[R4]`）: 現行（current/accepted）から deprecated/superseded/archived への降格、本文を空にする編集、Bash の `rm`・`git rm`・`mv` を対象とする。その文書を指す現行の逆依存が残っているとき、これらを拒否する。逆依存は graph の `reverse_current_dependents(id)` で引く。

## 制約
- 三ガードを不変→ICD依存→削除安全の順で当て、最初に拒否したガードで止める。
- ICD依存ガードは `status` を見ない（C12）。構造、すなわちドメインと、型が ICD かどうかだけを見る。
- R7 の拒否文は spec §4.2 を一字一句なぞる: `<dep> は <相手ドメイン> の内部です。<相手ドメイン> の ICD 宛にしてください。`
- C13（整合判断id）の分岐: 構文は正しく索引に無い dep（dangling）は許す（死リンクは監査が見つける）。登録簿が接頭辞から型を読めない dep（UNKNOWN（不明））は、安全側に倒して拒否する。
- Bash 経路は deny だけを使い、文脈の注入（additionalContext）も block も使わない。コマンドを `; && || | 改行` で分割し、各 `rm`・`git rm`・`mv` の対象を取り出す。
- PostToolUse の削除安全は PRE（書き込み前）から POST（書き込み後）への遷移で判じる。POST の全文に編集を逆向きに当てて PRE を復元し、本当に降格・本文消しが起きた組だけを咎める。

## エラー時挙動
- 不変ガードと削除安全ガードが落ちたら、安全側に倒して deny する（「ガード異常、手で確認」）。
- ICD依存ガードは、docs/ の外にある、フロントマターを持たない純粋な非文書の Write のときだけ、安全側に通して allow する。それ以外の例外は安全側に倒して deny する。
- 展開できない glob を含む削除コマンドは、安全側に倒して拒否する。
- Hook 事象では main から例外を投げない。判定は JSON に載せ、終了コードは常に 0 を返す。

## 受入基準
TEST-003 が次を確認する: 受入シナリオ TC（番号は次のとおり）。TC-070..072（越境ICD許可・非ICD拒否・同ドメイン許可）、TC-117（相手 `status` 無関係）、TC-123（分類不能=拒否）、dangling 連れ合い（=許可）、TC-075..077（不変）、TC-078..081（削除安全）、TC-118（block→張り替え→許可）、TC-119（Write deny と Edit block が同一違反）、TC-132（Bash deny に additionalContext も block も無い）。

<!-- 入れない: 廃止、検討、実装コードの写し -->
