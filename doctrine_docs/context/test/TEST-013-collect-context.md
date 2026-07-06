---
id: TEST-013
title: collect-context のテスト計画
type: TEST
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_collect.py]
depends_on: [SPEC-013]
llm_context: task
---

# collect-context のテスト計画

SPEC-013 の受入基準を `plugin/tests/test_collect.py` で確かめる `[R5]`。

## 受入基準への対応

- 被覆を計算する前に never 群を取り除き、応答に一切現れないこと。
- 貪欲法で覆い、後ろ向きにそぎ落とした結果が、決定的に再現すること。各事実に出所が付くこと。
- depends_on をたどって ICD を多段に同梱し、never は引かないこと。
- `task_pack_token_cap` が `injection_token_cap` と独立に効くこと（C10とは凍結した契約の整合を見る判断項目をいう）。

## 退行観点

- 覆えなかった要求を隠さず、uncovered として理由を添えて表に出すこと（WATCH と突き合わせる）。
- 境界違反には印を付けるだけで、拒否はしないこと（拒否はガードの職分）。

## 合否基準

`plugin/tests/test_collect.py` の全ケースが通り、上記の退行観点が破れていなければ合格とする。

<!-- 入れない: 無関係な要求 -->
