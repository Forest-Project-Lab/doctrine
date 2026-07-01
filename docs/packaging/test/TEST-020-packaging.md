---
id: TEST-020
title: 配布・標準ライブラリの受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_meta.py, plugin/tests/test_packaging.py]
depends_on: [SPEC-020]
llm_context: task
---

# 配布・標準ライブラリの受入

## 受入基準への対応

SPEC-020 と REQ-013 の受入基準を確認する。

- `plugin.json` が妥当な JSON で、最小キー（name=`doctrine`・version=`0.1.0`・license=MIT・description・author）を満たす。
- 想定外の最上位キーを持たない。
- `scripts/` の全 `.py` が、標準ライブラリと兄弟の `_` コアだけを import する `[R9]`。
- 各エントリスクリプトが、`def main` と `sys.path.insert` のブートストラップを持つ。
- README（案内ファイル）が存在し、索引項目（install 経路・`.claude/` への退避・7 つの技能・4 つの Hook・スクリプト名・段）と `## 保証限界`（予防・検出・委ねる）を持つ。

## 退行観点

- README の `## 保証限界` 節が消えていないこと（WATCH の R9 観点と突き合わせる）。
- 第三者モジュールの import がスクリプトに紛れ込んでいないこと。

## 合否基準

`plugin/tests/test_meta.py`（`TestStdlibOnly`・`TestPluginInstallShape`・`TestReadme`・`TestEntryScriptConvention`）と `plugin/tests/test_packaging.py`（`TestPluginJson`・`TestScriptsStdlibOnly`）が、すべて成功すれば合格とする。

<!-- 入れない: 無関係な要求 -->
