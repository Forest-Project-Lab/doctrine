---
id: CHANGE-012
title: 器 0.2 への追随と requirements 口への参照切り替え（#294 第3信・第4信）
type: CHANGE
domain: model
status: current
owner: doctrine-maintainers
created: 2026-08-16
updated: 2026-08-16
sources: ["https://github.com/Forest-Project-Lab/doctrine/issues/294", "2026-08-16 の所有者の裁定（会話）"]
depends_on: [ADR-165]
llm_context: task
---

# 器 0.2 への追随と requirements 口への参照切り替え（#294 第3信・第4信）

## 変更内容

doctrine-lens が #294 で告知した二件を取り込む。

1. **器 0.2 への貼り直し**（第3信の告知。ADR-165 決定4 の合意にもとづく追随）。同梱する
   一枚を `plugin/schemas/system-map-gold-model-0.2.json` に貼り直す。固定点は tag
   `system-map/gold-model-0.2`（commit `991b8a6e3e6870d9651279956a8f7a60292e47af`）、
   指紋は sha256（内容の指紋を採る算法）で
   `92fa79c38b4db5e53ed1c02c73bdab948ccb41d6f7188531ee32972b5cb5a30c`。
   0.1 との差は、制約の追加（`realization`/`realized_by` の排他・`minLength: 1`）と版名
   だけであり、必須欄と語彙は動いていない（取得した一枚を機械で突き合わせて実測）。
2. **requirements 口への参照切り替え**（第4信。ADR-165 決定6 が定めた解除条件の成立）。
   器が書けない M 層の不変条件の機械可読の一覧は、lens 側の
   `validate.mjs --requirements --json`（`system-map/requirements/1`）を参照する。
   写さないのは変わらない。

## 理由（要求元）

- 貼り直すまで、doctrine の投影は上流の器（0.2）の門 M-18 で落ちる（第3信 §4 の実測。
  落ちるのは `schema` の値だけで、中身は 0.2 に適合している）。
- ADR-165 決定6 は「上流が機械可読の口を出したら、そのときに参照へ切り替える」と定めて
  おり、第4信でその口ができた。
- 要求元: 所有者が 2026-08-16 の会話で取り込みを裁定した。上流の告知は #294 の第3信
  （2026-08-14）・第4信（2026-08-15）。

## 影響の初期見積

決定の記録（ADR-168）、外部依存の登録（EXT-007 の付け替え・EXT-008 の新設）、現行仕様
（SPEC-031・SPEC-029 の版名）、実装（同梱の一枚・`_model.py`・`map-draft-check.py`・
README・技能の手引き二枚）、テスト（`test_model.py` の道と、模型を組む三つのテストの
版名）、投影（MODEL-001 の JSON・Overview）。詳細は IMPACT-012。

<!-- 入れない: 決定の理由づけ(ADR-168 が持つ)、実装の写し -->
