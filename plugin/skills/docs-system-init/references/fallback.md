# 配置と退避配置

## プラグイン配置

`/plugin install` で配る。`hooks/hooks.json` のパスは `${CLAUDE_PLUGIN_ROOT}/scripts/...` で解決する（§5）。スクリプトの呼び出し元はこの変数を使い、絶対パスをハードコードしない。

## `.claude/` 退避配置

プラグインを使わないときは、このスキルが `.claude/` 配下へ退避配置する（§5）。スクリプトのパスは `.claude/` 起点で解決する。監査結果の要約も、プラグインの `.cache/` が無いときは `.claude/.cache/last-audit.json` へ退避する。

## 手で配線するときのパス書き換え（#75）

同梱の `hooks/hooks.level2.json` は、プラグイン経由の解決を前提に `${CLAUDE_PLUGIN_ROOT}/scripts/...` を使う。**プラグインを使わず手で `.claude/settings.json` に配線するときは、この変数を実際のスクリプトの場所に書き換えること**。書き換えないと、`${CLAUDE_PLUGIN_ROOT}` が未定義のため各 `command` が `"/scripts/..."` に展開されて毎イベント失敗する。PreToolUse のガードは非ブロッキングの失敗となり、予防が黙って全て無効になる（fail-open。利用者は気づけない）。

書き換えの手順:

1. スクリプトの置き場所の絶対パスを決める（退避配置なら `<repo>/.claude/scripts`）。
2. `hooks.level2.json` の各 `command` の `${CLAUDE_PLUGIN_ROOT}/scripts/` を、その絶対パス + `/` に置き換える（例: `"/abs/repo/.claude/scripts/inject-contract.py"`）。
3. 置き換えた内容を `.claude/settings.json` の `hooks` に貼る。
4. 検証: 一つ壊れた依存を持つ文書を編集し、ガードが実際に拒否することを確かめる（沈黙していないこと）。フックの設定はセッション開始時に読み込まれるので、貼った後は新しいセッションで反映する（§5末尾）。

## 入口の案内

`CLAUDE.md` と `AGENTS.md` は投影である。事実を集めず、入口だけを示す（§5／§3.7）。手で保守しない。すでにあるときは置かない（非破壊）。

## 非破壊の不変条件

`scaffold.py` は欠けたものだけを作る（skip-if-exists・べき等・原子的書き込み）。既存の文書は上書きも改変もしない。全部すでにあるなら、何も書かずに終了コード 0 で終える。
