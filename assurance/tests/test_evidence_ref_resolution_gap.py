#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""台帳に書いた参照が実在しなくても、どの門も反応しない（INC-041）。

REPRODUCE_RED である。**是正の前に赤であることが要件**で、最初から緑なら
再現と認めない（運転手順 §2）。凍結するのは次の三つ。

- 宣言による免除: `evidence_kind` が語彙に在ると `_validate_incident_evidence`
  は即 continue し、その行に書かれた `evidence_refs` を一度も見ない。
- 部分解決の許容: 宣言が無くても、判定は `not any(resolve(r) for r in refs)`
  なので、**一つでも解決すれば**残りが実在しなくても緑になる。
  この二つは独立で、どちらか一方を直しても INC-040 は今も検出されない。
- 欠陥の側: `prompts.verify_cast_analysis` の照合対象は
  `control_element_id` と `normative_refs` の二つのフィールドで、
  `evidence_ref` は最初から照合の枠に入っていない。解決しない参照が
  `citation_defect` の刻みも無いまま評価器の成果物へ写る。
  **この三つ目は本反復では直さない**（修正は一度に一つ。運転手順 §2）。
  赤の証拠は `ledger/red/INC-041-….json` に保存してある。

実物は INC-040 の `doctrine_docs/packaging/decisions/ADR-134-scoped-staleness.md`
（実体は `ADR-134-staleness-is-scoped-to-what-the-judgement-cited.md`）で、
2026-08-10 から 4 日間、`validate` は `problems: []` を返し続けた。

赤／助言のどちらへ倒すかは未決（INC-041 の分析の推奨#4）。ここでは
**赤（problems へ現れる）**の形で凍結する。ADR が助言を選ぶなら、
判定の宛先をその channel へ移す —— 移すべきは宛先であって、
「解決しない参照を surface する」という要件ではない。

事象の記録の当時の姿は fixture として持つ。生きた台帳へ直接あてない ——
INC-040 の参照が直った後もこの試験は同じことを言い続ける必要がある。
"""
import os
import subprocess
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import orchestrator  # noqa: E402


# INC-040 が 2026-08-10 に台帳へ積まれたときの証拠の宣言（そのまま）。
# 3 件のうち解決するのは cast-coverage.json だけである。
INC_040_AS_FILED = {
    "id": "INC-040-document-axis-invalidates-wholesale",
    "evidence_kind": "measurement",
    "evidence_refs": [
        "assurance/harness/system_index.py の build（category_sha256 は種別ごとに全件を畳む）",
        "doctrine_docs/packaging/decisions/ADR-134-scoped-staleness.md",
        "assurance/ledger/catalogs/cast-coverage.json",
    ],
}


def _resolve_like_the_real_index(pointer):
    """実索引の代わり。cast-coverage.json だけが解決する。"""
    return "file" if pointer == "assurance/ledger/catalogs/cast-coverage.json" else None


class DeclaredKindDoesNotExemptWrittenRefs(unittest.TestCase):
    """宣言の意味は『証拠の実体が体系の外に在る』であって、
    『体系内に書いた参照文字列の正しさを免除する』ではない。"""

    def _gate(self, incident, resolve=lambda ptr: None):
        return orchestrator._validate_incident_evidence(
            incidents=[incident], resolve=resolve)

    def test_declared_kind_still_checks_the_refs_that_were_written(self):
        problems = self._gate(
            {"id": "INC-099-x", "evidence_kind": "measurement",
             "evidence_refs": ["no-such-file.md"]})
        self.assertTrue(problems, "宣言が在っても、書いた参照の解決は検める")

    def test_declaring_a_kind_without_refs_stays_green(self):
        """免除の単位は『体系外の実体』。refs を書かない行は今までどおり緑。"""
        for kind in orchestrator.EXTERNAL_EVIDENCE_KINDS:
            self.assertEqual(
                self._gate({"id": "INC-099-x", "evidence_kind": kind}), [], kind)

    def test_one_resolving_ref_does_not_excuse_the_others(self):
        """部分解決の許容。宣言が無くても、一つ解決すれば残りは見られない。"""
        problems = self._gate(
            {"id": "INC-099-x", "evidence_refs": ["good", "no-such-file.md"]},
            resolve=lambda ptr: "file" if ptr == "good" else None)
        self.assertTrue(problems, "解決しない参照が混ざっていることを報せる")

    def test_the_record_that_actually_slipped_through_is_caught(self):
        """INC-040 を積まれた当時の姿のまま門へ通す（二つの穴の合流点）。"""
        problems = self._gate(INC_040_AS_FILED,
                              resolve=_resolve_like_the_real_index)
        self.assertTrue(problems, "実在しない ADR の名を引く行が素通りしている")
        self.assertTrue(
            any("ADR-134-scoped-staleness" in p for p in problems),
            "報せるなら、どの参照が解決しないかを名指しする: %s" % problems)


class TheRepairedLedgerStaysGreen(unittest.TestCase):
    """門を立てることと、今の台帳がその門を通ることは、同じ変更で示す。"""

    def test_the_real_ledger_has_no_unresolving_ref(self):
        self.assertEqual(orchestrator._validate_incident_evidence(), [])

    def test_no_ref_points_at_something_the_repository_does_not_carry(self):
        """参照はリポジトリが持つ物だけを指す（ADR-166 第5項）。

        実行時の状態（`.claude/.cache/` の下）を指す参照は、それを作った機械の
        上でだけ解決する。門を立てた最初の走行で、手元は緑・CI は赤という形で
        現れた —— 参照の解決が環境に依ることは、門を立てるまで見えなかった。
        追跡されている物か、追跡されている物を含む場所だけを許す。
        """
        tracked = set(subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True,
            cwd=_REPO).stdout.splitlines())
        dirs = {os.path.dirname(p) for p in tracked}
        dirs.discard("")
        offenders = []
        for inc in orchestrator.load_incidents():
            for ref in (inc.get("evidence_refs") or []):
                if "/" not in ref:      # 文書 id・Hook の口の名・検査名
                    continue
                if ref in tracked or ref in dirs:
                    continue
                offenders.append((inc.get("id"), ref))
        self.assertEqual(offenders, [], "リポジトリが持たない場所を指している")


if __name__ == "__main__":
    unittest.main()
