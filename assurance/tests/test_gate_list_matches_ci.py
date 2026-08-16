#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""手順が名指す門と、CI が実際に走らせる門を突き合わせる（INC-049 推奨#0）。

INC-049 の形は「門の同一性は名前ではなく引数を含む呼び出しにあるのに、
手順は名前までしか指していない」だった。是正として §6 に呼び出し行の一覧を
置いたが、**その一覧が CI と食い違っても誰も気付かない**——散文が二箇所に在り、
照合されていない。分析の統制欠陥[1]がまさにこれを指す:

  「二つの実行は同じ門の名前を共有するが、検査集合の差を突き合わせる経路が
    存在しない。CI 側の呼び出しが変わっても、手順文書が指す呼び出しとの差が
    検出される仕組みは無く、両者の一致は偶然に依存する。」

ここが照合の経路である。

**逐語一致は要求しない。**分析の推奨#0 は逐語の文字列比較を求めているが、
二つの呼び出しは目的が違うので逐語では一致しえない —— CI は `--fail-on error`
で赤く落としたく、手元は `--json` で数を読みたい。逐語を強いると、どちらかの
用途を壊すか、片方を飾りの写しにするかしかない。ここが検めるのは

  (1) CI が門として走らせるスクリプトが、手順の一覧に**在ること**
  (2) 手順の一覧に在るスクリプトが、CI でも走ること（免除は機械で確かめる）
  (3) 引数で検査集合が変わると分かっている呼び出しは、手順側がその引数を持つこと

の三つである。(1)(2) は「片側にしか無い門」の族を捕らえ、(3) は INC-049 の
現物（`--diff-base`）と同族（`--today`）を捕らえる。**逐語一致より弱い。**
逐語でしか捕らえられない差（同じスクリプトを別の対象へ向ける引数の食い違いなど）は
ここを素通りする。この残余は推奨#0 の処遇へ書いてある。
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "checks.yml")
SKILL = os.path.join(ROOT, ".claude", "skills", "assurance-loop", "SKILL.md")

#: 手順の一覧に在って CI が走らせない門と、その免除の根拠。
#: **根拠は文字列ではなく機械で確かめる**（下の test を見よ）。免除を足すときは
#: 確かめる術も同時に足す。確かめられない免除は免除でない。
LOCAL_ONLY_EXEMPTIONS = {
    "assurance/harness/orchestrator.py": (
        "レーン試験が実台帳に対して validate() == [] を主張しており、"
        "そのレーン試験は CI で走る（間接に覆われている）"),
}

#: 引数を落とすと検査集合が変わると分かっている呼び出し。
#: 手順側の行がこの引数を持たなければ赤。
ARGUMENT_SENSITIVE = {
    "scripts/release-check.py": "--diff-base",   # 記録の義務（INC-049）
    "plugin/scripts/docs-audit.py": "--today",   # 壁時計（WATCH-001 第11項）
}


def _script_tokens(text):
    """コマンド片から、リポジトリに実在する .py の相対パスを拾う。"""
    found = set()
    for token in re.findall(r"[\w./-]+\.py", text):
        token = token.lstrip("./")
        if os.path.isfile(os.path.join(ROOT, token)):
            found.add(token)
    return found


def _run_block(body):
    """step の本文から `run:` の中身だけを取り出す。

    step 全体を読むと、**次の step に付いたコメント**まで混ざる。最初にこれを
    踏み、term-check の欠落が隠れた（次の step のコメントが release-check.py に
    触れていたため「全部が欠けている」条件が成り立たなかった）。コメントは
    門ではない。読むのは実際に走る行だけにする。
    """
    m = re.search(r"^(\s*)run:[ \t]*(.*)$", body, flags=re.M)
    if not m:
        return ""
    indent = len(m.group(1))
    rest = m.group(2).strip()
    if rest and not rest.startswith("|"):
        return rest            # `run: <一行のコマンド>`
    lines = body[m.end():].splitlines()
    out = []
    for line in lines:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        out.append(line)
    return "\n".join(out)


def _ci_gate_steps():
    """CI の step 名 → その step が走らせるスクリプトの集合。"""
    with open(WORKFLOW, encoding="utf-8") as fh:
        text = fh.read()
    steps = {}
    parts = re.split(r"^\s*- name: (.+)$", text, flags=re.M)
    # parts = [前置き, 名前1, 本文1, 名前2, 本文2, ...]
    for name, body in zip(parts[1::2], parts[2::2]):
        run = _run_block(body)
        scripts = _script_tokens(run)
        if "unittest discover -s assurance/tests" in run:
            scripts.add("assurance/tests")
        if scripts:
            steps[name.strip()] = scripts
    return steps


def _skill_gate_lines():
    """手順 §6 の門の一覧（コードブロックの各行）。"""
    with open(SKILL, encoding="utf-8") as fh:
        text = fh.read()
    head = text.index("門（")
    block = text[head:]
    fence = block.index("```")
    body = block[fence + 3:block.index("```", fence + 3)]
    return [l.strip() for l in body.splitlines() if l.strip()]


class GateListMatchesCITest(unittest.TestCase):
    def setUp(self):
        self.ci = _ci_gate_steps()
        self.lines = _skill_gate_lines()
        self.skill_scripts = set()
        for line in self.lines:
            self.skill_scripts |= _script_tokens(line)
            if "unittest discover -s assurance/tests" in line:
                self.skill_scripts.add("assurance/tests")

    def test_every_ci_gate_appears_in_the_procedure(self):
        """CI が門として走らせるものは、手順の一覧に在る（INC-049 の順向き）。"""
        missing = {}
        for name, scripts in self.ci.items():
            absent = scripts - self.skill_scripts
            if absent:
                missing[name] = sorted(absent)
        self.assertEqual(
            missing, {},
            "CI が走らせる門が手順 §6 の一覧に無い。手元の緑が CI の緑を"
            "意味しなくなる（INC-049）: %r" % (missing,))

    def test_every_procedure_gate_runs_in_ci_or_is_exempt_with_a_checked_reason(self):
        """手順の一覧に在るものは CI でも走る。免除は根拠つきで、根拠は機械で確かめる。"""
        ci_scripts = set()
        for scripts in self.ci.values():
            ci_scripts |= scripts
        local_only = self.skill_scripts - ci_scripts
        unexplained = sorted(local_only - set(LOCAL_ONLY_EXEMPTIONS))
        self.assertEqual(
            unexplained, [],
            "手順だけが走らせる門は CI をすり抜ける経路になる。免除するなら"
            "LOCAL_ONLY_EXEMPTIONS へ根拠を書き、その根拠を確かめる試験を足すこと: %r"
            % (unexplained,))

    def test_the_orchestrator_exemption_is_actually_true(self):
        """免除の根拠を機械で確かめる —— レーン試験が実台帳の validate を主張しているか。

        免除を文字列で書けるだけなら、免除は「書けば通る」ものになる。
        根拠が偽になった日にここが赤くなることが、免除を免除たらしめる。
        """
        path = os.path.join(ROOT, "assurance", "tests", "test_orchestrator.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn(
            "self.assertEqual(orchestrator.validate(), [])", src,
            "LOCAL_ONLY_EXEMPTIONS が orchestrator.py を免除する根拠は"
            "「レーン試験が実台帳の validate を主張している」だが、その主張が"
            "見つからない。免除の前提が消えている。")

    def test_argument_sensitive_calls_carry_their_argument_in_the_procedure(self):
        """引数で検査集合が変わる呼び出しは、手順側がその引数を持つ（INC-049 の現物）。"""
        problems = []
        for script, flag in sorted(ARGUMENT_SENSITIVE.items()):
            lines = [l for l in self.lines if script in l]
            if not lines:
                problems.append("%s が手順 §6 の一覧に無い" % script)
                continue
            if not any(flag in l for l in lines):
                problems.append("%s の行が %s を持たない" % (script, flag))
        self.assertEqual(
            problems, [],
            "引数を落とすと検める範囲が変わる。手順は呼び方まで含めて指す"
            "（INC-049）: %r" % (problems,))
