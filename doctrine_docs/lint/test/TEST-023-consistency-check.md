---
id: TEST-023
title: 整合点検と横断リマインダの受入
type: TEST
domain: lint
status: current
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-08-14
sources: [scripts/consistency-check.py, plugin/tests/test_linter.py]
depends_on: [SPEC-023]
llm_context: task
---

# 整合点検と横断リマインダの受入

SPEC-023 の受入である `[R2][R6]`。

## 受入基準への対応

- 実走: 本リポジトリでの `python3 scripts/consistency-check.py` が「食い違いなし」で 0 を返す(`CI` 相当の確認は WATCH-001 第5項の点検として、リマインダの督促で定期実行する)。
- リンタ側の不変条件(登録済み非文書に schema ERROR を出さない)は `plugin/tests/test_linter.py` の ADR-024 受入①〜④が凍結する。
- リマインダの発火間隔(10 回ごと)は、カウンタファイルの手動操作で確認する(会話 10 回目に助言が注入される)。

## 退行観点

- 監査とリンタが `.md-intake` を別実装で読む変更を入れない(共有コア `_intake.py` 経由を保つ)。
- 点検不能を「食い違いなし」に数えない。

## 合否基準

実走が 0 を返し、`test_linter.py` の該当受入が緑であること。

<!-- 補足: 二本の実体はリポジトリ直下 scripts/ にあり、配布物(plugin/)には含めない -->
