---
id: SPEC-020
title: パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ）
type: SPEC
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-28
sources: [plugin/.claude-plugin/plugin.json]
depends_on: [REQ-013]
llm_context: task
---

# パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ）

`.claude-plugin/plugin.json` を正本とする配布物の形と、`/plugin install` で配置する経路を定める仕様である `[R9]`。

## 入出力

入力は `/plugin install` の実行である。結果は、配置されたプラグイン（`plugin.json`・`hooks/`・`scripts/`・`skills/`・`templates/`・`README.md`）である。`plugin.json` の最小キーは次のとおり。

- `name`: `doctrine`
- `version`: 三成分の版番号。値の正本は `plugin.json` で、`marketplace.json` と一致させる（テストが強制する）
- `license`: MIT
- `description`: 非空の一文（日本語）
- `author`: name を持つオブジェクト

## 制約

- `plugin.json` は最小キーだけを持つ。想定外の最上位キーを足さない。
- スクリプトは、標準ライブラリと、兄弟の `_` コア（`_registry`・`_frontmatter` など）だけを import する。pip で入れる第三者依存を作らない（ADR-031）`[R5]`。
- 配布物のほかに、リポジトリ直下の `scripts/`（整合点検の二本。SPEC-023）が在る。これは本リポジトリ専用の自己適用であり、配布物には含めない。「`scripts/`」と書くときは、`plugin/scripts/`（配布物）とリポジトリ直下 `scripts/`（自己適用）を必ず書き分ける。
- 各エントリスクリプトは `def main` を定義し、`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` のブートストラップを持つ。これで兄弟コアを解決する。
- プラグインを配置できないときは、`.claude/` へ退避する（`scaffold.py --fallback`）。

## エラー時挙動

- `plugin.json` の JSON が壊れていれば、読み込みで失敗し、弾く。
- 第三者モジュールを import するスクリプトは、標準ライブラリ点検で失敗とする。

## 実装の指紋

- コード対応なし: 実装は配布の構成(plugin.json と配置)であり、単一のコード範囲を持たない

## 受入基準

`plugin.json` が妥当な JSON で最小キーを満たし、`name` が `doctrine` であること。`plugin/scripts/` の全 `.py` が、標準ライブラリと兄弟コアだけを import すること。README（ビュー。ADR-073）が存在し、索引項目（install 経路・7 つの技能・Hook の各イベント・スクリプト名・段）と刻印（書式の正本は ICD-005 の `view-stamp-format`）を含むこと。対応テストは TEST-020。

<!-- 入れない: 廃止、検討、実装コードの写し -->
