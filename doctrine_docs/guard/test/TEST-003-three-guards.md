---
id: TEST-003
title: 三ガードの受入試験
type: TEST
domain: guard
status: current
owner: doctrine-maintainers
created: 2026-06-30
updated: 2026-07-29
sources: [plugin/tests/test_guard.py]
depends_on: [SPEC-003]
llm_context: task
---

# 三ガードの受入試験

## 受入基準への対応
SPEC-003 の受入基準を `plugin/tests/test_guard.py` の各クラスで確認する。`[R7]`

- `TestR7IcdDependency`: 受入シナリオ TC（番号は次のとおり）。TC-070（越境ICD宛=許可）・TC-071（越境非ICD宛=拒否、拒否文を一字一句照合）・TC-072（同ドメイン=許可）・TC-117（相手が deprecated でも許可、`status` 無関係）・TC-123（分類不能=fail-closed 拒否）・dangling 連れ合い（索引に無いが既知型=許可）。
- `TestPostBlock`: TC-073（Edit が違反を持ち込むなら PRE（書き込み前）で deny。ADR-076）・TC-073b（POST の block は突き合わせとして残る）・TC-074（MultiEdit の block）・TC-119（同一違反で Write も Edit も MultiEdit も PRE で deny）・ICD 宛の依存は追加の承認なしで allow・組み立て不能な統治文書の編集は deny・リンタは decision を出さない。
- `TestImmutability`: TC-075（無関係な現行文書の編集=許可）・TC-076（archive 下の Write/Edit=拒否）・TC-077（既存ADRの改変=拒否、carve-out の `status` 遷移=許可・本文変更=拒否）。
- 不変の開始点（ADR-095）: `proposed` の ADR の本文編集=許可、`accepted` の本文編集=拒否、**`accepted → proposed` の降格=拒否**（唯一の穴になりうる経路なので、carve-out の外に留まることを凍らせる）、`proposed → accepted` の昇格=許可、`archive/` 下の `proposed` な ADR=拒否（置き場所の不変は `status` に依らない）。**歯止め自身の実効を実測してある**（2026-08-03）: ガードの `proposed` の分岐を外すと落ち、戻すと通った。
- `TestDeleteSafety`・`TestPostDeleteSafetyTransition`: TC-078..081（降格・本文消し・Bash rm/git rm/mv=拒否、逆参照ゼロ=許可）・TC-118（block→張り替え→許可）・既存 deprecated や既存空本文の無関係な編集は誤って block しない。
- `TestBashOutputGrammar`: TC-132（Bash deny に additionalContext も block も無い）。
- `TestDeleteSafety` の #71 追加: ディレクトリ対象(rm -rf/git rm -r/git mv)の deny・依存なしディレクトリの allow・mv -t の引数逆転上書き deny・mv -t 新規名 allow。
- `TestTreelessProjectBoundary`（ADR-036）: 統治木の無いプロジェクトで depends_on を持つ他体系の Write=許可、型を持たない素のメモ+パス形式の依存=許可、対照として木が在れば木の外の stray 文書の越境依存=拒否。
- `TestEarlyOutNonDocs`: doctrine_docs/ の外の純粋な非文書（.py/.txt）の編集は依存グラフを組まずに allow し（グラフ構築の呼び出し回数がゼロ）、doctrine_docs/ 内の編集はグラフを組んで全ガードを当てる。フロントマターを持つ doctrine_docs/外の Write は早期通過せず Guard2（ICD依存ガード） が拒否する。doctrine_docs/ 外のパス（external/…）やシンボリックリンク経由で `id` を持つ統治文書を降格する Edit は早期通過せず Guard3（削除安全ガード） が拒否する。`id` を持たないが `domain`＋越境 `depends_on` を持つ doctrine_docs/外の文書型を編集した PostToolUse は早期通過せず Guard2 が block する。
- ADR-075: `status` 行の整形（空白2つ・タブ・末尾空白）を変えても降格の拒否が外れないこと。編集が生の全文へ当たること。
- ADR-075: シンボリックリンク経由で倉庫の文書を編集・著作できないこと（包含の判定が realpath）。
- ADR-075: `cd <dir> && rm <file>` と `git -C <dir> rm <file>` が拒否されること。`cd` の宛先を静的に決められない削除が拒否されること。削除の動詞を含まない経路には何も言わないこと。
- ADR-075: 現行でない文書の削除も、現行の逆依存が残るなら拒否されること（本文消しと判定が対称であること）。
- ADR-075: 既存 ADR のフロントマターの構文修復が通り、修復に見せかけた本文・鍵の書き換えは拒否されること。
- ADR-075: 判定を標準の書き出し口へ渡せないとき、PreToolUse が終了コード 2 へ倒れること。非 UTF-8 の locale でも拒否が消えないこと。

## 退行観点
WATCH-001 と突き合わせる。守るべき退行は二つある。一つは、削除安全を PRE から POST への遷移で判じること、すなわち、もとから deprecated だったり本文が空だったりする文書を、無関係な編集で取り違えて block しないことである。もう一つは、Bash の拒否を deny だけで行うことである。

## 合否基準
列挙した全 TC が合格し、R7 拒否文が原文とバイト単位で一致し、取り違えの block と取り違えの deny がともにゼロのとき、合格とする。

<!-- 入れない: 無関係な要求 -->
