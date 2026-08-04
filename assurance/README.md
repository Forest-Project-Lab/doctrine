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
```

## 状態語彙

PASS（適合の証拠あり）/ FAIL（走ったが不適合）/ UNKNOWN（観測できず判定不能）/ UNASSESSED（前提欠如で未評価）/ DEGRADED（縮退運転）/ NOT-APPLICABLE（非該当）

- 前提が欠けて評価できないときは PASS ではなく **UNASSESSED** へ倒す（終了コード 3）。
- 走ったが oracle（合否を機械で判じる基準）を満たさないときは **FAIL**（終了コード 2）。
- 緑であることと保証が成立することを同一視しない。

## 証拠

- `assurance/ledger/` — 選別した証拠（コミットする）。`smoke-latest.json` は直近の煙試験の記録。
- `assurance/ledger/runs/` — 生の実行記録（コミットしない。使い捨て）。
- 各記録は commit SHA（コミットの識別子）・SDK 版・model・プロンプトの sha256（内容の指紋）・費用・所要時間を持つ。

## してはならないこと

- 配布 Skill（7個）を増減・変更する入口にしない。保証用エージェントはこのレーンからプログラム的に定義する。
- 評価者の CHALLENGE（独立批判）と VERIFY（独立検証）へ、実装者の会話・弁明・期待回答を渡さない。渡してよいのは構造化された成果物だけ。
- 模擬（stub）で通った結果を、実 Claude での保証として記録しない。記録には必ず実行種別を書く。

<!-- doctrine:view src=doctrine as-of=0.10.0 date=2026-08-04 refs=DECIDED-001,NONGOAL-001 -->
