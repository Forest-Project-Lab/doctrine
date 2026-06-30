# フォルダと層の遅延生成（§3.7）

`docs-system-init` の既定は全ツリーを作らない。ドメインのフォルダと各層は、その型の文書が最初に作られるときに `doc-author` が生成する。空の足場を先に作らない。`[R8]`

## 生成の手順

1. その型の文書を書く直前に、`docs/<domain>/` が無ければ作る。
2. その型が要る層のフォルダだけを作る。
   - `SPEC`・`DATA`・`API` → `<domain>/spec/`
   - `ADR`・`CHANGE`・`IMPACT` → `<domain>/decisions/`
   - `IMPL` → `<domain>/implementation/`
   - `TEST`・`WATCH` → `<domain>/test/`
   - `RESEARCH` → `<domain>/research/`
   - `ARCHIVE` → `<domain>/archive/`
   - `ICD` → `<domain>/`（直下に `ICD.md`）
3. その文書に要らない層は作らない。要る型が出たときに、そのとき作る。

## 命名規則（§3.7）

- ファイル名は `<型コード>-<連番>-<短い主題>.md`（例 `SPEC-014-refund-policy.md`）。
- `id` はファイル名と一致させる。
- 日付は `ISO 8601`。
- 日本語ファイル名・空白・版番号の埋め込みは禁止。
- ICD だけは例外で、ファイル名を `ICD.md` 一つに固定する。

## init との分担

`docs-system-init` はドメインのツリーを作らない。利用者が「ドメインを作って」と頼んだら、このスキル（`doc-author`）へ回す。フォルダはそのとき生成される。
