---
id: ADR-078
title: Hook 事象の集合を数で凍らせず、能力で検める
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-02
updated: 2026-08-02
sources: ["外部レビュー 2026-07-31", "Claude Code 公式 hooks reference 2026-08-02 再確認", "doctrine#156"]
depends_on: [SPEC-019]
llm_context: task
---

# Hook 事象の集合を数で凍らせず、能力で検める

## 背景

`plugin/tests/test_packaging.py` の `test_has_all_seven_events` は、`hooks.json` の事象の
集合を**完全一致**で凍らせていた。

```python
events = set(self.hooks.get("hooks", {}).keys())
self.assertEqual(events, {"SessionStart", "UserPromptSubmit", "PreToolUse",
                          "PostToolUse", "Stop", "PreCompact", "SessionEnd"})
```

これは「7個が全部在る」ではなく「事象の集合はちょうど 7 個である」を凍らせている。
`EXT-001` も同じ 7 個を名前で書き下していた。

**現行の公式仕様が定める事象は 30 個ある**（2026-08-02 確認）。7 個の外に、統治に直接効く
ものとして少なくとも `SubagentStart`・`SubagentStop`・`TaskCompleted`・`PostToolBatch`・
`ConfigChange`・`PermissionRequest`・`PreToolUseFailure`・`PostToolUseFailure` がある。

したがって **実行環境の機能追加を取り込む改善が、テスト破壊として現れる**。守っている
つもりの門が、門を増やすことを禁じている。

## 却下した選択肢

**期待する集合に新しい事象を足して回る。** 名前の列挙を保つ限り、上流が増えるたびに
こちらが追う。追い忘れれば同じ壁がまた立つ。列挙そのものが陳腐化する形である。

**集合の検査をやめる。** 配線の欠落（既存の 7 個のどれかが消える）を検出できなくなる。
凍らせたいのは「必要な配線が在る」であって「余計な配線が無い」ではない。

**上流の事象一覧をこちらに持つ。** `REQ-003`（上流の語彙をこちらが持たない）に反する。
名前の一覧を持てば、それ自体が古びる。

## 決定

**「必要な事象がすべて配線されている」を検め、集合の上限は凍らせない。**

1. `test_has_all_seven_events` を、必要な 7 個が**部分集合として在る**ことの検査に変える。
   事象を増やしても落ちない。減らせば落ちる。
2. 名前を検査に残すのは、配線の欠落を捉えるためだけとする。上限の主張はしない。
3. `EXT-001` を、事象名の列挙から**依存している能力**の記述へ書き換える。名前の列挙は
   `review_by` の周期より速く動く。
4. 事象を増やすときは feature detection を伴わせ、未対応の版で黙って無効化されない
   ようにする（R11）。

## 帰結

- 実行環境の機能追加を取り込む改善が、テスト破壊として現れなくなる。
- 配線の欠落は引き続き落ちる（部分集合の検査は残る）。
- 保証限界: 「余計な配線が無い」ことは検めない。意図しない事象が足されても門は黙る。
  配線の妥当性は人が見る（`hooks.json` は手で保守する短い表であり、差分で読める）。
- 保証限界: 上流の事象一覧をこちらは持たない。ある事象が存在するかは実行環境の仕様で
  あり、`EXT-001` の `review_by` で定期再検証する。

<!-- 入れない: 複数決定、どの事象を新たに配線するか（別の決定）、現行仕様の全文 -->
