---
id: EXT-006
title: System View 検証（実験ブランチ）の現行参照点への依存
type: EXT
domain: graph
status: current
owner: doctrine-maintainers
created: 2026-08-04
updated: 2026-08-14
sources: [https://github.com/Forest-Project-Lab/doctrine/issues/204]
review_by: 2026-09-03
llm_context: task
---

# System View 検証（実験ブランチ）の現行参照点への依存

統治木の外への依存を登録するアンカーである（ADR-026）。中身は写さない。現行の合意台帳（issue #204。以後「台帳」）の第8項（各 Phase の完了ごとに両統治木へ記録する）の doctrine 側の記録であり、参照は台帳第15項の規則（tag 名に、その時点の commit SHA（コミットを一意に指す指紋）を併記）に従う。

## 何に依存しているか

ADR-112（現行は置換後の ADR-162）が応答した System View 構想の検証（Phase 0–1）は、doctrine-lens リポジトリの実験ブランチ `experiment/system-map` で行われる。doctrine 側の決定（器の凍結・読み口の宣言）の再検討条件——意味モデルの改訂回数・M 層（機械）と H 層（人間）の通過——は、この検証の成果物にだけ記録される。三条件は 2026-08-14 に満ちたと裁かれ、器の凍結は解かれた（ADR-162）。

Phase 1 は 2026-08-04 に「検証継続」と裁かれた（正式移管・閉鎖はしない。俯瞰レビューの再確認済み）。この裁きの意味は「Phase 1 の結果を検証継続として固定した」だけであり、移管・製品採用・スキーマ確定の承認ではない。先行の tag `system-map/phase-0`（commit `cca109d`）も参照点として残存する。

## 期待

- 対象: `https://github.com/Forest-Project-Lab/doctrine-lens/tree/system-map/phase-1-continue`（tag `system-map/phase-1-continue`、commit `d920130f5113541ae4603d16e242064fc66ff588`）
- 検査: review_by のみ（対象が外部リポジトリのため exists・hash の機械検査はできない。通信しない）
- 期待する状態: Phase 1 の成果物（Phase 1 終了記録・M 層の実判定の器・画面の静止画）が tag で参照でき、次の裁きまで実験ブランチが統治木の外に留まること。**H 層は 2026-08-14 に実施され、床（ADR-160 決定2）の四つの逆読みは 0 件だった**（証跡の等級は所有者の報告。逐次記録は残っていない。ADR-162 決定1）。これを受けて器の凍結は ADR-162 で解いた。以後この対象へ期待するのは、実施の事実と成果物が tag で辿れることまでである

## 動いたら何が壊れるか

tag が付け替えられる・成果物が消えると、凍結解除（ADR-162 が ADR-112 決定5 を置換した）の判定材料が失われる。凍結は既に解いたので、失われて困るのは「何を根拠に解いたか」を後から辿る道である。H 層の逐次記録はもともと残っていない（ADR-162 決定1 の等級）ので、辿れるのは M 層の器と画面の成果物までであり、そこが消えると根拠は所有者の報告だけになる。検出は本アンカーの review_by（期限の見張り）と、issue #204 上の巡回に委ねる。

<!-- 入れない: 外部の正本の中身の写し(正本の二重化)。要点の転記と出所の参照だけを許す -->
