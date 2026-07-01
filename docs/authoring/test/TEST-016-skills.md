---
id: TEST-016
title: skills の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_skills.py, plugin/tests/test_skills_authoring.py]
depends_on: [SPEC-016]
llm_context: task
---

# skills の検証

7技能の受入を検証する。`[R9]`

## 受入基準への対応

SPEC-016 の受入基準に対応する。次の各点を確認する。技能がちょうど7つあること。各 `description` が §7 の文言と一字一句一致し、三人称で500行未満であること。各技能が `## 保証限界` 節と、予防・検出・委ねるの三層を持つこと。各技能の本文と `references/` が用語チェッカーで誤りを出さないこと。各技能に固有の役割が書かれていること（初期化が既存を壊さないこと、フォルダや層をそのつど生成すること、ICD が予防・検出・委ねるを宣言すること、変更の手順が順序を守ること、どこからも依存されない文書だけを降格すること）。

## 退行観点

次の各点が崩れていないかを WATCH と突き合わせて確かめる。技能が7つを超えないこと（ICD 専用の技能を作らない）。機械で割り切れる処理を技能の本文へ書き戻さないこと。Level 2 で異常終了せず、機能を一部落としつつ穏やかに減ること。

## 合否基準

`plugin/tests/test_skills.py`（7つの技能すべてに共通する点検）と `plugin/tests/test_skills_authoring.py`（作成と流れに関わる4技能の中身の取り決め）が合格する。

<!-- 入れない: 無関係な要求 -->
