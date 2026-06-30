---
name: doc-review
description: "Reviews a document's prose and positioning against the writing norms: runs the term checker alongside (unapproved terms, banned synonyms, banned calque expressions, undefined jargon), and judges calque the linter cannot catch using the back-translation tell (translate the suspect phrase back to English; if it lands on an English idiom, it is calque). On a defined cadence it also checks for missing canonical_for, off-dictionary translationese, and semantic duplication. Use this skill when the user wants to \"review this doc\", \"check the writing\", \"proofread\", \"review terminology\", \"check for calque / 訳語臭\", \"is this prose clear\", or runs the periodic \"docs review / 定例レビュー\"."
---

# doc-review

## 役割

文章規範と位置づけを見直す。用語チェッカーを併走させ、辞書外のカルク（訳語臭）を逆翻訳テルで判定する。満たす要求は §2 の `R6`・`R10`（要求番号は §2 の登録簿で定める）。

**著述・編集のたびに走らせる**。doc-author の最後の手順がこのスキルを回す（手順 11）。記載されれば動く、を既定にする。定例は、それでも残る `canonical_for` 未付与・意味的重複の点検に充てる。

**指摘は定義の在処へ書き戻す**。一覧外のカルクは用語辞書の正本（§1 のカルク表）へ一行足す。新しい承認語は ADR と用語辞書の更新をもって加える。型コードは登録簿（§3.2）、要求タグ（`[R番号]`）は §2 で既に定義済みとして扱い、辞書に二重定義しない。これにより、同じ指摘が次から機械的に閉じる。

## 委ねる先（決定論は scripts へ）

- `${CLAUDE_PLUGIN_ROOT}/scripts/term-check.py`（リンタの一機能）— 禁止同義語・禁止表現（カルク辞書）・未定義語を機械的に照合する。このスキルはその傍らで走る（用語チェッカーを併走）。
- 用語辞書の正本（§1）— 語彙を二重定義しない。強制する（`R6`）。
- `${CLAUDE_PLUGIN_ROOT}/scripts/term-extract.py` の候補 — 新しい承認語を提案するときの助言に使う。採否は人間。

## 手順

1. 対象文書に用語チェッカーをかけ、機械的な指摘を集める（禁止同義語・一覧のカルク・未定義語）。
2. 文章の規則を当てる（§1）。一文一義。サ変名詞＋「を行う」を動詞にする。「することができる」を「できる」にする。専門語・略語を初出で定義する。抽象語を具体語・数値・固有名に置き換える。同じ概念は同じ語で書く。
3. カルクは逆翻訳テルで判定する（§1）。怪しい箇所を英語に戻し、英語の慣用句・固定表現にそのまま戻るなら、それはカルクである。直すときは英語を捨て、日本語で選び直す。擬陽性を避ける。定着した借用語（`データ`・`リスク`）と普通の否定文はカルクではない。
4. 位置づけを点検する。型は正しいか。置き場所は正しいか。`llm_context` は正しいか。正本か投影か。よそが正本である事実を二重に書いていないか。
5. 定例でだけ閉じる点検（運用契約、§7）。`canonical_for` 未付与・辞書外の訳語臭・意味的重複。仕様はこれらに周期を定める（§4.1／§7）。doc-review がこれを定例で走らせる。手動の依頼だけに頼らない。
6. 本当に新しい承認語が要るなら、`term-extract.py` の候補を証跡にして提案する。ただし `ADR` と用語辞書の更新を必須にする（§1）。自分で承認しない。新しいカルクは、別ファイルを作らず、§1 の表に一行足す。
7. 指摘は自己修正のための助言として出す。硬い拒否はしない（それはリンタとガードの役目）。

## 詳細（references/）

- `references/back-translation-tell.md` — §1 カルク表の実例、擬陽性の避け方。
- `references/writing-rules.md` — §1 文章の規則の展開。
- `references/cadence-review.md` — 定例の `canonical_for`・訳語臭・意味的重複の手順、監査との対。
- `references/term-addition.md` — `ADR` と用語辞書の更新の流れ、`term-extract` の候補の使い方。

## 保証限界

- **予防**: 何も予防しない。この見直しは助言である。
- **検出**: 機械的には用語チェッカーで（一覧の項目だけ）。判断的には逆翻訳テルと位置づけで。
- **委ねる**（§7 の核）: 意味的重複か矛盾かの最終判断、§1 の一覧に無いカルク、`canonical_for` の付与。これらは doc-review の定例でしか閉じない。完全な検出は埋め込みか大規模言語モデル（`LLM`）が要り、機械の手は届かない。doc-review が `R6`・`R10` の人間と判断の層を担う。
