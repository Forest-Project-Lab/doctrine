---
name: llm-context-pack
description: "Builds the minimal context for a specific task: gathers only the fewest documents whose coverage satisfies the task's requirements, excludes everything marked llm_context: never (RESEARCH, ARCHIVE), and shows the provenance (source document) of each fact so near-vocabulary documents are not confused. Use this skill when the user wants to \"build context for this task\", \"pack the minimal context\", \"what docs do I need for X\", \"assemble LLM context\", \"give me the smallest set of docs to work on Y\", or \"prepare context for the agent\"."
---

# llm-context-pack

タスク別の最小の文脈を集める。タスクの要求を満たす最少の文書だけを集め、`llm_context: never` の文書（RESEARCH・ARCHIVE）をすべて除外し、各事実の出所（出所となる文書）を示して、語彙の近い文書を取り違えないようにする。主な要求は R5。

決定論の処理は `collect-context.py` に委ねる。この技能は、被覆が曖昧なときに最少集合をどう選ぶかの判断を持つ。

## 何に頼るか

- `collect-context.py` — `llm_context` で絞り、出所つきの最少被覆集合を返す。
- §3.2 の `llm_context` 既定（always／task／never）と、`dep-graph.py` 経由の `depends_on` グラフを読み、被覆を計算する。

## 手順

1. タスクの記述を取り、触れる要求・仕様を特定する。
2. `collect-context.py` を走らせる。`llm_context: never` の文書（RESEARCH・ARCHIVE。本文は LLM へ渡らない。R5）をすべて除外する。`task` と関係する `always` を候補に入れる。
3. 最少被覆集合（§3.9）。タスクの要求を被覆する最少の文書を入れる。関係しない文書を足さない。縮める順序（§3.9）は、まず取りこぼしを減らし、次に重複を除く。
4. 出所の表示（§3.9）。各事実にその出所となる文書の id を付け、語彙の近い文書から来た事実を混ぜない。
5. 位置の配慮（§3.9）。最も重要な文書を集合の冒頭と末尾の両方に置く。端は注意を引きやすい。
6. 要点の復唱（§3.9）。長い本文の前に、モデルへ要点を先に書かせ、長い文脈での劣化に抗う。
7. 廃止本文は決して入れない（R5）。関係を超えて入れない。入力が長いこと自体が成功率を下げる（§7）。

## 常時集合の上限との関係

この技能は**タスク**の文脈を組む。常時集合（SessionStart の契約）の上限と縮小は `inject-contract.py`（Hook）が持ち、上限を超えたら `docs-curate` を促す。この技能は常時集合の結果を受け取るが、上限は持たない。

## 参照

詳細は `references/` に分ける。

- `references/min-set.md` — `dep-graph.py` 経由の被覆計算、取りこぼし優先・重複除去の縮小順序。
- `references/provenance.md` — 出所の表示の形式。
- `references/long-context.md` — §3.9 の根拠。なぜ端へ置くか、なぜ復唱するか、なぜ上限を設けるか。

## 保証限界

R9 の予防／検出／委ねるの切り分けを宣言する。

- 予防: `never` の本文を決定論で除外する（`llm_context` の絞りで、本文が LLM へ渡るのを防ぐ）。これは R5 について技能とスクリプトの対が与える唯一の本当の予防である。
- 検出: 被覆の経路に無い文書を入れすぎていないかを検出する。
- 委ねる: 被覆が曖昧なときの「本当に最少か」の最終判断は人間に委ねる。最適な上限の値は §7 の限界であり、構造ではなく運用と受入基準で定まる。人間の判断に委ねる。
