---
id: RESEARCH-003
title: 紐づけ体系の先行事例が実運用で残した未解決問題（4系統の一次資料調査）
type: RESEARCH
domain: graph
status: draft
owner: doctrine-maintainers
created: 2026-07-27
updated: 2026-07-27
sources: [https://github.com/itsallcode/openfasttrace/issues/204, https://github.com/doorstop-dev/doorstop/issues/84, https://github.com/strictdoc-project/strictdoc/issues/1360, https://github.com/useblocks/sphinx-needs/issues/685, https://github.com/github/spec-kit/issues/620, https://github.com/Fission-AI/OpenSpec/issues/1139, https://github.com/anthropics/claude-code/issues/19471, https://swimm.io/blog/how-does-swimm-s-auto-sync-feature-work, https://github.com/apiaryio/dredd, https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.1?topic=objects-clearing-suspect-links, https://link.springer.com/article/10.1007/s10664-014-9314-z, https://link.springer.com/article/10.1007/s00766-023-00408-9]
llm_context: never
---

# 紐づけ体系の先行事例が実運用で残した未解決問題（4系統の一次資料調査）

## この調査の位置づけ

コードと仕様の双方向トレース（SPEC-026）と統治の生存性（[R11]）の設計を検める材料として、同種の紐づけを試みた先行の道具が実運用で残した問題を、4系統の一次資料（GitHub の issue・公式文書・実証研究）から集めた。**結論を出すための手続きではない。** 本文書は調査であって決定ではない（`llm_context: never`。決定は ADR へ、確定事実は DECIDED へ）。出所の無い主張は書いていない。issue の open/closed は 2026-07-27 時点。

## 1. 系統別の要点

### 1.1 要求トレーサビリティの OSS（Doorstop・StrictDoc・OpenFastTrace・Sphinx-Needs）

- **Doorstop** は親項目の内容ハッシュ（stamp）で suspect link（疑義リンク）を検出する。指紋の対象外の属性を編集しても疑義にならない偽陰性（doorstop#337）と、作成直後のリンクが即座に疑義になる雑音（doorstop#173）の両側で苦しみ、検証の実行自体が印を消した偽陰性の不具合もあった（doorstop#178）。連番 id はブランチ並行で二重採番され、対策案が採番サーバにまで後退した（doorstop#84）。改番・再配置は公式手段が無く（doorstop#233）、並べ替えで見出しが消えた（doorstop#246）。約2,000項目で規模の壁を体感した報告がある（doorstop#430）。安全規格運用への適合の欠落を列挙した issue は未解決のまま残る（doorstop#561、open）。
- **StrictDoc** はコード側マーカー注釈で範囲を結ぶ。マーカーが改行で折り返されると紐づけが黙って失われ（strictdoc#2130）、未知の拡張子は実在するのに「存在しない」とされて追跡から漏れる（strictdoc#1621）。被参照を保ったままの id 改名は今も未実装（strictdoc#1360、open）。100文書規模で表示に10秒かかった（strictdoc#2428）。
- **OpenFastTrace** は手動のリビジョン昇番で古びを表す。**内容が変わっても昇番を忘れれば無傷に見える**という構造的偽陰性が指摘されたまま8年未解決（openfasttrace#204、open）。記法により解析が食い違い（openfasttrace#423、open）、文書側にカバレッジタグを置けない（openfasttrace#562、open）。
- **Sphinx-Needs** には内容変更を検出する疑義の機構そのものが無く、要望が未実装のまま（sphinx-needs#685、open）。導入すると増分ビルドが壊れて全再ビルドになり（sphinx-needs#343）、needs.json が130MBに達した報告（sphinx-needs#1082、open）、約10万件でスキーマ検証に最大280秒（sphinx-needs#1580、open）と、規模の問題が形を変えて繰り返す。

### 1.2 AI 仕様駆動開発（GitHub Spec Kit・OpenSpec・Kiro・Claude Code）

- **実装後に仕様が更新されない**: 既存仕様の反復更新の経路が無いという報告が最多級の反応を集め（spec-kit#1191）、「新機能が旧機能の仕様を陳腐化させたときどうするか」への確答が無いまま残る（spec-kit#620、open）。実装後の差分を仕様へ畳み込むコマンドの要望（spec-kit#1063、OpenSpec#821 open）は、乖離が常態である裏返し。
- **機能単位の仕様は変更指示書であり、現行の正がどこにも蓄積されない**: spec-kit#916・#1100（open）が module 単位の持続仕様を要望する。フラットな仕様集合が規模に耐えない報告も（OpenSpec#662）。
- **規範文書は「置けば読まれる」が成立しない**: CLAUDE.md の必須規則が恒常的に無視される（claude-code#2544、open）。**圧縮の後に規範が完全に消える**（claude-code#19471）。サブエージェントに規範が無言で継承されない（claude-code#29423）。仕様モードでこそ規範注入が効かない例もある（Kiro#884、open）。注入の生死を確かめる機構を持つ道具は調査範囲に無かった。
- **儀式が粒度に適応しない**: 既存構造を無視した大量生成が「見せかけの仕事」と断じられ（spec-kit#75）、不具合修正でも要求工程が強制され空の文書が生まれ（Kiro#9963、open）、生成物の掃除が無く8GB超に膨れた（Kiro#4165、open）。
- **統治を売る道具が自分の統治に失敗する**: 初期化が同内容の規範を二系統に複製し（OpenSpec#1139、open）、廃止済みの命令体系を生成し続け（OpenSpec#1129、open）、公式手順とエージェントの実挙動が乖離する（OpenSpec#863、open）。
- **強制と暴走の間**: 規範を強めると意図しない実行が起き（spec-kit#896）、緩めると無視に戻る。従ったかを実行後に機械で検める層が欠けたまま、指示の強度で調整されている。

### 1.3 文書とコードの同期を商品にした道具（Swimm・ADR ツール・TechDocs・API 乖離検出）

- **Swimm** の公式文書は、自動追随（Auto-sync）が実質的な変更では人手の再選択に落ちる保守的設計だと明記し、通知過多への公式対処は「通知を減らす設定」である。本体事業はレガシー近代化へ転換した。
- **ADR の道具は先に死ぬ**: adr-tools の最終リリースは2018年。log4brains は利用者から「not maintained」と名指しされ（log4brains#29）、数年の停止を経た。**腐りを検出する道具の寿命が、守るべき文書の寿命より短い**ことが繰り返されている（Dredd も2024年にアーカイブされ、OpenAPI 3 対応は experimental のまま終わった）。
- **Backstage TechDocs** では、更新を把握する機能の要望が stale ラベルで閉じられ（backstage#20832）、修正の摩擦を減らす提案も採用されなかった（backstage#12543）。検出はできても直す導線が設計されない。
- **意味論の隙間**: openapi-diff は意味的に等価な整理を破壊的変更と誤報し（openapi-diff#192）、Schemathesis は正しい拒否を不具合と誤報する（schemathesis#2978）。行・字句・構文の差分から「意味が変わったか」は判定できず、最後は必ず人の裁定が残る。
- **存在の有無だけの被覆計測は形骸化する**: interrogate が測るのは docstring の有無だけで、十数種の除外設定で計測対象自体を緩められる。

### 1.4 商用の要求管理と規格実務（DOORS・Polarion・Jama・実証研究）

- **DOORS の suspect link には一括クリアが正規操作として用意され**、公式フォーラムの専門家が「両端を検分しない盲目のクリアは機構の目的自体を無効にする」と警告する状態を生んだ。競合の Jama は発火条件の絞り込みを売りにする — 「あらゆる変更で発火」が雑音源だという業界の共通認識の裏返しである。
- **重さと分断**: 1文書に千超の項目でほぼ使用不能（PeerSpot の Polarion 評）、高価な利用権が Excel への逃避を生む（r/systems_engineering）。Doorstop の論文は商用の要求管理の欠点を「ソースファイルからの本質的な分断」と要約した。
- **実証研究**: 維持されたトレースリンクを持つ開発者は保守作業を有意に速く正確にこなすが、**古びたリンクは無用どころか誤導するため有害**（Mäder & Egyed 2015 と後続の decay 研究）。実務者55名の調査では、採用を阻む最大の壁は「見返りが目に見えないこと」で、**価値を信じているのに保守できない**姿が実証された（Why don't we trace?、2023）。
- **それでも続ける理由**: 実務者が擁護する価値は監査の証憑ではなく「どの行がどの要求とどの試験に対応するか分かるから、**変更の後にどの試験を走らせるべきか分かる**」体験である（HN の航空機組込み開発者の証言）。

## 2. 横断の問題類型

| # | 類型 | 代表の証拠 |
|---|---|---|
| 1 | 古び検知は「全部ハッシュ（うるさい）」か「手動昇番（忘れる）」の二択で、意味のある変更だけを疑う中間が無い | doorstop#337/#173、openfasttrace#204、sphinx-needs#685 |
| 2 | 走査の視界の外は「未カバー」でなく「不可視」になり、全数性が崩れる | strictdoc#1621/#2130、openfasttrace#562 |
| 3 | id の改名・改番・統合は道具の支援が無く、事実上の永久不変を強いる | strictdoc#1360、doorstop#233/#246 |
| 4 | 連番 id と分散版管理の併用は採番衝突を必然にする | doorstop#84 |
| 5 | トレース計算は全体で閉じ、増分化に失敗し、回避が「検証を切る」に流れる | doorstop#430、strictdoc#2428、sphinx-needs#343/#1082/#1580 |
| 6 | 規範の注入は無言で失効する（圧縮・サブエージェント・モード切替）。生死を確かめる機構が無い | claude-code#19471/#29423/#2544、Kiro#884 |
| 7 | 変更指示書と現行仕様が未分離で、実装後に正へ畳み込む所有者が居ない | spec-kit#620/#916/#1100、OpenSpec#821 |
| 8 | 儀式が変更の粒度に適応せず、読まれない生成物が「見せかけの仕事」を量産する | spec-kit#75、Kiro#9963/#4165 |
| 9 | 検出は自動でも修正は人手のままで、通知疲れと「直す導線の不在」に行き着く | Swimm 公式、backstage#12543/#20832 |
| 10 | 乖離のとき文書とコードのどちらが正かを裁く者が道具の中に居ない | schemathesis#2978、openapi-diff#192 |
| 11 | 疑義の印に逃げ道（一括クリア・除外設定）があると、必ず逃げ道として使われる | DOORS 公式の一括クリア、interrogate の除外群 |
| 12 | 紐づけを守る道具自身が先に死ぬ。道具の死後にデータが読めるかが問われる | adr-tools、Dredd、log4brains#29、Swimm の転換 |
| 13 | 統治を司る道具が自分自身の統治に失敗する | OpenSpec#1139/#1129/#863 |
| 14 | リンクは作る費用でなく**保守する費用**で死に、古びたリンクは誤導するため無いより有害 | Mäder & Egyed 2015、Why don't we trace? 2023 |

## 3. 所見（設計へ引き取る原則の候補）

いずれも候補であり、採るなら対応する決定を ADR で起こす。

1. **保守費用の最小化を作成費用より優先する。** 疑義は人の印でなく内容の指紋の再照合で自然に解消する形にし（類型1・14）、一括で消せる印・計測を緩める除外を設計しない（類型11）。除外は列挙された規則だけに許し、規則ごとの件数を常に報告する（類型2）。
2. **注入の生死を構造で確かめる。** 「置けば読まれる」を前提にせず、注入の欠落を検出して人へ報せる（類型6。[R11] の方向を裏づける）。
3. **変更の記録と現行の正を型で分ける。** 決定（ADR）を現行文書へ畳み込む所有者を機械の検査で代替する（類型7。adr_not_landed の方向を裏づける）。
4. **儀式は変更の性質で段階づける**（類型8。ADR-051 の方向を裏づける）。大量の初期生成はせず、触った所から紐づける。
5. **検出の終点を「人への通知」でなく「次セッションの LLM への作業指示」に置く**（類型9）。裁定（どちらが正か）だけを人に残す（類型10）。
6. **道具の死後も読めるデータ形式を保つ**（類型12）。平文と標準ライブラリだけで再導出できる索引は、この要請を満たす。
7. **自分の統治への自己適用を検査で強制する**（類型13。本体系が三度起こした「文書上の宣言に留まる」欠陥類型と同じものが、調査した全系統で観測された）。

## 出所

### 1.1 系統
- <https://github.com/doorstop-dev/doorstop/issues/337> / <https://github.com/doorstop-dev/doorstop/issues/173> / <https://github.com/doorstop-dev/doorstop/issues/178> / <https://github.com/doorstop-dev/doorstop/issues/84> / <https://github.com/doorstop-dev/doorstop/issues/233> / <https://github.com/doorstop-dev/doorstop/issues/246> / <https://github.com/doorstop-dev/doorstop/issues/430> / <https://github.com/doorstop-dev/doorstop/issues/561>
- <https://github.com/strictdoc-project/strictdoc/issues/2130> / <https://github.com/strictdoc-project/strictdoc/issues/1621> / <https://github.com/strictdoc-project/strictdoc/issues/1360> / <https://github.com/strictdoc-project/strictdoc/issues/2428>
- <https://github.com/itsallcode/openfasttrace/issues/204> / <https://github.com/itsallcode/openfasttrace/issues/423> / <https://github.com/itsallcode/openfasttrace/issues/562> / <https://github.com/itsallcode/openfasttrace/issues/86>
- <https://github.com/useblocks/sphinx-needs/issues/685> / <https://github.com/useblocks/sphinx-needs/issues/343> / <https://github.com/useblocks/sphinx-needs/issues/1082> / <https://github.com/useblocks/sphinx-needs/issues/1580>

### 1.2 系統
- <https://github.com/github/spec-kit/issues/1191> / <https://github.com/github/spec-kit/issues/620> / <https://github.com/github/spec-kit/issues/1063> / <https://github.com/github/spec-kit/issues/916> / <https://github.com/github/spec-kit/issues/1100> / <https://github.com/github/spec-kit/issues/75> / <https://github.com/github/spec-kit/issues/896> / <https://github.com/github/spec-kit/issues/264> / <https://github.com/github/spec-kit/issues/1436>
- <https://github.com/Fission-AI/OpenSpec/issues/821> / <https://github.com/Fission-AI/OpenSpec/issues/1139> / <https://github.com/Fission-AI/OpenSpec/issues/1129> / <https://github.com/Fission-AI/OpenSpec/issues/863> / <https://github.com/Fission-AI/OpenSpec/issues/662>
- <https://github.com/anthropics/claude-code/issues/2544> / <https://github.com/anthropics/claude-code/issues/19471> / <https://github.com/anthropics/claude-code/issues/29423>
- <https://github.com/kirodotdev/Kiro/issues/884> / <https://github.com/kirodotdev/Kiro/issues/9963> / <https://github.com/kirodotdev/Kiro/issues/4165>

### 1.3 系統
- <https://swimm.io/blog/how-does-swimm-s-auto-sync-feature-work> / <https://docs.swimm.io/continuous-integration/github-app/> / <https://swimm.io/>
- <https://github.com/npryce/adr-tools/releases> / <https://github.com/thomvaill/log4brains/issues/29> / <https://github.com/apiaryio/dredd>
- <https://github.com/backstage/backstage/issues/20832> / <https://github.com/backstage/backstage/issues/12543>
- <https://github.com/OpenAPITools/openapi-diff/issues/192> / <https://github.com/schemathesis/schemathesis/issues/2978>
- <https://github.com/econchick/interrogate>

### 1.4 系統
- <https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors/9.7.1?topic=objects-clearing-suspect-links> / <https://jazz.net/forum/questions/284539/what-are-suspect-links-in-dng-and-how-can-it-be-fixed>
- <https://www.jamasoftware.com/blog/2025/09/13/the-importance-of-suspect-tracking-in-requirements-management/>
- <https://www.peerspot.com/questions/what-needs-improvement-with-polarion-requirements>
- <https://scholarworks.gvsu.edu/oapsf_articles/32/>（Doorstop 論文）
- <https://link.springer.com/article/10.1007/s10664-014-9314-z>（Mäder & Egyed 2015） / <https://link.springer.com/article/10.1007/s00766-023-00408-9>（Why don't we trace? 2023） / <https://arxiv.org/abs/2206.04462>（When Traceability Goes Awry）
- <https://news.ycombinator.com/item?id=17540280>（変更影響の特定の証言）
