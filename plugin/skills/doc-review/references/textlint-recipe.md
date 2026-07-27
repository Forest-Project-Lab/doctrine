# textlint-ja 連携レシピ（任意・CI 用。#82）

doctrine 本体は標準ライブラリだけで動く（外部の pip / npm 依存を作らない。DECIDED 事実7）。文章規範（R10）のうち、一文の長さ・サ変名詞＋「を行う」・ですます／である混在などは、textlint-ja の技術文書向けプリセットが既に機械化している。これらを CI で使いたい導入先のために、**任意の**レシピを示す。本体には組み込まない。

## 位置づけ

- doctrine の用語チェッカーが担うのは、承認語の強制・禁止同義語・禁止表現（カルク辞書）・逆翻訳テル（doc-review）である。カルク辞書と逆翻訳テルに相当する既存ルールは textlint 側に無く、ここは doctrine の独自性である（重ねて持たない）。
- textlint が担うのは、上に挙げた一般の日本語技術文書の規範である。doctrine のカルク検出と**重複しない**部分だけを足す。

## レシピ（導入先の CI で任意に足す）

`.textlintrc.json`（例）:

```json
{
  "rules": {
    "preset-ja-technical-writing": {
      "sentence-length": { "max": 100 },
      "no-mix-dearu-desumasu": true,
      "ja-no-successive-word": true
    }
  }
}
```

CI の一段（例）:

```yaml
- name: textlint (任意・日本語文章規範)
  run: |
    npm ci
    npx textlint "doctrine_docs/**/*.md" spec/*.md
```

## 注意

- これは**任意**である。本体の CI（`checks.yml`）には足さない（本体は標準ライブラリのみ）。導入先が自分の CI に足す。
- doctrine の禁止同義語・カルク・逆翻訳テルは、doctrine 側（`term-check.py` と doc-review）で引き続き担う。textlint とは役割を分ける（同じ点検を二重に持たない）。
- 出典: textlint-ja の技術文書向けプリセット（`textlint-rule-preset-ja-technical-writing`）。2026-07 の競合調査より。
