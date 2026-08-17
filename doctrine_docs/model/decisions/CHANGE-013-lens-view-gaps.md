---
id: CHANGE-013
title: 第5信の欠けへの応え — MODEL の列挙・複数の木・出所ごとの判定・語彙の在り処
type: CHANGE
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", "2026-08-16 の所有者の裁定（会話）"]
depends_on: [ADR-168]
llm_context: task
---

# 第5信の欠けへの応え — MODEL の列挙・複数の木・出所ごとの判定・語彙の在り処

## 変更内容

doctrine-lens が #294 第5信（2026-08-16）で挙げた欠け 6 点と小 2 点へ応える。
第5信は各欠けに G1（欠けの1番）から G6（欠けの6番）までの番号を振っており、
本文書も同じ番号で指す。内訳は次のとおり。

1. **G1（MODEL を列挙する読み口の欠け）**: 木の中の MODEL を列挙する読み口
   `model-index/1` を新設する（`render-projection.py model --list`。ADR-169）。
2. **G2（一つの模型が複数の木にまたがれない欠け）**: 一つの MODEL が複数のリポジトリの
   系を描くことを射程内とし、跨ぐ接頭の宣言を正本 .md のフロントマター（任意キー
   `repos`）に置く。ローカル経路は宣言せず、実行時の束縛（`--repo 接頭=経路`）のまま
   残す（ADR-170）。
3. **G5（出所ごとの判定が読み口に無い欠け）**: `map-draft-check/1` に出所ごとの機械の
   判定（五値の verdict）と、測った木の版（`repos` の各項）・作り手（`generator`）を
   足す（ADR-171）。
4. **G6（表示語彙を誰が持つかの未決）と小2点**: 表示語彙は view の領分とし doctrine は
   持たない。実測の述語の正本は lens 側 requirements 口の `policy` とし写さない。鮮度の
   三値の判定規則は ICD-002 の版の鍵の宣言に定める（ADR-172）。
5. **G3（主張と出所を結ぶ任意欄の提案）**: 器へ任意欄 `supports` を足す提案が doctrine の
   導出面（必須欄・語彙・段・出所・最上位・版）に影響しないことを機械で確かめ、#294 へ
   報告する（決定は要らない。実測のみ）。
6. **G4（locator が機械で辿れない欠け）**: `locator` の形の要求は器の版上げ（lens 側）と
   して受領する。告知が来たら ADR-165 決定4 の合意どおり追随する（本波では変更しない）。

## 理由（要求元）

- 所有者が 2026-08-16 の会話で「第5信を読み、doctrine-lens 側の要望に応える」ことを
  裁定した。上流（lens）は「先に上流の判断が要るのは G2 と G6 だけ」と明言しており、
  G1・G5 は読み口の欠けとして実測つきで挙がっている。
- lens 側の方針転換（Lens は view に徹し、画面が要る事実は doctrine が管理する）により、
  模型そのものが統治木へ移る。列挙の読み口（G1）と出所ごとの判定（G5）が無いと、
  移した後の画面が「実測」と「書き手の主張」を機械の言葉で分けられない。

## 影響の初期見積

決定の記録（ADR-169〜ADR-172）、現行仕様（SPEC-014・SPEC-029・SPEC-031）、境界の宣言
（ICD-006・ICD-007・ICD-002）、注入する事実（DECIDED-001 事実13 の採用先）、実装
（`render-projection.py`・`map-draft-check.py`・`_model.py`・MODEL-001 の宣言）、テスト
（TEST-014・TEST-029・TEST-031 と plugin/tests）、投影（Overview）。詳細は IMPACT-013。

<!-- 入れない: 決定の理由づけ(各 ADR が持つ)、実装の写し -->
