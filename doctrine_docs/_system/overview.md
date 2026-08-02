---
id: OVERVIEW-001
title: 現行文書の一覧
type: OVERVIEW
domain: _system
status: current
owner: render-projection
updated: 2026-08-02
llm_context: always
sources: []
---

描画される。手で編集しない。

# Overview

| id | type | domain | title |
|---|---|---|---|
| GLOSSARY-001 | GLOSSARY | _system | 用語辞書の正本 |
| DECIDED-001 | DECIDED | _system | 横断の確定方針（12事実） |
| NONGOAL-001 | NONGOAL | _system | 横断のやらないこと（17項） |
| WATCH-001 | WATCH | _system | 横断の退行監視（10項） |
| ICD-005 | ICD | audit | audit のインターフェース（全件監査の境界） |
| REQ-008 | REQ | audit | 最小性の監査（過剰と不足の両側を全件検出） |
| SPEC-011 | SPEC | audit | 全件監査の検査群・要約スキーマ・決定性 |
| ADR-008 | ADR | audit | 孤児を三条件の連言で定義する |
| ADR-020 | ADR | audit | テスト不能記述の判定は監査でなく doc-review が担う |
| ADR-021 | ADR | audit | 体系外 .md は分類の記録と突き合わせ、未分類だけを監査が挙げる |
| ADR-034 | ADR | audit | 移行の台帳は分類の記録から導出し、二重の台帳を持たない |
| ADR-039 | ADR | audit | EXT の hash 検査を実装し、hash 指定を沈黙で素通りさせない |
| ADR-056 | ADR | audit | 追跡の検査は、仕様が指紋を記録したときだけ効く（黙って始まり、黙って終わる） |
| ADR-069 | ADR | audit | 監査の検査群を枠と検査モジュールへ分割する — 方針と、分割で変えないものの凍結 |
| ADR-073 | ADR | audit | 体系外の解釈文書はビューと定め、刻印で参照時点を義務づける |
| CHANGE-004 | CHANGE | audit | 体系外の解釈文書をビューと定め、刻印で古びを見えるようにする |
| IMPACT-004 | IMPACT | audit | ビューと刻印 — 影響の列挙 |
| IMPL-011 | IMPL | audit | docs-audit.py の実装メモ |
| IMPL-018 | IMPL | audit | _intake.py（分類の記録の共有コア）の実装メモ |
| TEST-011 | TEST | audit | 監査の検査群テスト計画 |
| ICD-007 | ICD | authoring | authoring のインターフェース（作成・初期化・支援） |
| REQ-011 | REQ | authoring | 型付き文書を正しい場所と様式で作り初期化は非破壊・最小に保つ |
| REQ-012 | REQ | authoring | 判断の層（技能と候補語抽出）が決定論を補い保証限界を明示する |
| REQ-015 | REQ | authoring | 会話知識の捕捉（セッションの決定は消える前にディスクへ） |
| SPEC-015 | SPEC | authoring | scaffold（_system 非破壊シード） |
| SPEC-016 | SPEC | authoring | skills（7技能を一仕様で） |
| SPEC-017 | SPEC | authoring | templates（20型＋icd-index） |
| SPEC-018 | SPEC | authoring | term-extract（c-TF-IDF 候補語抽出） |
| SPEC-022 | SPEC | authoring | 会話知識の捕捉（終端の確認・圧縮前の退避・次セッションの選別） |
| ADR-010 | ADR | authoring | 作成・初期化の設計判断（7技能固定・遅延生成・テンプレが語彙符号化） |
| ADR-029 | ADR | authoring | CLAUDE.md と AGENTS.md は投影ではなく案内と定める |
| ADR-051 | ADR | authoring | 変更フローの段数は、規模ではなく決定を含むか否かで分ける |
| ADR-077 | ADR | authoring | 圧縮前の促しは届かない。退避の合図を圧縮後の注入へ移す |
| IMPL-015 | IMPL | authoring | scaffold/term-extract の実装注記 |
| IMPL-016 | IMPL | authoring | skills/templates の実装注記 |
| IMPL-020 | IMPL | authoring | capture-nudge.py / precompact-dump.py（捕捉）の実装メモ |
| TEST-015 | TEST | authoring | scaffold の検証 |
| TEST-016 | TEST | authoring | skills の検証 |
| TEST-017 | TEST | authoring | templates の検証 |
| TEST-018 | TEST | authoring | term-extract の検証 |
| TEST-022 | TEST | authoring | 会話知識の捕捉の受入 |
| ICD-006 | ICD | context | context のインターフェース（注入・パック・投影描画の契約） |
| REQ-009 | REQ | context | 見つけやすさ（投影を正本から決定論で描画） |
| REQ-010 | REQ | context | LLM適合（常時投入を最小に・never群を渡さない） |
| SPEC-012 | SPEC | context | SessionStart 最小契約の注入 |
| SPEC-013 | SPEC | context | タスク別最小被覆パック |
| SPEC-014 | SPEC | context | 投影の決定論描画 |
| ADR-009 | ADR | context | 注入とパックで二つの別上限を持つ（C10） |
| ADR-014 | ADR | context | DECIDED へ写すのは横断の確定事実だけとする |
| ADR-016 | ADR | context | 投影を正本から描画し直せる派生表示に限り、刊行物は投影一覧に含めない |
| ADR-037 | ADR | context | 監査要約キャッシュはプロジェクトスコープを先に読み、旧プラグインroot配置は後方互換のフォールバックに限る |
| ADR-040 | ADR | context | 注入境界のフィールドをサニタイズし、引用データと指示を分ける |
| ADR-043 | ADR | context | SessionStart 契約は確定事実・非目標・退行監視の要点行を運ぶ |
| ADR-053 | ADR | context | 監査要約の読み取りを一箇所に正本化し、木の世代をまたいだ要約は捨てる |
| IMPL-012 | IMPL | context | `inject-contract.py` の実装メモ |
| IMPL-013 | IMPL | context | `collect-context.py` の実装メモ |
| IMPL-014 | IMPL | context | `render-projection.py` の実装メモ |
| TEST-012 | TEST | context | inject-contract のテスト計画 |
| TEST-013 | TEST | context | collect-context のテスト計画 |
| TEST-014 | TEST | context | render-projection のテスト計画 |
| ICD-002 | ICD | graph | graph のインターフェース（依存グラフ問い合わせ契約） |
| REQ-002 | REQ | graph | 追跡性（要求→仕様→実装→テスト→決定をたどる） |
| REQ-003 | REQ | graph | 変更耐性（影響集合を依存から列挙する） |
| SPEC-006 | SPEC | graph | 依存グラフの契約（forward/reverse/classify/reverse-orphans） |
| SPEC-026 | SPEC | graph | コード注釈の書式（対の印・範囲の指紋・走査の対象） |
| ADR-006 | ADR | graph | cross_domain_violation は depends_on 端のみに付ける |
| ADR-038 | ADR | graph | 依存の循環を監査が検出する（自己依存と多頂点循環） |
| ADR-045 | ADR | graph | 本文の要求タグは自己適用の約束であり、追跡の正路は depends_on の REQ である |
| ADR-048 | ADR | graph | コードと仕様の双方向トレースは、条件を満たす段階拡張として採る |
| ADR-054 | ADR | graph | 統治対象に「注釈が囲むコードの範囲」を加え、言語ごとに手段を分けない |
| ADR-055 | ADR | graph | トレース索引はファイルに置かず毎回導出し、記録するのは人の確認だけとする |
| ADR-058 | ADR | graph | 走査は勘定を返し、触れた対象を必ず分類する（保存則） |
| ADR-059 | ADR | graph | 印に見えるが読めない行を疑いとして挙げる（打ったつもりの無音を塞ぐ） |
| ADR-060 | ADR | graph | 走査の門を「節の有無」に揃え、検査の挙動を正本の列挙で添字づけた試験が凍結する |
| ADR-061 | ADR | graph | 仕様はコードとの関係を宣言できる — 明示の「対応なし」と、宣言と実態の矛盾の検査 |
| ADR-063 | ADR | graph | 印の無いコードを編集したとき、セッションに一度だけ紐づけを促す |
| ADR-065 | ADR | graph | 紐づけの整理をキャンペーンで駆動し、進捗の停滞を名指しする |
| ADR-067 | ADR | graph | ファイルは統治外の意思を自分の中に宣言できる — exempt の印と勘定の第四項 |
| ADR-072 | ADR | graph | 悉皆トレースモード — 「未分類」を残高にする opt-in |
| ADR-081 | ADR | graph | 検証は証拠の提示である。証跡の形だけを採り、ハザード層と過程適合は採らない |
| CHANGE-003 | CHANGE | graph | 悉皆トレース — 印なしゼロを選べる体系にする |
| IMPACT-003 | IMPACT | graph | 悉皆トレース — 影響の列挙 |
| IMPL-006 | IMPL | graph | `_depgraph.py`＋`dep-graph.py` の実装メモ |
| IMPL-021 | IMPL | graph | `_tracescan.py`（コード注釈の走査）の実装メモ |
| TEST-006 | TEST | graph | 依存グラフのテスト計画 |
| TEST-026 | TEST | graph | コード注釈の書式の検証 |
| ICD-003 | ICD | guard | guard のインターフェース（三ガードの公開境界） |
| REQ-004 | REQ | guard | 境界明瞭（越境依存は相手ICD宛のみ許す） |
| SPEC-003 | SPEC | guard | 三ガードの判定規則（不変・ICD依存・削除安全） |
| ADR-003 | ADR | guard | C13 の分岐（dangling 許容／分類不能 拒否） |
| ADR-004 | ADR | guard | PostToolUse の事前状態を raw 全文で復元する |
| ADR-036 | ADR | guard | 統治木の無いプロジェクトでは二・三ガードとナッジ・退避を発火させない |
| ADR-044 | ADR | guard | 不変の ADR に誤りを見つけたときの正規の直し方 |
| ADR-076 | ADR | guard | ICD 依存の境界は Edit・MultiEdit でも書き込む前に判ずる |
| IMPL-003 | IMPL | guard | `policy-guard.py` の実装メモ |
| TEST-003 | TEST | guard | 三ガードの受入試験 |
| ICD-004 | ICD | lint | lint のインターフェース（リンタと用語チェッカーの公開契約） |
| REQ-005 | REQ | lint | 現行性（型↔status・id↔ファイル名・型↔置き場所を機械点検） |
| REQ-006 | REQ | lint | 用語統一（未承認語・禁止同義語を弾く） |
| REQ-007 | REQ | lint | 明快な日本語（カルクを照合する） |
| SPEC-007 | SPEC | lint | 単一文書リンタの全 PostToolUse 点検 |
| SPEC-008 | SPEC | lint | 用語チェッカーの照合規則 |
| SPEC-023 | SPEC | lint | 整合点検（linter と audit の食い違いの回帰ガード）と横断リマインダ |
| SPEC-024 | SPEC | lint | review-nudge（手編集への doc-review の促しと捕捉の印） |
| ADR-005 | ADR | lint | 承認辞書を体系内で一度だけ符号化する |
| ADR-007 | ADR | lint | 禁止同義語セルの末尾注記の扱い |
| ADR-012 | ADR | lint | 構造語彙を正本で定義済みと認め、doc-reviewを著述時の閉じた輪にする |
| ADR-018 | ADR | lint | 固有名と登録承認語を辞書から動的に覆い、照合から外す |
| ADR-023 | ADR | lint | 用語チェッカーは never 文脈の RESEARCH・ARCHIVE を点検しない |
| ADR-024 | ADR | lint | リンタは登録済み非文書と統治木外に schema 強制をしない（用語助言のみ） |
| ADR-082 | ADR | lint | 門は語の途中で切れる一致で咎めない。雛形の語彙と語を変える接尾を除く |
| ADR-083 | ADR | lint | 助言の行番号はファイルの行番号とし、換算を共有コアの出口に置く |
| IMPL-007 | IMPL | lint | `docs-linter.py` の実装メモ |
| IMPL-008 | IMPL | lint | `_termcheck.py` の実装メモ |
| IMPL-009 | IMPL | lint | `term-check.py` の実装メモ |
| TEST-007 | TEST | lint | リンタのテスト計画 |
| TEST-008 | TEST | lint | 用語チェッカーのテスト計画 |
| TEST-023 | TEST | lint | 整合点検と横断リマインダの受入 |
| TEST-024 | TEST | lint | review-nudge の受入 |
| ICD-001 | ICD | model | model のインターフェース（登録簿と解析の公開契約） |
| REQ-001 | REQ | model | 構造規則とメタデータ様式を単一の正本として定義する |
| SPEC-001 | SPEC | model | 登録簿の契約（registry contract） |
| SPEC-002 | SPEC | model | フロントマター解析の契約 |
| DATA-001 | DATA | model | 登録簿とフロントマターのスキーマ |
| ADR-001 | ADR | model | 構造規則の単一正本化（C2） |
| ADR-002 | ADR | model | フロントマター解析の3要素戻り値（C1） |
| ADR-013 | ADR | model | 手順を運ぶ型 PROC を一つだけ新設する |
| ADR-015 | ADR | model | 統治の対象を知識と決定の層に限る |
| ADR-025 | ADR | model | 型ごとの既定点検周期で全現行文書に実効期限を張る |
| ADR-026 | ADR | model | 統治木の外への依存を EXT 型のアンカーとして統治する |
| ADR-027 | ADR | model | status archived の文書は型に依らず倉庫に置き、状態でも不変にする |
| ADR-033 | ADR | model | 必須キーはちょうど 8 個とする(追認) |
| ADR-035 | ADR | model | ハーネスのメモリは環境と個人の事実に限り、影の正本化を見張る |
| ADR-049 | ADR | model | 重複 id の採用規則を登録簿に一本化し、先勝ちに統一する |
| ADR-057 | ADR | model | 統治はリポジトリ一つの内側に閉じ、組織を横断する統治は引き受けない |
| ADR-064 | ADR | model | 三つの保証限界（サブエージェント注入・id の改名・採番の衝突）を非目標として明文化する |
| IMPL-001 | IMPL | model | `_registry.py` の実装メモ |
| IMPL-002 | IMPL | model | `_frontmatter.py` の実装メモ |
| TEST-001 | TEST | model | 登録簿契約のテスト計画 |
| TEST-002 | TEST | model | フロントマター解析契約のテスト計画 |
| EXT-003 | EXT | model | 上位設計書（spec/doctrine.ja.md, DOCTRINE-001）への依存 |
| ICD-008 | ICD | packaging | packaging のインターフェース（配布物の形・Hook配線・段差） |
| REQ-013 | REQ | packaging | 保証限界の明示（各成果物が予防・検出・委ねるを書く） |
| REQ-014 | REQ | packaging | 統治の生存性（統治自身の死活が可視で、沈黙する故障を禁じる） |
| SPEC-019 | SPEC | packaging | Hook配線（7イベント／matcher／解決／縮小構成／スナップショット） |
| SPEC-020 | SPEC | packaging | パッケージ配布（plugin.json／install／.claude フォールバック／標準ライブラリ） |
| SPEC-021 | SPEC | packaging | 統治ハートビート（監査の鮮度・定例の期限・外部アンカーの存在） |
| SPEC-025 | SPEC | packaging | 被覆マトリクス（統治要求×発火経路×証跡） |
| SPEC-027 | SPEC | packaging | リリース整合の門（release-check — 版の整合と記録の義務） |
| SPEC-028 | SPEC | packaging | 試験走行の証跡 |
| ADR-011 | ADR | packaging | 段階導入とBash matcherの拒否限定 |
| ADR-019 | ADR | packaging | 段差は .docs-level をスクリプト自身が読んで自主停止で実現する |
| ADR-022 | ADR | packaging | 統治木の既定名を doctrine_docs にし、素の docs は他所の土地として触れない |
| ADR-028 | ADR | packaging | Hook を 7 イベントに広げ、生存性と捕捉を発火面に載せる |
| ADR-030 | ADR | packaging | 既定 Level 2 を追認し、生存性と捕捉は段差に依らず動くと定める |
| ADR-031 | ADR | packaging | 全スクリプトは標準ライブラリだけで動く(追認) |
| ADR-041 | ADR | packaging | 導入直後を警告で始めない（状態の種蒔き・Level 昇格・初日の中立案内） |
| ADR-042 | ADR | packaging | 監査要約のスキーマは全読者が照合する・状態ファイルの書式は前方寛容とする |
| ADR-046 | ADR | packaging | 既定 Level 2 では全件検査を CI に委ね、初回監査前は警告でなく案内を出す |
| ADR-047 | ADR | packaging | 開発方法論（TDD・DDD・OOP の採用範囲）と性能の上限・導入先への無影響保証 |
| ADR-050 | ADR | packaging | ガードが拒否できる状態かは検出しないと明記し、機能カナリアを次の版に分ける |
| ADR-052 | ADR | packaging | 編集画面の表示層は統治判断を持たず、索引が無ければ黙る |
| ADR-062 | ADR | packaging | フックは発火の印を残し、対の食い違いから拒否経路の欠落を疑う |
| ADR-066 | ADR | packaging | 体系は段階と版を自己認知する — 版の切替の検出と Level 昇格の一度きりの案内 |
| ADR-068 | ADR | packaging | 開発方法論の機械化残差 — コード層の検算三点と開発規範の正本化 |
| ADR-070 | ADR | packaging | 導入済みの複製の遅れを鼓動が検める — 正本の版との照合 |
| ADR-071 | ADR | packaging | リリースの整合を CI の門で検める — 変更履歴の書き忘れの構造的な防止 |
| ADR-074 | ADR | packaging | 不具合の報告は「検出は機械・送信は人」の二層に分ける |
| ADR-075 | ADR | packaging | フック境界は沈黙して開かない — 読み手・書き出し・経路解決・配布の四点を実行環境に対して堅くする |
| ADR-078 | ADR | packaging | Hook 事象の集合を数で凍らせず、能力で検める |
| ADR-079 | ADR | packaging | サブエージェントへ注入しない理由を「届かない」から「呼び出し側が組む」へ置き換える |
| ADR-080 | ADR | packaging | Hook 設定は固定されない。settings 由来は live reload される前提へ置き換える |
| ADR-084 | ADR | packaging | 被覆の各行は実効を示す試験を名指す。示せないなら未証と明示する |
| ADR-085 | ADR | packaging | 試験走行は判定の依り所を刷る。証跡は保存せず、走らせた場が持つ |
| CHANGE-001 | CHANGE | packaging | 導入済みプラグインの版の遅れを生存性として照合する |
| CHANGE-002 | CHANGE | packaging | リリースの整合を CI の門で検める — 変更履歴の書き忘れを止める |
| CHANGE-005 | CHANGE | packaging | 不具合の兆候を記録し、承認を経た issue 報告を促す |
| CHANGE-006 | CHANGE | packaging | フック境界と実行環境の堅牢化 — 何を変えたか |
| IMPACT-001 | IMPACT | packaging | 版の遅れの照合 — 影響の列挙 |
| IMPACT-002 | IMPACT | packaging | リリース整合の門 — 影響の列挙 |
| IMPACT-005 | IMPACT | packaging | 不具合の記録と報告 — 影響の列挙 |
| IMPACT-006 | IMPACT | packaging | フック境界と実行環境の堅牢化 — 影響の列挙 |
| IMPL-017 | IMPL | packaging | パッケージ・Hook配線の実装注記 |
| IMPL-019 | IMPL | packaging | gov-heartbeat.py（統治ハートビート）の実装メモ |
| PROC-001 | PROC | packaging | 開発規範 — 方法論の採用範囲と、機械の検算・人の査読の分担 |
| TEST-019 | TEST | packaging | Hook配線・e2e連鎖の受入 |
| TEST-020 | TEST | packaging | 配布・標準ライブラリの受入 |
| TEST-021 | TEST | packaging | 統治ハートビートと死活警告の受入 |
| TEST-025 | TEST | packaging | 被覆マトリクスの受入 |
| TEST-027 | TEST | packaging | リリース整合の門の受入 |
| TEST-028 | TEST | packaging | 試験走行の証跡の受入 |
| EXT-001 | EXT | packaging | Claude Code の Hook 仕様とツール名への依存 |
| EXT-002 | EXT | packaging | 自己適用の設定（.claude/settings.json のマーケットプレイス登録）への依存 |
| EXT-004 | EXT | packaging | 継続的結合の定義（.github/workflows/checks.yml）への依存 |
