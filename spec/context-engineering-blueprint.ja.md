---
id: DESIGN-001
title: context-engineering-blueprint — LLM開発のための情報統治（Claude プラグイン設計書）
type: ARCH
status: current
owner: （受領者が記入）
created: 2026-06-24
updated: 2026-06-25
review_by: 2026-09-24
sources:
  - 本書の初版「LLM開発情報管理体系.md」と compass_artifact を統合
  - https://code.claude.com/docs/en/hooks
  - https://code.claude.com/docs/en/skills
  - arXiv:2602.11988（ETH Zürich & LogicStar.ai, 2026）
depends_on: []
impacts: []
llm_context: always
---

# context-engineering-blueprint — LLM開発のための情報統治（Claude プラグイン設計書）

## 0. この文書の使い方（受領する Claude への前置き）

この一枚は、**ビルド指示書**である。読み手としては、人間ではなくこれを渡された Claude（主に Claude Code）を想定する。最終目的は、ここに定義した情報管理体系を **再利用可能な Claude Code プラグイン**（Skills と Hooks とスクリプトとテンプレートの束）として実装させることにある。プラグインを一度作れば、どのリポジトリでも同じ統治を効かせられる。これが「一枚を渡せばどこでも使い回せる」の意味である。

読み順は次のとおりとする。第1〜4章で「何を・なぜ作るか」を確定する。第5章が **正本リファレンス**（Skills と Hooks が共通で実装する単一の正本）である。第6〜9章が実装仕様（Skills／Hooks／スクリプト／パッケージング）である。第10章がビルド順序の具体的指示である。第11〜13章が検証・破綻予測・チェックリストである。付録にテンプレートと出典を置く。

この設計書自体が、本体系の文章規範（第5.7節）に従って書かれている。すなわち一段落一トピック、推量と断定の分離、空句の排除、同一概念は同一語で表記、「100%保証」を主張しないという規範である。実装される文書も同じ規範に従わせる。ただし本書はビルド指示書のため、追跡対象の固有名（スクリプト名・ファイル名など）は散文でも用いる。

**前提となる思想（3点。以降の全設計がここから導かれる）**

1. 文書は資産ではなく**負債**である。各文書は存在を正当化しなければならない。生成はほぼ無料になったが、読む・保守する・内容を信頼してよいか見極めるコストは人間に残る。したがって既定の失敗様式は「散乱（sprawl）」であり、対策は「少なく書き、積極的に消し、各事実の正本を一つだけ保つ」ことである。
2. LLM の典型的失敗（廃案復活・未決の既決化・仕様文書と実装ノートの混同・古い前提の採用）の**多く**は、情報の位置づけ（現行か、廃案か、未決か、根拠か）が文書構造に書かれていないことに起因する。ただし仕様と実装の**挙動の乖離**は、位置づけだけでなくテストの欠如にも起因し、構造だけでは閉じない（§1.3）。ゆえに設計の主眼は、量を捌くことではなく、各情報片に**位置づけ・出所・依存・現行性**を付与して追跡可能にすることに置く。
3. コンテキストは「多いほど良い」ではない。リポジトリのコンテキストファイル（CLAUDE.md / AGENTS.md）を肥大させると、コーディングエージェントの成功率はむしろ下がり、推論コストは増える（ETH Zürich & LogicStar.ai, arXiv:2602.11988, 2026）。この研究が示すのは肥大の害であって、最小注入そのものの益ではない。最小注入が有益かは仮説であり、運用と受入テストで検証する。ゆえに常時投入は「最小の、エージェントが他から知り得ない非自明な事実」に絞る。CLAUDE.md は知識の集積ではなく、現行文書への入口だけを示す**最小限の案内**にする。

---

## 1. 結論（ピラミッド）

### 1.1 頂点の主張

**Claude Code 用の単一プラグイン `context-engineering-blueprint` を実装する。** このプラグインは、(a) 情報管理の手続きと判断を担う **6 個の Skill**、(b) 不変条件を機械的に強制する **少数の Hook**、(c) Hook が呼ぶ **決定論的バリデータ・スクリプト群**、(d) 文書型テンプレート、(e) 最小限の案内としての CLAUDE.md / AGENTS.md ひな型、から成る。これを任意のリポジトリで有効化すれば、人間と LLM の双方が情報の位置づけ・現行性・依存を追跡でき、変更と退行に耐えられる開発を継続できる。

### 1.2 主張を支える3本の柱

- **柱1（役割分担）**: 本体系の核心は「構造が予防・検出できること」と「人間とテストに委ねること」の分界にある。これを Claude Code の機構に対応づける。**Hook = 決定論的な強制（リンタ/CI に相当）**、**Skill = 手続き的知識と判断の補助**、**スクリプト = Hook が呼ぶ検証器**、**テンプレート = 文書型の契約**、**CLAUDE.md/AGENTS.md = 常時投入の最小限の案内**。決定論で守れるものは Hook が守り、判断が要るものは Skill が支援する。
- **柱2（単一の正本仕様）**: Skills と Hooks は、別々の規則を持ってはならない。第5章の正本リファレンス（文書型・ステータス統制語彙・メタデータ・フォルダ・LLMコンテキスト区分・ライフサイクル・文章規範）を、両者が同一の真実として参照する。リンタの判定規則と、Skill が文書を作る規則は、同じ表から導かれる。
- **柱3（最小から始め、不便が出てから育てる）**: 体系の重さは成熟度に応じて段階的に増やす。`docs-system-init` の既定は **Level 1 の最小5ファイル + 最小限の案内**であり、空のフォルダを先に作らない。フォルダや重いメタデータは、その文書型が初めて必要になった時点で `doc-author` が遅延生成する。これは「空の足場自体が、避けたかった散乱である」という規律に従う。

### 1.3 保証できる範囲と、できない範囲（責任分界点）

**予防・検出・早期発見できるもの（構造と Hook とスクリプトで対処）**

- 必須メタデータの欠落、ステータス統制語彙の逸脱、ID とファイル名の不一致、型とフォルダの不整合（PostToolUse リンタが検出）。
- 無効な参照 ID（dead link）と、依存グラフの破れ（フルリポジトリ監査が検出）。
- アーカイブ済み文書への直接編集、確定済み ADR の改変（PreToolUse ガードが拒否）。
- 廃案・未決・禁止事項を常時提示することで、退行・既決化の確率を下げ、矛盾出力を検出可能にする（SessionStart 注入と Regression Watchlist）。これは予防の保証ではない。注入そのものの性能上の益は仮説であり（前提3）、確率的逸脱は完全には防げない。
- 現行文書の陳腐化の疑い（`review_by` 超過をフルリポジトリ監査が一覧化）。

**人間レビューとテストに委ねるもの（構造だけでは閉じない）**

- 仕様が実装どおりに動くかの最終検証。これは受入・退行テストの責務である。文書は意図を、テストは挙動を保証する。
- 文書に書かれた抽象的なビジネス要求が市場の真のニーズを満たすかの判断。
- 暗黙のビジネス前提の記述漏れ。人間が書き忘れた前提は、構造では補完できない。
- LLM の確率的逸脱。指示を渡しても LLM は一定確率で逸脱しうる。
- 外部依存（外部 API 仕様・価格・法令）の予告なき変更。これは予防ではなく検出・早期発見でしか対処できない。

「100%の予防」は構造上不可能である。本プラグインの効果は、**適切に運用された場合に、特定の失敗類型を検出・早期発見できる**ことに限定される。

---

## 2. 「ビルドが成功した」の定義（受け入れ基準）

ビルドの成否は、抽象的な「管理できている感」ではなく、**7つの観点それぞれについて、それを担保する Skill・Hook・スクリプト・テンプレートを指させるか**で判定する。指させれば達成、指させなければ未達とする。ただし本章が測るのは**機構の存在**（ビルド受入の基準）であって、機構の**有効性**ではない。有効性は運用で別に測る。最大のリスクは「機構はあるが運用が回らない」こと（第12章#11）であり、運用の点検は第13.3〜13.6節で行う。

| # | 観点 | 達成条件（何を指させればよいか） |
|---|---|---|
| 1 | 見つけやすさ | フォルダ・命名規則・Overview 索引で目的の文書に到達できる。`doc-author` が型コード命名を強制し、`docs-audit` が孤立文書を検出する。 |
| 2 | 現行性 | 各文書の `status` で現行が判別できる。リンタが統制語彙を強制し、監査が `review_by` 超過の現行文書を一覧化する。 |
| 3 | 追跡性 | Requirement→Spec→実装→Test→ADR を `depends_on`/`impacts` でたどれる。`change-impact` がトレーサビリティを生成・点検する。 |
| 4 | 変更に耐える | 変更時に更新すべき文書集合を依存リンクから列挙できる。`change-impact` の14ステップと、監査の dead-link 検出。 |
| 5 | LLMに強い | 常時投入が現行・禁止・非目標・未決に限定され、廃案本文は渡らない。SessionStart 注入と `llm-context-pack` と PreToolUse アーカイブガード。 |
| 6 | 認知負荷 | 一文書一目的、粒度が揃い、抽象語でぼかさない。`doc-review` の規範（§5.7・付録E）。 |
| 7 | 保証の限界の明示 | 何を予防・検出・早期発見できるか、何を人間とテストに委ねるかが各成果物に書かれている。本設計書 第1.3 節を継承する。 |

加えて、次のメタ条件を満たすこと。**(a)** プラグインが `/plugin install` で他リポジトリへ配布できる。**(b)** `docs-system-init` が新規・既存いずれのリポジトリでも最小セットを安全に配置できる（既存ファイルを破壊しない）。**(c)** すべてのスクリプトが標準ライブラリのみで動く（外部 pip 依存ゼロ。どこでも動くため）。**(d)** Hook の既定構成がエージェントを体感的に遅くしない（フルリポジトリ監査は毎ターンではなくコマンド/CI で実行する）。

---

## 3. イシューツリー（ビルド問題の分解）

中心問い「**この情報管理体系を、どこでも再利用できる Claude Code 拡張としてどう実装するか**」を、相互に重複しない枝へ分ける。

- **A. 正本仕様の確定（何を実装するか）**
  - A1 正本仕様の確定方針（ステータス語彙・メタデータ・フォルダ・文書型・変更フロー）
  - A2 文書型の単一表（型コード・フォルダ・既定 status・llm_context・書く/書かない）
  - A3 メタデータ・スキーマ（必須 vs 推奨、成熟度別）
  - A4 ライフサイクル規則（昇格・退行・変更・アーカイブの状態遷移）
- **B. 役割分担の原則（決定論 vs 判断）** — 誰が何を担うかの原則を定める。各担い手の具体実装は C（Skills）・D（Hooks）。
  - B1 Hook が機械的に守るべき不変条件の集合
  - B2 Skill が手続き的に支援すべき判断の集合
  - B3 両者が共有するスクリプト（検証器）の境界
- **C. Skills 実装**
  - C1 各 Skill のトリガー設計（呼ばれにくさを避ける description）
  - C2 各 Skill の手続き・参照ファイル・スクリプト・対応 Hook
  - C3 成熟度（Level）への対応づけ
- **D. Hooks とスクリプト実装**
  - D1 イベント選択（SessionStart / PreToolUse / PostToolUse / 任意）
  - D2 マッチャと `if` 条件、終了コードと JSON 出力の契約
  - D3 ETH 知見に基づく最小注入（常時投入の肥大回避）
  - D4 Hook が呼ぶスクリプト（検証器）の実装（第8章）
- **E. パッケージングと配布**
  - E1 プラグイン構成（plugin.json / hooks.json / skills/ / scripts/）
  - E2 パス解決（`${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}`）
  - E3 リポジトリへの配置（init Skill）とプレーン `.claude/` フォールバック
- **F. 検証**
  - F1 中心主張の妥当性（Toulmin）
  - F2 ビルド・運用が破綻する経路（Premortem）
  - F3 ビルド・採用・運用のチェックリスト

---

## 4. SCQA（問題設定）

- **Situation（状況）**: LLM 支援開発で、調査・設計案・実装案・比較表・判断メモが大量に生成される。生成コストは限界まで下がった。Claude Code は Skills・Hooks・Plugins により、エージェントの挙動へ決定論的・手続き的な統制を後付けできるようになった。
- **Complication（複雑化）**: 生成物には位置づけがない。仕様・実装・調査・判断・廃案・未決が同じ粒度・同じ見た目で並ぶ。後から読むと、なぜそこにあるか、どれが現行か、何に依存するかが分からない。LLM 自身も古いログや廃案を現行として再採用する。一方で、対策として常時コンテキストを増やすと、エージェントの性能はむしろ下がる（arXiv:2602.11988）。手づくりの `.claude/` 設定は各人がばらばらに持ち、リポジトリ間で同期しない。
- **Question（問い）**: どのような Skills・Hooks・スクリプト・テンプレートと、それを束ねる配布形態を設計すれば、人間と LLM の双方が位置づけ・現行性・依存を追跡でき、変更と退行に耐え、かつ常時コンテキストを最小に保ったまま、**どのリポジトリでも同じ統治を再利用できるか**。
- **Answer（答え）**: 位置づけで分離する文書型体系と、出所・依存・現行性を必須メタデータ化する運用を、**Hook（決定論的強制）と Skill（手続き的支援）に役割分担**して実装する。両者は単一の正本仕様（第5章）を参照する。常時投入は最小限の案内と最小の確定事実に限定する。これらを単一プラグインに束ね、`/plugin install` で配布し、init Skill で各リポジトリへ最小配置する。詳細を次章以降で示す。

---

## 5. 正本リファレンス（システム仕様）

本章は Skills と Hooks が共通で実装する**単一の正本**である。実装はすべてこの章の表に従う。仕様の変更は本章でのみ行い、Skills・Hooks のコードに規則を二重定義しない。

### 5.1 情報分類と文書型（単一表）

各文書は「型」と「位置づけ」を持つ。型コードは ID の接頭辞であり、フォルダと既定の `llm_context` 区分を一意に決める。`doc-author` はこの表に従って文書を作り、リンタは `type` とフォルダと `status` の整合をこの表で検証する。

| 型コード | 文書型 | フォルダ | 既定 status | llm_context | 入れる | 入れてはいけない |
|---|---|---|---|---|---|---|
| OVERVIEW | Overview（索引） | /00-overview | current | always | 現行文書一覧、各文書一行説明、未決/廃案一覧へのリンク | 仕様の本文（重複管理） |
| GLOSSARY | Glossary（用語集） | /00-overview | current | always | 用語、定義、文脈ごとの意味差、初出リンク | 曖昧な言い換え |
| PRODUCT | Product（製品定義） | /10-product | current | task | ビジョン、対象ユーザー、システム境界 | 技術選定、API 詳細 |
| REQ | Requirement（要求） | /10-product | current | task | 要求文（EARS＝要求記述の構文。推奨）、優先度、受入基準参照、出所 | 実現方法（Spec/Arch へ） |
| NONGOAL | Non-goal（非目標） | /10-product | current | **always** | やらないこと、その理由 | あいまいな願望 |
| SPEC | Specification（仕様） | /20-spec | current | task | 入出力、制約、エラー時挙動、受入基準 | 廃案、検討経緯（ADR へ）、実装コードの写し |
| DATA | Data Model | /20-spec | current | task | エンティティ、保存方針（Decided Facts と整合）、保持期間 | 処理のビジネスロジック |
| API | API Reference | /20-spec | current | task | エンドポイント、入出力、エラー（中立・網羅・現在形） | 「なぜ」の解説（Explanation へ） |
| PRICING | Pricing Model | /20-spec | current | task | プラン、原価依存（depends_on）、改定履歴リンク | 営業トーク、決済 API 実装 |
| ARCH | Architecture Description | /30-architecture | current | task | C4 Context/Container 図、品質特性シナリオ、関連 ADR | 頻繁に変わるコード詳細（C4 Code レベル） |
| CTXMAP | Context Map（統合ビュー） | /30-architecture | current | task | 各文書へのリンクと結合ロジックの要約 | 具体仕様の本文（重複させない） |
| ADR | Architecture Decision Record | /40-decisions | accepted | task | 背景、検討案と却下理由、決定、帰結 | 複数決定（1ADR1決定）、現行仕様の全文 |
| CHANGE | Change Request | /40-decisions | proposed | task | 変更内容、理由、要求元、影響の初期見積 | 承認前の決定としての記述 |
| IMPACT | Impact Analysis | /40-decisions | current | task | 影響文書・実装・テスト・表示の列挙、工数見積 | 分析を伴わない感想 |
| RESEARCH | Research Note | /50-research | draft | **never** | 出所 URL、取得日、事実、比較 | 決定（ADR へ。混ぜない） |
| COMPET | Competitor Research | /50-research | draft | **never** | 比較軸、取得日、価格・機能の出所 | 自社の現行仕様 |
| LEGAL | Legal Research | /50-research | draft | **never** | 関連法規、適用条件、管轄、出所 | 法的根拠なき個人見解、確定要件との混同 |
| IMPL | Implementation Note | /60-implementation | current | task | 実装上の制約、gotcha、対象コンポーネント | 仕様の正本（Spec へ） |
| TEST | Test Plan | /70-test | current | task | 受入基準への対応表、退行観点、環境、合否基準 | 無関係な要件定義 |
| WATCH | Regression Watchlist | /70-test | current | **always**（要点のみ） | 戻ってはならない事項、撤回/決定日、根拠、監視点 | 安定し監視不要な機能 |
| RUNBOOK | Runbook（運用手順） | /80-operation | current | task | トリガー、前提、手順、復旧、確認方法 | 設計議論（Explanation） |
| INCIDENT | Incident Report | /80-operation | current | never | 事象、時系列、根本原因、再発防止 | 個人の非難 |
| DECIDED | Decided Facts | /90-llm | current | **always** | 確定方針、決定日、根拠 ADR リンク | 迷い、調査、提案中の事項 |
| OPENQ | Open Questions | /90-llm | open | **always** | 問い、選択肢、期限、担当、暫定の傾き | あたかも決定したかの断定 |
| DEPREC | Deprecated Item | /90-llm | deprecated | **always**（事実のみ） | 撤回理由、撤回日、後継リンク、再評価条件 | 現行ファイル内への放置 |
| CTXPACK | LLM Context Pack | /90-llm | current | task | 当該タスクの確定方針抜粋・非目標・禁止事実・対象 Spec | 廃案の本文、巨大ログ |
| ARCHIVE | Archive Note | /99-archive | archived | **never** | 退役理由、退役日、後継リンク | 現行システムに関する情報 |

**llm_context の運用要点**: `always` = 最小限の案内（CLAUDE.md/AGENTS.md）+ OVERVIEW/GLOSSARY/NONGOAL/DECIDED/OPENQ/DEPREC（事実のみ）/WATCH（要点のみ）。`task` = そのタスクに直接関わる現行の SPEC/ARCH/ADR/IMPL/TEST など。`never` = RESEARCH/COMPET/LEGAL/INCIDENT/ARCHIVE の本文、古い会話ログ、機密。`always` 群でも本文全量ではなく**事実・要点のみ**を注入する（肥大回避）。

### 5.2 ステータス統制語彙

`status` の統制語彙は8値である。うち `accepted` は ADR 専用で、ADR 以外の型は `accepted` を除く7値を使う。これ以外は使わない。自由語を増やすと見つけやすさと機械検証が崩れる。

| 値 | 意味 | 主な型 |
|---|---|---|
| `draft` | 草案。まだ現行ではない。 | RESEARCH, COMPET, LEGAL, 作成途中の各型 |
| `proposed` | 提案中。承認待ち。 | ADR, CHANGE |
| `current` | 現行。今の真実。 | SPEC, ARCH, DECIDED, REQ ほか多数 |
| `accepted` | 受理（ADR 専用）。current に相当。 | ADR のみ |
| `deprecated` | 廃案。現行ではない。 | DEPREC, 廃案にした各型 |
| `superseded` | 後継ありで置換された。 | ADR, SPEC（旧版） |
| `archived` | 退役。証跡として保管。 | ARCHIVE |
| `open` | 未決。決定していない。 | OPENQ |

ADR（type=ADR）の許可値は {proposed, accepted, superseded, deprecated}、それ以外の型は7値（accepted を除く）とする。これは意図的で境界の明確な例外であり、リンタは型ごとの許可リストで `status` を検証する。

### 5.3 メタデータ・スキーマ（YAML フロントマター）

全文書の先頭に YAML フロントマターを置く。**必須は絞る**（多すぎると形骸化する）。成熟度に応じて推奨項目を足す。

```yaml
---
id: <型コード>-<連番>          # 例 SPEC-014。ファイル名の型コード+連番と一致させる
title: <一文の主題>
type: <第5.1節の型コード>
status: <第5.2節の統制語彙>
owner: <個人名>                # チーム名でなく個人。陳腐化の責任の所在
created: <YYYY-MM-DD>           # ISO 8601
updated: <YYYY-MM-DD>          # 現行性検出に使う
sources: [<出所URL/会話ID>]     # 真正性。LLM由来か人間か、どの会話/URLか
# --- 以下は Level 3+ で推奨 ---
review_by: <YYYY-MM-DD>        # 次回レビュー期限。超過した現行文書を監査が一覧化
depends_on: [<id>]            # この文書が前提とするもの
impacts: [<id>]               # 変更時に波及する先
supersedes: <id>              # 置換した旧文書（任意）
superseded_by: <id>           # 後継（退行防止の要）
llm_context: <always|task|never>
---
```

**リンタが必須とする項目（Level 2 以降）**: `id`, `title`, `type`, `status`, `owner`, `updated`, `sources`。
**Level 3+ で必須化する項目**: 強い依存（破壊時影響=大）を持つ文書の `depends_on`/`impacts`、退役・置換時の `superseded_by`、LLM 投入区分 `llm_context`。
**形骸化を防ぐ設計**: `status` と `updated` は LLM に更新を代行させ、人間は承認のみ。`review_by` 超過の現行文書を `docs-audit` が「現行性疑い」として一覧化する。

### 5.4 フォルダ構成と命名規則

```
<repo>/
├── AGENTS.md                 # ルート直下。最小限の案内。最初に読む規約
├── CLAUDE.md                 # 同上（Claude Code 用。AGENTS.md を指すか同内容）
└── docs/
    ├── 00-overview/          # Overview, Glossary。入口
    ├── 10-product/           # Product, Requirement, Non-goal。何を作るか
    ├── 20-spec/              # Specification, Data Model, API, Pricing。現行の正本
    ├── 30-architecture/      # Architecture, Context Map
    ├── 40-decisions/         # ADR（追記型・連番）, Change Request, Impact Analysis
    ├── 50-research/          # Research, Competitor, Legal。出所付き調査。決定とは別
    ├── 60-implementation/    # Implementation Note。実装の制約
    ├── 70-test/              # Test Plan, Regression Watchlist
    ├── 80-operation/         # Runbook, Incident Report
    ├── 90-llm/               # Decided Facts, Open Questions, Deprecated Item, Context Pack
    └── 99-archive/           # 退役文書。現行と物理的に分離。RAG（検索拡張生成）/検索から除外
```

**注意**: `docs-system-init` の既定はこの全ツリーを作らない。Level 1 の最小（`90-llm/decided-facts.md`, `90-llm/open-questions.md`, `10-product/non-goals.md`, `00-overview/glossary.md`, `00-overview/overview.md` の5ファイル + ルートの最小限の AGENTS.md/CLAUDE.md）のみを配置する。各フォルダは、その型の文書が初めて作られるときに `doc-author` が生成する。空の足場を先に作らない。

**命名規則**

- ファイル名: `<型コード>-<連番>-<短い主題>.md`（例 `SPEC-014-refund-policy.md`, `ADR-0009-no-server-side-address.md`）。
- 型コードで一覧の見通しが立ち、連番で一意、主題で想起できる。
- ID（フロントマターの `id`）はファイル名の型コード+連番と一致させる。
- 日付は ISO 8601（YYYY-MM-DD）。
- 禁止: 日本語ファイル名の濫用、空白、版番号のファイル名埋め込み（version はメタデータか git で管理）、`design.md`/`memo.md` などの文脈を伝えない抽象名。

### 5.5 LLM コンテキスト管理（3区分）

LLM に渡す情報を3区分し、廃案・未決・禁止を分離する。`llm-context-pack` Skill と SessionStart Hook がこれを実装する。

- **常時投入（llm_context: always）**: AGENTS.md（最小限の案内）、Decided Facts、Non-goals、Deprecated Item（撤回事実のみ）、Glossary、Regression Watchlist（要点のみ）。本文全量でなく事実・要点に絞る。
- **タスク別投入（llm_context: task）**: 当該機能の現行 Spec、関連 ADR、関連 Implementation Note。段階的に開示する（progressive disclosure）。文脈を肥大させない。
- **投入禁止（llm_context: never）**: 廃案の本文（撤回事実のみ渡し、本文は渡さない。復活を誘発するため）、古い会話ログ、未整理の調査メモ、機密。
- **古い情報を証跡として渡す場合**: 「これは退役した旧仕様であり現行ではない」と位置づけを明示して渡す。位置づけラベルなしに渡すと現行と誤読される。

### 5.6 ライフサイクルと状態遷移

#### 変更フロー（14ステップ）

`change-impact` Skill が実装する。Change Impact Analysis を軸にする。

1. 変更要求を記録（Change Request 起票：内容・理由・要求元）。
2. 変更対象を分類（価格／保存方針／対象ユーザー／法務要件／外部 API／競合価格／フェーズ移行 のどれか）。
3. 依存関係を抽出（対象文書の `depends_on`/`impacts` をたどる）。
4. 影響文書を列挙（Impact Analysis に記載）。
5. 影響実装を列挙。
6. 影響テストを列挙（受入・退行）。
7. ADR が必要か判定（構造・非機能・不可逆・外部依存・横断影響のいずれかに該当すれば ADR：アーキテクチャ的有意性テスト）。
8. 仕様を更新（Spec を現行化。旧版は Archive へ）。
9. 実装を更新。
10. テストを更新。
11. LLM コンテキストを更新（Decided Facts, Context Pack, AGENTS.md）。
12. 廃案・旧版を整理（Deprecated Item と Regression Watchlist に追記、Archive へ移動）。
13. 退行チェックを実施（Watchlist の監視点を確認）。
14. 更新結果を記録（Change Request をクローズ）。

**更新順序の原則**: 根拠（ADR）→現行仕様（Spec）→実装→テスト→LLMコンテキスト→廃案整理。根拠を先に固めないと実装が先行して乖離する。**「何を変えたか」（Change Request/git）と「なぜ決めたか」（ADR）は別管理する。**

#### 退行（リグレッション）管理

退行＝一度決めた仕様・方針が、後続の LLM 出力や実装変更で昔へ戻る／矛盾する現象。`regression-guard` Skill と SessionStart 注入と PreToolUse ガードで対処。

- 検出する文書構造: Decided Facts（現行の確定方針の単一索引）、Deprecated Item（撤回事実・日付・後継）、Regression Watchlist（戻ってはならない事項）、Non-goals。
- 各層の対策: 撤回時に必ず Deprecated Item と Watchlist へ記載し、旧文書を Archive へ移し `superseded_by` を付ける（文書上）。方針を受入テスト化する（テスト上）。Context Pack に禁止事実を常時投入し矛盾出力を拒否させる（LLM 上）。変更レビューで Watchlist の監視点を確認する（人間上）。
- 復旧手順: 退行を検出 → Watchlist の根拠 ADR を確認 → 現行へ戻す Change Request を起票 → 原因分類（位置づけ未記載か、テスト欠如か） → 監視点を強化 → Incident に記録。

#### 価値の変化（昇格・降格・廃棄）

情報の価値は時間と状況で変わる。`doc-author` と `change-impact` が昇格基準で扱う。

- 昇格: メモ→仕様（同じ事実が二回以上、設計判断の前提として参照されたとき）。仕様→ADR（その仕様が議論を呼び、選択肢の記録が必要になったとき）。調査→根拠（決定の `sources` から参照されたとき）。
- 捨てる: 出所が不明で、他文書から参照されず、再現可能な一時メモ。
- アーカイブ: 現行ではないが証跡価値がある（退役仕様、廃案、旧価格）。`/99-archive` へ。
- 上位索引（Overview/Decided Facts）に載せる: 現行の判断に常時必要、または LLM に毎回読ませる必要があるもの。
- 廃案の再評価: 別市場・別フェーズで有効になりうる廃案は、Deprecated Item に「再評価条件」を残し、Watchlist（戻してはならない退行）とは区別する。

### 5.7 日本語技術文書規範

`doc-review` Skill がレビュー基準として実装する。文書と LLM 出力の双方に適用する。

**取り込む規則（採用）**

- 一文一義、一段落一トピック。段落の先頭文でその段落の役割（結論・根拠・例外）を示す。
- 段落先頭で前段落との論理関係を接続表現（「であれば」「しかし」「実際」）で示す。LLM は接続詞がないと因果を捏造しやすい。
- 推量・可能性・反実仮想を機械的に断定へ変えない（未確定事項を断定にしない）。これは「未決を既決にしない」要請と一致する。
- 異なるものを「同じ」とまとめない。複数要因を単一原因に還元しない。
- 因果を主張するときは機構を一文で示す。
- 「必ず検出できる/解決できる」と書かない。条件付きで述べる。
- 用語の初出定義、同じ概念は同じ語で呼ぶ（Glossary と一致）。
- LLM っぽい空句の禁止（「重要なのは」「正面から」「不可欠」「掘り下げる」「多角的」「〜において」「非常に」など）。
- 冗長の排除: 同じ主張を繰り返さない。読者が補える中間段階を書かない。

**改変して取り込む規則**

- 「後で参照しない固有名（ファイル名・関数名）を出さない」: 技術文書では追跡性のため ID と出所が要る。**本体系では、散文では一般名で書き、参照用 ID はメタデータ・リンク欄に置く**と改変する。

**取り込まない規則**

- 整形の細則（脚注・コラム記法、ダッシュ・中黒の細則）: Markdown 慣習に合わせる。

**レビュー観点（doc-review が出力するルーブリック）**

1. 各段落の先頭文でその段落の役割が分かるか。
2. 推量と断定が区別されているか。未決を既決にしていないか。
3. 結論・根拠・条件・例外が分離されているか。
4. 保証できないものを保証できるように書いていないか。
5. 抽象語・LLM 空句がないか。
6. 同じ概念を同じ語で呼んでいるか。

**併用する運用チェックリスト**: `doc-review` は、上記の本書固有の観点（LLM 空句・過剰保証・推量と断定の区別など）に加え、付録Eの日本語・論理チェック（出典: JTCA『日本語スタイルガイド』／波頭亮『思考・論理・分析』）を併用する。両者は補完関係にある（§5.7＝本書固有の観点、付録E＝明快さと論理の汎用チェック）。

---

## 6. 実装仕様 — Skills（手続きと判断）

Skill は「段階的に開示される専門知識（progressive disclosure）」である。description が常時コンテキストに載り、本文はトリガー時のみ読み込まれる。**description がトリガーそのもの**であるため、三人称・主要ユースケース先頭・ユーザーが実際に言う語句の列挙で書く。Claude は単純な一手で済むタスクには Skill を使わない傾向（呼ばれにくさ）があるため、description は少し「押しが強い」書き方にする。

すべての Skill は本プラグインの `skills/<skill-name>/SKILL.md` に置く。本文は500行未満を目安とし、超える知識は `references/` に分け、SKILL.md から「いつ読むか」を明示して参照させる。決定論的処理は `scripts/` のスクリプトに委ね、コンテキストを消費せず実行させる。スクリプトのパスは `${CLAUDE_SKILL_DIR}` で解決する（個人/プロジェクト/プラグインのどこに置かれても解決できる）。

実装する Skill は次の6つ。各 Skill に、トリガー（description 要旨）・成熟度・手続き・参照ファイル・スクリプト・対応 Hook を示す。

### 6.1 `docs-system-init`（配置）｜Level 0→2

- **description 要旨**: 「リポジトリに LLM 向け情報統治を導入する。`/docs` 構造の最小セットと、最小限の AGENTS.md/CLAUDE.md、ステータス統制語彙、メタデータ規約、リンタ・監査スクリプト、Hook 設定を配置する。新規リポジトリの初期化、既存リポジトリへの体系導入、`docs` の標準化、AGENTS.md の整備を求められたら必ず使う。」
- **手続き**:
  1. 既存の `docs/` と AGENTS.md/CLAUDE.md を検出し、**破壊しない**（あれば差分提案、なければ新規）。
  2. 既定（Level 1）で最小5ファイル + 最小限の案内のみ配置する（第5.4節）。フル11ツリーは作らない。
  3. プロジェクトに Hook を有効化する。プラグインとして配布する場合はプラグインの `hooks/hooks.json` が効くので追加不要。プレーン `.claude/` 運用の場合は `.claude/settings.json` に第7章の Hook を書き込む。
  4. リンタ・監査スクリプトを配置（プラグイン同梱なら参照のみ。スタンドアロンなら `.claude/scripts/` へコピー）。
  5. 配置後、第13章の「採用チェックリスト」を出力し、次のレベルへの移行条件を示す。
- **参照ファイル**: `references/levels.md`（Level 0–5 の状態・移行条件・失敗しやすい点）、`references/folder-layout.md`（第5.4節の詳細）。
- **スクリプト**: `scripts/scaffold.py`（最小配置。既存ファイル非破壊）。
- **対応 Hook**: 配置後は SessionStart 注入、PreToolUse ガード、PostToolUse リンタが効く。

### 6.2 `doc-author`（型付き文書の作成・更新）｜Level 1→2

- **description 要旨**: 「型付きの文書（仕様・要求・ADR・調査・Decided Facts・Non-goal など）を、正しいフロントマターと配置で作成・更新する。仕様を書く、ADR を起こす、Non-goal を足す、調査メモを残す、用語を定義する、決定済み事実を追加する、といった依頼で必ず使う。型の取り違え（調査に決定を書くなど）と、廃案の現行ファイルへの放置を防ぐ。」
- **手続き**:
  1. 第5.1節の表から型を決め、フォルダと既定 status と llm_context を引く。フォルダが無ければ生成する（遅延生成）。
  2. ファイル名（`<型コード>-<連番>-<主題>.md`）と `id` を一致させる。
  3. 付録のテンプレートからフロントマター+本文骨格を生成し、「書く/書かない」規則を適用する。
  4. 価値の変化の昇格基準（第5.6節）に該当する場合は、元文書を残しつつ昇格先（ADR など）を作り、`sources`/`supersedes` でリンクする。
  5. 作成後、PostToolUse リンタが自動でフロントマターを検証する。失敗時はリンタの指摘に従い修正する。
- **参照ファイル**: `references/templates/`（型ごとのテンプレート。付録Aと同内容）、`references/adr-workflow.md`（ADR は追記型。覆すときは新 ADR を作り旧 ADR に `superseded_by`。編集で消さない。アーキテクチャ的有意性テスト）、`references/promotion.md`（昇格・降格・廃棄基準）。
- **スクリプト**: `scripts/new-doc.py`（連番採番とテンプレート展開。任意）。
- **対応 Hook**: PostToolUse リンタ（必ず併用する）、PreToolUse ADR 改変ガード。

### 6.3 `doc-review`（文章規範＋位置づけレビュー）｜Level 2→3

- **description 要旨**: 「文書または LLM 生成物に、日本語技術文書規範と位置づけレビューを適用する。文章をレビューする、LLM の出力を点検する、抽象的すぎる記述を直す、推量と断定の混在を直す、未決が既決として書かれていないか確認する、といった依頼で必ず使う。」
- **手続き**:
  1. 第5.7節のレビュー観点6項目を順に適用し、違反箇所を列挙する。
  2. 位置づけレビュー: `status` が内容と一致するか、未決（open）が断定で書かれていないか、current と draft が混ざっていないかを点検する。
  3. 修正案を示す（断定/推量の分離、空句の削除、用語統一）。固有名は散文では一般名にし、ID はメタデータ・リンク欄へ寄せる。
- **参照ファイル**: `references/jp-writing-rubric.md`（第5.7節の全規則と良い例・悪い例）。
- **スクリプト**: `scripts/empty-phrase-lint.py`（既知の LLM 空句の機械検出。補助。最終判断は本文の指示で行う）。
- **対応 Hook**: なし（判断主体のため Hook 化しない）。任意で Stop 時に prompt 型 Hook で「出力に空句がないか」を点検させてもよい。

### 6.4 `change-impact`（変更・依存・影響分析）｜Level 4

- **description 要旨**: 「仕様・要件・外部依存の変更に対し、14ステップの変更フローと Change Impact Analysis を実行する。仕様を変える、価格や API の変更を反映する、要件を更新する、変更の影響範囲を知りたい、依存をたどりたい、といった依頼で必ず使う。変更漏れによる矛盾（退行）を防ぐ。」
- **手続き**: 第5.6節の14ステップを実行する。`depends_on`/`impacts` をたどり、影響文書・実装・テストを列挙し、アーキテクチャ的有意性テストで ADR の要否を判定し、更新順序（ADR→Spec→実装→テスト→LLM→廃案整理）を守り、旧版を Archive へ移し `superseded_by` を付ける。Impact Analysis 文書を出力する。
- **参照ファイル**: `references/impact-analysis.md`（依存の種類・方向・強さ、表現の使い分け＝メタデータ/文書/図/トレーサビリティ表/テスト/ADR）、`references/combination.md`（統合・分割・上位ビュー・依存マップの決定木）。
- **スクリプト**: `scripts/dep-graph.py`（全文書の `depends_on`/`impacts` から有向グラフを構築し、指定 ID の波及先を列挙。dead link も報告）。
- **対応 Hook**: PostToolUse リンタ（更新後の整合検証）。

### 6.5 `regression-guard`（退行防止）｜Level 4

- **description 要旨**: 「退行（廃案の復活、撤回した方針の再採用、決定の取り違え）を防ぐ。Decided Facts・Deprecated Item・Regression Watchlist を整備・点検し、提案中の変更や新規仕様が過去の決定と矛盾しないか確認する。『この方針は前に却下したはず』『廃案が復活していないか』といった文脈、および新仕様の提案時に必ず使う。」
- **手続き**:
  1. 変更・新仕様の内容を、Decided Facts と Regression Watchlist（戻ってはならない事項）と Non-goals に突き合わせる。
  2. 矛盾を検出したら、根拠 ADR を示し、退行か正当な再評価か（Deprecated Item の「再評価条件」）を仕分ける。
  3. 退行なら復旧手順（第5.6節）を起動する。Watchlist へ監視点を追加し、可能なら受入テスト化する（例「住所が DB に保存されないこと」）。
- **参照ファイル**: `references/regression-model.md`（退行の種類と原因分類、各層の対策、復旧手順、Watchlist テンプレート）。
- **スクリプト**: `scripts/watchlist-check.py`（Watchlist の監視点と現行文書/実装の照合補助）。
- **対応 Hook**: SessionStart 注入（Decided Facts/Deprecated/Watchlist 要点を常時投入）が、退行の確率を下げ矛盾出力を検出可能にする主力（予防の保証ではない。前提3）。

### 6.6 `llm-context-pack`（コンテキスト・エンジニアリング）｜Level 5

- **description 要旨**: 「特定タスクのために LLM へ渡す最小コンテキスト（Context Pack）を組み立てる。Claude にタスクを依頼する前の準備、コンテキストの整理、『何を読ませるべきか』の判断で必ず使う。常時投入の事実・非目標・禁止事実・用語に加え、当該タスクの現行 Spec と関連 ADR のみを集約し、廃案本文・古いログ・調査メモは明示的に除外する。肥大させない。」
- **手続き**:
  1. 第5.5節の3区分に従い、`always` 群（事実・要点のみ）+ タスク対象の現行 Spec + 関連 ADR を集約する。
  2. `never` 群（廃案本文・古いログ・未整理調査・機密）を明示的に除外する。証跡として古い仕様を含める場合は「退役・現行ではない」と位置づけを明示する。
  3. ETH 知見に従い**最小**に保つ。冗長な構造説明やリンタが担う規約は入れない（前提3）。
  4. 付録A-7 の Context Pack テンプレートに出力し、`/90-llm/` に CTXPACK として保存する。
- **参照ファイル**: `references/context-engineering.md`（3区分の運用、段階的な開示（progressive disclosure）、ETH 知見の要約と「最小限の非自明情報に絞る」原則）。
- **スクリプト**: `scripts/collect-context.py`（`llm_context` メタデータでフィルタし、`always`/指定タスクの `task` のみ収集。`never` を除外）。
- **対応 Hook**: SessionStart 注入（`always` 群）と整合させる。Context Pack はタスク別の上乗せである。

### 6.7 Skill 設計の共通原則

- **呼ばれにくさ対策**: description は「〜の依頼で必ず使う」を含め、ユーザーが実際に使う語句を列挙する。
- **粒度**: 上記6つに限定し、安易に増やさない。Skill を増やしすぎると、文書型を増やしすぎたのと同じ散乱を招く。「依存管理」は `change-impact` 内、「昇格」は `doc-author` 内に references として収め、独立 Skill にしない。
- **本文の長さ**: 各 SKILL.md は500行未満。テンプレート群と詳細規則は `references/` へ。
- **スクリプトは stdlib のみ**: pip 依存を作らない（どこでも動くため。第8章）。

---

## 7. 実装仕様 — Hooks（決定論的強制）

Hook は「LLM の選択に依存せず、ある動作が必ず起きる」決定論的制御である。本体系では Hook を「リンタ/CI に相当する強制層」と位置づける。Hook はライフサイクルの特定点で発火し、command 型ではイベントの JSON を stdin で受け取り、終了コードと stdout の JSON で結果を返す。Hook の設置場所は、プラグインの `hooks/hooks.json`（プラグイン有効時に適用。配布に最適）を第一とし、プレーン運用では `.claude/settings.json`（プロジェクト共有）を使う。

**終了コードと JSON 出力の契約（共通）**

- 終了コード 0 かつ出力なし = 判断なし（通常フロー続行）。
- 終了コード 2 = ブロック。PreToolUse ではツール実行を止め、stderr を Claude に見せる。
- 構造化制御は `hookSpecificOutput` を使う。PreToolUse は `permissionDecision`（`allow`/`deny`/`ask`）と `permissionDecisionReason`、必要なら `updatedInput`（ツール引数の書き換え）、`additionalContext`（Claude への追加文脈）。
- PostToolUse は `{"decision": "block", "reason": "..."}` でターンを止める（ツール結果は Claude に渡らない）。ターンを止めずに指摘だけ返して Claude に自己修正させるには、`decision` を出さず `hookSpecificOutput.additionalContext` に指摘を入れる。**リンタにはこれを使う。**
- SessionStart と UserPromptSubmit の stdout は Claude のコンテキストに追加される。UserPromptSubmit はプロンプトを置換できず `additionalContext` の注入のみ可能。

実装する Hook は**コア3種**（必須）と**任意3種**（オプション）。

### 7.1 コア Hook（必須）

#### (1) SessionStart → 契約の最小注入

- **イベント / マッチャ**: `SessionStart`（matcher: `startup|resume|clear` など）。
- **目的**: セッション開始時に、常時投入すべき「契約」を**最小**で注入する。注入内容は Decided Facts（current）+ Non-goals + Deprecated Item の**事実のみ** + Glossary の見出し + Regression Watchlist の「戻ってはならない事項」列。本文全量は注入しない（前提3）。
- **ハンドラ**: `type: command`、`${CLAUDE_PLUGIN_ROOT}/scripts/inject-contract.py` を実行。stdout に最小契約を出力（コンテキストに追加される）。
- **強制する不変条件**: 「LLM に毎回読ませるべき文書」の常時不在を防ぐ。これにより廃案復活・既決化・古い前提の採用の確率を下げ、矛盾を検出可能にする（予防の保証ではない。前提3）。
- **設定例**:
```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|clear",
        "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/inject-contract.py\"", "timeout": 10 } ] }
    ]
  }
}
```

#### (2) PreToolUse → アーカイブ／ADR 改変ガード

- **イベント / マッチャ**: `PreToolUse`（matcher: `Edit|Write|MultiEdit`）。`if` 条件で対象を絞る。
- **目的**: (a) `/99-archive/**` への書き込み・編集を拒否する（退役文書は不変の証跡。編集は退行を招く）。(b) `/40-decisions/ADR-*.md` の**既存ファイルの改変**（Edit/MultiEdit）を拒否する（ADR は追記型。覆すときは新 ADR を作り `superseded_by`）。
- **ハンドラ**: `type: command`、`${CLAUDE_PLUGIN_ROOT}/scripts/archive-guard.py`。stdin の `tool_input.file_path` を見て、対象なら `permissionDecision: "deny"` を返す。
- **終了コード / JSON**:
```json
{ "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "アーカイブ済み文書は不変です。退役文書は編集せず、現行は /20-spec で更新してください。" } }
```
ADR 改変の場合の理由文: 「ADR は追記型です。覆すときは新しい ADR を作成し、旧 ADR に superseded_by を付けてください（編集で消さない）。」
- **強制する不変条件**: 退役文書の不変性、ADR の追記型運用。
- **設定例**:
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit",
        "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/archive-guard.py\"" } ] }
    ]
  }
}
```

#### (3) PostToolUse → フロントマター・リンタ（本体系の中核強制）

- **イベント / マッチャ**: `PostToolUse`（matcher: `Edit|Write|MultiEdit`）。
- **目的**: 文書の書き込み・編集の直後に、触れたファイルのフロントマターを検証する。これが「CI でリンタを走らせ、必須メタデータの欠落をビルドエラーとして弾く」の per-turn 版である。無効な参照 ID（dead link）の全件照合は重いため監査（`docs-audit.py`）に委ねる（§7.3）。
- **検証規則（`docs-linter.py` が実装。第8章）**: 必須キーの存在（id/title/type/status/owner/updated/sources）、`status` が型別許可リストに含まれる、日付が ISO 8601、`id` がファイル名の型コード+連番と一致、`type` とフォルダが第5.1節表と整合、`llm_context ∈ {always,task,never}`、型規律の軽い検査（例：RESEARCH に「## 決定」見出しがあれば警告）。参照整合（dead link）は全 docs の走査が要るため per-turn では検査せず、監査（`docs-audit.py`）に委ねる。
- **ハンドラ / 出力**: `type: command`、`${CLAUDE_PLUGIN_ROOT}/scripts/docs-linter.py`。違反時は `decision` を出さず `hookSpecificOutput.additionalContext` に指摘を入れて返す。ターンは止めず、Claude が指摘を読んで修正する（`decision:"block"` はターンを止めツール結果も渡さないため使わない）。`docs/` 配下の `.md` 以外は終了コード 0 で素通り。
- **強制する不変条件**: メタデータ品質、ステータス統制、ID 整合、型規律（参照整合は監査が担う）。
- **設定例**:
```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit",
        "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/docs-linter.py\"" } ] }
    ]
  }
}
```

### 7.2 任意 Hook（オプション。必要になってから足す）

- **(4) Bash 安全ガード（PreToolUse, matcher: `Bash`, if: `Bash(rm *)` など）**: `/99-archive` の削除や破壊的コマンドを拒否する。証跡の喪失を防ぐ。汎用安全策。
- **(5) フルリポジトリ監査（手動 / CI / 任意で Stop）**: `docs-audit.py` を `/audit` コマンドまたは CI で実行する。dead link の全件、`review_by` 超過の現行文書、N 日以上 draft 放置、RESEARCH に決定混入、Watchlist 未保守 を一覧化する。**毎ターンは実行しない**（エージェントを遅くするため）。重い検査は per-turn ではなくここに置く。
- **(6) UserPromptSubmit リマインダ（matcher なし）**: 実装・変更を示唆するプロンプトで Context Pack 未参照なら、`additionalContext` で「Decided Facts と Non-goals を確認し、必要なら Context Pack を組め」と注入する。ドリフトが観測された場合のみ有効化（既定は無効。常時注入の肥大を避ける）。

### 7.3 Hook 設計の共通原則

- **マッチャは大文字小文字を区別する**（`bash` は `Bash` にマッチしない）。ツールイベントは `tool_name` でマッチする。マッチャは、英数字・`_`・`|` のみなら `|` 区切りの完全一致リスト（`Edit|Write|MultiEdit` はこれ）、`.`/`*`/`^`/`$` などのメタ文字を含むと JavaScript 正規表現として評価される。さらに細かい絞り込みは `if`（パーミッション規則構文、例 `Edit(*/99-archive/*)`）で行う。
- **速度を最優先する**: per-turn の Hook（PostToolUse リンタ）は単一ファイルのみ検証する。全件走査・依存グラフ・陳腐化の検出は `docs-audit.py`（コマンド/CI）に隔離する。不要に発火する Hook はエージェントを著しく遅くする。
- **冪等・無害**: 非クリティカルな Hook は失敗してもワークフローを止めない設計にする。リンタは `decision` を出さず additionalContext で指摘し、修正余地を残す。
- **パス解決**: プラグイン同梱スクリプトは `${CLAUDE_PLUGIN_ROOT}`、プロジェクト設置は `${CLAUDE_PROJECT_DIR}` を使う。

---

## 8. 実装仕様 — スクリプト（決定論的バリデータ）

Hook と一部 Skill が呼ぶ検証器を定義する。**すべて Python 3 標準ライブラリのみで実装する**（pip 依存を作らない。どこでも動くため）。フロントマターは本体系では意図的にフラット（`key: value` と単純リスト）なので、PyYAML を使わず最小パーサで読む。これにより外部依存ゼロを達成する。

設置場所はプラグインの `scripts/`。Hook からは `${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py` で呼ぶ。Skill からは `${CLAUDE_SKILL_DIR}` 経由、または共有のため `${CLAUDE_PLUGIN_ROOT}` を使う。

### 8.1 スクリプト一覧

| スクリプト | 呼び出し元 | 入力 | 出力・効果 |
|---|---|---|---|
| `docs-linter.py` | PostToolUse Hook | stdin JSON（tool_input.file_path） | 単一ファイルのフロントマター検証（参照整合は docs-audit）。違反時 additionalContext で指摘 |
| `archive-guard.py` | PreToolUse Hook | stdin JSON（tool_input.file_path） | `/99-archive` 編集・既存 ADR 改変を deny |
| `inject-contract.py` | SessionStart Hook | なし（`/docs` を読む） | 最小契約を stdout 出力（コンテキスト注入） |
| `docs-audit.py` | コマンド/CI | リポジトリルート | 全件 dead link・陳腐化した現行文書・draft 放置・型規律違反の一覧 |
| `dep-graph.py` | change-impact Skill | 対象 ID | 依存有向グラフと波及先列挙、dead link 報告 |
| `collect-context.py` | llm-context-pack Skill | タスク ID | `llm_context` でフィルタした最小コンテキスト |
| `scaffold.py` | docs-system-init Skill | レベル指定 | 最小5ファイル+最小限の案内を非破壊で配置 |

### 8.2 共通：最小フロントマター・パーサ（stdlib のみ）

すべてのスクリプトが共有するヘルパ。`---` で囲まれた先頭ブロックを読み、`key: value`、インラインリスト `[a, b]`、ブロックリスト（`- item`）に対応する。

```python
# scripts/_frontmatter.py  （標準ライブラリのみ）
import re, sys

def parse_frontmatter(text):
    """先頭の --- ... --- を辞書に。値は文字列 / list[str]。"""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        return {}, text
    body = text[m.end():]
    meta, key = {}, None
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        if re.match(r'^\s*-\s+', raw) and key is not None:           # ブロックリスト要素
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(raw.split('-', 1)[1].strip())
            continue
        if ':' in raw:
            k, v = raw.split(':', 1)
            key, v = k.strip(), v.strip()
            if v == '':                                              # 次行がブロックリスト
                meta[key] = []
            elif v.startswith('[') and v.endswith(']'):              # インラインリスト
                meta[key] = [x.strip() for x in v[1:-1].split(',') if x.strip()]
            else:
                meta[key] = v
    return meta, body
```

### 8.3 `docs-linter.py`（中核。参照実装）

PostToolUse から呼ばれ、触れた単一ファイルの**フロントマター構文・status・型/フォルダ・id 整合のみ**を検証する（高速）。参照整合（dead link）の全件照合は行わず `docs-audit.py`（コマンド/CI）に委ねる（§7.3）。`docs/` 配下の `.md` でなければ即 exit 0。違反は `decision` を出さず `additionalContext` で Claude に返す。

```python
#!/usr/bin/env python3
# scripts/docs-linter.py  （標準ライブラリのみ）
import json, sys, os, re, datetime
from _frontmatter import parse_frontmatter

# --- 正本リファレンス（第5章）をデータとして保持 ---
TYPE_FOLDER = {  # 型コード -> 期待フォルダ（部分一致）
  "OVERVIEW":"00-overview","GLOSSARY":"00-overview","PRODUCT":"10-product",
  "REQ":"10-product","NONGOAL":"10-product","SPEC":"20-spec","DATA":"20-spec",
  "API":"20-spec","PRICING":"20-spec","ARCH":"30-architecture","CTXMAP":"30-architecture",
  "ADR":"40-decisions","CHANGE":"40-decisions","IMPACT":"40-decisions",
  "RESEARCH":"50-research","COMPET":"50-research","LEGAL":"50-research",
  "IMPL":"60-implementation","TEST":"70-test","WATCH":"70-test",
  "RUNBOOK":"80-operation","INCIDENT":"80-operation","DECIDED":"90-llm",
  "OPENQ":"90-llm","DEPREC":"90-llm","CTXPACK":"90-llm","ARCHIVE":"99-archive",
}
STATUS_GLOBAL = {"draft","proposed","current","deprecated","superseded","archived","open"}
STATUS_BY_TYPE = {"ADR":{"proposed","accepted","superseded","deprecated"}}  # 型別例外
REQUIRED = ["id","title","type","status","owner","updated","sources"]
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

def report(reason):
    # decision は出さず additionalContext で指摘のみ返す（ターンは止めず Claude が自己修正）
    print(json.dumps({"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":reason}}))
    sys.exit(0)

def main():
    data = json.load(sys.stdin)
    path = (data.get("tool_input") or {}).get("file_path","")
    if "/docs/" not in path.replace("\\","/") or not path.endswith(".md"):
        sys.exit(0)
    if "/99-archive/" in path:                 # アーカイブは検証対象外（不変）
        sys.exit(0)
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        sys.exit(0)
    meta, body = parse_frontmatter(text)
    errs = []
    # 1) 必須キー
    for k in REQUIRED:
        if k not in meta or meta[k] in ("", [], None):
            errs.append(f"必須メタデータ {k} を補ってください")
    t = meta.get("type","")
    # 2) status 統制（型別許可リスト）
    allowed = STATUS_BY_TYPE.get(t, STATUS_GLOBAL)
    if meta.get("status") and meta["status"] not in allowed:
        errs.append(f"status '{meta['status']}' は型 {t} では使えません（許可: {sorted(allowed)}）")
    # 3) 日付 ISO 8601
    for dk in ("created","updated","review_by"):
        if meta.get(dk) and not DATE_RE.match(str(meta[dk])):
            errs.append(f"{dk} は YYYY-MM-DD 形式にしてください（現在: {meta[dk]}）")
    # 4) id とファイル名の整合
    fname = os.path.basename(path)
    if meta.get("id") and not fname.startswith(meta["id"]):
        errs.append(f"id '{meta['id']}' をファイル名 '{fname}' の接頭辞に一致させてください")
    # 5) type とフォルダの整合
    if t in TYPE_FOLDER and TYPE_FOLDER[t] not in path.replace("\\","/"):
        errs.append(f"type {t} は /{TYPE_FOLDER[t]}/ に置いてください")
    # 6) llm_context 語彙
    if meta.get("llm_context") and meta["llm_context"] not in {"always","task","never"}:
        errs.append(f"llm_context は always|task|never のいずれかにしてください（現在: {meta['llm_context']}）")
    # 7) 参照整合（dead link）は全 docs の走査が要るため per-turn では行わず、
    #    docs-audit.py（コマンド/CI）に委ねる（§7.3「単一ファイルのみ・高速」の原則）
    # 8) 型規律（軽い検査）
    if t in ("RESEARCH","COMPET","LEGAL") and re.search(r'^#+\s*決定', body, re.M):
        errs.append("調査文書に『決定』を書かないでください。決定は ADR(/40-decisions) へ。")
    if errs:
        report("ドキュメント・リンタ違反:\n- " + "\n- ".join(errs))
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 8.4 `inject-contract.py`（SessionStart 最小注入。参照実装）

`/docs/90-llm` と `/00-overview` を読み、常時投入すべき**事実・要点のみ**を stdout に出す。本文全量は出さない（肥大回避）。

```python
#!/usr/bin/env python3
# scripts/inject-contract.py  （標準ライブラリのみ）
import os, sys, glob
from _frontmatter import parse_frontmatter

ROOT = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
DOCS = os.path.join(ROOT, "docs")

def emit(title, globpat, max_lines=40):
    paths = sorted(glob.glob(os.path.join(DOCS, globpat)))
    if not paths: return
    print(f"## {title}")
    for p in paths:
        meta, body = parse_frontmatter(open(p, encoding="utf-8", errors="ignore").read())
        if meta.get("status") in ("deprecated","superseded","archived") and "90-llm" not in p:
            continue
        # 箇条書き行のみ抽出（要点）。本文の散文は注入しない
        bullets = [ln for ln in body.splitlines() if ln.lstrip().startswith(("-","*","|"))]
        for ln in bullets[:max_lines]:
            print(ln)
    print()

def main():
    if not os.path.isdir(DOCS):
        sys.exit(0)
    print("<!-- 情報統治コントラクト（自動注入・最小）。現行のみ。廃案本文は含まない -->")
    emit("確定済み事実（Decided Facts）", "90-llm/*decided*.md")
    emit("非目標（Non-goals）", "10-product/*non-goal*.md")
    emit("廃案・禁止事項（事実のみ）", "90-llm/*deprecated*.md")
    emit("退行監視（戻ってはならない事項）", "70-test/*watchlist*.md")
    emit("用語（Glossary 見出し）", "00-overview/*glossary*.md", max_lines=60)
    print("詳細が要るときは該当文書を開く。/99-archive と /50-research の本文は現行ではない。")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 8.5 残りのスクリプト（仕様。実装は上記2本に準ずる）

- **`archive-guard.py`**: stdin JSON の `tool_input.file_path` を読み、`/99-archive/` を含むか、`/40-decisions/ADR-` 始まりの既存ファイルへの編集（`tool_name in {Edit, MultiEdit}` かつファイルが存在）なら、第7.1(2)節の deny JSON を出力。それ以外は exit 0。
- **`docs-audit.py`**: リポジトリ全体を走査し、(a) 全 dead link、(b) `review_by < today` の current/accepted 文書、(c) `updated` が N 日以上前の draft、(d) RESEARCH/COMPET/LEGAL に決定混入、(e) Watchlist 行に対応するテスト/監視点の欠落、(f) どこからも参照されない孤立文書、を一覧化。終了コードは件数>0 で非0（CI で落とせる）。毎ターンでなくコマンド/CI で実行。
- **`dep-graph.py`**: 全文書の `depends_on`/`impacts` から有向グラフを作り、指定 ID の上流・下流を BFS（幅優先探索）で列挙。dead link も報告。`change-impact` の影響列挙を支援。
- **`collect-context.py`**: `llm_context` メタデータでフィルタし、`always` 群（事実・要点）+ 指定タスクの `task` 文書を収集、`never` を除外して Context Pack のひな型を出力。
- **`scaffold.py`**: 既存 `docs/` と AGENTS.md/CLAUDE.md を確認し、無いものだけを作成（**非破壊**）。既定は Level 1 の最小5ファイル + 最小限の案内のみ。フル11ツリーは作らない。

---

## 9. パッケージングと配布（Plugin）

「どこでも再利用」を満たす最良の形態は **Claude Code プラグイン**である。プラグインは Skills・Hooks・スクリプト・テンプレートを一つのバージョン付き単位に束ね、`/plugin install` で配布・更新・信頼できる。プラグインは新機能を導入するのではなく、既存の能力を**一つのパッケージにまとめる**。すべての構成要素は単独でも `.claude/` に設定できるが、束ねることでチーム・複数リポジトリ間で同期する手間が消える。

### 9.1 プラグイン構成

```
context-engineering-blueprint/
├── .claude-plugin/
│   └── plugin.json                 # プラグイン定義（name/version/description）
├── hooks/
│   └── hooks.json                  # 第7章の Hook（settings.json の hooks と同形式）
├── skills/
│   ├── docs-system-init/SKILL.md
│   ├── doc-author/SKILL.md         （+ references/ templates/）
│   ├── doc-review/SKILL.md         （+ references/）
│   ├── change-impact/SKILL.md      （+ references/）
│   ├── regression-guard/SKILL.md   （+ references/）
│   └── llm-context-pack/SKILL.md   （+ references/）
├── scripts/
│   ├── _frontmatter.py
│   ├── docs-linter.py
│   ├── archive-guard.py
│   ├── inject-contract.py
│   ├── docs-audit.py
│   ├── dep-graph.py
│   ├── collect-context.py
│   └── scaffold.py
├── templates/                      # 付録Aの文書型テンプレート群
│   ├── AGENTS.md.tmpl              # 最小限の案内（付録C）
│   ├── decided-facts.md.tmpl
│   ├── regression-watchlist.md.tmpl
│   ├── adr.md.tmpl
│   └── ...（全型）
└── README.md
```

`plugin.json` の最小例:
```json
{ "name": "context-engineering-blueprint",
  "version": "0.1.0",
  "description": "LLM開発のための情報統治。文書の位置づけ・依存・現行性を Skills と Hooks で強制する。" }
```

`hooks/hooks.json` は第7章の Hook をそのまま入れる（`settings.json` の `hooks` オブジェクトと同形式）。パスは `${CLAUDE_PLUGIN_ROOT}/scripts/...` で解決する。

### 9.2 配布・有効化と、プレーン `.claude/` フォールバック

- **配布**: プラグインをマーケットプレイス（リポジトリ）として公開し、各リポジトリで `/plugin install context-engineering-blueprint@<marketplace>` で導入する。`/reload-plugins` で hooks/scripts/agents の変更を反映する。
- **適用**: プラグイン有効時、`hooks/hooks.json` の Hook が自動で効く。各リポジトリでは `docs-system-init` Skill を一度呼んで最小配置する。
- **フォールバック（プラグインを使わない場合）**: `docs-system-init` が `.claude/settings.json` に第7章 Hook を書き、`.claude/scripts/` にスクリプトを置き、`.claude/skills/` に各 Skill を置く。この場合パスは `${CLAUDE_PROJECT_DIR}/.claude/scripts/...`。
- **パス解決の使い分け**: プラグイン同梱 = `${CLAUDE_PLUGIN_ROOT}`、Skill 同梱資源 = `${CLAUDE_SKILL_DIR}`、プロジェクト設置 = `${CLAUDE_PROJECT_DIR}`。
- **スコープと上書き順**: Skill の探索は プロジェクト `.claude/skills/`（起動フォルダから親をたどりリポジトリルートまで）と 個人 `~/.claude/skills/` と プラグイン。Hook の設置場所は `~/.claude/settings.json`（全プロジェクト）/ `.claude/settings.json`（プロジェクト・コミット可）/ `.claude/settings.local.json`（gitignore）/ プラグイン `hooks/hooks.json` / Skill・agent フロントマター。

### 9.3 CLAUDE.md / AGENTS.md は最小限の案内にする

常時読まれる規約ファイルは**知識の集積にしない**。入口（`/docs/00-overview/overview.md`、Decided Facts、Non-goals、Watchlist）への**案内**に徹する。タスク固有の深さはリンク先に置く。肥大は避ける（前提3）。ひな型は付録C。

---

## 10. ビルド順序（受領する Claude への具体的指示）

以下の順で実装する。各段階は前段階の成果物に依存する。

1. **正本リファレンスをコード化する**: 第5章の表（TYPE_FOLDER / STATUS / REQUIRED / llm_context 既定）を `scripts/_frontmatter.py` と `docs-linter.py` のデータ構造として固定する。規則をここに一元化し、以降のコードに二重定義しない。
2. **スクリプトを実装する**: 第8章。まず `_frontmatter.py` → `docs-linter.py` → `inject-contract.py` → `archive-guard.py` → `scaffold.py` → `docs-audit.py` → `dep-graph.py` → `collect-context.py`。標準ライブラリのみ。`docs-linter.py` と `inject-contract.py` は本書の参照実装を出発点にする。
3. **Hook を構成する**: 第7章のコア3種を `hooks/hooks.json` に書く。任意3種はコメントで残し既定無効。
4. **Skill を実装する**: 第6章の6つ。各 `SKILL.md` は description を「押しの強い」三人称で書き、本文を500行未満に保ち、詳細を `references/` に分ける。テンプレートは `templates/`（付録A）。
5. **テンプレートと最小限の案内を用意する**: 付録A・C を `templates/` に置く。
6. **プラグインとしてパッケージ化する**: 第9.1節の構成と `plugin.json`・`hooks.json`。
7. **自己検証する**: 空のテストリポジトリで `docs-system-init` → 最小5ファイルが配置されることを確認。わざと壊した文書（status 不正・型/フォルダ不一致）を書き、PostToolUse リンタが `additionalContext` で指摘することを確認。dead link は `docs-audit.py`（コマンド/CI）が検出することを確認。`/99-archive` への編集が deny されることを確認。SessionStart で最小契約のみが注入されることを確認。
8. **README を書く**: 導入手順、Skill 一覧、Hook 一覧、`/audit` の使い方、成熟度の上げ方（付録の採用チェックリストへリンク）。

実装中に正本仕様へ疑問が出たら、コードを勝手に分岐させず第5章を更新し、両者を一致させる（柱2）。

---

## 11. Toulmin による中心主張の検証

**主張（Claim）**: 「このプラグイン（Skills + Hooks + スクリプト）を導入すれば、人間と LLM の双方が、どのリポジトリでも仕様・実装・意思決定を位置づけ付きで管理でき、変更と退行に耐えられる。」

この主張を絶対保証として扱わず、構成要素に分解する。

- **根拠（Grounds）**: 位置づけ分離（Decided Facts / Deprecated Item / Open Questions）と必須メタデータ（status/sources/updated）と依存リンク（depends_on/impacts）と退行テストを、Hook（決定論的強制）と Skill（手続き的支援）に役割分担して実装すれば、廃案復活・未決の既決化・仕様実装乖離は検出できる、という設計上の対応関係。
- **論拠（Warrant）**: LLM の典型的失敗は「情報の位置づけが構造化されていない」ことに起因する。位置づけを構造化し、Hook で機械的に強制すれば、検出可能性が上がる。
- **裏付け（Backing）**: 記録管理（ISO 15489 の真正性・信頼性・完全性・利用可能性）、要求工学（ISO/IEC/IEEE 29148 の追跡性）、ADR 実務（追記型・superseded 管理）、Claude Code の Hook/Skill 機構（決定論的制御と、段階的に開示される専門知識）、コンテキスト最小化の経験的知見（arXiv:2602.11988）。
- **限定（Qualifier）**: 「管理できる」は「予防」ではなく「**検出・早期発見**」に限る。テスト化できる退行はテストで、それ以外は人間レビューで。条件は「メタデータが更新され、Hook が有効で、運用が回ること」。
- **反証（Rebuttal）**: 運用が形骸化すれば（メタデータ未更新、Watchlist 未保守）、本体系は「管理できている感」だけを生む。CLAUDE.md/AGENTS.md を肥大させれば、LLM の性能はむしろ下がる（前提3）。仕様自体の誤り・外部依存の変化・LLM の確率的逸脱は、本体系では予防できない。Hook が過剰に発火すればエージェントが著しく遅くなる。

**結論**: 主張は「適切に運用され、常時コンテキストが最小に保たれた場合に、特定の失敗類型を検出・早期発見できる」という限定付きでのみ成立する。「100%管理できる」は成立しない。

---

## 12. Premortem（このビルドと運用が一年後に破綻するとしたら）

ある出来事がすでに起きたと想定して振り返ると、これから起きる結果の原因を正しく言い当てる力が上がる（prospective hindsight）。本ビルドが破綻した未来を想定し、原因を先回りする。

| # | 破綻シナリオ | 原因 | 対策（設計に織り込み済み） |
|---|---|---|---|
| 1 | Skill が呼ばれない | description が弱く呼ばれにくい | 三人称・「〜の依頼で必ず使う」・実使用語句の列挙（第6章）。導入後に起動率を点検し description を調整。 |
| 2 | エージェントが遅い | Hook が重く毎ターン全件走査 | per-turn は単一ファイル検証のみ。全件監査は `docs-audit`（コマンド/CI）に隔離（第7.3節）。 |
| 3 | リンタが誤検出で邪魔 | 規則が厳しすぎる | 必須は7項目に絞る。additionalContext で指摘し修正余地を残す。型規律は警告レベル（第5.3, 8.3節）。 |
| 4 | CLAUDE.md 肥大で性能低下 | 常時投入を増やした | 最小限の案内厳守。SessionStart は事実・要点のみ注入（第7.1, 9.3節、前提3）。 |
| 5 | メタデータ形骸化 | 必須が多すぎ手動更新が続かない | 必須を7項目に絞る。status/updated は LLM 代行＋人間承認。`review_by` 超過を監査が一覧化（第5.3節）。 |
| 6 | フォルダが空のまま増える | 空ツリーを先に作った | init 既定は最小5ファイル。フォルダは初使用時に遅延生成（第5.4, 6.1節）。 |
| 7 | 廃案が現行として復活 | 廃案の位置づけが文書化されず | Deprecated Item + Watchlist + SessionStart 常時投入 + PreToolUse アーカイブガード（第5.6, 7.1節）。 |
| 8 | 調査と決定が混ざる | RESEARCH に決定を書く | 型の分離。リンタが RESEARCH 内の「決定」見出しを警告（第8.3節）。 |
| 9 | 仕様と実装が乖離 | テストがない／変更フロー不遵守 | 受入・退行テスト化、`change-impact` の14ステップ、更新順序の強制（第5.6節）。文書だけでは閉じないと明示。 |
| 10 | プラグインがリポジトリ間で陳腐化 | 各人が手で `.claude/` を持つ | プラグイン配布＋`/plugin install`＋`/reload-plugins`で中央更新（第9章）。 |
| 11 | 「管理できている感」だけ生まれる | 体系はあるが運用が回らない | 第2章の7観点で「指させるか」を定期点検。これが**最大のリスク**であり、ツールでなく運用習慣で対処する。 |

---

## 13. チェックリスト

### 13.1 ビルド・チェックリスト（受領する Claude 向け）

- [ ] 第5章の表をデータ構造として一元化し、コードに二重定義していない。
- [ ] スクリプトはすべて標準ライブラリのみ（pip 依存ゼロ）。
- [ ] `docs-linter.py` が必須メタデータ・status 統制・id 整合・型/フォルダ整合・型規律を検出する（参照整合＝dead link は `docs-audit.py`）。
- [ ] PostToolUse リンタが `decision` を出さず `additionalContext` で指摘を Claude に返す。
- [ ] PreToolUse が `/99-archive` 編集と既存 ADR 改変を deny する。
- [ ] SessionStart が事実・要点のみを最小注入する（本文全量を注入しない）。
- [ ] フルリポジトリ監査は毎ターンでなくコマンド/CI に隔離されている。
- [ ] 各 SKILL.md の description が三人称・押しが強い・実使用語句を含む。
- [ ] `docs-system-init` 既定が最小5ファイル＋最小限の案内のみを非破壊で配置する。
- [ ] CLAUDE.md/AGENTS.md が最小限の案内である。
- [ ] プラグインとしてパッケージ化され `/plugin install` で配布できる。
- [ ] 自己検証（壊した文書の検出、アーカイブ編集の deny、最小注入）が通る。

### 13.2 採用チェックリスト（各リポジトリで体系を導入する人向け）

- [ ] 置き場所を一つに決めた（`/docs`）。
- [ ] `docs-system-init` で最小5ファイル＋AGENTS.md を作った。
- [ ] status 統制語彙7語を理解した。
- [ ] プラグインを有効化（または `.claude/` にフォールバック配置）した。

### 13.3 運用チェックリスト

- [ ] 新規文書に id/title/type/status/owner/updated/sources を付けた。
- [ ] `review_by` を過ぎた現行文書を点検した（`docs-audit`）。
- [ ] 調査（RESEARCH）と決定（ADR）を別ファイルにした。

### 13.4 変更チェックリスト

- [ ] Change Request を起票した。
- [ ] `depends_on`/`impacts` をたどり影響文書を列挙した（`change-impact`）。
- [ ] 更新順序（ADR→Spec→実装→テスト→LLM→廃案整理）を守った。
- [ ] 旧版を Archive へ移し `superseded_by` を付けた。

### 13.5 LLM 投入チェックリスト

- [ ] Decided Facts・Non-goals・禁止事実を常時投入した。
- [ ] 廃案の本文を渡していない（事実のみ）。
- [ ] コンテキストを最小限に保った（肥大していない）。

### 13.6 レビュー・チェックリスト

- [ ] 一文書一目的か。粒度は揃っているか。
- [ ] 未決を既決にしていないか。
- [ ] 保証できないものを保証と書いていないか。
- [ ] Regression Watchlist の監視点を確認したか。

---

## 付録A. 文書型テンプレート（`templates/` に配置）

各テンプレートは「共通フロントマター（第5.3節）＋型別本文骨格」で構成する。主要なものを示す。残りの型も同形式で作る。

### A-1. Decided Facts（DECIDED / always）
```markdown
---
id: DECIDED-001
title: 確定済み事実
type: DECIDED
status: current
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
llm_context: always
---
# 確定済み事実（Decided Facts）
<!-- 確定した方針のみ。迷い・調査・提案中は書かない。各行に決定日と根拠ADR -->
- <確定事実>（決定日 YYYY-MM-DD / 根拠 ADR-XXXX）
```

### A-2. Non-goals（NONGOAL / always）
```markdown
---
id: NONGOAL-001
title: 非目標
type: NONGOAL
status: current
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
llm_context: always
---
# 非目標（Non-goals）
<!-- やらないことと、その理由。あいまいな願望は書かない -->
- <やらないこと> ｜ 理由: <なぜやらないか>
```

### A-3. ADR（ADR / accepted・追記型）
```markdown
---
id: ADR-0001
title: <決定の主題>
type: ADR
status: accepted        # proposed / accepted / superseded / deprecated
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
depends_on: []
impacts: []
supersedes:             # 旧ADRを覆す場合のみ
llm_context: task
---
# ADR-0001: <決定の主題>
## 背景（Context）
<なぜこの決定が必要になったか。事実のみ>
## 検討した選択肢（Options）
- 案A: <利点 / 欠点>
- 案B: <利点 / 欠点>
## 決定（Decision）
<採用案と、それを選んだ根拠を一文の機構で>
## 帰結（Consequences）
<良い帰結 / 悪い帰結 / 新たに生じる制約>
```
**運用**: ADR は編集で覆さない。覆すときは新 ADR を作り、旧 ADR の `status` を `superseded` に、`superseded_by` に新 ID を記す。

### A-4. Specification（SPEC / current）
```markdown
---
id: SPEC-001
title: <仕様の主題>
type: SPEC
status: current
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
depends_on: [REQ-XXX]
impacts: []
llm_context: task
---
# SPEC-001: <仕様の主題>
## 対応する要求
- REQ-XXX
## 前提条件
## 入出力
## 正常系フロー
## 異常系フロー（エラー時挙動）
## 受入基準（Given/When/Then）
<!-- 廃案・検討経緯（ADRへ）・実装コードの写しは書かない -->
```

### A-5. Regression Watchlist（WATCH / always・要点）
```markdown
---
id: WATCH-001
title: 退行監視リスト
type: WATCH
status: current
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
llm_context: always
---
# 退行監視リスト
| id | 戻ってはならない事項 | 撤回/決定日 | 根拠 | 監視点（どこを見れば検出できるか） |
|----|--------------------|-----------|------|-----------------------------|
| RW-01 | <例: 住所をサーバー保存しない> | YYYY-MM-DD | ADR-XXXX | DBスキーマ、分析要件、データフロー図 |
```

### A-6. Research Note（RESEARCH / never）
```markdown
---
id: RESEARCH-001
title: <調査の主題>
type: RESEARCH
status: draft
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: [<URL>]
llm_context: never
---
# RESEARCH-001: <調査の主題>
## 調査目的
## 出所と取得日
## 事実・比較
## 結論（暫定）
<!-- 決定は書かない。決定はADRへ。昇格時は sources から参照させる -->
```

### A-7. LLM Context Pack（CTXPACK / task）
```markdown
---
id: CTXPACK-001
title: <タスク名> 用コンテキスト
type: CTXPACK
status: current
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
llm_context: task
---
# LLM Context Pack（<タスク名>）
## 現行の確定方針（Decided Facts 抜粋）
## 非目標
## 禁止・廃案事項（本文は渡さない。事実のみ）
## 未決事項（決定しないこと）
## 用語
## このタスクの対象仕様
- SPEC-XXX（current）
## 出力形式・レビュー観点
- 一文一義、抽象語禁止、推量と断定を分ける
```

（他の型 — PRODUCT, REQ, DATA, API, PRICING, ARCH, CTXMAP, CHANGE, IMPACT, COMPET, LEGAL, IMPL, TEST, RUNBOOK, INCIDENT, OPENQ, DEPREC, ARCHIVE, OVERVIEW, GLOSSARY — も同じ「共通フロントマター＋型別骨格」で作る。各型の「書く/書かない」は第5.1節表に従う。）

---

## 付録B. Open Questions / Deprecated Item テンプレート

### B-1. Open Questions（OPENQ / open / always）
```markdown
---
id: OPENQ-001
title: 未決事項
type: OPENQ
status: open
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
llm_context: always
---
# 未決事項（Open Questions）
<!-- 決まっていないこと。断定で書かない。LLMは未決を決定せず人間に返す -->
- 問い: <...> ｜ 選択肢: <A / B> ｜ 期限: YYYY-MM-DD ｜ 担当: <...> ｜ 暫定の傾き: <...>
```

### B-2. Deprecated Item（DEPREC / deprecated / always・事実のみ）
```markdown
---
id: DEPREC-001
title: 廃案事項
type: DEPREC
status: deprecated
owner: <個人名>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
sources: []
superseded_by:
llm_context: always
---
# 廃案事項（Deprecated Item）
<!-- 廃案にした事項の事実のみ。本文（廃案の中身）は書かない -->
- 廃案にした事項: <...> ｜ 撤回日: YYYY-MM-DD ｜ 後継: <現行のリンク or なし> ｜ 再評価条件: <別市場/別フェーズで有効になる条件 or なし>
```

---

## 付録C. 最小限の案内ひな型（`AGENTS.md` / `CLAUDE.md`）

知識を書かない。入口へのリンクに徹する。肥大は避ける（前提3）。

```markdown
# AGENTS.md（最小限の案内）

このリポジトリの情報統治は `/docs` にある。詳細は集積せず、ここでは入口だけを示す。

## まず読む（常時）
- 全体像: `docs/00-overview/overview.md`
- 確定済み事実: `docs/90-llm/decided-facts.md`
- 非目標（やらないこと）: `docs/10-product/non-goals.md`
- 戻ってはならない事項: `docs/70-test/regression-watchlist.md`
- 用語: `docs/00-overview/glossary.md`

## 規約
- 現行仕様は `docs/20-spec/`。決定の経緯は `docs/40-decisions/`（ADRは追記型）。
- `docs/50-research/` と `docs/99-archive/` の本文は現行ではない。現行として扱わない。
- 廃案・未決を勝手に決定しない。未決は人間に返す。
- 構造変更は提案のみ。実行は人間承認。
- 文書を作る・直すときは `doc-author`、変更影響は `change-impact`、退行確認は `regression-guard` を使う。

タスク固有の深さは上記リンク先にある。この規約ファイルには知識を集積しない。
```

`CLAUDE.md` は同内容にするか、`AGENTS.md` を指す一行（`See AGENTS.md`）にする。

---

## 付録D. 出典・根拠

**前身（一次入力）**
- 本書は、初版「`LLM開発情報管理体系.md`」（概念枠組み版。24テンプレート、6観点成熟度、状態分離）と `compass_artifact`（実務に即した精密版。7語統制語彙、リッチなメタデータ、14ステップ変更フロー、ETH 研究の限界提示）を統合したもの。前者の網羅性に後者の厳密さを採り入れた。

**Claude Code 公式（実装機構の根拠。執筆時点で確認）**
- Hooks reference — https://code.claude.com/docs/en/hooks （イベント一覧、3つの発火点（Pre/Post/Session）、マッチャ規則、終了コード2、hookSpecificOutput、additionalContext、設置場所）
- Extend Claude with skills — https://code.claude.com/docs/en/skills （SKILL.md 構成、`.claude/skills/` 配置、`.claude-plugin/plugin.json` でプラグイン化、`${CLAUDE_SKILL_DIR}`、live reload）
- Plugins（Skills/Hooks/MCP のパッケージ化と配布、`hooks/hooks.json`、`/plugin install`）

**経験的知見・標準（裏付け）**
- ETH Zürich & LogicStar.ai, "Evaluating AGENTS.md", arXiv:2602.11988（2026）— コンテキストファイルの肥大は成功率を下げコストを増やす。常時投入は最小・非自明に絞る。
- Gary Klein, "Performing a Project Premortem", HBR（2007）／Mitchell・Russo・Pennington（1989）— prospective hindsight。
- 記録管理 ISO 15489（真正性・信頼性・完全性・利用可能性）、要求工学 ISO/IEC/IEEE 29148（追跡性）、アーキテクチャ記述 ISO/IEC/IEEE 42010、ADR（Michael Nygard, 2011; adr.github.io）、Diátaxis（Daniele Procida）、DDD Ubiquitous Language / Context Map、C4 モデル。
- 日本語規範: JTCA『日本語スタイルガイド』（簡潔・明快・誤解されない）。論理: 波頭亮『思考・論理・分析』。（付録Eの規範の出典）

**注記**: 本設計書の経験的数値（ETH 研究の成功率・コスト変化など）はアップロード文書と一次資料の記述に基づく。保証の限界は第1.3節のとおりで、「100%保証」は主張しない。

---

## 付録E. 日本語・論理チェック規範（全文）

`doc-review`（第6.3節）が用いる、日本語と論理のチェック規範を全文収録する。出典は、日本語＝JTCA『日本語スタイルガイド』（簡潔・明快・誤解されない）、論理＝波頭亮『思考・論理・分析』。「日本語」節のみを適用するチェックを `jp-style-check`、論理を含む全体を `logic-jp-check` と呼ぶ。本文・LLM 出力の双方に適用し、引っかかった点だけを出力する（問題なしは書かない＝肥大を避ける）。なお、LLM 空句・過剰保証（「100%」など）・推量と断定の区別は §5.7 が担い、付録Eは明快さ（簡潔・カルクなど）と論理を担う（補完関係）。

正しい結論 = ファクト × ロジック。それを誤解なく日本語に載せる。前者を波頭亮『思考・論理・分析』、後者を JTCA『日本語スタイルガイド』（簡潔・明快・誤解されない）で点検する。

### E-1. 進め方

1. 対象を論理面と日本語面で点検する。下のチェックは内部の視点であり、全項目は出力しない。
2. 出力は引っかかった点だけを挙げる。問題なしの項目は書かない（肥大を避ける）。
3. 各指摘に直し方を一言添える。必要ならリライト案を出す。

### E-2. 論理（波頭『思考・論理・分析』）

A 主張と根拠
- 主張と根拠が別々の命題として立っているか。単語だけ、主張だけは論理にならない。
- 根拠と主張は意味でつながるか。無関係な二つ（乖離命題）を並べていないか。

B 推論の型
- 演繹なら、置いた大前提は普遍的に真か。個人の経験・好み・「べき論」を普遍の前提にしていないか。
- 帰納なら、事例数と偏りは足りるか。外れ値を切り捨てていないか。一般化が飛びすぎていないか。

C ファクト
- 前提の各命題は現実と合うか。形式が妥当（valid）でも、前提が偽なら結論は偽で、真（truth）ではない。現実に正しいことだけが正しい。

D 分け方（比較・要素分解をするとき）
- 比べる対象の抽象度はそろうか（ディメンジョン）。
- 切り口＝分類基準（クライテリア）は目的に合い、示されているか。
- モレとダブりはないか（MECE）。

E 因果（原因を述べるとき）
- 相関を因果と取り違えていないか。共通原因（第三ファクター）はないか。
- 直接の原因（近因）か。逆向き・相互の因果ではないか。その因果は十分に強いか。

F 深さと自覚
- 「なぜそうなるか（Why so?）」を一段で止めず詰めたか。
- 結論を先に決めて都合よく解釈していないか（バイアスの自覚）。

### E-3. 日本語（JTCA『日本語スタイルガイド』）

各チェックは「美しいか」でなく「この欠陥があるか」を見る欠陥検出器。点数化しない（美・滋味・品格は測れない。品質を数値で出すならA層の欠陥密度だけ）。最大の敵は擬陽性なので、まず文体を判定する——文学・修辞・カジュアルでは反復強調・意図的な文体切替・曖昧・表記の遊びが正当で、その場合は指摘しない。各項目末の「除外」はその上の個別の歯止め。出力は A=反証可能な欠陥→〔指摘〕／B=数えられる癖（感覚系）は確度が低い→〔助言〕で分ける。

解釈の制御（明快さ。ここが主役）
- 一文一義：係り受けが2通り以上に取れるか。一文を短くする。除外：長い＝曖昧ではない。文脈で一意に決まる曖昧さは叩かない。（一文一義は「情報を一つ」でなく「解釈を一つ」の意。）
- 主述対応：主語と述語がねじれていないか。除外：日本語は主語省略が自然——省いて一意なら欠陥でない（主格の非明示はむしろ名文）。
- 簡潔：「することができる」→「できる」、「初期化を行う」→「初期化する」（サ変名詞＋を行う）。不要な「〜的／〜性／〜化／〜上」、過剰な受動態・二重否定・名詞化、情報量ゼロの決まり文句（「〜と言っても過言ではない」など）、外しても意味が変わらない修飾を削る。除外：定着語（可能性・具体的・重要性）と必要な受身（被害・自発・尊敬）、機能している比喩・反復は残す。
- カルク（訳語臭の中核）：英語の語・比喩・構文をなぞっていないか。判定は逆翻訳テル——怪しい箇所を英語に戻し、英語の慣用句・固定表現・有標な構文にそのまま戻って、その形のまま日本語になっていればカルク（例：同じページにいる→認識が揃う、テーブルの上にある→検討中、針を動かす→効果を出す）。ただし、単に文法的な普通の文に戻るだけ（「私は学生です」→"I am a student"）はカルクではない——ここを混同すると自然な日本語まで叩く（擬陽性が最大の敵）。直すときは英語を捨て、日本語で選び直す。
  - ルールの盲点＝一語訳：単語は慣用句でないので逆翻訳テルに掛かりにくい。status→「位置づけ・区分」、authority→「拠りどころ」、native→「標準で・組み込みで」。辞書の一番目を疑う。
  - 除外（擬陽性回避）：定着した借用語（データ・リスク・ストレスなど）と、普通の否定文（「これは問題ではない」）はカルクではない。
  シードは「ルールが取りこぼす型」だけ載せる（現状は一語訳のみ）。型が増えたと感じたら、シードを足さずルールの一文を研ぐ。別ファイルは作らない。
- 明快：専門語・略語は初出で定義する。体言止め・名詞化で「誰が何をするか」を曖昧にしない。除外：対象読者が知る語は定義不要。一意な体言止めは可。
- 具体：抽象語を具体語・数値・固有名に置く。曖昧な指示語を減らす。除外：一般原則・定義は抽象でよい。具体化は「曖昧で動けない」時だけ。

一貫性（一物一名：同じものは同じ語・表記・格で書く。混ぜると読者は別物だと思う＝誤解の主因）
- 用語の統一：同じ概念をその都度ちがう語で言い換えていないか（始める／開始する／スタート、使う／利用／活用 を混ぜない）。逆に、ちがう概念を同じ語で呼んでいないか。除外：(a) 本物の曖昧・目立つ単調がある時の言い換えは可（代名詞か同語反復で済むなら優先）、(b) 固定するのは鍵語だけ——助詞・接続・動詞まで一律に縛らない。真因は語でなく情報の重複——語の反復は罰しない（一物一名はむしろ要求）。消すのは重複した情報で、一度言って先へ進む。
- 表記：同一語で漢字と仮名が混在していないか（出来る／できる）。補助動詞・形式名詞は開く（〜という事→ということ）。係り受けを切る読点の欠落。除外：統一されていれば漢字でも仮名でもよい。読点の打ちすぎも欠陥。
- 語格：敬体（です・ます）と常体（だ・である）の混在、文体に合わない俗語、ら抜き・い抜きの崩れ。除外：くだけた文体・話し言葉で統一されていれば俗語もら抜きも可。意図的な切替（引用・強調）は可。

感覚（欠陥のみ＝B層・助言扱い。音読の美・滋味の有無は判定しない＝LLMは測れないので褒めない）
- リズム（数えられる癖だけ）：同一助詞の3連（のの／がが／を…を…を）、文末の単調な反復（だ。だ。だ。）、句点なしの長文、漢語の過密。

### E-4. 出力形式

````
## 論理
- 〔型 A–F〕指摘 → 直し方
（なければ：問題なし）

## 日本語
- 〔指摘〕〔チェック名〕欠陥 → 直し（A層：一文一義・主述・簡潔・カルク・明快・具体・用語統一・表記・語格）
- 〔助言〕〔リズム〕癖 → 直し（B層：確度低・任意）
（なければ：問題なし。文体が文学・カジュアルなら適用除外した旨を一言）

## リライト案
（短ければ全文、長ければ該当箇所のみ。求めがなければ省略可）
````

本規範自身もこの基準で書く（当然、カルクも表記ゆれも入れない）。

<!-- END OF DESIGN DOCUMENT -->




