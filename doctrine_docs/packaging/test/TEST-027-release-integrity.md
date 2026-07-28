---
id: TEST-027
title: リリース整合の門の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-07-28
updated: 2026-07-28
sources: [plugin/tests/test_release_check.py, scripts/release-check.py]
depends_on: [SPEC-027]
llm_context: task
---

# リリース整合の門の受入

SPEC-027 の受入である。テストコードは `plugin/tests/test_release_check.py`（CI が
毎回走らせる単体テスト群の一つ）。

## 受入基準への対応

- 版の整合: 先頭の版付き節の版と正本（plugin.json）の一致・日付の存在・
  「未リリース」節の読み飛ばし・区切り（— と -）の両受けを単体で凍結する。
- 記録の義務: 擬似 git リポジトリで「plugin/ に触れて CHANGELOG（リリースごとの
  変更を利用者向けに記す変更履歴ファイル）に触れない」差分が赤、両方に触れる
  差分が緑、題名の `[no-changelog]` で免除、を凍結する。免除が版の整合に
  及ばないことも見る。
- 前提が読めない（plugin.json・CHANGELOG.md の不在、版付き節ゼロ、引けない
  基準 ref）は例外に倒し、入口では終了コード 2 になることを凍結する。
- 公開ビューの刻印（ADR-073）: 3件が刻印を持ち `as-of` が正本と一致すれば緑、
  刻印の欠落・読めない刻印（必須欄の欠落）・版の遅れ・ファイルの不在が赤に
  なることを凍結する（ViewStampTest）。
- 自己適用の実走: 本リポジトリ自身が門を通る（終了コード 0。公開ビュー3件の
  刻印の一致を含む）。

## 退行観点

- marketplace.json との一致の検査を release-check へ足さない（TEST-020 が正本。
  二重定義しない）。
- 免除の印を、差分の中身など読めない場所へ移さない（題名だけが免除の証跡）。

## 合否基準

`python3 plugin/run_tests.py` で `test_release_check.py` の全件が緑であること。
