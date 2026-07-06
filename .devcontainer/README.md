# 開発コンテナ（Claude Code プラグイン開発）

このリポジトリで Claude Code プラグインを開発するための devcontainer である。CLI 版と拡張機能版の Claude Code を同梱する。本仕様（[../spec/context-engineering-blueprint.ja.md](../spec/context-engineering-blueprint.ja.md)）はフックを Python スクリプトで記述する。コンテナはこれに合わせて Node・Python・jq・git・gh を備える。

## 前提

- Docker Desktop（Windows は WSL2 バックエンドを有効にする）。
- VS Code と拡張機能「Dev Containers」（`ms-vscode-remote.remote-containers`）。

## 起動

1. VS Code でこのリポジトリを開く。
2. コマンドパレットで「Dev Containers: Reopen in Container」を実行する。
3. 初回はイメージの取得と Feature の導入で数分かかる。

## 同梱するもの

- Node.js 22（Claude Code CLI が要する実行環境）。
- Python 3.12（仕様のフックスクリプト用）。
- GitHub CLI（`gh`）。プラグインの配布とリポジトリ操作に使う。
- Claude Code CLI（`claude`）と VS Code 拡張機能 `anthropic.claude-code`。公式 Feature `ghcr.io/anthropics/devcontainer-features/claude-code` が両方を入れる。

CLI と拡張機能は同じ `~/.claude` を共有する。会話履歴と設定は両者で共通である。

## 認証

初回はサインインが要る。次のいずれかで行う。

- 統合ターミナルで `claude` を実行し、表示される手順でブラウザ認証する。
- または左側パネルの Claude Code 拡張機能で「Sign in」を押す。

ブラウザのコールバックがコンテナに届かない場合は、画面のコードを「Paste code here if prompted」に貼る。

`~/.claude` は名前付きボリューム（`claude-code-config-${devcontainerId}`）に退避する。コンテナを再ビルドしても認証と履歴は残る。ボリュームはこのプロジェクト専用に分離する。

## プラグイン開発の最小ループ

1. 直接読み込んで試す: `claude --plugin-dir ./<plugin>`（インストール不要）。
2. 編集後はセッション内で `/reload-plugins` で再読み込みする（`SKILL.md` の変更は即時反映、フック・`.mcp.json`・エージェントの変更は再読み込みが要る）。
3. 検証する: `claude plugin validate ./<plugin> --strict`。問題は `claude --debug` で追う。
4. 配布を試す: `.claude-plugin/marketplace.json` に相対パス（`./` 始まり）で登録し、`/plugin marketplace add ./<dir>` と `/plugin install <name>@<marketplace>` で確認する。

プラグインのマニフェストは `.claude-plugin/plugin.json` に置く。`.claude-plugin/` に入れるのは `plugin.json` だけで、`skills/`・`agents/`・`hooks/` などはプラグインのルートに置く。

## Windows での注意

- リポジトリは WSL2 のファイルシステム（例: `\\wsl$\...`）に置くと I/O が速い。`C:\` 上のバインドマウントは遅い。
- 改行コードは [.gitattributes](../.gitattributes) で正規化する。コンテナで動かすスクリプトは LF を保つ。

## ネットワーク制限（任意）

Anthropic は送信先を制限する参照 firewall（`init-firewall.sh` と `NET_ADMIN`/`NET_RAW`）を公開する。本コンテナは既定で導入しない。信頼できないリポジトリを無人で扱う場合にのみ検討する。手順は公式ドキュメント（<https://code.claude.com/doctrine_docs/en/devcontainer>）を参照する。
