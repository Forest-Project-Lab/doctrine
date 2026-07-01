---
id: TEST-007
title: リンタのテスト計画
type: TEST
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_linter.py]
depends_on: [SPEC-007]
llm_context: task
---

# リンタのテスト計画

## 受入基準への対応

- SPEC-007 の各点検を、発火すべき入力と発火すべきでない入力の両方で確認する[R2]。対象は、必須キー不足・空キー・`status` の型別許可・未知の型・`id` とファイル名の一致・型と置き場所の整合・ドメイン区画・`llm_context`・SPEC の 4 節・追跡性・ICD 依存（事後検出）である。
- フロントマターが無いときは `MISSING_FRONTMATTER` 一件で止まること、`_system` の固定ファイル名が id とファイル名の一致点検を免除されることを確認する。

## 退行観点

- リンタは決して `decision` を出さず、助言だけを出す[R7]。WATCH に挙げた懸念事項と突き合わせて確かめる。
- 例外が起きても終了コードは 0 で、後続の Hook の連鎖を壊さない。

## 合否基準

- `tests/test_linter.py` が全観点で合格すること。各点検が期待どおりのコードと重大度で発火し、誤検出が無いことを合格とする。

<!-- 入れない: 無関係な要求 -->
