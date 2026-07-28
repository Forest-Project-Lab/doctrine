---
id: CHANGE-004
title: 体系外の解釈文書をビューと定め、刻印で古びを見えるようにする
type: CHANGE
domain: audit
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-28
sources: [外部独立レビュー 2026-07-28, plugin/scripts/_audit_stray.py]
depends_on: [SPEC-011, ICD-005]
llm_context: task
---

# 体系外の解釈文書をビューと定め、刻印で古びを見えるようにする

## 変更内容

分類の記録（`.md-intake`）に第四の分類「ビュー」を足す。ビューは、正本を
ある時点で人向けに解釈した体系外の文書であり、刻印（どの正本の・いつ時点の
状態を見て書いたか）を必ず持つ。監査に検査 view_stale を新設し、刻印の欠落
（warn）と、刻印の参照先の古び・現行でない参照（advisory）を挙げる。公開
ビュー（README・plugin/README・CONTRIBUTING（寄稿の方針ファイル））は
リリース整合の門にも配線し、
刻印の版が版番号の正本と食い違えばリリースを止める。リンタは、ビューと分類
された文書の編集時に刻印の欠落を助言する。llm-context-pack の生成物には刻印を
自動で書かせる。あわせて README の古びた記述3件（要求数・Hook イベント数・
監査の検査数）を直す。

## 理由（要求元）

外部の独立レビュー（2026-07-28）が、監査 error 0 の状態で README の主張3件
（`R1`〜`R10`・Hook 4イベント・18検査）が現行仕様（R12 まで・7イベント・
33検査）から古びていることを指した。原因は機構の故障ではなく射程の欠落 —
README は「非文書」と分類され、依存グラフのノードにならず、どの検査も主張を
読まなかった。検査が配線された主張（test_meta が見る plugin/README の技能
一覧）だけが鮮度を保ち、配線の無い主張はすべて古びた。解釈文書は正本から
機械的に再描画できない（ADR-029 が投影化を却下した理由）が、参照時点は常に
刻める。内容は保証せず、古びだけを機械が見る — コードの範囲に対する既定
（DECIDED-001 事実10）と同じ規律を、体系外の解釈文書へ広げる。

## 影響の初期見積

- 文書: ADR（新規1件）、ICD-005（記録の書式・検査表）、SPEC-011（検査群）、
  SPEC-027（門の追加検査。packaging 側）、SPEC-007（リンタ助言。lint 側）、
  SPEC-020（plugin/README の呼称。packaging 側）、GLOSSARY（承認語
  「ビュー」「刻印」）、DECIDED-001（事実の追加）、WATCH-001（再分類による
  骨抜きの監視）、TEST-011・TEST-027・TEST-007。
- 実装: `_intake.py`（分類の追加・完全一致の優先）、`docs-audit.py` と
  `_audit_stray.py`（view_stale）、`scripts/release-check.py`（公開ビューの
  刻印の版）、`docs-linter.py`（助言）、llm-context-pack の技能文書。
- 自己適用: `.md-intake` の再分類（README・CONTRIBUTING・plugin/README）、
  三つの公開ビューへの刻印、README の記述3件の修正。
- ドメイン跨ぎ: packaging（門と plugin/README の呼称）と lint（助言）。
  分類の記録の書式は ICD-005 が正本のままで、読み手は共有コア `_intake` に
  一本化されている（変更なし）。

## 実施の記録

2026-07-28 に完了。決定は ADR-073、影響の列挙は IMPACT-004。ビュー3件を
再分類して初期の刻印を打ち、README の主張3件と「投影」自称の残存・TEST-020 の
「4 つの Hook」を修正した。全テスト（1018件）緑、view_stale の受入10件と
公開ビューの門の受入6件を追加。ADR-029 は置換せず存続（案内の決定は不変。
本決定は主張を含む体系外文書の類型を別に立てた）。
