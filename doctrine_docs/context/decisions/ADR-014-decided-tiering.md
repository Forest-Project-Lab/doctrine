---
id: ADR-014
title: DECIDED へ写すのは横断の確定事実だけとする
type: ADR
domain: context
status: accepted
owner: doctrine-maintainers
created: 2026-07-02
updated: 2026-07-02
sources: [doctrine_docs/model/research/RESEARCH-001-robustness-matrix.md]
depends_on: [SPEC-012]
llm_context: task
---

# DECIDED へ写すのは横断の確定事実だけとする

## 背景

頑健性評価（従来開発とビジネスの成果物584件の対応付け）で、確定事実の写し先として DECIDED が最多（113件）になった。DECIDED は置き場所が `_system/` に固定され、`llm_context` の既定が always である。ドメイン固有の確定や一回限りの確定まで写すと、常時集合が注入量の上限（12000トークン。DECIDED-001 の事実6）と衝突し、「常時投入は最小」の思想を脅かす。[R5]

## 却下した選択肢

- DECIDED の置き場所を `<domain>/` にも広げる。常時集合の境界が崩れ、どの DECIDED が常時なのかを機械で判別できなくなる。
- 注入量の上限を引き上げる。長い入力はそれ自体が成功率を下げる（付録C）。量を増やす解決は R5 に反する。

## 決定

DECIDED へ写すのは、体系・横断の確定事実だけとする。ドメイン固有の確定事実は、そのドメインの ICD「正本である事実」または task の文書（SPEC・ADR）で持つ。一回限りの確定（完了判定など）は accepted の ADR で持つ。常時集合に入れない事実は `llm_context` の上書き（§3.4）で外す。

## 帰結

常時集合は横断の事実に限られ、上限と衝突しにくくなる。docs-curate は、ドメイン固有の事実が DECIDED へ入っていないかを定例で点検する。保証限界: 「横断かドメイン固有か」の最終判断は機械では下せず、人に委ねる。

<!-- 入れない: 複数決定、現行仕様の全文 -->
