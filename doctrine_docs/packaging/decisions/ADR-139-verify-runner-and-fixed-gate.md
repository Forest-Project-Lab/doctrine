---
id: ADR-139
title: VERIFY（修正の独立検証）は走らせ手を持ち、新規の fixed:true は PASS（適合）の verify 記録を要す
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-07
updated: 2026-08-07
sources: ["所有者裁定（2026-08-07。INC-021 推奨#3 を両方実装と決めた）", doctrine_docs/_system/non-goals.md, doctrine_docs/packaging/decisions/ADR-128-firing-points-are-run-or-declared-unimplemented.md, assurance/ledger/incidents.json]
depends_on: [ADR-116, ADR-128]
llm_context: task
---

# VERIFY（修正の独立検証）は走らせ手を持ち、新規の fixed:true は PASS（適合）の verify 記録を要す

## 背景

状態機械は `FIX_APPLIED → VERIFY → ATTACK_EVALUATOR` の遷移を持つのに、VERIFY を
踏む実体が無かった。修正の正しさを別セッションが確かめる段を一度も経ないまま、
成果が台帳へ記録され所有者へ渡っていた（事象 INC-021。ADR-128 が「未実装の明記」
として宣言した側）。

実害はもう一段深い。事象の台帳の `fixed: true` は**実装者の自己申告**であり、
それを検める門がどこにも無い。修正したという申告をそのまま信じる形は、この体系が
繰り返し「やらない」と決めてきた（ADR-050・ADR-127・NONGOAL-001 第9項の同型）。
2026-08-07 時点で 26 の事象が在り、うち 13 件が `fixed: true` を独立の検証なしに
持っている。

所有者は 2026-08-07 に、INC-021 推奨#3 —— FORMALIZE（定式化。ADR-138）と VERIFY
の二段の実装 —— について「両方実装する」と裁定した。本 ADR はその VERIFY 側である。

## 却下した選択肢

- **既存の 26 事象へ遡って検証を要求する**: 全件が即座に赤になり、正本の自己検査が
  恒久の赤を抱える。直せない赤は信号を殺す（INC-017 で見た形）。既に済んだ修正は
  当時の反復の試験と監査を通っており、遡及の再検証は買い直しである。門は以後に課す。
- **`fixed: true` の書き方を運転手順の規律だけに任せる**: 規律は三度破れた
  （INC-012・INC-015・INC-016 の「憶えておく」の失敗）。機械の門にする。
- **遷移エンジンを作って guard を実行時に強制する**: 状態機械の正本は表であり、
  遷移は外側の決定論コードが判ずる（ADR-115）。エンジンはこの設計の置換であり、
  ここで要るのは guard 名が指す呼べる実体と、台帳を検める門だけである。
- **上限を超える diff を切り詰めて渡す**: 一部だけ見た検証が全体の検証として
  記録される。黙って切り詰めず、UNASSESSED（前提欠如）へ倒して止まる。

## 決定

VERIFY は走らせ手の三点を持つ —— 実行器 `assurance/harness/verify_fix.py`・
組み立て関数 `prompts.build_verify_prompt`（構造化された一つの対象＝対象 id・
主張・赤の証拠・diff・修正後の観測だけを受け取る。会話の口は無い）・台帳の
成果物種別 `verify/<対象 id>.json`。あわせて次を定める:

1. 検証役は評価役であり、最低線は ADR-116 のまま（opus × effort high）。
2. 赤の証拠（`ledger/red/<対象 id>.json`）が無ければ検証は始まらない ——
   UNASSESSED の記録を書いて止まる。修正前に FAIL（不適合）した観測が無い修正は、
   効いたかどうかを原理的に測れない。
3. 判定の記録は verdict と三つの checks（修正前は赤だったか・修正後は緑か・
   変更は一主題か）を持つ。verdict が PASS で三つ全てが PASS のときだけ、
   guard `before_fail_after_pass`（`verify_fix.py` が持つ呼べる実体）が真になる。
4. **以後に `fixed: true` と書く事象は、PASS の verify 記録へ解決する
   `verify_ref` を持たなければならない。**正本の `validate()` が検め、
   満たさない事象は赤にする。
5. 2026-08-07 時点の全 26 事象は凍結タプル（`VERIFY_GRANDFATHERED`）で祖父条項と
   する。この列を増やすことは検証の門を後ろへ動かすことであり、保証範囲の変更と
   して所有者判断を要する。

## 帰結

- **得られるのはセッションの独立までである（NONGOAL-001 第17項の限界）。**
  独立した組織による検証（`IV&V`）ではなく、検証役も実装者も同系 model なので、
  共通原因故障（同型の誤りを共有すること）は残余リスクとして残る。この記録は
  「独立セッションの判定」以上を主張しない。
- 検証の記録は `load_verify_records` が読み、`evaluator_outputs_latest` に
  数えられて故障注入の鮮度判定（ADR-120）の対象に入る。
- 運転手順（assurance-loop 技能 §2）に一行を足した —— FIX（最小修正）の後、`verify_fix.py`
  の記録が PASS になるまで `fixed: true` と書かない。
- `status` の `firing_points.unimplemented` は空になる。ADR-128 の二分の不変条件
  そのものは維持され、FORMALIZE（ADR-138）と合わせて INC-021 推奨#3 が閉じる。
- 門が課すのは記録の存在と判定の値だけである。判定の**中身**が正しいことは
  この門では保証されない —— それを測るのは評価器への故障注入（ADR-120）の側で
  ある。

<!-- 入れない: 複数決定、現行仕様の全文 -->
