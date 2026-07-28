---
id: IMPL-003
title: `policy-guard.py` の実装メモ
type: IMPL
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-28
sources: [plugin/scripts/policy-guard.py]
depends_on: [SPEC-003]
llm_context: task
---

# `policy-guard.py` の実装メモ

## 実装制約
- 標準ライブラリだけを使う。pip も通信も使わず、同じ入力には常に同じ判定を返す。
- `_route` が `hook_event_name` と `tool_name` の組で処理を振り分ける。終了コードは常に 0 を返す。経路判定が落ちたときは、実行時例外の要約をエラージャーナル（`_auditcache.record_error`。書式の正本は SPEC-021。ADR-074）へ最善努力で残してから、安全側の判定を返す。
- `_handle_pre_edit_write` が三ガードを順に当て、最初に拒否したガードで止める。`[R7]` 不変ガードの後、`_pre_target_is_guard_inert` が真（realpath 解決後 doctrine_docs/ の外で、フロントマター無し Write か、on-disk に `id` を持たない Edit/MultiEdit）なら、依存グラフを組まずに allow する（レイテンシの早期通過、判定不変）。`id` を持つ対象（リンク経由含む）は早期通過せず Guard3（削除安全ガード） が当たる。`_handle_post_edit` も同様に、realpath 解決後 doctrine_docs/ の外で、書き込まれた本文が `---` フェンスで始まらない非文書はグラフを組まずに静かに通す（id ではなくフェンスで判定し、`domain`＋`depends_on` を持つ文書型の POST（書き込み後の状態） block を落とさない）。
- ドメインの解決と逆依存は `_depgraph` に、型と `status` の既定は `_registry` に委ね、ここでは定義し直さない。

## 注意点
- C13（整合判断id）が知らぬ間に「危険でも通す」側へ倒れないようにする。`_icd_judge_dep` は、索引にある dep なら domain を読んで判定し、索引に無い dep なら `_registry.type_of` で型を引く。型を引ければ dangling として許し、引けなければ拒否する。
- PostToolUse の削除安全は `_post_delete_safety` が PRE（書き込み前）から POST（書き込み後）への遷移で判じる。`_reconstruct_pre_edit_state` と `_invert_edits` が、POST の全文に編集を逆向きに当てて PRE を復元する。当て直しは生の全文（raw_post_text）に対して行う。組み直した近似に当てると、フロントマター内の編集で当て直しが外れることがあるからである。
- Bash 経路は `_split_command`・`_tokenize`・`_strip_redirections`・`_expand_glob` で対象を取り出す。展開できない glob は安全側に倒して拒否する。リダイレクト先のファイルは削除対象に数えない。ディレクトリ対象は `_expand_dir_targets` が配下の `.md` を再帰列挙して検査する(#71)。`mv` の `-t`/`--target-directory` は `_extract_remove_targets` が引数逆転を解いて DIR を宛先として扱う(#71)。
- 統治木の無いプロジェクトでは二・三ガードを発火させない（ADR-036）。`_project_has_tree` が `walkup_docs_root(file_path, cwd)` で木の有無を判じ、`_handle_pre_edit_write` は木が無ければ早期に allow、`_handle_post_edit` は木が無ければ静かに通す。木が在れば木の外の stray 文書にも従来どおり当てる。

## 対象部品
`plugin/scripts/policy-guard.py`。主な関数: `_route`・`_handle_pre_edit_write`・`_handle_pre_bash`・`_handle_post_edit`、`guard_immutability`・`_adr_delta_ok`、`guard_icd_dependency`・`_icd_judge_dep`・`_icd_message`、`guard_delete_safety_edit`・`guard_delete_safety_bash`・`_post_delete_safety`・`_invert_edits`。import 先は `plugin/scripts/_depgraph.py`・`plugin/scripts/_registry.py`・`plugin/scripts/_frontmatter.py`。

<!-- 入れない: 仕様の正本 -->
