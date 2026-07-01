---
id: TEST-001
title: 登録簿契約のテスト計画
type: TEST
domain: model
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [DOCTRINE-001]
depends_on: [SPEC-001]
llm_context: task
---

# 登録簿契約のテスト計画

SPEC-001 の登録簿契約を検証する。実装テストは `plugin/tests/test_registry.py`。[R2][R6][R8]

## 受入基準への対応

- 18 型の登録簿（順序・既定 `status`・既定 `llm_context`・置き場所）が、DATA-001 と一致する。
- `status_allowed` の許可表が型ごとに正しい。accepted は ADR だけ、draft は RESEARCH だけが許される。
- `type_of` が接頭辞を正しく読み取り、接頭辞が未知のとき、`id` が不正のとき、文字列でないときに None を返す。
- `effective_llm_context` が上書きを優先して解決し、型が不明のときや辞書でないときに None を返す。
- `required_keys` が DECIDED と WATCH に `review_by` を加え、level が不正なら ValueError を投げる。

## 退行観点

- 規則をほかのスクリプトが二重定義していないこと（WATCH-001 の「term-check 登録簿を二重定義しない」と整合する）。
- 返した集合やリストを書き換えても、登録簿が変わらないこと（複製を返すこと）。
- `domain_of` が登録簿に復活していないこと。

## 合否基準

全テストが成功し、許可表・置き場所・解決結果が DATA-001 と SPEC-001 の記述に一致したとき合格とする。ValueError は、例外を投げるべき箇所（level が不正な場合）でだけ出ることを確認する。

<!-- 入れない: 無関係な要求 -->
