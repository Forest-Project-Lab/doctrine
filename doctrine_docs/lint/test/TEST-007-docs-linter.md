---
id: TEST-007
title: リンタのテスト計画
type: TEST
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/tests/test_linter.py]
depends_on: [SPEC-007]
llm_context: task
---

# リンタのテスト計画

## 受入基準への対応

- SPEC-007 の各点検を、発火すべき入力と発火すべきでない入力の両方で確認する[R2]。対象は、必須キー不足・空キー・`status` の型別許可・未知の型・`id` とファイル名の一致・型と置き場所の整合・ドメイン区画・`llm_context`・SPEC の 4 節・追跡性・ICD 依存（事後検出）である。
- フロントマターが無いときは `MISSING_FRONTMATTER` 一件で止まること、`_system` の固定ファイル名が id とファイル名の一致点検を免除されることを確認する。
- ADR-075: フロントマターの構文の誤りが `FRONTMATTER_SYNTAX`（ERROR）で表に出ること。
- ADR-075: 根の案内（CLAUDE.md・AGENTS.md）と dot ディレクトリ配下へ何も出さないこと。
- ADR-075: 依存先のドメインの解決で兄弟文書を開かないこと（開いた統治文書が編集対象の一件だけであること）。
- ADR-075: 助言の描画が `sanitize_inline` を通ること（改行入りのファイル名で偽の所見行を作れないこと）。
- ADR-075: 必須節の直後に小見出しを置いた SPEC が `SPEC_EMPTY_SECTION` にならないこと。
- ADR-075: 発火の印が PostToolUse の経路のときだけ残ること。

## 退行観点

- リンタは決して `decision` を出さず、助言だけを出す[R7]。WATCH に挙げた懸念事項と突き合わせて確かめる。
- 例外が起きても終了コードは 0 で、後続の Hook の連鎖を壊さない。
- `RESEARCH_HAS_DECISION` の見出し照合が、語を別語にする接尾（`決定的`・`決定論`）を巻き込まないこと。併せて『決定』を主題にした見出し（`## 決定`・`## 決定の背景`・`## 我々の決定事項`）は引き続き咎めることを見る（ADR-082。WATCH 第10項。門が正しいものを咎める型は、見逃しより害が大きい）。

## 追加の観点（ADR-021）

- `STRAY_DOCUMENT`: 登録簿の型を持つ .md が doctrine_docs/ の木の外に在れば `ERROR` で出ること。doctrine_docs/ の中の型付き文書と、doctrine_docs/ の外の型なし .md には出ないこと。

## 追加の観点（ADR-024・監査との整合）

- ①登録済み非文書: intake に『非文書』と登録された型なし .md には `MISSING_FRONTMATTER` も schema の ERROR も出ないこと（用語助言は WARN で可）。②統治木の中の型なし・未登録 .md には従来どおり `MISSING_FRONTMATTER`（ERROR）が出ること。③型付き文書が統治木のサブツリーの外なら `STRAY_DOCUMENT` を維持すること。④統治木の根に到達できない体系外のファイルには何も出さないこと。⑤『ビュー』と登録された型なし .md も schema 強制を飛ばし、刻印が無ければ `VIEW_MISSING_STAMP`（WARN）が出ること、刻印があれば出ないこと（ADR-073）。
- 整合の合否は `scripts/consistency-check.py` が緑（監査が非文書と認めるファイルにリンタが ERROR を出さない）であることでも確かめる。

## 合否基準

- `tests/test_linter.py` が全観点で合格すること。各点検が期待どおりのコードと重大度で発火し、誤検出が無いことを合格とする。
- `BatchModeTest`(#91): `--batch` が clean な木で 0、ERROR を含む木で 1、統治木なしで 0 を返す。

<!-- 入れない: 無関係な要求 -->
