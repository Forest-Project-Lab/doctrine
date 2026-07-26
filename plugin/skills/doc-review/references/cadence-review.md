# 定例の点検（運用契約、§7）

次の三つは、機械では完全に閉じない。doc-review の定例でだけ閉じる。`[R6][R10]`

## 点検する三つ

1. **`canonical_for` 未付与**: 同じ事実が二重に書かれているのに、どれが正本か宣言されていない。付与の候補を挙げる。確定は人間（§7）。
2. **辞書外の訳語臭**: 一覧に無いカルク。逆翻訳テルで拾う。新しいカルクは、運用正本（`_system/glossary.md`）のカルク表に一行足す（`ADR` は要らない。§1）。
3. **意味的重複**: 語彙が違うが意味が重なる文書対。語彙的検出（`c-TF-IDF`・`Jaccard`）は言い換えを取りこぼすため、ここで人間と大規模言語モデル（`LLM`）が判断する。

## 周期の実体

周期は願望ではなく、記録と督促で回す。

- **実施記録**: 定例を終えたら `<統治木>/_system/.governance-state` の `last_cadence_review` に日付（`YYYY-MM-DD`）を書く。この記録が周期の正本である。
- **督促**: UserPromptSubmit の `gov-heartbeat.py` が、この記録と既定周期（30日。`.context-config.json` の `cadence_review_days` で変更可）を照合し、超過していれば会話の冒頭で定例を促す。人手の起動だけに頼らない。
- **臨時**: SessionStart の注入が `review_by` 超過・語彙的酷似・`canonical_for` 衝突を報せたときも、定例を前倒しで走らせる。

## 手順

1. 作業一覧を取る。`${CLAUDE_PLUGIN_ROOT}/scripts/docs-audit.py --root <統治木> --json` の `counts_by_check` と `findings` から、`near_duplicate`・`canonical_conflict`・`review_by_overrun` を拾う。
2. 点検する三つを、一覧の各項目について判断する。指摘は定義の在処へ書き戻す（カルク→運用正本の表、承認語→`ADR`＋辞書、正本宣言→`canonical_for`）。
3. 終えたら `last_cadence_review` を更新する。更新しなければ督促が鳴り続ける（記録しない定例は、無かったものとして扱う）。

## 監査との対

監査（`docs-audit.py`）は全件で、語彙的に酷似する文書対を助言として一覧化する。doc-review の定例は、その助言を起点に、意味の判断を加える。監査が構造の欠落を出し、doc-review が意味を閉じる。二つで対になる。
