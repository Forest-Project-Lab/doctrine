---
id: ADR-036
title: 統治木の無いプロジェクトでは二・三ガードとナッジ・退避を発火させない
type: ADR
domain: guard
status: accepted
owner: doctrine-maintainers
created: 2026-07-27
updated: 2026-07-27
sources: [plugin/scripts/policy-guard.py, plugin/scripts/review-nudge.py, plugin/scripts/capture-nudge.py, plugin/scripts/precompact-dump.py]
depends_on: [SPEC-003]
llm_context: task
---

# 統治木の無いプロジェクトでは二・三ガードとナッジ・退避を発火させない

## 背景

プラグインは利用者単位で導入される。doctrine を使う気の無いプロジェクト（統治木 `doctrine_docs/` も、`_system/` を持つ `docs/` も無い土地）でも、全 Hook は発火する。ここで次の誤爆が実機で確認された。

- **ICD 依存ガード（Guard2）の誤 deny**: frontmatter に `depends_on` 風のキーを持つ他体系（Obsidian・Jekyll 等）の `.md` を Write すると、依存 ID が登録簿の型として解けず C13 の fail-closed で deny になる。Edit では PostToolUse で block になる。
- **doc-review ナッジと Stop 差し止めの越境発火**: `type: SPEC` 等の登録簿型を持つ `.md` を編集すると、存在しない `_system/glossary.md` への書き戻し指示が注入され、`edits-<sid>` の印が残り、セッション終端の Stop が一度差し止められる。
- **退避指示の越境発火**: PreCompact が、存在しない `_system/.session-notes` への退避を指示する。

リンタは ADR-024 で「統治木の外・体系外のファイルには schema 強制をしない（用語助言のみ）」という境界を既に持つ。ガードとナッジ・退避には同じ境界が無かった。

## 却下した選択肢

- **frontmatter の有無で判定する（従来の proxy）**: fail-open を「フェンス `---` を持たない純粋な非文書」に限っていた。しかし `depends_on` を持つ他体系の文書は `---` を持つため取りこぼす。誤爆の直接原因であり、却下する。
- **深く沈黙させる（木の外の文書には常に無発火）**: 統治木が在るプロジェクトの stray 文書（木の外に置かれた型付き文書）まで無発火にすると、越境依存の予防が効かなくなる。過剰であり、却下する。

## 決定

**判定は「このファイルのプロジェクトに統治木が一つでも解決できるか」に置く**（`walkup_docs_root(file_path, cwd)` が None でないか）。統治木が一つも無いプロジェクトでは、次を発火させない。

- Guard2（ICD 依存）と Guard3（削除安全）: PreToolUse で早期に allow、PostToolUse で静かに通す。Guard1（不変性）は統治木の中の archive/ADR にしか効かないため元から無影響。
- review-nudge: 印も助言も出さない。
- capture-nudge: 印が残らないため Stop を差し止めない（review-nudge を根で断つことで従属的に解決）。
- precompact-dump: 退避指示を出さない。

統治木が在れば、木の外の stray 文書に対しても**従来どおり**点検する（境界は「プロジェクトに木が在るか」であって「この文書が木の中か」ではない）。これは ADR-024 がリンタに定めた体系外無発火の境界を、ガードとナッジ・退避へ一貫適用したものである。

## 帰結

- doctrine 未導入のプロジェクトで、他体系の文書編集を誤って拒否・差し止めしなくなる（`R7` の予防は統治対象の内側に限定される）。
- 統治木が在るプロジェクトの挙動は不変（回帰テストで固定）。stray 文書の越境依存は引き続き deny する。
- 「統治木の存在」は `walkup_docs_root` の一箇所で判定し、各スクリプトはそれを読む（規則をコードに二重定義しない）。
- 既知の限界: 統治木が在るプロジェクトでは、いずれの Hook も従来どおり発火するため、本 ADR は導入済みプロジェクトの利用者体験を変えない。
