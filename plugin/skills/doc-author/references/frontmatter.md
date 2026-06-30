# フロントマターの欄（§3.4）

全文書の先頭に `YAML` フロントマター（`---` で囲む先頭の構造化メタデータ）を置く。必須は絞る。`[R3]`

## 必須（Level 2 以降）

`id`・`title`・`type`・`domain`・`status`・`owner`・`updated`・`sources`。
- `id`: `<型コード>-<連番>`。ファイル名と一致させる。
- `domain`: どの区画の文書か。`_system` はシステム階層。
- `status`: §3.3 の語彙。型ごとの許可リストはリンタが点検する。
- `owner`: 陳腐化の責任の所在。

## 型で追加が要るもの

- `DECIDED`・`WATCH`: `review_by`（次回点検期限）を必須にする。古びの検出に使う。

## Level の段差で足すもの

- Level 3 以降: `depends_on`（前提とする文書、`R7` の対象）・`impacts`（変更時に波及する先）。
- Level 4 以降: `canonical_for`（この文書がそのトピックの正本である宣言）。同じ事実が二重に書かれた型から付ける。
- `created` は推奨だが必須ではない（テンプレートには含める）。

## 値の規則

- 日付は `ISO 8601`（`YYYY-MM-DD`）。
- リスト欄（`sources`・`depends_on`・`impacts`・`canonical_for`）は空でもよいが、空白の値と空リストと欠落を取り違えない。読むときは `_frontmatter.py` の `as_list` を通す。
