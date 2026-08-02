---
id: TEST-028
title: 試験走行の証跡の受入
type: TEST
domain: packaging
status: current
owner: doctrine-maintainers
created: 2026-08-02
updated: 2026-08-02
sources: []
depends_on: [SPEC-028]
llm_context: task
---

# 試験走行の証跡の受入

## 受入基準への対応

SPEC-028 の受入基準の五項に一対一で対応させる。手立ては
`plugin/tests/test_meta.py` の `TestRunProvenance` に置く。走者の証跡を刷る関数だけを
別プロセスで呼び、全件を回さずに投影を検める。

| 確かめること | 手立て |
|---|---|
| `PROVENANCE:` の節に五つの項目が上の順で並ぶ | 節を解析して鍵の並びを突き合わせる |
| `python`・`platform`・`plugin` が実際の値を持つ | 未取得の印でないこと・空でないことを見る |
| `git` の届かない場所でも走行が落ちない | `PATH` から `git` を外して呼び、終了符号 0 と該当項目の未取得を見る |
| 統治対象の内容を刷らない | 節の中にプラグインの置き場所・作業ディレクトリ・統治木の名前が現れないことを見る |
| 証跡の失敗が合否を変えない | 上の `git` 無しの走行で終了符号が変わらないことを見る |

## 実物での確認

2026-08-02、実際の走行で次を得た。**`core.fileMode` の一行が、CI との食い違いを説明する。**

```text
SUMMARY: 1054 run, 1054 passed, 0 failed, 0 error, 0 skipped
RESULT: PASS
PROVENANCE:
  python: CPython 3.12.13
  platform: Linux 6.18.33.2-microsoft-standard-WSL2
  plugin: 0.8.0
  core.fileMode: false
  commit: ba61644deeeb4e70bb80132ec5b6ed158f0f6b55
```

同日、この一つの差で `_hookio.py` の実行ビットが手元では 1036 件すべて緑、CI では落ちた。
そのときこの節は無く、主張は環境を持っていなかった。

## この受入が赤いときの意味

**判定の依り所が読めない。** 走行の合否そのものは変わらない（証跡は合否に影響しない）が、
「試験が通った」が何の環境の話なのかを後から確かめられなくなる。

## 覆わないもの

- 証跡の無い判定を機械が咎めること（監査は試験の走行を見ていない。ADR-085 の保証限界）。
- 証跡が在れば内容が真であること。名指された試験が弱ければ、強い証跡が弱い主張を飾る。
- 刷る項目の網羅。判定を変える性質を列挙し切ったとは主張しない（SPEC-028 の制約3）。
