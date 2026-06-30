---
name: docs-system-init
description: 'Sets up the document governance system in a repository: creates the minimal _system layer (glossary, decided-facts, non-goals, overview projection) and the root entry points (CLAUDE.md, AGENTS.md), and wires up the guards and linter without overwriting anything that already exists. Use this skill when the user wants to "initialize docs", "set up the documentation system", "bootstrap docs governance", "install the blueprint", "scaffold _system", or asks "how do I start using this plugin" / "set up doc governance in this repo".'
---

# docs-system-init

## 役割

`_system` の最小配置と入口の案内を置き、ガードとリンタを設定する。既存の文書を壊さない。`[R1][R8]`

このスキルは `_system` の最小だけを置く。ドメインのフォルダと各層は作らない。最初の型付き文書を書くときに `doc-author` が生成する（§3.7「空の足場を先に作らない」）。

## 委ねる先（決定論は scripts へ）

- `${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py` — `_system` の最小を非破壊で置く。段階導入の縮小構成（Level 2）も選べる。
- `hooks/hooks.json` の設定を置く。パスは `${CLAUDE_PLUGIN_ROOT}/scripts/...` で解決する。プラグインを使わないなら `.claude/` へ退避配置する（§5）。

## 手順

1. 既存の状態を調べる。`docs/_system/` はあるか。プラグイン配置か `.claude/` 退避配置か。どの Level か（§4.4）。
2. 構成を選ぶ。既定は縮小構成の Level 2 とする。利用者が Level 3 か 4 を求めたときだけ上げる。縮小構成は `_frontmatter.py`・`docs-linter.py`・`policy-guard.py`・`inject-contract.py` だけを使い、型を `ICD`・`REQ`・`SPEC`・`ADR`・`DECIDED`・`OVERVIEW` に絞る（型コードは§3.2の登録簿で定める）。
3. `scaffold.py` を非破壊で実行する。欠けたものだけを作る。既存の文書は上書きも改変もしない（受入条件「既存を壊さない」）。
4. `_system` の最小を置く。`glossary.md`（用語辞書の正本）・`decided-facts.md`（`DECIDED` の正本）・`non-goals.md`（`NONGOAL` の正本）・`overview.md`（`OVERVIEW` の投影）。Context Map と ICD 一覧は Level 4 まで先に作らない。
5. 入口の案内 `CLAUDE.md`・`AGENTS.md` を投影として置く。入口だけを示し、事実を集めない（§5／§3.7）。すでにあるときは置かない。
6. ガードを設定する。SessionStart の `inject-contract.py`、PreToolUse の三つのガード、PostToolUse のリンタ、SessionEnd と継続的結合（`CI`）の監査。Hook の設定はセッション開始時にだけ取り込まれると伝える。ガードを変えたら新しいセッションで効く（§5 運用上の前提）。
7. 何を作り何を飛ばしたか（既存だから飛ばした分）を報告する。引き渡す。「最初の文書は `doc-author` で作る。フォルダはそのとき生成される」。

## 詳細（references/）

- `references/levels.md` — §4.4 の Level 2／3／4 の型とスクリプトの対応表。
- `references/fallback.md` — プラグイン配置と `.claude/` 退避配置、`${CLAUDE_PLUGIN_ROOT}` の解決。
- `references/hook-snapshot.md` — Hook 設定がセッション開始時にだけ取り込まれる前提。

## 保証限界

- **予防**: このスキル単体は何も予防しない。後で予防するガードを設定するだけである。既存を壊さない不変条件は、書き込み前に各ファイルの存在を確かめて守る（ガードではない）。木が一部だけ存在する端の場合は、ファイルごとの存在確認に委ねる。
- **検出**: 既存だから飛ばしたファイルを報告する。
- **委ねる**: どの Level にするか（人間）。`.claude/` 退避配置を使うか（人間）。
