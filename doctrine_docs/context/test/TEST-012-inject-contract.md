---
id: TEST-012
title: inject-contract のテスト計画
type: TEST
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-07
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
- 見積りと較正が共有コア `_tokens` に一本化されていること（ADR-105）。較正が効くこと（2.0 で 1000 文字が 500）、**壊れた値（零・負・非数・真偽値・無限）が既定へ退避し負を返さないこと**、例外を投げないこと、**パックが較正を読むこと**（以前は説明文だけが約束していた）。**歯止め自身の実効を実測してある**（2026-08-03）: 較正の退避を外す／パックが較正を読まないように戻す／写しを一つ作る／見積りの天井を床へ替える、の四通りで落ち、いずれも戻すと通った。
- 設定の読み取りが共有コア `_config` に一本化されていること（ADR-104）。BOM 付きの設定も読めること、写像でないとき・壊れているとき・通常ファイルでないときに空の写像を返して例外を投げないこと、**設定の名前を文字列定数で持つスクリプトが正本の外に無いこと**（`TestConfigIsReadThroughTheCanon`）。**歯止め自身の実効を実測してある**（2026-08-03）: 正本を `utf-8` へ緩めると落ち、設定の名を自前で持つ写しを作ると落ち、共有の読み手を素の `open` へ替えると落ちた。**通常ファイルの門は構造で凍らせる** —— 名前付きパイプで戻らないことは測れない（測ろうとすると試験が止まる）ので、「共有の読み手を呼び、素の `open` を持たない」ことを見る。ディレクトリを置く試験は頑健さの検めであって門の証明ではない（素の `open` でも同じく黙ることを実測した）。
- 監査要約の読み取りが共有コア `_auditcache` に一本化され、鼓動と同じ答えを返すこと。統治木を作り直したときに前の世代の要約を運ばないこと（tests/test_auditcache.py の `ReaderAgreementTest`・`ReinstallGenerationTest`。ADR-053）。
- 監査要約の受け渡しが `${CLAUDE_PROJECT_DIR}/.claude/.cache/last-audit.json`（スキーマ `docs-audit/1`、プロジェクトスコープ）を介して成り立つこと。監査要約が無いときは「前回監査なし」を出すこと。読み取りの候補順はプロジェクトスコープが先、旧 `${CLAUDE_PLUGIN_ROOT}/.cache` は後方互換の最後の候補（ADR-037）。同じ root を指す旧残骸が在っても新しいプロジェクトスコープの要約が勝ち、偽の死活警報を出さないこと（`test_project_scope_cache_wins_over_stale_plugin_root`）。契約が DECIDED/NONGOAL/WATCH の本文の要点行を運び、極小の上限では要点が削れて見出しが残ること（`TestContractCarriesFacts`。ADR-043、#88）。

## 退行観点

- never 群の本文も、どの文書の本文全量も、どの節にも現れないこと（WATCH と突き合わせる）。
- 内容に由来する例外が起きても、終了コードが非ゼロにならないこと（常に 0 を返し、セッションを落とさない側に倒す）。

## 合否基準

`plugin/tests/test_inject.py` の全ケースが通り、上記の退行観点が破れていなければ合格とする。

<!-- 入れない: 無関係な要求 -->
