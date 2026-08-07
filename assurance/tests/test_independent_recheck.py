#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""抜取りの独立再判定の決定論試験（SDK 不要・通信不要）。

束で速く回した判定の質が落ちていないかは、**同じ評価器の一致では言えない**
（運転手順 §4「AI の一致は客観的証拠でない」）。読むのは不一致の中身であり、
不一致が出た項は判定を取り下げて台帳へ戻す。

凍結したいこと:
- 抜取りが決定論であること（種を与えれば同じ標本。実時計を読まない。WATCH-001 第11項）。
- 独立の判定に、前の判定が渡らないこと（渡ると独立でなくなる）。
- 不一致の項が**未割当の UNKNOWN へ戻る**こと —— そうして初めて正本が
  MAP_COVERAGE として拾い直す。戻さないと不一致は台帳に埋もれる。
- 一致した項の判定を書き換えないこと（実装者は評価者の判定を書き換えない。ADR-115）。
- 一致率を成果として持たないこと（帳簿の鍵に置かない）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import independent_recheck, orchestrator, prompts  # noqa: E402


def _entry(key, disposition="対応計画あり", assigned=True):
    e = {"key": key, "disposition": disposition}
    if assigned:
        e["assigned_at"] = "2026-08-07T06:00:00Z"
        e["assigned_by"] = {"index_sha256": "a" * 64}
        e["reassessments"] = [{"disposition": "UNKNOWN"}]
    return e


class SamplingTest(unittest.TestCase):
    def test_sample_is_deterministic_for_a_seed(self):
        """同じ種なら同じ標本。実時計や無種の乱数を読まない。

        試験が実時計を読むと、誰も何も変えていないのに日が変わって赤くなる
        （WATCH-001 第11項。2026-08-03 に実際に起きた）。抜取りも同じで、
        再現できない標本は「その標本で測った」と言えない。
        """
        pool = [_entry("K%d" % i) for i in range(50)]
        a = independent_recheck.sample(pool, 10, seed=7)
        b = independent_recheck.sample(pool, 10, seed=7)
        c = independent_recheck.sample(pool, 10, seed=8)
        self.assertEqual([e["key"] for e in a], [e["key"] for e in b])
        self.assertNotEqual([e["key"] for e in a], [e["key"] for e in c])

    def test_sample_only_takes_judged_entries(self):
        """未割当の項は抜取らない。判定の無い項に「再」判定は無い。"""
        pool = [_entry("judged"), _entry("fresh", assigned=False)]
        got = independent_recheck.sample(pool, 5, seed=1)
        self.assertEqual([e["key"] for e in got], ["judged"])

    def test_sample_does_not_exceed_the_pool(self):
        pool = [_entry("K%d" % i) for i in range(3)]
        self.assertEqual(len(independent_recheck.sample(pool, 25, seed=1)), 3)


class IndependenceTest(unittest.TestCase):
    def test_prior_judgement_is_not_in_the_prompt(self):
        """独立の判定に前の判定を渡さない。

        渡せば、独立ではなく追認になる。DISCOVER と CHALLENGE を別々の一回限り
        セッションに分ける規律（運転手順 §4）と同じ理由である。
        """
        # 五値の語そのものは憲章（採点規準の説明）に必ず出る。漏れを見るのは
        # **対象の一件ごとの記述**であり、そこに前の判定が混じっていないこと。
        principles = [{"key": "K1", "title": "題", "statement": "原則",
                       "category": "分類", "applicability": "当てはめ",
                       "suggested_oracle": "oracle"}]
        text = prompts.build_map_coverage_prompt(principles, "索引の本文")
        block = text.split("--- 割当の対象")[1].split("--- 対象ここまで ---")[0]
        for leak in ("対応計画あり", "実装・試験・証拠あり", "非該当で理由あり",
                     "assigned_at", "reassessments", "disposition"):
            self.assertNotIn(leak, block, "前の判定が漏れている: %s" % leak)

    def test_recheck_passes_only_principles_to_the_builder(self):
        """組み立て関数が受け取るのは原則の本体だけで、台帳の項ではない。

        台帳の項を渡せる形にしておくと、いつか前の判定ごと渡る。
        """
        import inspect
        sig = inspect.signature(prompts.build_map_coverage_prompt)
        self.assertEqual(list(sig.parameters), ["principles", "system_index_text"])

    def test_recheck_uses_only_the_shared_prompt_builder(self):
        """プロンプトは prompts.py の組み立て関数だけを使う（運転手順 §4）。"""
        import inspect
        src = inspect.getsource(independent_recheck)
        self.assertIn("build_map_coverage_prompt", src)


class DisagreementTest(unittest.TestCase):
    def test_disagreement_returns_the_entry_to_unmapped(self):
        """不一致は判定を取り下げ、未割当の UNKNOWN へ戻す。

        「UNKNOWN へ戻す」だけでは足りない —— 割当済みの UNKNOWN は評価の結論
        であって未評価ではなく、正本は次の行動に挙げない（INC-006 で分けた）。
        assigned_at を落として初めて MAP_COVERAGE が拾い直す。
        """
        entry = _entry("K1", "実装・試験・証拠あり")
        independent_recheck.withdraw(entry, "独立の再判定が 対応計画あり を返した")
        self.assertEqual(entry["disposition"], "UNKNOWN")
        self.assertNotIn("assigned_at", entry)
        self.assertIn("独立の再判定", entry["reason"])

    def test_withdrawal_keeps_the_previous_judgement_in_history(self):
        """取り下げても前の判定を消さない（ADR-130）。"""
        entry = _entry("K1", "実装・試験・証拠あり")
        before = len(entry["reassessments"])
        independent_recheck.withdraw(entry, "不一致")
        self.assertEqual(len(entry["reassessments"]), before + 1)
        self.assertEqual(entry["reassessments"][-1]["disposition"],
                         "実装・試験・証拠あり")

    def test_withdrawn_entry_is_counted_as_unmapped(self):
        """取り下げた項を正本が未評価として数える（読む段が在ることの確認）。

        走らせ手を足すときは、その成果を正本が読む段も同時に足す
        （INC-012・INC-015）。ここでの読む段は coverage_status であり、
        取り下げが unmapped に現れることがその証拠になる。
        """
        entry = _entry("K1", "実装・試験・証拠あり")
        independent_recheck.withdraw(entry, "不一致")
        cov = {"entries": [entry]}
        self.assertEqual(orchestrator._count_unmapped(cov), 1)

    def test_agreement_does_not_rewrite_the_entry(self):
        """一致した項は触らない。実装者は評価者の判定を書き換えない（ADR-115）。"""
        entry = _entry("K1", "対応計画あり")
        snapshot = dict(entry)
        independent_recheck.apply_verdict(entry, "対応計画あり", "同じ")
        self.assertEqual(entry["disposition"], snapshot["disposition"])
        self.assertEqual(entry["assigned_at"], snapshot["assigned_at"])


class LedgerKindTest(unittest.TestCase):
    def test_recheck_evidence_kind_is_declared(self):
        """台帳に現れる種別は必ず宣言する（ADR-124）。

        宣言の無いファイルが台帳に在るとレーンの自己検査が赤になる。
        """
        kinds = [k["match"] for k in orchestrator.LEDGER_KINDS]
        self.assertIn("recheck-*.json", kinds)

    def test_recheck_kind_declares_why_it_is_not_read(self):
        """読む関数か、読まない理由か、ちょうど一方を持つ（ADR-124）。"""
        row = [k for k in orchestrator.LEDGER_KINDS
               if k["match"] == "recheck-*.json"][0]
        self.assertFalse(row["read_by"])
        self.assertTrue((row["why_not_read"] or "").strip())

    def test_validate_stays_clean_with_the_new_kind(self):
        self.assertEqual(orchestrator.validate(), [])


class NoAgreementRateTest(unittest.TestCase):
    def test_summary_has_no_agreement_rate_key(self):
        """一致率を成果として持たない（運転手順 §4・§5）。

        AI の一致は客観的証拠ではない。帳簿の鍵に置くと、次に読む者が
        それを品質の指標として読む。数えるのは不一致の**中身**である。
        """
        summary = independent_recheck.summarize([
            {"key": "K1", "before": "対応計画あり", "after": "対応計画あり",
             "agreed": True},
            {"key": "K2", "before": "実装・試験・証拠あり", "after": "対応計画あり",
             "agreed": False},
        ])
        for banned in ("agreement_rate", "一致率", "accuracy", "score"):
            self.assertNotIn(banned, summary)
        self.assertEqual(summary["disagreements"], 1)
        self.assertEqual(summary["sampled"], 2)
        self.assertTrue(summary["disagreement_detail"])


if __name__ == "__main__":
    unittest.main()
