# フック無しで doctrine を運用する（可搬性。#83）

doctrine の強制はフック（Claude Code の PreToolUse・PostToolUse・SessionEnd 等）で効く。しかし、フックの無いエージェント（Codex・Cursor・Gemini CLI 等）や、フックを使わない運用でも、doctrine のスクリプトは標準ライブラリだけで動くため、pre-commit と CI で同じ検査を回せる。`AGENTS.md` の投影があるため、これらのエージェントは入口を読める。

## 何をどこで回すか

| 検査 | フック（Claude Code） | フック無し（pre-commit / CI） |
|---|---|---|
| 単一文書のスキーマ・用語 | PostToolUse の `docs-linter.py` | CI の `docs-linter.py --batch <root>`（#91） |
| 全件監査（孤児・逆孤児・投影ドリフト等） | SessionEnd の `docs-audit.py` | CI の `docs-audit.py --root <root> --fail-on error` |
| 用語（禁止同義語・カルク） | PostToolUse に含む | CI の `term-check.py <files>` |
| ガード（ICD 依存・削除安全） | PreToolUse の `policy-guard.py` | pre-commit で `policy-guard.py`（stdin に編集の JSON を渡す配線が要る。無ければ監査の事後検出に委ねる） |

## pre-commit の例

`.pre-commit-config.yaml`（例）:

```yaml
repos:
  - repo: local
    hooks:
      - id: doctrine-batch-lint
        name: doctrine schema gate
        entry: python3 plugin/scripts/docs-linter.py --batch doctrine_docs
        language: system
        pass_filenames: false
      - id: doctrine-audit
        name: doctrine corpus audit
        entry: python3 plugin/scripts/docs-audit.py --root doctrine_docs --fail-on error
        language: system
        pass_filenames: false
```

## 限界

- ガード（予防）はフックの PreToolUse でだけ実行前に拒否できる。フック無しの運用では、ガード相当は pre-commit（コミット前）か CI（マージ前）の**事後検出**に下がる。ディスクが一時的に不整合になりうる点は、フック運用と同じ既知の限界の延長である（§7）。
- 契約の注入（SessionStart）と会話知識の捕捉（Stop・PreCompact）は、フックが前提である。フック無しのエージェントでは、`AGENTS.md`・`CLAUDE.md` の入口から `_system` の正本を読む運用に委ねる。
- スクリプトは標準ライブラリだけで動くため、Python 3 があれば追加の導入は要らない。
