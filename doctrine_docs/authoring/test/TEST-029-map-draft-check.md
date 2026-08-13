---
id: TEST-029
title: map-draft-check の検証
type: TEST
domain: authoring
status: current
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-13
sources: [plugin/tests/test_mapdraft.py, plugin/tests/test_mapdraft_hardening.py, plugin/tests/test_read_surface.py]
depends_on: [SPEC-029]
llm_context: task
---

# map-draft-check の検証

意味モデル下書きの出所検証（機械の門）の受入を検証する。試験は決定的である: 壁時計を読まず `--today` を固定し、追跡索引は `--trace-json` で注入し、git の要らない素の木で退きの道を確かめる。

## 受入基準への対応

SPEC-029 の受入基準に対応する。次の各点を `plugin/tests/test_mapdraft.py` が確認する。正しい最小モデルが所見 0 で 0 終了すること。実在しないパスの出所・行数を超える `locator` の行番号・本文に無い引用が `D2_SOURCE_UNRESOLVED` で挙がり、実在する引用と `verdict: silent` の引用では挙がらないこと。未来の `checked_at` と形の崩れた日付が `D3_BAD_DATE` で挙がること。注入した追跡索引に無い `target` のアンカーが `D4_ANCHOR_UNMATCHED` で挙がり、在る `target` では挙がらないこと。依存辺（`dep-graph`・`depends_on`）を名指しした Flow の出所が `D5_FLOW_FROM_DEP_EDGE` で挙がること。負の出所を欠く `unknown` の Contract が `D6_UNKNOWN_WITHOUT_NEGATIVE` で挙がり、持つものは挙がらないこと。`confirmed` を名乗る実体が `D1_NOT_PROPOSED` で挙がること。最上位の必須キーの欠落・語彙の外れ値・`from`/`to` の欠落・JSON として読めないモデルが `D7_SHAPE` で挙がること。URL・会話・別接頭の出所が所見にならず機械検証不能の一覧に載ること。git の無い木で `@rev` と `source_revision` の検査が機械検証不能へ退くこと。使い方の誤りが 2、実体の欠落が 3 で終わること。`--json` が `map-draft-check/1` の形（findings・unverifiable・totals）を返すこと。

## 退行観点

次の各点が崩れていないかを確かめる。

- 捏造出所を通さない: 実在しない出所が所見にならなくなる緩みを、`D2` の負例（実在しないパス・行数超え・無い引用）が捕まえる。この門に固有の務めであり、ここが緩めば技能の検収そのものが崩れる。
- 検証可能性を偽らない: URL や履歴に無い rev を検証済みと言う変更も、逆に検証できないだけのものを所見（赤）と言う変更も、機械検証不能の一覧の試験が捕まえる。URL を取得して検証済みと称する変更は、ネットワーク不使用の制約への退行でもある。
- 依存辺の Flow 化を通さない: `dep-graph`・`depends_on`・`impacts` を出所に持つ Flow が黙って通る緩みを、`D5` の負例が捕まえる（M-08 の早期信号を消さない）。

## 合否基準

`plugin/tests/test_mapdraft.py` が合格する。実行は plugin/ から `python3 -B -m unittest tests.test_mapdraft` とする。

<!-- 入れない: 無関係な要求 -->

## 素通りさせない形（INC-035）

独立再監査 2026-08-09 の故障注入が実測した素通りの形を、一件ずつ凍結する
（`plugin/tests/test_mapdraft_hardening.py`）。凍結するのは「所見か機械検証不能の
どちらかへ必ず落ちる」ことであって、すべてを所見にすることではない —— 検証の道が
無いものは、道が無いと言えばよい。

正直な下書きが通り続けることも同時に見る（射程を狭めすぎない）。修正前に組んだ
故障注入の fixture 13 種を修正後のコードへ当て、13/13 が捕捉されることを実測した。
