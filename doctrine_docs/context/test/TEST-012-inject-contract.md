---
id: TEST-012
title: inject-contract のテスト計画
type: TEST
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/tests/test_inject.py]
depends_on: [SPEC-012]
llm_context: task
---

# inject-contract のテスト計画

SPEC-012 の受入基準を `plugin/tests/test_inject.py` で確かめる `[R5]`。

## 受入基準への対応

- 節が定めた順（要点復唱 → … → 超過通知）どおりに描画されること。
- 上限を超えたときは要点まで切り詰め、それでも超過通知を必ず出すこと。超過の判定は、切り詰める前の推定値で行うこと。
- 重複 `id` があるとき、契約が運ぶのは登録簿の `resolve_duplicate_id` が返す一件であり、影の側の題も要点も契約に現れないこと（`TestDuplicateIdAgreesWithGraph`。ADR-049）。
- 監査要約の読み取りが共有コア `_auditcache` に一本化され、鼓動と同じ答えを返すこと。統治木を作り直したときに前の世代の要約を運ばないこと（tests/test_auditcache.py の `ReaderAgreementTest`・`ReinstallGenerationTest`。ADR-053）。
- 監査要約の受け渡しが `${CLAUDE_PROJECT_DIR}/.claude/.cache/last-audit.json`（スキーマ `docs-audit/1`、プロジェクトスコープ）を介して成り立つこと。監査要約が無いときは「前回監査なし」を出すこと。読み取りの候補順はプロジェクトスコープが先、旧 `${CLAUDE_PLUGIN_ROOT}/.cache` は後方互換の最後の候補（ADR-037）。同じ root を指す旧残骸が在っても新しいプロジェクトスコープの要約が勝ち、偽の死活警報を出さないこと（`test_project_scope_cache_wins_over_stale_plugin_root`）。契約が DECIDED/NONGOAL/WATCH の本文の要点行を運び、極小の上限では要点が削れて見出しが残ること（`TestContractCarriesFacts`。ADR-043、#88）。

## 退行観点

- never 群の本文も、どの文書の本文全量も、どの節にも現れないこと（WATCH と突き合わせる）。
- 内容に由来する例外が起きても、終了コードが非ゼロにならないこと（常に 0 を返し、セッションを落とさない側に倒す）。

## 合否基準

`plugin/tests/test_inject.py` の全ケースが通り、上記の退行観点が破れていなければ合格とする。

<!-- 入れない: 無関係な要求 -->
