# 外部仕様の確認記録（保証レーン）

記憶に依存しないための台帳。対象は Claude Agent SDK（エージェント実行の開発キット。以下 SDK）と関連する公式仕様。
各項は「事実 / 参照 / 確認日 / 対象版 / 仮定 / 破れた場合の影響 / 再確認の契機」を持つ。
確認は公式一次文書の取得による（モデルが書いた要約は正本にしない。取得は本リポジトリの保証セッションが実施）。
状態語彙は `assurance/README.md` と同じ（UNASSESSED（前提欠如で未評価）・DEGRADED（縮退運転）ほか）。

## 1. パッケージと同梱物

- 事実: PyPI の `claude-agent-sdk` の現行は 0.2.129（2026-08-04 公開）。Python 3.10 以上。TypeScript/Python とも Claude Code のネイティブバイナリを同梱し、別途の CLI インストールは不要。
- 参照: https://pypi.org/project/claude-agent-sdk/ / https://code.claude.com/docs/en/agent-sdk/quickstart.md
- 確認日: 2026-08-04 / 対象版: 0.2.129
- 仮定: wheel が manylinux x86_64 で本環境（WSL2（Windows 上の Linux 実行環境）の devcontainer）に適合する。
- 破れた場合: venv 構築か実行が落ちる。doctor の venv_sdk 検査が missing → UNASSESSED で顕在化する。
- 再確認の契機: requirements.lock の版更新時。実行環境（基本ソフト・アーキテクチャ）の変更時。

## 2. 認証の公式経路

- 事実: 公式の主経路は `ANTHROPIC_API_KEY`。加えて `claude setup-token` が発行する `CLAUDE_CODE_OAUTH_TOKEN`（約1年の期限）が CI・スクリプト向けに文書化されている。後者はサブスクリプション（Pro/Max/Team/Enterprise）で認証し、model への要求だけができる。
- 参照: https://code.claude.com/docs/en/agent-sdk/quickstart.md / https://code.claude.com/docs/en/authentication.md
- 確認日: 2026-08-04 / 対象版: 文書の当日版
- 仮定: サブスクリプション経由の SDK 利用が利用規約上許容されている（setup-token の文書化がその根拠）。
- 破れた場合: レーンの認証を API の鍵へ切り替える必要が生じ、費用構造が変わる。所有者判断が要る。
- 再確認の契機: 認証エラーの発生時。四半期ごと。

## 3. 対話ログイン資格情報の自動流用（実測で確立した経路）

- 事実: `~/.claude/.credentials.json`（対話ログインの保存資格情報）を SDK が自動で使うことは**公式文書に記載が無い**。認証の優先順の文書は `CLAUDE_CODE_OAUTH_TOKEN` を「/login のサブスクリプション資格情報」より先に見るとするのみ。
- 実測: 本レーンの煙試験（`assurance/ledger/smoke-latest.json`）が、環境変数の鍵なし・資格情報ファイルありの条件で成否を記録する。
- 確認日: 2026-08-04 / 対象版: claude-agent-sdk 0.2.129
- 仮定: 同梱 CLI が保存資格情報を読む挙動は**無保証の実装詳細**である。
- 破れた場合: 煙試験が UNASSESSED（認証系）へ落ちる。その時は `claude setup-token` で `CLAUDE_CODE_OAUTH_TOKEN` を発行する（文書化された代替）。
- 再確認の契機: SDK 版更新時。煙試験の認証系失敗時。

## 4. setting_sources の既定値（隔離の要）

- 事実: `setting_sources` を省略すると `["user", "project", "local"]` と等価になり、CLAUDE.md・Skill・Hook・settings を読み込む。隔離セッションには空配列の明示が必須。
- 参照: https://code.claude.com/docs/en/agent-sdk/claude-code-features.md
- 確認日: 2026-08-04 / 対象版: 文書の当日版
- 仮定: 空配列で project 設定由来の Hook（本リポジトリの統治フック）が子セッションに載らない。
- 破れた場合: 評価者が実装者の文脈・フックを継いでしまい、独立性の主張が崩れる。隔離検証試験（次反復で fixture 化）が検出するまで DEGRADED と扱う。
- 再確認の契機: SDK 版更新時。評価者の応答に本リポジトリ固有の契約文言が混入した時。

## 5. 構造化応答

- 事実: `query()` に `output_format={"type": "json_schema", "schema": ...}` を渡すと、応答完了時に schema 検証済みの `structured_output` が得られる。検証失敗時は再試行される。
- 参照: https://code.claude.com/docs/en/agent-sdk/structured-outputs.md
- 確認日: 2026-08-04 / 対象版: 文書の当日版
- 仮定: SDK 側検証と本レーン側の再検証（schemas.validate）は独立に走らせる（同じ誤りを複製しない）。
- 破れた場合: `sdk_lane` が sdk-option-mismatch を報せ UNASSESSED になる（黙って自由文へ縮退しない）。
- 再確認の契機: SDK 版更新時。

## 6. model の既定と煙試験の model

- 事実: `model` 省略時は Claude Code 側の既定（認証方法とサブスクリプションに依存）。小型で安価な現行 model は `claude-haiku-4-5`（正式 id `claude-haiku-4-5-20251001`）。
- 参照: https://code.claude.com/docs/en/agent-sdk/agent-loop.md / https://platform.claude.com/docs/en/about-claude/models/overview.md
- 確認日: 2026-08-04 / 対象版: 文書の当日版
- 仮定: サブスクリプション認証で haiku 系が呼べる。
- 破れた場合: 煙試験が model 起因で失敗する。`--model` で差し替えて切り分ける。
- 再確認の契機: model の廃止告知。煙試験の失敗時。

## 7. 入れ子実行（Claude Code セッション内から SDK を呼ぶ）

- 事実: 公式文書に入れ子実行の注意・制約の記載は見つからなかった（未確認事項として持つ）。
- 実測: 本セッション（Claude Code 内）からの煙試験の成否を台帳に記録する。
- 確認日: 2026-08-04
- 仮定: 親セッションの環境変数が子へ渡っても、`setting_sources=[]` と空の一時 cwd で設定面の隔離は保てる。
- 破れた場合: 煙試験・評価実行が不安定になる。CI（セッション外）での再実行と比較して切り分ける。
- 再確認の契機: レーンの実行環境を変えた時。原因不明の失敗時。
