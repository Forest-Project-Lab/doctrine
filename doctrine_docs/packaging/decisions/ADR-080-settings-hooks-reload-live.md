---
id: ADR-080
title: Hook 設定は固定されない。settings 由来は live reload される前提へ置き換える
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-08-02
updated: 2026-08-02
sources: ["外部レビュー 2026-07-31", "Claude Code 公式 settings 文書 2026-08-02 確認", "doctrine#157"]
depends_on: [SPEC-019]
llm_context: task
---

# Hook 設定は固定されない。settings 由来は live reload される前提へ置き換える

## 背景

`ADR-032`（追認）は「Hook の設定はセッション開始時に読み込まれ、以後固定される」を運用の
前提として据え、`DECIDED-001` 事実8 の後段がそれに載っていた。ADR-032 は自ら次を書いていた。

> この前提自体は実行環境(Claude Code)の仕様であり、機械で追えないため、EXT アンカー
> (EXT-001)の `review_by` で定期再検証する。……**実行環境がこの挙動を変えたら、EXT-001 の
> 再検証で拾い、本 ADR を置換する。**

**その前提は偽である。** 現行の公式 settings 文書が明文で否定している（2026-08-02 確認）。

> "Claude Code watches your settings files and reloads them when they change, so edits to
> most keys apply to the running session without a restart. This includes `permissions`,
> `hooks`, and credential helpers like `apiKeyHelper`. The reload covers user, project,
> local, and managed settings, and the `ConfigChange` hook fires for each detected change."

`EXT-001` の `review_by` は 2026-10-26 で、定例の再検証はまだ走っていない。反証は外部
レビューという別経路から先に来た。**置換の仕掛けは正しく働いた。期日より早く来ただけである。**

重いのは中身である。モデルはセッション冒頭に注入された契約を読んで動く。契約は固定前提で
書かれているのに、実際の hook は差し替わりうる。**モデルが読んだ契約と、実際に発火する
ガードが食い違う窓**が開く。これは確定事実12「フックの境界は沈黙して開かない」を、
境界の外側から破る経路である。

## 却下した選択肢

**「全部 live reload される」に置き換える。** 層を潰すことになる。settings 由来の hooks は
reload されるが、インストール済み plugin の hooks はセッション中に保持され、
`/reload-plugins` で再読込される。挙動が違うものを一つの前提にまとめると、また偽になる。

**`ConfigChange` を配線して、変更を検知したら protected action を拒否する。** 筋は通るが、
本 ADR で決めるべきは前提の訂正である。何をどう拒否するかは、再認証の設計（何を attest
するか・どこまで拒むか）を含む別の判断であり、一つの ADR に混ぜない。

**前提を訂正せず、運用の注意書きだけ足す。** `DECIDED-001` は確定事実の正本である。
偽の事実を置いたままの注意書きは、読んだ者を二重に迷わせる。

## 決定

**`ADR-032` を置換する。前提を層ごとに分けて書き直す。**

1. **settings 由来の hooks**（user・project・local・managed）は、セッション中に live
   reload される。変更ごとに `ConfigChange` が発火する。
2. **インストール済み plugin の hooks** は、セッション中は保持される。`/reload-plugins`
   で hooks・skills・agents などが再読込される。
3. したがって「設定を変えたら新しいセッションで反映を確かめる」は、plugin 層にだけ当たる
   運用である。settings 層では、変えた直後の同一セッション内で既に新しい hook が動く。
4. `DECIDED-001` 事実8 の後段を、この二層の記述へ書き換える。根拠を ADR-032 から本 ADR へ
   張り替える。
5. `EXT-001` に、この二層の挙動を依存として登録する。
6. **モデルが読んだ契約と実際の hook が食い違いうる**ことを、保証限界として明記する
   （`NONGOAL-001`）。塞ぐ手立て（`ConfigChange` の配線・再認証）は別の決定で裁く。

## 帰結

- 確定事実が、実行環境の仕様に照らして真になる。
- 「設定を変えたら新しいセッションで確かめる」という運用が、どの層に当たるかが明確になる。
- 保証限界: settings を変えた瞬間から、モデルが冒頭で読んだ契約は古くなりうる。
  いまの体系はその食い違いを検知しない。`ConfigChange` は配線していない。
  **これは新たに生まれた穴ではなく、もともと開いていた穴が可視になったものである。**
- ADR-032 の置換の仕掛け（EXT アンカーの `review_by` で定期再検証し、変わったら置換する）が
  実際に機能したことの記録になる。ただし発火したのは定例ではなく外部レビューであった。
  定例の周期（`review_by`）が、実行環境の変化の速さに追いついていない可能性がある。

<!-- 入れない: 複数決定、ConfigChange の配線と再認証の設計（別の決定）、現行仕様の全文 -->
