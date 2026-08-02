---
id: ADR-076
title: ICD 依存の境界は Edit・MultiEdit でも書き込む前に判ずる
type: ADR
domain: guard
status: accepted
owner: doctrine-maintainers
created: 2026-08-02
updated: 2026-08-02
sources: ["外部レビュー 2026-07-31", "doctrine#158"]
depends_on: [SPEC-003]
llm_context: task
---

# ICD 依存の境界は Edit・MultiEdit でも書き込む前に判ずる

## 背景

三つのガードのうち、ICD 依存境界（Guard2・`[R7]`）だけが `Write` のときしか事前に判じて
いなかった。`Edit` と `MultiEdit` は素通りし、`PostToolUse` の `block` に回していた。

その理由は `policy-guard.py` の docstring に書いてあった。

> Write のみ事前判定する。Edit/MultiEdit は**事前に全文を作れないので**、ここでは
> 判定しない（PostToolUse の block に回す）。

`SPEC-003` にも同じ前提が載っている ——「Edit・MultiEdit は書き込む前に全文を組み立て
られないため、PostToolUse の block に回す」。

**この前提は、同じファイルの隣の関数によって反証されている。** `_proposed_text` が
`_apply_edits` を呼んで変更後の全文を組み立てており、それを **Guard1 不変**と
**Guard3 削除安全**が、どちらも `PreToolUse` の事前判定で使っている。Guard3 は
`Edit` を事前に判じて deny する。作れないのではなく、Guard2 が作っていないだけだった。

しかも ADR-075 が `_proposed_text` を「ディスクの生の全文へ編集を当てる」形へ直した
ことで、この組み立ては以前より確かになっている。前提が真だった時期があるとしても、
いまは真でない。

帰結として、ICD 依存境界は `Edit` 経路では**事前の門ではなく事後の検出**になっていた。
違反する依存が一度作業木へ書き込まれ、それから警告が出る。`PostToolUse` の `block` は
書き込みを巻き戻さないので、その間、作業木は不正な状態で残る。

## 却下した選択肢

**`PostToolUse` の検出を厚くする。** 事後の検出をいくら厚くしても、書き込みは起きた
あとである。`[R7]` は「境界明瞭、ガードは拒否する」であり、拒否は書き込みの前にしか
置けない。

**Guard3 と同じく、組み立てられないときは `PostToolUse` へ回す。** Guard3 の
「回す」は、降格や本文消しが**事前に確定できない**という意味である。Guard2 が見るのは
`depends_on` の一覧であり、全文が作れれば必ず確定する。確定できないのは全文が作れない
ときだけで、それはガードが判定を持たない状態そのものである。ADR-075 が直したのは
まさに「判定を持たないまま allow へ倒れる」欠陥だった。同じ穴をここに残さない。

**三ガードすべてを `PostToolUse` に寄せる。** 予防を捨てて検出だけにする案。
`[R7]` と仕様 §3 の予防の位置づけを覆す。

## 決定

**Guard2 は `Edit` と `MultiEdit` でも `PreToolUse` で判ずる。** 判定に使う全文は、
Guard1・Guard3 と同じ `_proposed_text`（ディスクの生の全文へ編集を当てたもの）とする。

1. `guard_icd_dependency` の `if tool != "Write": return None` を外す。
2. `Edit`・`MultiEdit` は、対象がディスクに在るときだけ判ずる（在らなければ `Write` の
   経路であり、Guard2 は `content` を見る）。
3. **全文を組み立てられないときは deny する。** ただし対象が統治文書のときに限る
   —— on-disk に `id` を持つか、`doctrine_docs/` の木の中に在るとき。それ以外
   （体系外の非文書）は従来どおり通す。ガードが判定を持たないまま allow へ倒れる経路を
   作らないための fail-closed であり、`_icd_judge_dep` の分類不能を deny する扱い
   （C13）と同じ倒し方に揃える。
4. `PostToolUse` の Guard2 は残す。外部の競合や tool 実装差を拾う突き合わせとして
   意味がある。ただし**主たる安全性をそこに依存させない**。
5. 早期通過（`_pre_target_is_guard_inert`）の `Edit`・`MultiEdit` の分岐から
   「Guard2 は構造上 None」の前提を外す。

## 帰結

- ICD 依存境界が、三ガードの中で一つだけ事後だった非対称を解消する。`[R7]` の拒否が
  書き込みの前に立つ。
- 違反する `Edit` は作業木へ届かない。「一時的に不正な状態で残る」窓が閉じる。
- 保証限界: 全文を組み立てられない統治文書の編集は deny になる。`old_string` が
  一致しない編集は tool 自身も失敗するので実害は小さいが、稀な誤拒否はありうる。
  判定を持たないまま通すより、拒んで人に見せるほうを採る。
- 保証限界: `PostToolUse` の Guard2 が拾う範囲（外部の競合・tool 実装差）は変わらない。
  そこは引き続き事後の突き合わせである。
- `SPEC-003` の「Edit・MultiEdit は書き込む前に全文を組み立てられない」の記述と、
  `TEST-003` の `TC-073`・`TC-074`・`TC-119` の期待を、事前拒否の契約へ改める。

<!-- 入れない: 複数決定、現行仕様の全文 -->
