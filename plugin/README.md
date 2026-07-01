# doctrine

文書を型と登録簿で整え、ガード・リンタ・投影で、LLM（大規模言語モデル）へ渡す情報を最小に保つClaude Codeプラグインである。設計書 `DOCTRINE-001`（[spec/doctrine.ja.md](../spec/doctrine.ja.md)）の参照実装にあたる。

本プラグインは設計書 `spec/doctrine.ja.md`（`DOCTRINE-001`）の実装である。設計書が要求（`R1`〜`R10`）と登録簿（型・状態・置き場所・必須キー）を定め、本プラグインがそれを再利用できる形（Skill・Hook・スクリプト・テンプレート）で機械的に強制する。設計書がモデルの正本であり、本プラグインは規則をコードに二重定義しない。規則の単一の出所は `scripts/_registry.py` と `templates/glossary.md.tmpl` にある。

この案内文書（`README`）は入口である。知識を集めず、各部品への入口だけを示す。詳細は各 `SKILL.md`・各スクリプトの先頭の説明・設計書にある。

---

## 導入

配布は marketplace 経由で行う。次の二段で導入する。

```text
/plugin marketplace add Forest-Project-Lab/doctrine
/plugin install doctrine@forest-project-lab
```

導入 ID は `<プラグイン名>@<marketplace 名>` で決まる（`marketplace.json` の `plugins[].name`＝`doctrine`、marketplace の `name`＝`forest-project-lab`）。プラグインのHookは、パスを `${CLAUDE_PLUGIN_ROOT}/scripts/...` で解決する。

プラグインを使わない場合は、Skill `docs-system-init` が `.claude/`（プラグイン外の設定置き場）へフォールバック配置する。`scaffold.py` が `_system` の最小配置とルートの案内、`.docs-level` の目印を置く（Hookは事前生成しない）。段階導入の縮小構成の Hook（`hooks/hooks.level2.json`）はプラグイン同梱で、ホストや利用者が配線する。既存のファイルは上書きしない。

導入後、Hookの設定はセッション開始時にスナップショットされる。ガードやリンタを変えても、その場では反映されない。新しいセッションで反映する。

---

## Skill（7つ）

各 Skill の本文は500行未満で、判断が要る活動を支援する。決定論で守れる点検はスクリプトに委ねる。

- `docs-system-init`: `_system` の最小配置とルートの案内（`CLAUDE.md`・`AGENTS.md`）を置き、ガードとリンタを設定する。既存を壊さない。
- `doc-author`: 型付き文書（`ICD` を含む）を作成・更新する。型・置き場所・フロントマターを正す。ドメインのフォルダはその型を最初に書くときに生成する。
- `doc-review`: 文章規範と位置づけを点検する。用語チェッカーを併走させ、一覧に無い訳語臭は逆翻訳テルで判定する。
- `change-impact`: 14ステップの変更フローを進める。依存をたどり影響する文書を列挙し、更新の順序を守る。
- `regression-guard`: 廃止した方針の復活と、撤回した決定の再採用を防ぐ。`DECIDED`・`WATCH` と突き合わせる。
- `llm-context-pack`: タスク別の最小の文脈を集約する。`never` 群を除外し、被覆を満たす最少集合に絞り、各事実の出所を表示する。
- `docs-curate`: 点検→統合・降格・削除を一片ずつ進める。逆参照を確認し、投影を描画し直し、常時集合が上限を超えたら縮める。

---

## Hook（4つのイベント）

per-turn（毎ターン）のHookは単一文書だけを点検する。全件走査はセッション境界のHookと `CI`（継続的結合の自動点検）へ隔離し、体感速度を守る。Hookの設定は `hooks/hooks.json` にある。

- `SessionStart` → `inject-contract.py`: 契約の最小注入。`DECIDED`（現行）・`NONGOAL`・廃止事実・`GLOSSARY` 見出し・`WATCH` の要点と、前回監査の要約を描画して渡す。注入量の上限を守り、冒頭で要点を復唱させ、重要な文書を冒頭と末尾に置く。
- `PreToolUse` → `policy-guard.py`: 三つのガード。不変性ガード（`archive/` と既存 `ADR` の改変を拒否）、`ICD` 依存ガード（ドメイン外の非 `ICD` 宛 `depends_on` を拒否）、削除安全ガード（現行の依存が残る降格・削除を拒否）。違反は実行前に拒否する。
- `PostToolUse` → `policy-guard.py`・`docs-linter.py`・`review-nudge.py`（この順）: ガードは `Edit`・`MultiEdit` の事後で、事前に判定できなかった `ICD` 依存違反・削除安全違反を再点検して止める。リンタは助言だけを返す（必須キー・状態の型別許可・id とファイル名の一致・型と置き場所の整合・`llm_context` の値・`SPEC` 必須4節・用語チェッカー・追跡性）。`review-nudge.py` は型付き文書の編集に doc-review を促す助言で、`decision` は出さない。リンタと nudge は決して止めない。
- `SessionEnd` → `docs-audit.py`: 全件監査を走らせ、結果の要約を保存する。次の `SessionStart` で注入する。当ターンには差し込まない。

---

## スクリプト（15個）

外部 pip 依存を作らない。標準ライブラリだけで動く。`scripts/` にある。

| スクリプト | 呼び出し元 | 役割 |
|---|---|---|
| `_frontmatter.py` | 共有 | フロントマター解析（決して例外を投げない） |
| `_registry.py` | 共有 | 型・状態・`llm_context`・必須キー・置き場所の登録簿（単一の出所） |
| `_depgraph.py` | 共有 | 依存グラフの中核（`dep-graph.py`・監査が読み込む） |
| `_termcheck.py` | 共有 | 用語チェックの中核（辞書の解析・照合。`term-check.py`・リンタが読み込む） |
| `docs-linter.py` | `PostToolUse` | 単一文書の点検（助言のみ） |
| `review-nudge.py` | `PostToolUse` | 型付き文書の編集時に doc-review を促す助言（`decision` は出さない） |
| `term-check.py` | リンタ | 禁止同義語・カルク・未定義語の照合 |
| `policy-guard.py` | `PreToolUse`・`PostToolUse` | 不変性・`ICD` 依存・削除安全の三ガード |
| `inject-contract.py` | `SessionStart` | 契約の最小注入 |
| `docs-audit.py` | `SessionEnd`・`CI` | 全件監査（孤児・逆孤児・dead link・`canonical_for` 衝突・`ICD` 違反・投影ドリフト・`review_by` 超過） |
| `dep-graph.py` | `change-impact`・ガード・監査 | 依存の有向グラフ。波及先と逆参照を列挙し、ドメイン跨ぎを分類する |
| `render-projection.py` | `docs-curate`・監査 | Overview・`ICD` 一覧・Context Map をフロントマターから描画する |
| `term-extract.py` | `docs-curate` | ドメイン特徴語の候補を出す（採否は人間） |
| `collect-context.py` | `llm-context-pack` | 被覆を満たす最少集合に絞り、各事実の出所を表示する |
| `scaffold.py` | `docs-system-init` | `_system` の最小配置（非破壊）。`--level` で能動 Level を `.docs-level` に記録する |

`_` で始まる4つ（`_frontmatter.py`・`_registry.py`・`_depgraph.py`・`_termcheck.py`）は、二つ以上の入口が共有する中核である。ハイフン名の入口スクリプトから読み込む。

---

## 段階導入（Level 2・3・4）

体系の重さを規模に合わせる。全部を最初から置かない。痛みが出た所だけ足す。これは体系自身の最小性である。段差はフロントマターの Level に対応する（設計書 §3.4・§4.4）。

- **Level 2（縮小構成）**: 必須キーだけ。型は `ICD`・`REQ`・`SPEC`・`ADR`・`DECIDED`・`OVERVIEW` に絞る。スクリプトは `_frontmatter.py`・`docs-linter.py`・`policy-guard.py`・`inject-contract.py` だけ。`scaffold.py` が縮小構成のHook（`hooks/hooks.level2.json`）を置く。
- **Level 3**: `depends_on`・`impacts` を加える。`dep-graph.py`・`change-impact`・`docs-audit.py` を足す。`review_by` 超過の点検はここから。
- **Level 4**: `canonical_for` と、全件監査・投影一式・ドメイン連携を加える。

上位へ上げるのは、その情報が要るとわかってからにする。

---

## 保証限界

本プラグインが、何を予防し、何を検出し、何を人間に委ねるかを明示する（要求 `R9`。設計書 §7 を継承する）。

### 予防（ガードが実行前に拒否する）

- ドメイン外の非 `ICD` 宛 `depends_on` を `Write` の時点で拒否する（`R7`）。
- `archive/` の編集と既存 `ADR` の改変を拒否する。
- 現行の依存が残る文書の降格・削除（`rm`・`git rm`・`mv` を含む）を拒否する（`R4`）。

### 検出（リンタと監査が後から指摘する）

- リンタが、必須キー・状態の型別許可・置き場所・`SPEC` 必須4節・禁止同義語・カルクを単一文書ごとに指摘する（`R2`・`R6`・`R8`・`R10`）。
- 監査が、全件で、孤児・逆孤児・dead link・`canonical_for` 衝突・投影ドリフト・`review_by` 超過を一覧化する（`R1`・`R3`・`R8`）。

### 委ねる（構造では閉じない。人間とLLMが判断する）

- 二つの記述が意味として重複か矛盾かの最終判断。語彙的検出（`c-TF-IDF`・`Jaccard`）は言い換えを取りこぼす。`doc-review` の定例で閉じる。
- 一度も記録に現れなかった必要（書かれなかった要求）。検出できるのは構造的な欠落だけである。
- 一覧に無い訳語臭。`doc-review` が逆翻訳テルで判定する。一覧を育てて取りこぼしを減らす。
- 任意スクリプト経由のガード回避。監査の逆参照が事後に補う。
- `Edit`・`MultiEdit` の境界違反は事後検出であり、修正までディスクが一時的に不整合になる。`Write` 経路に寄せて予防の比率を上げる。
- 常時集合に何を残すかの最終判断。上限は肥大を機械的に検出する歯止めにすぎない。
- 仕様が実装どおり動くか。これはテストの責務であり、構造だけでは閉じない。

「100%の予防」は構造上できない。本プラグインの効果は、適切に運用された場合に、特定の失敗類型を検出・早期発見できることに限る。
