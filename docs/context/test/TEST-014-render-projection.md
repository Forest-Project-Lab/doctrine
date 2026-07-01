---
id: TEST-014
title: render-projection のテスト計画
type: TEST
domain: context
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-06-30
sources: [plugin/tests/test_render.py]
depends_on: [SPEC-014]
llm_context: task
---

# render-projection のテスト計画

SPEC-014 の受入基準を `plugin/tests/test_render.py` で確かめる `[R1]`。

## 受入基準への対応

- 同じ源から描き直すと、結果がバイト単位で一致すること（冪等）。投影の `updated` が各源の最大値に追従し、壁時計に依らないこと。
- 並びが、ドメイン昇順 → §3.2 型順 → id 昇順の順で決定的に決まること。
- `--check` が投影ドリフト（または未生成）を非ゼロ終了で知らせ、一致したときは 0 を返すこと。
- 投影のフロントマターが `type: OVERVIEW`・`id: OVERVIEW-<n>` であること（C8とは凍結した契約の整合を見る判断項目をいう）。

## 退行観点

- 投影が自分自身を Overview の一覧に載せないこと（WATCH と突き合わせる）。
- Context Map で、印の外側の散文がドリフト扱いされず、そのまま保たれること。

## 合否基準

`plugin/tests/test_render.py` の全ケースが通り、上記の退行観点が破れていなければ合格とする。

<!-- 入れない: 無関係な要求 -->
