---
id: TEST-006
title: 依存グラフのテスト計画
type: TEST
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-08-13
sources: [plugin/tests/test_depgraph.py, plugin/tests/test_read_surface.py]
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
- 重複 `id` のとき、ノードになるのは登録簿の `resolve_duplicate_id` が返す一件（整列した順の最初）であり、`resolve` の答えがそれと一致すること（ADR-049）。
- CLI の終了コードが 0/2/3 になること、`--reverse-refs` が既定で現行文書のみを返すこと。

## 退行観点

- 越境した impacts 端を、誤って `cross_domain_violation` に分類しないこと（WATCH の項目と照らし合わせて確かめる）。
- 逆依存と逆孤児の対象を、現行文書より外まで広げないこと。
- 所見が見つかっても CLI を非ゼロ終了にしないこと。問い合わせ用の CLI を、違反を止めるゲートと混同しない。
- 両端から書かれた同じ事実に印が付くこと（ADR-088）。`MirroredEdgeTest` が確認する —— 両端書きは印が付き、片方だけは付かず、`kind` は据え置き、**両端書きを循環として返さず**、本当の循環は引き続き `find_cycles` が返すこと。読み手が自前の鍵で畳んだ結果と印が一致することも見る。
  実物で確かめてある（2026-08-02）: 呼び手の木で 10 対 = 20 本（辺の 28%）が印を持ち、自前の鍵で数えた結果と完全に一致した。issue の実例（`IMPL-001 → SPEC-001` ほか）を再現している。
- 直列化が項を隠さないこと（ADR-087）。`title` と鮮度の項（`updated`・`review_by`・`llm_context`・`superseded_by`）が返り、**組み立てが節点へ入れた項と直列化が返す項が一致する**こと。後者が本当の歯止めである —— 正本を書いても、一致を機械が見ていなければまたずれる。
  `JsonNodeShapeTest` が確認する。**歯止め自身の実効を実測してある**（2026-08-02）: 白名簿を復活させると一致の検査が落ち、組み立てから題名を外すと題名の検査が落ち、復元すると全て通った。
- **必須キー8個がすべて節点に在ること**（ADR-098）。`owner` は集めていない最後の一つで、題名・出所に続く三件目だった。**この観点が四件目を防ぐ。**
- 節点が `sources` を運ぶこと（ADR-097）。**必須項なのに集めていなかった**ので、宣言した道が実在するかを誰も検められなかった（ADR-087 が名指した欠陥の二件目）。
- 節点がドメインの種類を運ぶこと（ADR-092）。三語がそのまま返り、未分類は**空文字**で返って項が消えないこと（項が消えると「未分類」と「取れなかった」を読み手が見分けられない）。語彙に無い値も黙って捨てず運ぶこと（当否はリンタが検める）。`SubdomainNodeTest` が確認する。**実効を実測してある**（2026-08-02）: 組み立てから項を外すと落ち、復元すると通った。
- スカラの項が入れ物（一覧・写像）に対して内部表記を返さないこと。`title: [t]` が `"['t']"` として載らない。**一項ではなくスカラの項すべてを見る**（共有の補助の欠陥だった）。`SubdomainNodeTest` の `test_no_field_leaks_a_container_repr` が確認する。**実効を実測してある**（2026-08-02）: 補助を元の `str()` へ戻すと落ちた。

## 合否基準

`DepGraphCoreTest`・`DepGraphCLITest`・`JsonNodeShapeTest`・`MirroredEdgeTest` のすべてのケースが合格すること。`find_cycles` は自己依存・多頂点循環を検出し、非循環と dangling 端は空を返す（ADR-038）。
