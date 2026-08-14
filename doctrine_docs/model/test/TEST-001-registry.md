---
id: TEST-001
title: 登録簿契約のテスト計画
type: TEST
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-14
sources: [DOCTRINE-001]
depends_on: [SPEC-001]
llm_context: task
---

# 登録簿契約のテスト計画

SPEC-001 の登録簿契約を検証する。実装テストは `plugin/tests/test_registry.py`。[R2][R6][R8]

## 受入基準への対応

- 型の登録簿（順序・既定 `status`・既定 `llm_context`・置き場所）が、DATA-001 と一致する。
- `status_allowed` の許可表が型ごとに正しい。accepted は ADR だけ、draft は RESEARCH だけが許される。
- `type_of` が接頭辞を正しく読み取り、接頭辞が未知のとき、`id` が不正のとき、文字列でないときに None を返す。
- `effective_llm_context` が上書きを優先して解決し、型が不明のときや辞書でないときに None を返す。
- `required_keys` が DECIDED と WATCH に `review_by` を加える。**段の口は無い**（渡すと TypeError。ADR-106）。
- `resolve_duplicate_id` が、与える順序に依らず整列した順の最初を返す。空・None・文字列でない要素に例外を投げない（ADR-049）。
- 消した表（`SYSTEM_TIER_TYPES`・`ALWAYS_CONTRACT_TYPES`・`LEVEL3_KEYS`・`LEVEL4_KEYS`）が**戻っていない**こと（ADR-106）。`required_keys` が型だけを取り、段を渡すと `TypeError` になること。**登録簿の公開名が消費者を持つ**ことをメタの受入が検めること。
- `SUBDOMAIN_KINDS` が手書きの期待表と一致し、三語で重複が無い（ADR-092）。`TestRequiredKeys` が確認する。
- MODEL の登録（既定 `status`=proposed・既定 `llm_context`=task・置き場所 `<domain>/model/`・点検周期 180 日・必須節の六つ）が、手書きの期待表と一致する（ADR-163）。`test_model_registration` と置き場所・必須節の凍結試験が確認する。

## 退行観点

- 規則をほかのスクリプトが二重定義していないこと（WATCH-001 の「term-check 登録簿を二重定義しない」と整合する）。
- 返した集合やリストを書き換えても、登録簿が変わらないこと（複製を返すこと）。
- `domain_of` が登録簿に復活していないこと。
- ドメインの種類の項が、必須キーにも段階キーの梯子にも入り込んでいないこと（ADR-092）。**後から `review_by` の要求や再点検周期を足すと、この観点が落ちる** —— 項の上書きは機械に見えないので、期限を課しても守られたことを確かめられない。
- 重複 `id` の採用規則を、グラフ・注入・監査が自前で持ち直していないこと。三者の答えが食い違う状態（監査が告げる採用先と、契約が運ぶ文書が別）に戻らないこと（ADR-049）。

## 合否基準

全テストが成功し、許可表・置き場所・解決結果が DATA-001 と SPEC-001 の記述に一致したとき合格とする。ValueError は、例外を投げるべき箇所（level が不正な場合）でだけ出ることを確認する。

<!-- 入れない: 無関係な要求 -->
