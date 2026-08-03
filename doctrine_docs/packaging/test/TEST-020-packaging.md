---
id: TEST-020
title: 配布・標準ライブラリの受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/tests/test_meta.py, plugin/tests/test_packaging.py]
depends_on: [SPEC-020]
llm_context: task
---

# 配布・標準ライブラリの受入

## 受入基準への対応

SPEC-020 と REQ-013 の受入基準を確認する。

- `plugin.json` が妥当な JSON で、最小キー（name=`doctrine`・version・license=MIT・description・author）を満たし、version が `marketplace.json` と一致する。
- 想定外の最上位キーを持たない。
- `scripts/` の全 `.py` が、標準ライブラリと兄弟の `_` コアだけを import する `[R9]`。
- `scripts/` の全 `.py` が実行ビットと `python3` のシバンを持つ（Hook が直接起動するため）。
- 各エントリスクリプトが、`def main` と `sys.path.insert` のブートストラップを持つ。
- README（ビュー。ADR-073）が存在し、索引項目（install 経路・`.claude/` への退避・7 つの技能・Hook の各イベント・スクリプト名・段）と `## 保証限界`（予防・検出・委ねる）と刻印（`doctrine:view` の一行。`as-of` の一致は TEST-027 の門が検める）を持つ。
- ADR-075: `plugin/` の下に実行時の状態（`.cache`・`.claude`）が無いこと。
- ADR-075: 同梱の試験が配布物の外を素で読まないこと。導入した複製で `run_tests.py` が通ること。
- ADR-096: 統治の設定（`_system/.context-config.json`）を対象にする現行の EXT アンカーが在り、その**検査が hash** で、**指紋の行を持つ**こと。`TestGovernanceConfigIsAnchored` が確認する。**アンカーそのものが消されても監査は何も言わない**（見張りが無くなった状態は、見張りでは分からない）ので、ここが唯一の歯止めである。検査の種別は**監査と同じ解析**（`_EXT_CHECK_RE`）で読む —— 本文全体で `hash` を探す書き方は、散文の「`hash` にする」で通ってしまった（実測。飾りだった）。**歯止め自身の実効を実測してある**（2026-08-03）: アンカーを消すと落ち、検査を `exists` に落とすと落ち、指紋の行を消すと落ち、いずれも戻すと通った。
- ADR-094: 試験が実時計に依っていないこと。時計を固定する口を持つ呼び出しを起動し、かつ固定日の `generated_at` を埋め込むクラスが、その固定を渡していること。判定はクラス単位で、同じモジュール内の基底クラスまで辿る。`TestNoWallClockInTests` が確認する。あわせて**歯止めが空回りしていないこと**（口を持つ呼び出しが一つ以上見えること）も見る。

## 退行観点

- README の `## 保証限界` 節が消えていないこと（WATCH の R9 観点と突き合わせる）。
- 第三者モジュールの import がスクリプトに紛れ込んでいないこと。
- 実時計の歯止めが**クラス単位のままである**こと（ADR-094。WATCH-001 第11項）。**ファイル単位へ緩めてはならない** —— 実測で、ファイル単位の検めは落ちた当日（`main`）でも通った（同じファイルの別のクラスが `--today` を使っていたため）。**歯止め自身の実効を実測してある**（2026-08-03）: `main` の版の試験を戻すと `test_inject.py::TestTraceCoverageLine` を名指しして落ち、直した版で通った。

## 合否基準

`plugin/tests/test_meta.py`（`TestStdlibOnly`・`TestPluginInstallShape`・`TestReadme`・`TestEntryScriptConvention`）と `plugin/tests/test_packaging.py`（`TestPluginJson`・`TestScriptsStdlibOnly`・`TestScriptsExecutable`）が、すべて成功すれば合格とする。

<!-- 入れない: 無関係な要求 -->
