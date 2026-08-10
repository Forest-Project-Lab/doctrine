#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""巨大な台帳 PR の門（scripts/ledger-diff-summary.py）。

本再監査キャンペーンは 600 件規模の台帳を書き換える PR を自律で merge し続けた。
diff は数千行で、人が読んで何が変わったかを掴むことはできない —— つまり
**誰も中身を見ていない merge** が積み上がった。所有者の要求で門を置く。

凍結するのは四つ。
1. 小さい差分は素通りする（一件の処遇で門が鳴らない）。
2. 大きい差分は、独立レビューか機械生成の要約のどちらかを要る。
3. 要約は **digest の一行**で照合する。書き手が数を打ち直せる形にしない。
4. 台帳が読めないときは黙って通さない（破損を「新規ファイル」に見せない）。

git を呼ぶので、実リポジトリではなく使い捨ての git 木で測る（決定的にするため）。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "scripts", "ledger-diff-summary.py")


def _load():
    spec = importlib.util.spec_from_file_location("ledger_diff_summary", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lds = _load()


def _git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args),
                   check=True, capture_output=True, text=True)


class _Fixture(unittest.TestCase):
    """使い捨ての git 木。実リポジトリには一切触れない。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lds-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _git(self.tmp, "init", "-q", "-b", "main")
        _git(self.tmp, "config", "user.email", "t@example.invalid")
        _git(self.tmp, "config", "user.name", "t")
        self._saved_repo = lds.REPO
        lds.REPO = self.tmp
        self.addCleanup(setattr, lds, "REPO", self._saved_repo)

    def write(self, rel, doc):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(doc, str):
                fh.write(doc)
            else:
                json.dump(doc, fh, ensure_ascii=False, indent=1)

    def commit(self, msg="c"):
        _git(self.tmp, "add", "-A")
        _git(self.tmp, "commit", "-q", "-m", msg)
        return subprocess.run(["git", "-C", self.tmp, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()

    def ledger(self, n, state="pending", start=0):
        return {"dispositions": [
            {"incident_id": "INC-%03d" % (i + start), "index": 0,
             "state": state, "note": "x" * 40} for i in range(n)]}


class SmallDiffPassesTest(_Fixture):
    def test_a_one_record_change_is_not_big(self):
        self.write("assurance/ledger/a.json", self.ledger(2))
        base = self.commit()
        self.write("assurance/ledger/a.json", self.ledger(3))
        self.commit()
        s = lds.summarize(base)
        self.assertFalse(s["is_big"], "小さい差分で門が鳴った: %d 行" % s["diff_lines"])
        self.assertEqual(lds.check(s, "", approved=False), [])


class BigDiffTest(_Fixture):
    def _big(self):
        self.write("assurance/ledger/big.json", self.ledger(10))
        base = self.commit()
        self.write("assurance/ledger/big.json", self.ledger(120, state="landed"))
        self.commit()
        return base, lds.summarize(base)

    def test_big_diff_without_anything_is_refused(self):
        _base, s = self._big()
        self.assertTrue(s["is_big"])
        problems = lds.check(s, "ふつうの本文", approved=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("独立レビューも機械生成の差分要約も", problems[0])

    def test_independent_review_satisfies_it(self):
        _base, s = self._big()
        self.assertEqual(lds.check(s, "", approved=True), [])

    def test_the_digest_line_satisfies_it(self):
        _base, s = self._big()
        body = "## 変更\n\n%s\n\n散文はご自由に。\n" % lds.digest_line(s)
        self.assertEqual(lds.check(s, body, approved=False), [])

    def test_a_hand_edited_digest_does_not_satisfy_it(self):
        # 数を打ち直せる形にしない。要約は主張ではなく測定である。
        _base, s = self._big()
        faked = lds.digest_line(s).replace("transitions=", "transitions=0 real=")
        self.assertNotEqual(lds.check(s, faked, approved=False), [])

    def test_transitions_are_counted(self):
        _base, s = self._big()
        # 10 件が pending → landed へ動き、110 件が増えた。
        self.assertEqual(len(s["transitions"]), 10)
        self.assertEqual(len(s["added"]), 110)
        self.assertEqual(len(s["removed"]), 0)

    def test_removed_records_are_named(self):
        self.write("assurance/ledger/big.json", self.ledger(120))
        base = self.commit()
        self.write("assurance/ledger/big.json", self.ledger(10))
        self.commit()
        s = lds.summarize(base)
        self.assertEqual(len(s["removed"]), 110)
        self.assertIn("assurance/ledger/big.json:INC-119#0", s["removed"])


class CorruptLedgerTest(_Fixture):
    def test_unreadable_after_is_reported_not_treated_as_empty(self):
        self.write("assurance/ledger/a.json", self.ledger(50))
        base = self.commit()
        self.write("assurance/ledger/a.json", '{"dispositions": [ truncated')
        self.commit()
        s = lds.summarize(base)
        self.assertTrue(any("(後)" in u for u in s["unreadable"]),
                        "破損を報告していない: %r" % (s["unreadable"],))

    def test_corrupt_does_not_look_like_a_brand_new_file(self):
        self.write("assurance/ledger/a.json", '{ truncated')
        base = self.commit()
        self.write("assurance/ledger/a.json", self.ledger(3))
        self.commit()
        s = lds.summarize(base)
        self.assertTrue(any("(前)" in u for u in s["unreadable"]))


class ScopeTest(_Fixture):
    def test_only_ledger_json_is_in_scope(self):
        self.write("assurance/ledger/a.json", self.ledger(2))
        self.write("README.md", "x\n" * 500)
        self.write("assurance/harness/x.py", "y\n" * 500)
        base = self.commit()
        self.write("README.md", "z\n" * 500)
        self.write("assurance/harness/x.py", "w\n" * 500)
        self.commit()
        s = lds.summarize(base)
        self.assertEqual(s["files"], [], "台帳でないものを数えている")
        self.assertFalse(s["is_big"])


class EntryPointTest(_Fixture):
    def test_missing_diff_base_is_a_usage_error(self):
        self.assertEqual(lds.main([]), 2)

    def test_unknown_flag_is_a_usage_error(self):
        self.assertEqual(lds.main(["--diff-base", "HEAD", "--nope"]), 2)

    def test_bad_base_does_not_silently_pass(self):
        # 判定を書けないときは沈黙して開かない（DECIDED-001 第12項）。
        self.write("assurance/ledger/a.json", self.ledger(2))
        self.commit()
        rc = lds.main(["--diff-base", "no-such-rev", "--check"])
        self.assertEqual(rc, 2)

    def test_check_returns_one_on_violation(self):
        self.write("assurance/ledger/big.json", self.ledger(10))
        base = self.commit()
        self.write("assurance/ledger/big.json", self.ledger(120))
        self.commit()
        body = os.path.join(self.tmp, "body.txt")
        with open(body, "w", encoding="utf-8") as fh:
            fh.write("要約は貼っていない")
        rc = lds.main(["--diff-base", base, "--check", "--pr-body-file", body])
        self.assertEqual(rc, 1)

    def test_check_returns_zero_when_satisfied(self):
        self.write("assurance/ledger/big.json", self.ledger(10))
        base = self.commit()
        self.write("assurance/ledger/big.json", self.ledger(120))
        self.commit()
        s = lds.summarize(base)
        body = os.path.join(self.tmp, "body.txt")
        with open(body, "w", encoding="utf-8") as fh:
            fh.write(lds.digest_line(s))
        rc = lds.main(["--diff-base", base, "--check", "--pr-body-file", body])
        self.assertEqual(rc, 0)


class WiringTest(unittest.TestCase):
    def test_ci_runs_the_gate(self):
        path = os.path.join(REPO, ".github", "workflows", "checks.yml")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("ledger-diff-summary.py", text,
                      "門を書いたのに CI が呼んでいない（走らせ手を足して"
                      "読む段を足さない形。INC-012/INC-015/ADR-148）")


if __name__ == "__main__":
    unittest.main()
