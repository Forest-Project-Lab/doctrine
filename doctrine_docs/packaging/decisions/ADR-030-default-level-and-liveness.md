---
id: ADR-030
title: 既定 Level 2 を追認し、生存性と捕捉は段差に依らず動くと定める
type: ADR
domain: packaging
status: accepted
owner: doctrine-maintainers
created: 2026-07-26
updated: 2026-07-26
sources: [全体批判レビュー 2026-07-26]
depends_on: [ICD-008]
---

# 既定 Level 2 を追認し、生存性と捕捉は段差に依らず動くと定める

## 背景

「既定は Level 2」は docs-system-init と `scaffold.py` が事実上決めていたが、根拠の ADR が無かった(体系自身の「決めたら ADR」に反する未記録の決定)。また Level 2 では監査・`review_by` 点検・起動後ガード・レビューのナッジが自主停止するため、「導入すれば勝手に回る」という利用者の期待と衝突していた。さらに inject-contract は Level を見ずに docs-curate を促す一方、docs-curate は Level 3 未満で動かないと宣言し、促しと拒否が往復していた。

## 却下した選択肢

- 既定を Level 3 以上へ上げる: 小規模の導入に `depends_on` の運用を強い、§4.4「痛みが出た所だけ足す」に反する。
- 生存性も段差で止める: 死活の可視性は保護であって重さではない。止めると全停止に気づけない(実際に起きた)。

## 決定

三つを定める。(1) 既定 Level は 2 とする(scaffold の現行挙動の追認)。(2) 統治の生存性(R11: `gov-heartbeat.py`・注入内の死活警告)と会話知識の捕捉(R12: `capture-nudge.py`・`precompact-dump.py`・捕捉の印)は、`.docs-level` の段差に依らず全 Level で動く。段差は軽量化であり、死活の可視性と記録の促しは削らない。(3) docs-curate の Level 要求は作業別に分ける(常時集合の縮小と体系外 .md の分類は全 Level、逆参照の確認を要する降格・削除は Level 3 以上)。

## 帰結

- 促しと拒否の往復が解消する(Level 2 でも促された作業の一部は必ず実行できる)。
- ADR-019 の自主停止の一覧に「止めないもの」の側が明文で加わる。
- 既定 Level を変えるときは本 ADR を置換する。
