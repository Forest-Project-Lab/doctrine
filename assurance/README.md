# assurance/ — 保証キャンペーンの開発専用レーン

これは Doctrine 本体の保証（検証・故障注入・独立評価）を回すための**開発専用**ハーネスである。
配布物ではない（marketplace が配布するのは `./plugin` だけ。`.claude-plugin/marketplace.json`）。

## 境界

- 「すべてのスクリプトは標準ライブラリだけで動く」（DECIDED-001）は**配布物 `plugin/` の制約**であり、このレーンには適用しない。ここは venv と pin した依存を持つ。
- このレーンのコードを `plugin/` から import してはならない。逆（レーンが plugin のスクリプトを試験対象として実行する）は許す。
- Claude Agent SDK（エージェント実行の開発キット。以下 SDK）はこのレーンだけに置く。配布物の実行時依存へ入れない。
- 評価セッションは `setting_sources=[]` を必ず明示する（省略時は user/project/local を読み込む。`assurance/external-specs.md` 第4項）。
- 破壊的な故障注入は一時ディレクトリ・使い捨て fixture だけで行う。main checkout・利用者データへ注入しない。

## 認証

サブスクリプション認証を流用する。優先順:

1. `CLAUDE_CODE_OAUTH_TOKEN`（`claude setup-token` で発行。CI 向け）
2. `ANTHROPIC_API_KEY`（従量課金。通常は使わない）
3. `~/.claude/.credentials.json`（対話ログイン済みの資格情報。**公式文書に自動流用の記載は無く、実測で確かめた経路**。`external-specs.md` 第3項）

資格情報の**内容**は、ログにも台帳にも応答にも書いてはならない。存在の有無だけを記録する。

## 使い方

```bash
# 前提診断（標準ライブラリのみ・どの python3 でも動く）
python3 assurance/harness/doctor.py --json

# venv 構築（初回のみ）
python3 -m venv assurance/.venv
assurance/.venv/bin/pip install -r assurance/requirements.lock

# 実 SDK の煙試験（サブスク認証・構造化応答・隔離セッション）
assurance/.venv/bin/python assurance/harness/smoke.py

# レーン自身の決定論試験（SDK 不要・通信不要）
python3 -m unittest discover -s assurance/tests -v

# オーケストレーションの現在地と次の行動（決定論。ADR-115）
# next_actions は空にならない。台帳の骨組みが在ることは割当が済んだことではなく、
# UNKNOWN が残る限り MAP_COVERAGE を挙げる（事象 INC-006）。
assurance/.venv/bin/python assurance/harness/orchestrator.py status
assurance/.venv/bin/python assurance/harness/orchestrator.py validate

# 規範カタログの抽出（評価役: opus high。再開可能・費用二段上限）
assurance/.venv/bin/python assurance/harness/extract_principles.py --book jerg

# 網羅台帳（五値）の骨組み生成と集計
assurance/.venv/bin/python assurance/harness/coverage.py init --book jerg
assurance/.venv/bin/python assurance/harness/coverage.py stats

# 事象 → 統制欠陥と先行指標（評価役: opus high。ADR-117 の三条件をコードが判ずる）
assurance/.venv/bin/python assurance/harness/cast_analysis.py --dry-run --all
assurance/.venv/bin/python assurance/harness/cast_analysis.py --all

# 網羅の割当（現状の索引に対して五値を割り当てる。ADR-118。束ごとに保存・再開可能）
assurance/.venv/bin/python assurance/harness/map_coverage.py --book jerg --dry-run
assurance/.venv/bin/python assurance/harness/map_coverage.py --book jerg --max-batches 2

# 失敗仮説の創出と独立批判（DISCOVER → CHALLENGE。別々の一回限りセッション）
assurance/.venv/bin/python assurance/harness/discover.py --dry-run
assurance/.venv/bin/python assurance/harness/discover.py

# 評価機構自身への故障注入（ADR-120。注入は評価器の入力に対してだけ行う）
assurance/.venv/bin/python assurance/harness/attack_evaluator.py --only A3   # 決定論の対照
assurance/.venv/bin/python assurance/harness/attack_evaluator.py            # 全注入
```

## 観点レーンと発火（ADR-115）

規範3冊は観点別レーンに分け、一つのセッションへ同時に読ませない。
「どの状態で・どのレーンが・何を見るか」の正本は `harness/orchestrator.py`。
語の読み: 冊子は JERG（宇宙機関の検証標準）・STPA（危険要因分析）・CAST（事故分析）、
状態は DISCOVER（創出）・CHALLENGE（独立批判）・FORMALIZE（定式化）・VERIFY（独立検証）・
APPLY_FINDINGS（推奨の処遇決め）・FAIL（不適合）・UNASSESSED（前提欠如で未評価）。

| レーン | 冊子 | 発火する状態 | 見るもの → 出すもの |
|---|---|---|---|
| stpa | STPA ハンドブック | DISCOVER | 境界と seed 事実 → 失敗仮説（scenario） |
| jerg | JERG-2-610C | MAP_COVERAGE・FORMALIZE・VERIFY | 計画と証拠 → 適合判定 |
| cast | CAST ハンドブック | CAST_ANALYSIS（FAIL・事象の後） | 事象と統制構造 → 統制欠陥・先行指標 |
| challenge | （共通） | CHALLENGE | DISCOVER の構造化 JSON だけ → 判定 |

発火点ごとの走らせ手の対応は `harness/orchestrator.py` の `FIRING_POINTS` が正本である
（ADR-128）。各発火点は「実行器・prompt 組み立て関数・台帳の成果物種別」の三点を持つか、
「未実装である旨と理由」を持つかのちょうど一方に属し、表の鍵集合はレーンの `fires_on` の
合併と一致する（両方向の差集合が空）。**現状 `FORMALIZE` と `VERIFY` は未実装と明記された
状態で緑になる** —— 緑は「実装されている」ではなく「実装されていないことが宣言されている」
の意味であり、`status` の `firing_points.unimplemented` に理由つきで出続ける。是正は
事象 INC-021 が持つ。

冊子の取り込みは jerg → stpa → cast の順。事象は `ledger/incidents.json` に積み、
cast 分析が済むまで閉じない。「済んだ」の定義は ADR-117 と ADR-121 が持つ —— 応答が
`CAST_ANALYSIS_SCHEMA` へ適合し、参照照合を通った統制欠陥が一つ以上残り、
先行指標が「どこで観測するか」と「何を異常とするか」を埋めていること。三つとも
`harness/cast_analysis.py` の決定論コードが判ずる。分析の入力は事象の構造化記録・
統制構造（`harness/control_structure.py`）・カタログ全件だけで、会話・弁明は渡さない。
分析の結果は `ledger/cast/<事象 id>.json` に残る。
四つ目の条件として、事象の証拠が体系の中で確かめられること（ADR-121）—— 構造化した
`evidence_refs` の少なくとも一つが解決するか、`evidence_kind` を `external` /
`conversational` / `measurement` のいずれかで宣言していること。自由文の `evidence` は
走査しない。証拠の解決先は索引と実ファイル系の二つである（ADR-123）。

## model 方針（ADR-116）

- 評価役（抽出・創出・批判・検証計画・事故分析）: `claude-opus-5` × effort `high` が
  最低線。`harness/model_policy.py` がコードで拒否し、決定論試験が凍結する。
- 配管確認（煙試験の nonce 往復。意味を要さない）: `claude-haiku-4-5`。
- 劣化プローブ: 弱い model で意味が保たれるかを**測る目的を明示して**だけ使う。
- opus が使えなければ評価は UNASSESSED。黙って弱い model へ落とさない。

## 状態語彙

PASS（適合の証拠あり）/ FAIL（走ったが不適合）/ UNKNOWN（観測できず判定不能）/ UNASSESSED（前提欠如で未評価）/ DEGRADED（縮退運転）/ NOT-APPLICABLE（非該当）

- 前提が欠けて評価できないときは PASS ではなく **UNASSESSED** へ倒す（終了コード 3）。
- **merge の門も同じ三値で判ずる**（ADR-129。`harness/merge_gate.py --pr <番号>`）。
  適合を採るのは、検査が実行され・状態語が割れておらず・**検査対象の識別子が適用対象の
  識別子と一致し**・結論が既知の語彙にあるときだけ。走ったうえでの不適合だけが FAIL で、
  それ以外の不成立は UNASSESSED。前提欠如は待機であって迂回ではない。
- 走ったが oracle（合否を機械で判じる基準）を満たさないときは **FAIL**（終了コード 2）。
- 緑であることと保証が成立することを同一視しない。

## 証拠

- `assurance/ledger/` — 選別した証拠（コミットする）。`smoke-latest.json` は直近の煙試験の記録。
- `assurance/ledger/runs/` — 生の実行記録（コミットしない。使い捨て）。
- 各記録は commit SHA（コミットの識別子）・SDK 版・model・プロンプトの sha256（内容の指紋）・費用・所要時間を持つ。
- 台帳に置く成果物の種別は、正本が**読む関数の名**を持つか、**読まない理由**を持つかの
  ちょうど一方に属する（ADR-124）。表は `harness/orchestrator.py` の `LEDGER_KINDS`。
  どちらも無い種別と、どの宣言にも当たらないファイルが在る間は `orchestrator.py validate`
  が赤になる。走らせ手を足すときは、その成果を正本が読む段を同じ差分で足すこと。
- `recommendation-status.json` — 事故分析が出した推奨の処遇（ADR-125）。鍵は
  `(事象 id, 番号)`、語彙は pending / landed / rejected / owner。未着手が残る間は正本が
  `APPLY_FINDINGS` を次の行動に挙げる。却下は理由を、機構化済みは証拠のポインタを持つ。
  所有者判断はレーンの未着手に混ぜないが、**成立するのは六類型のどれかを名指したときだけ**
  である（ADR-127。`OWNER_DECISION_KINDS` が正本）。処遇が無い推奨の既定は、分析が何を
  印していようと `pending`。事故分析の入力に統治木は入っておらず、`owner_decision_required`
  は権限の判定ではなく**評価者の視野の申告**だからである。申告の件数（`evaluator_claimed_owner`）
  と成立した件数（`counts.owner`）は `status` が別々に出す。
- `assumptions.json` — 保証が寄りかかる想定の登記簿（ADR-126）。決定でも非目標でもなく、
  引き受けているのに検めていない前提を一件ずつ載せる。各項は `verified_by`（検証者が
  居なければ `null` と明記）と、「どこで観測するか」「何を異常と見るか」を埋めた
  先行指標を一つ以上持つ。観測には日付と状態語彙を添え、成り立たないと判った指標は
  `rejected_indicators` に理由つきで残す。PASS でない観測を持つ想定は、対応する事象 id
  を持たないかぎり `REVIEW_ASSUMPTION` として次の行動に挙がる（位置は推奨の山より前）。

## してはならないこと

- 配布 Skill（7個）を増減・変更する入口にしない。保証用エージェントはこのレーンからプログラム的に定義する。
- 評価者の CHALLENGE（独立批判）と VERIFY（独立検証）へ、実装者の会話・弁明・期待回答を渡さない。渡してよいのは構造化された成果物だけ。
- 模擬（stub）で通った結果を、実 Claude での保証として記録しない。記録には必ず実行種別を書く。

<!-- doctrine:view src=doctrine as-of=0.10.0 date=2026-08-05 refs=DECIDED-001,NONGOAL-001 -->
