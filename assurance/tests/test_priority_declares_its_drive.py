#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""優先順の表は、駆動源と待ち行列の有界性を宣言する（INC-051 推奨#1）。

INC-051 の形は、APPLY_FINDINGS(50) の待ち行列が**空にならない**のに、その下に
鮮度で駆動される ATTACK_EVALUATOR(60) が置かれていたことだった。鮮度駆動の
行動は毎反復挙がるので、上に無界の在庫が在れば**毎反復 2 番目に置かれ、先頭を
飛ばさない限り決して着手されない**。実測で DISCOVER 8 日・FORMALIZE 7 日・
承認済み計画の再現 7 日（30 件中 1 件のみ）と、飢餓は下位で一様に起きていた。

**ここは順序を裁定しない。**閾値や昇格の規則は優先順の表そのものの書き換えで
あり所有者判断である（推奨#0・ADR-131）。ここが捕らえるのは**表の形の誤り**
だけ —— すなわち「無界と分かっている在庫駆動の下に、鮮度駆動を置いた」という
配置である。裁定を待たずに、同じ形の再発だけを止める。

宣言を持たない行動を足せば赤になる。宣言は表と同じ場所に置き、**行動を足した
者が駆動源を言う**ことを強いる（言えない行動は、飢えるかどうかも言えない）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator  # noqa: E402


class PriorityDeclaresItsDriveTest(unittest.TestCase):
    def test_every_prioritised_action_declares_its_drive(self):
        """優先順の表に載る行動は、駆動源と有界性を宣言している。"""
        undeclared = sorted(set(orchestrator.ACTION_PRIORITY)
                            - set(orchestrator.ACTION_DRIVE))
        self.assertEqual(
            undeclared, [],
            "駆動源を宣言していない行動がある。在庫駆動か鮮度駆動か、待ち行列が"
            "有界かを ACTION_DRIVE に書くこと（INC-051 推奨#1）: %r" % (undeclared,))

    def test_no_declaration_without_a_place_in_the_table(self):
        """表に無い行動の宣言を残さない（消えた行動の宣言が古びる）。"""
        orphan = sorted(set(orchestrator.ACTION_DRIVE)
                        - set(orchestrator.ACTION_PRIORITY))
        self.assertEqual(orphan, [], "優先順の表に無い行動の宣言が残っている: %r"
                         % (orphan,))

    def test_the_declared_vocabulary_is_closed(self):
        for action, decl in sorted(orchestrator.ACTION_DRIVE.items()):
            self.assertIn(decl["drive"], ("在庫", "鮮度"), action)
            self.assertIn(decl["bounded"], (True, False), action)
            self.assertTrue((decl.get("why") or "").strip(),
                            "%s の宣言に根拠が無い" % action)

    def test_no_new_starvation_shaped_pair_appears(self):
        """飢餓の形の対は、所有者裁定待ちの既知の一件を除いて増えていない。

        既知の一件（APPLY_FINDINGS → ATTACK_EVALUATOR）は**見えなくしたのでは
        ない** —— 直すこと自体が優先順の表の書き換えで、ADR-131 が表を凍結し
        INC-051 推奨#0 が所有者判断を立てている。裁定待ちであることを記録した
        うえで、**新しい対が生えたら赤**にする。
        """
        pairs = set(orchestrator.starvation_shaped_pairs())
        known = set(orchestrator.STARVATION_SHAPED_OWNER_PENDING)
        self.assertEqual(
            sorted(pairs - known), [],
            "新しい飢餓の形が生えた。上が空にならない限り下は着手されない"
            "（INC-051）: %r" % (sorted(pairs - known),))

    def test_the_owner_pending_exemption_still_has_its_basis(self):
        """免除の根拠を機械で確かめる —— 処遇が `owner` のまま在るか。

        裁定が下りて処遇が動けば、免除は根拠を失って赤になる。免除が
        自分の期限を持つ形にしてある（書けば通る免除にしない）。
        """
        for pair, ref in sorted(
                orchestrator.STARVATION_SHAPED_OWNER_PENDING.items()):
            self.assertTrue(
                orchestrator._owner_pending_is_real(ref),
                "%r の免除は %s が『所有者判断』であることに依っているが、"
                "その処遇が台帳に無いか、既に動いている。免除の前提が消えた"
                % (pair, ref))

    def test_no_exemption_without_a_pair_that_needs_it(self):
        """要らなくなった免除を残さない（古びた免除は次の目隠しになる）。"""
        pairs = set(orchestrator.starvation_shaped_pairs())
        stale = sorted(set(orchestrator.STARVATION_SHAPED_OWNER_PENDING) - pairs)
        self.assertEqual(stale, [], "対が解消したのに免除が残っている: %r" % (stale,))

    def test_the_check_would_catch_the_incident_as_it_stood(self):
        """事象が起きた当時の表を与えれば、この検査は赤になる。

        現在の表で緑であることは、検査が効いていることの証拠にならない
        （直したのだから緑である）。**当時の配置を再現して赤を確かめる。**
        """
        as_it_stood = {"APPLY_FINDINGS": 50, "ATTACK_EVALUATOR": 60}
        problems = orchestrator.starvation_shaped_pairs(priority=as_it_stood)
        self.assertTrue(
            problems,
            "INC-051 が起きた当時の配置（APPLY_FINDINGS 50 / ATTACK_EVALUATOR 60）"
            "を与えても赤にならない。検査が形を捕らえていない")
