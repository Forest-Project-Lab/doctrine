---
id: SPEC-020
title: パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/.claude-plugin/plugin.json]
depends_on: [REQ-013]
llm_context: task
---

# パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ）

`.claude-plugin/plugin.json` を正本とする配布物の形と、`/plugin install` で配置する経路を定める仕様である `[R9]`。

## 入出力

入力は `/plugin install` の実行である。結果は、配置されたプラグイン（`plugin.json`・`hooks/`・`scripts/`・`skills/`・`templates/`・`README.md`）である。`plugin.json` の最小キーは次のとおり。

- `name`: `doctrine`
- `version`: `0.1.0`
- `license`: MIT
- `description`: 非空の一文（日本語）
- `author`: name を持つオブジェクト

## 制約

- `plugin.json` は最小キーだけを持つ。想定外の最上位キーを足さない。
- スクリプトは、標準ライブラリと、兄弟の `_` コア（`_registry`・`_frontmatter` など）だけを import する。pip で入れる第三者依存を作らない `[R5]`。
- 各エントリスクリプトは `def main` を定義し、`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` のブートストラップを持つ。これで兄弟コアを解決する。
- プラグインを配置できないときは、`.claude/` へ退避する（`scaffold.py --fallback`）。

## エラー時挙動

- `plugin.json` の JSON が壊れていれば、読み込みで失敗し、弾く。
- 第三者モジュールを import するスクリプトは、標準ライブラリ点検で失敗とする。

## 受入基準

`plugin.json` が妥当な JSON で最小キーを満たし、`name` が `doctrine` であること。`scripts/` の全 `.py` が、標準ライブラリと兄弟コアだけを import すること。README（案内ファイル）が存在し、索引項目（install 経路・7 つの技能・4 つの Hook・スクリプト名・段）を含むこと。対応テストは TEST-020。

<!-- 入れない: 廃止、検討、実装コードの写し -->
