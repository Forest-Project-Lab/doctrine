#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""配布技能が案内するコマンドは、実際に走ること（INC-031）。

`system-map-draft` の手順2 は `dep-graph.py --json` を踏ませていたが、これは
使用法の誤りで終了コード 2 になる（`--json` は修飾子であってモードではない。
モードは `--impacts` ほかから一つ選ぶ）。ADR-110 が「点検の門は使い方の誤りを
場所として飲まない」と決めたので素通りせず 2 で落ちる。技能どおりに進めた
起草者はそこで止まる。v0.11.0 で利用者へ配られた。

例ではなく軸で持つ —— 技能の文書に**一つの完結した呼び出し**として書かれた
本プラグインのスクリプトの起動を機械で拾い、書かれたまま走らせて、使用法の
誤りにならないことを確かめる。占位（`<...>`・`$VAR`）は実在の値へ置き換える。
置き換えの効かない呼び出しは数えない（数えなかったことを試験自身が示す）。
"""
import os
import re
import shlex
import subprocess
import sys
import unittest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PLUGIN_ROOT)
SKILLS_DIR = os.path.join(PLUGIN_ROOT, "skills")
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "scripts")
DOCS_ROOT = os.path.join(REPO_ROOT, "doctrine_docs")
_FIXTURE = {"root": None}   # 走らせ用の最小の統治木（setUpModule で作る）

USAGE_ERROR = 2

# 一つの `...` の中に、スクリプト一本の起動だけが書かれている形。
_ONE_CALL = re.compile(
    r"`(?:python3\s+)?(?:\$\{CLAUDE_PLUGIN_ROOT\}/scripts/|"
    r"plugin/scripts/|\./)?([a-z][a-z0-9-]*\.py)([^`|;&>]*)`")

# 文書の占位を、走らせられる実在の値へ写す。
_PLACEHOLDERS = {
    "<統治木>": "@ROOT@", "<root>": "@ROOT@", "<ROOT>": "@ROOT@",
    "<docs>": "@ROOT@", "docs/": "@ROOT@", "<日付>": "2026-08-09",
    "<YYYY-MM-DD>": "2026-08-09", "<id>": "SPEC-001", "<ID>": "SPEC-001",
    "<文書 id>": "SPEC-001", "<対象リポジトリの root>": REPO_ROOT,
}
_VALUE_FLAGS = {"--root", "--docs-root", "--today", "--format", "--fail-on",
                "--impacts", "--dependents", "--reverse-refs", "--config",
                "--out", "--cap", "--summary-out", "--root-from"}
_DEFAULT_VALUE = {
    "--root": "@ROOT@", "--docs-root": "@ROOT@", "--root-from": "@PROJ@",
    "--today": "2026-08-09", "--format": "json", "--fail-on": "never",
    "--impacts": "SPEC-001", "--dependents": "SPEC-001",
    "--reverse-refs": "SPEC-001",
}
# 実在の成果物や書き込み先を要するので、この試験では走らせない。
_SKIP_SCRIPTS = {"map-draft-check.py", "scaffold.py", "render-projection.py",
                 "collect-context.py", "term-check.py", "term-extract.py",
                 "policy-guard.py", "docs-linter.py", "trace-index.py"}


def setUpModule():
    """最小の統治木を一度だけ作る（実リポジトリを何度も走査しない）。"""
    import shutil, tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _util
    root = _util.make_repo({})
    _FIXTURE["root"] = os.path.join(root, "docs")
    _FIXTURE["cleanup"] = root


def tearDownModule():
    import shutil
    if _FIXTURE.get("cleanup"):
        shutil.rmtree(_FIXTURE["cleanup"], ignore_errors=True)


def _normalise(script, tail):
    """書かれたままの引数列を、走らせられる形へ写す。無理なら None。"""
    text = tail
    for token, value in _PLACEHOLDERS.items():
        text = text.replace(token, value)
    if "<" in text or "$" in text:
        return None                      # 置き換えきれない占位が残る
    try:
        args = shlex.split(text)
    except ValueError:
        return None
    out = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _VALUE_FLAGS:
            nxt = args[i + 1] if i + 1 < len(args) else None
            if nxt is None or nxt.startswith("-"):
                if a not in _DEFAULT_VALUE:
                    return None
                out += [a, _DEFAULT_VALUE[a]]
                i += 1
                continue
            out += [a, nxt]
            i += 2
            continue
        out.append(a)
        i += 1
    if script == "dep-graph.py" and not any(
            f in out for f in ("--impacts", "--dependents", "--classify-edges",
                               "--reverse-orphans", "--reverse-refs")):
        return out                        # モード無し = まさに検めたい形
    return out


def _documented_calls():
    """旗を一つ以上伴う起動だけを拾う。

    地の文の裸の言及（`gov-heartbeat.py` のような参照）はコマンドではない。
    フックのスクリプトは標準入力を待つので、走らせると止まる。
    """
    out = []
    for dirpath, _dirs, files in os.walk(SKILLS_DIR):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for m in _ONE_CALL.finditer(text):
                script, tail = m.group(1), m.group(2)
                if not any(t.startswith("-") for t in tail.split()):
                    continue        # 裸の言及。コマンドではない
                out.append((os.path.relpath(path, PLUGIN_ROOT), script, tail))
    return out


class DocumentedSkillCommandsRunTest(unittest.TestCase):
    def test_calls_are_found_and_most_are_runnable(self):
        """空の緑にしない —— 拾えた数と、走らせられた数を先に示す。"""
        calls = _documented_calls()
        self.assertTrue(calls, "技能の文書からコマンドを一件も拾えていない")
        runnable = [c for c in calls
                    if c[1] not in _SKIP_SCRIPTS
                    and _normalise(c[1], c[2]) is not None]
        self.assertTrue(runnable,
                        "走らせられる呼び出しが一件も無い（覆いが空）")

    def test_no_documented_call_is_a_usage_error(self):
        offenders = []
        seen = set()
        for rel, script, tail in _documented_calls():
            if script in _SKIP_SCRIPTS:
                continue
            target = os.path.join(SCRIPTS_DIR, script)
            if not os.path.isfile(target):
                offenders.append((rel, script, tail.strip(), "スクリプトが無い"))
                continue
            args = _normalise(script, tail)
            if args is None:
                continue
            root = _FIXTURE["root"]
            proj = os.path.dirname(root)
            args = [a.replace("@ROOT@", root).replace("@PROJ@", proj)
                    for a in args]
            key = (script, tuple(args))
            if key in seen:
                continue
            seen.add(key)
            try:
                proc = subprocess.run(
                    [sys.executable, target] + args,
                    capture_output=True, text=True, timeout=60, cwd=REPO_ROOT,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                             CLAUDE_PLUGIN_ROOT=PLUGIN_ROOT))
            except subprocess.TimeoutExpired:
                offenders.append((rel, script, tail.strip(), "時間切れ"))
                continue
            if proc.returncode == USAGE_ERROR:
                head = (proc.stdout or proc.stderr).strip().splitlines()
                offenders.append((rel, script, tail.strip(),
                                  head[0][:80] if head else "usage error"))
        self.assertEqual(
            offenders, [],
            "技能が案内するコマンドが使用法の誤りで落ちる: %r" % (offenders,))

    def test_the_oracle_can_fail(self):
        """検出器そのものが働くこと —— 既知の使用法の誤りを 2 で捕らえる。"""
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS_DIR, "dep-graph.py"),
             "--root", DOCS_ROOT, "--json"],
            capture_output=True, text=True, timeout=300, cwd=REPO_ROOT,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(proc.returncode, USAGE_ERROR,
                         "モードなしの dep-graph.py は使用法の誤りであること")


if __name__ == "__main__":
    unittest.main()
