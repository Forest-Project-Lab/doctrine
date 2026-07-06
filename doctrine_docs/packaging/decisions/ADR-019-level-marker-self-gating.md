---
id: ADR-019
title: 段差は .docs-level をスクリプト自身が読んで自主停止で実現する
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-07-06
updated: 2026-07-06
sources: [plugin/scripts/_registry.py, plugin/hooks/hooks.json]
depends_on: [SPEC-019]
llm_context: task
---

# 段差は .docs-level をスクリプト自身が読んで自主停止で実現する

## 背景

全体監査で二つの欠陥を確認した。第一に、`doctrine_docs/_system/.docs-level` は scaffold が書くだけで、どのスクリプトも読んでいなかった。教義・ICD-008・levels.md の「他のスクリプトがそこから読む」は文書上の宣言に留まっていた。第二に、縮小構成 `hooks.level2.json` を選ぶ機構が存在しなかった。プラグインの規約が自動配線するのは `hooks/hooks.json` だけで、`plugin.json` に選択面は無く、利用者設定へ写しても `${CLAUDE_PLUGIN_ROOT}` が解決されない。Level 2 は機構として成立していなかった。`[R8][R9]`

## 却下した選択肢

- `plugin.json` や配布物を Level 別に分ける。配布物が二つに割れ、marketplace の導入手順も割れる。段差の実体(どの検査を効かせるか)と配布の実体が絡まる。
- `.docs-level` の宣言を諦め、マーカーを目印だけに格下げする。切替機構の不在が残り、Level 2 は永遠に手作業の配線になる。教義の宣言を実装へ寄せるより、実装を宣言へ寄せる方が、利用者の運用(マーカー一行で段が決まる)として単純である。

## 決定

全構成の Hook(`hooks.json`)だけを配線し、Level 2 が持たない部分はスクリプト自身が `.docs-level` を読んで自主停止する。読み取りは登録簿の `docs_level(docs_root)` に一度だけ実装する。マーカーが無い・読めない・不正なときは 4(全構成)として扱う。段差で外れるのは軽量化であって保護ではないため、不明時は統治を全て効かせる側に倒す。自主停止する部分は次の三つである。SessionEnd の全件監査(`docs-audit.py` は SessionEnd 配線だけが付ける `--respect-docs-level` で飛ばす。CI は付けず Level に依らず監査する)、PostToolUse の起動後ガード(`policy-guard.py` の block)、`review-nudge.py` のナッジ。PreToolUse の予防・リンタ・注入は Level 2 でも残す。`hooks.level2.json` は、プラグインを使わず手で配線する場合の代替として同梱を続ける。

## 帰結

`scaffold.py --level 2` がマーカーを書いた時点で Level 2 が実際に効く。切替は「マーカーを一行書き換え、新しいセッションを開く」だけになる。教義の「他のスクリプトがそこから読む」が実装で成立する。保証限界: マーカーの書き換え自体は統制しない(体系の重さの選択は利用者の判断)。Hook 設定はセッション開始時に固定されるため、段の変更は次のセッションから効く。

<!-- 入れない: 複数決定、現行仕様の全文 -->
