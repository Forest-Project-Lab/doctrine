---
id: SPEC-003
title: 三ガードの判定規則（不変・ICD依存・削除安全）
type: SPEC
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [spec/doctrine.ja.md §4.2]
depends_on: [REQ-004, ICD-001, ICD-002]
llm_context: task
---

# 三ガードの判定規則（不変・ICD依存・削除安全）

`policy-guard.py` の判定規則を定める。三ガード（不変=Guard1（不変性ガード）・ICD依存=Guard2（ICD依存ガード）・削除安全=Guard3（削除安全ガード））を不変→ICD依存→削除安全の順に当て、最初に拒否したガードで止める。登録簿の解決は ICD-001 に、ドメインと逆依存の解決は ICD-002 に依存する。`[R4]`（R4=変更耐性）`[R7]`（R7=境界明瞭）`[R8]`（R8=最小性）

## 入出力
入力は Hook の標準入力 JSON（フロントマター=文書冒頭のメタデータ）。`hook_event_name` と `tool_name` を見て、どの処理に振り分けるかを自分で決める。

- PreToolUse `Edit|Write|MultiEdit`: 三ガードを順に当て、`permissionDecision: "allow"` または `"deny"`（理由つき）を返す。
- PreToolUse `Bash`: 削除安全だけを当て、deny または allow を返す（deny だけを使う）。
- PostToolUse `Edit|MultiEdit`: 書き込んだファイルを読み直し、ICD依存または削除安全に違反していれば `decision: "block"` を、なければ空オブジェクトを返す。ADR-076 以降、これは**主たる門ではなく突き合わせ**である（外部の競合・tool 実装差を拾う）。主たる拒否は PreToolUse に立つ。

各ガードの規則:

- 不変（Guard1, `[R8]`）: `<domain>/archive/` 下の編集を拒否する。加えて、置き場所に依らず、ディスク上の実効 `status` が archived の既存文書の編集も拒否する（ADR-027。パス判定だけでは倉庫の外に居る archived 文書が編集自由になる）。現行から archived への遷移の書き込み自体は対象外とする（それは降格の操作であり、削除安全ガードが逆参照ゼロを守る）。既存の `type:ADR` ファイルの改変も拒否する。**ただし不変は `accepted` から始まる**（ADR-095）—— ディスク上の実効 `status` が `proposed` の ADR は、まだ決定ではなく下書きなので本文を直せる。判定はディスクの状態で行い、編集後の申告では行わない。**逆向き（`accepted → proposed`）は carve-out の外に留める** ので、受理済みを下書きへ落として書き換える道は開かない。語彙は最初から `proposed` を許し、carve-out も `proposed→accepted` を明記していたのに、ガードが存在した瞬間から凍らせていたため、木に `proposed` の ADR は一件も生まれなかった（実測）。ただし carve-out だけは許す。carve-out とは、`status` を proposed→accepted・accepted→superseded・accepted→deprecated の範囲で動かし、`superseded_by` と `updated` を付ける編集をいう。ADR に誤りを見つけたときの正規の直し方は ADR-044 が定める（未コミットは削除して作り直す・マージ済みは後継で置換する。作成時に用語とフロントマターを正すのが第一）。
- ICD依存（Guard2, `[R7]`）: 変更後の全文からフロントマターを読み、`depends_on` の各 dep を調べる。相手のドメインが自ドメインと異なり、しかも相手の型が ICD でなければ拒否する。dep の `status` は見ない（C12: 整合判断id）。**Write・Edit・MultiEdit のいずれも書き込む前に判ずる（ADR-076）。** 全文は Write なら `content`、Edit・MultiEdit ならディスクの生の全文へ編集を当てたもの（Guard1・Guard3 と同じ `_proposed_text`）とする。全文を組み立てられないとき、対象が統治文書（on-disk に `id` を持つ、または統治木の中）なら拒否する（ガードが判定を持たないまま allow へ倒れる経路を作らない）。体系外の非文書は従来どおり通す。
- 削除安全（Guard3, `[R4]`）: 現行（current/accepted）から deprecated/superseded/archived への降格、本文を空にする編集、Bash の `rm`・`git rm`・`mv` を対象とする。その文書を指す現行の逆依存が残っているとき、これらを拒否する。逆依存は graph の `reverse_current_dependents(id)` で引く。

## 制約
- 統治木の無いプロジェクト（doctrine 未導入の土地。`walkup_docs_root` が木を一つも解決できない）では、ICD依存・削除安全の二ガードは発火しない（ADR-036）。`depends_on` 風のキーを持つ他体系（Obsidian 等）の Write/Edit を誤って deny/block しない。判定は「このファイルのプロジェクトに木が在るか」であって「この文書が木の中か」ではない。木が在れば、木の外の stray 文書に対しても以下の規則を従来どおり当てる。この境界は、リンタの体系外無発火（ADR-024）をガードへ一貫適用したものである。
- 三ガードを不変→ICD依存→削除安全の順で当て、最初に拒否したガードで止める。不変を当てた後、対象を realpath で解決した実体が doctrine_docs/ の木の外にあり、かつ ICD依存・削除安全のどちらも発火しえない（content がフロントマターを持たない Write、または on-disk に `id` を持たない Edit/MultiEdit）ときは、依存グラフを組まずに allow してよい。これは判定を変えない早期通過であり、上の削除安全規則を弱めない。`id` を持つ文書（非 doctrine_docs/ パスやリンク経由を含む）は早期通過せず、逆依存が残る降格は従来どおり拒否する。
- ICD依存ガードは `status` を見ない（C12）。構造、すなわちドメインと、型が ICD かどうかだけを見る。
- R7 の拒否文は spec §4.2 を一字一句なぞる: `<dep> は <相手ドメイン> の内部です。<相手ドメイン> の ICD 宛にしてください。`
- C13（整合判断id）の分岐: 構文は正しく索引に無い dep（dangling）は許す（死リンクは監査が見つける）。登録簿が接頭辞から型を読めない dep（UNKNOWN（不明））は、安全側に倒して拒否する。
- Bash 経路は deny だけを使い、文脈の注入（additionalContext）も block も使わない。コマンドを `; && || | 改行` で分割し、各 `rm`・`git rm`・`mv`（`git mv` を含む）の対象を取り出す。`mv` の対象は src 群に加え、宛先側も上書き（=宛先の内容の破壊）になる分を含める: 宛先が既存ファイルならその宛先、宛先が glob なら展開した各既存ファイル（展開不能は安全側で拒否）、宛先が既存ディレクトリなら中の同名（src の basename）既存ファイル。新しい名前への改名だけは破壊でないので含めない。`mv` の `-t`／`--target-directory[=DIR]` は引数順を逆にする（`-t DIR SRC…`）ため、DIR を宛先・位置引数をすべて src として解析する（取り違えると宛先の上書き検査が誤対象になる。#71）。
- 対象がディレクトリのとき（`rm -rf <domain>`・`git rm -r`・`git mv <domain>` 等）は、配下の `.md` を再帰列挙して一つずつ検査する（#71）。単一ファイル指定より、ドメインごと消す方が高頻度の破壊経路であり、素通りさせない。
- Bash 削除安全が対象としないもの（既知の限界）: `cp` による上書き、`>`／`>>` のリダイレクトによる切り詰め、任意スクリプト経由の削除。列挙した動詞（`rm`・`git rm`・`mv`・`git mv`）以外の破壊経路は事後の監査（逆参照・アーカイブ整合）で拾う。予防は「よくある経路」に限る（§7）。
- PostToolUse の削除安全は PRE（書き込み前）から POST（書き込み後）への遷移で判じる。POST の全文に編集を逆向きに当てて PRE を復元し、本当に降格・本文消しが起きた組だけを咎める。
- 段差ゲート（ADR-019）: 対象の体系の `doctrine_docs/_system/.docs-level` が `level: 2` のとき、PostToolUse の再判定（block）は静かに済ませる（縮小構成に起動後ガードは無い）。PreToolUse の予防は Level 2 でも全て残す。目印が無い・不正なときは全構成として扱う。
- 編集はディスクの生の全文へ当てる。再構成は生が読めないときの退避に限る。整形の揺れ（余分な空白・タブ・引用符・コメント行）で判定が外れてはならない（ADR-075）。
- 包含の判定は `realpath` に対して行う。リンク経由で倉庫の外に見せかける経路を塞ぐ（ADR-075）。
- 既存 ADR の carve-out に構文修復を含む。編集前に構文の誤りがあり、編集後に無く、本文が変わらず、誤りに関わらない鍵の値も変わらないときに限る（ADR-075）。
- Bash 経路は区切りを順に走り、`cd`／`pushd` で基準を移す。`git` の大域オプション（`-C` ほか）を読み飛ばしてから部分コマンドを判じる。基準を静的に決められない経路は拒否する。削除の動詞を含まない経路には何も言わない（ADR-075）。
- 削除（`rm`／`git rm`／`mv`）は対象の `status` を問わない。削除は状態に依らず現行の依存先を死リンクにする（ADR-075）。

## エラー時挙動
- 不変ガードと削除安全ガードが落ちたら、安全側に倒して deny する（「ガード異常、手で確認」）。
- ICD依存ガードは、doctrine_docs/ の外にある、フロントマターを持たない純粋な非文書の Write のときだけ、安全側に通して allow する。それ以外の例外は安全側に倒して deny する。
- 展開できない glob を含む削除コマンドは、安全側に倒して拒否する。
- Hook 事象では main から例外を投げない。判定は JSON に載せ、終了コードは常に 0 を返す。経路判定で落ちたときは、実行時例外の要約をエラージャーナル（書式の正本は SPEC-021）へ最善努力で残す（ADR-074）。

## 実装の指紋

対象はADR の許可遷移と許可キー。更新は `trace-index.py --id SPEC-003` が返す行を写す（ADR-061）。

- sha256:734cc0bb328183c4b8a99e351bf58eb9c6a43c704b718f1aff4adfb425504293

## 受入基準
TEST-003 が次を確認する: 受入シナリオ TC（番号は次のとおり）。TC-070..072（越境ICD許可・非ICD拒否・同ドメイン許可）、TC-117（相手 `status` 無関係）、TC-123（分類不能=拒否）、dangling 連れ合い（=許可）、TC-075..077（不変）、TC-078..081（削除安全）、TC-118（block→張り替え→許可）、TC-119（Write deny と Edit block が同一違反）、TC-132（Bash deny に additionalContext も block も無い）。加えて、`mv` の宛先が既存の被依存文書なら deny、新パスへの改名なら allow。archived の不変（倉庫の外でも deny、現行→archived の遷移は allow）は `plugin/tests/test_liveness_capture.py` が確認する（ADR-027）。

<!-- 入れない: 廃止、検討、実装コードの写し -->
