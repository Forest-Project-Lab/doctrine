---
id: TEST-006
title: 依存グラフのテスト計画
type: TEST
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_depgraph.py]
depends_on: [SPEC-006]
llm_context: task
---

# 依存グラフのテスト計画

## 受入基準への対応

`plugin/tests/test_depgraph.py` が SPEC-006 の各契約を確認する。以下の TC（受入シナリオの識別子）ごとに対応づける。

- 前向き影響集合が推移閉包になること、循環があっても止まること、鎖が途切れた場合の扱い（TC-113..116）。[R4]
- 逆依存が現行文書のみに絞られること、また参照リンクだけでは逆依存に数えないこと（TC-078・TC-090）。[R3]
- 端が intra_domain / cross_domain_icd / cross_domain_violation / cross_domain_impact / dangling に正しく分類されること、および分類できない id の扱い（TC-069..072・TC-117・TC-123・TC-083）。[R7]
- 逆孤児を二種類（仕様の無い要求と、テストの無い仕様）に分けること（TC-093..095）。
- `resolve` の戻り値が `{path, domain, type, status}` のキーを持つこと。
- CLI の終了コードが 0/2/3 になること、`--reverse-refs` が既定で現行文書のみを返すこと。

## 退行観点

- 越境した impacts 端を、誤って `cross_domain_violation` に分類しないこと（WATCH の項目と照らし合わせて確かめる）。
- 逆依存と逆孤児の対象を、現行文書より外まで広げないこと。
- 所見が見つかっても CLI を非ゼロ終了にしないこと。問い合わせ用の CLI を、違反を止めるゲートと混同しない。

## 合否基準

`DepGraphCoreTest` と `DepGraphCLITest` のすべてのケースが合格すること。
