# 導入先の CI 監査ステップの雛形（任意）

このスキルもプラグインも、導入先に CI の設定は作らない（scaffold は `_system` の最小だけを置く）。導入先が継続的結合（`CI`）を持つなら、次の雛形を案内する。持たないなら、監査は SessionEnd の Hook と `gov-heartbeat.py` の鮮度照合（前回監査が古いままなら会話の冒頭で報せる）で回る。

## GitHub Actions の例

```yaml
# .github/workflows/doctrine-audit.yml
name: doctrine-audit
on:
  pull_request:
  schedule:
    - cron: "0 0 * * 1"   # 週次。セッションが無くても監査が走る唯一の足
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Docs audit
        run: python3 <プラグインの場所>/scripts/docs-audit.py --root <統治木> --fail-on error
      - name: Projection drift
        run: python3 <プラグインの場所>/scripts/render-projection.py all --check --docs-root <統治木>
```

`<プラグインの場所>` は、プラグインをリポジトリへ同梱している場合はそのパス、していない場合はチェックアウト手順を足して doctrine のリポジトリから取る。`<統治木>` は既定 `doctrine_docs`（`_system/` を持つ `docs` も可。ADR-022）。

## 要点

- `--fail-on error` は error 所見があると失敗する。`review_by` 超過は warn であり `CI` を落とさない（超過の督促は `gov-heartbeat.py` と SessionStart の注入が担う）。
- `schedule`（週次）は、誰もセッションを開かない期間でも監査を走らせる唯一の経路である。付けられるなら付ける。
- `CI` は Level の段差に依らず全件監査する（縮小はセッション内の軽量化であり、マージ前の検証は削らない。§4.4）。
