---
id: TEST-012
title: inject-contract のテスト計画
type: TEST
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_inject.py]
depends_on: [SPEC-012]
llm_context: task
---

# inject-contract のテスト計画

SPEC-012 の受入基準を `plugin/tests/test_inject.py` で確かめる `[R5]`。

## 受入基準への対応

- 節が定めた順（要点復唱 → … → 超過通知）どおりに描画されること。
- 上限を超えたときは要点まで切り詰め、それでも超過通知を必ず出すこと。超過の判定は、切り詰める前の推定値で行うこと。
- 監査要約の受け渡しが `${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json`（スキーマ `docs-audit/1`）を介して成り立つこと。監査要約が無いときは「前回監査なし」を出すこと。

## 退行観点

- never 群の本文も、どの文書の本文全量も、どの節にも現れないこと（WATCH と突き合わせる）。
- 内容に由来する例外が起きても、終了コードが非ゼロにならないこと（常に 0 を返し、セッションを落とさない側に倒す）。

## 合否基準

`plugin/tests/test_inject.py` の全ケースが通り、上記の退行観点が破れていなければ合格とする。

<!-- 入れない: 無関係な要求 -->
