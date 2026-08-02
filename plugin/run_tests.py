#!/usr/bin/env python3
# doctrine:exempt 試験の入口。方法論の正本は ADR-047/PROC-001(ADR-067)
"""Discover and run the plugin's unittest suite.

Runs `tests/test_*.py` via unittest's TestLoader.discover, prints a pass/fail
summary, and exits 0 on success / 1 on any failure or error.

Works both as:
    python3 plugin/run_tests.py     (from repo root)
    python3 run_tests.py            (from plugin/)

Equivalent to:
    python3 -m unittest discover -s plugin/tests -p 'test_*.py'
"""

import os
import sys

# 作業木に __pycache__ を残さない(ADR-075)。marketplace の source がディレクトリ
# のとき、配布は作業木の複製であり、試験を走らせた痕跡がそのまま利用者へ配られる。
# 環境変数も置く: 試験は入口スクリプトを子プロセスでも起こすので、旗だけでは
# 親プロセスにしか効かない。
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import unittest                                          # noqa: E402

# This file lives at plugin/run_tests.py, so PLUGIN_ROOT is its directory
# regardless of the current working directory.
PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.join(PLUGIN_ROOT, "tests")
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "scripts")

# Ensure tests/ (for `import _util`) and scripts/ (for the cores/entry scripts)
# are importable no matter where we were launched from.
for path in (TESTS_DIR, SCRIPTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)


def main(argv=None):
    verbosity = 2
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, pattern="test_*.py", top_level_dir=TESTS_DIR)
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failures - errors  # skipped tests still count as run

    # 0 件を成功と読まない(ADR-075)。discover が何も拾えなかった状態は
    # 「全部通った」ではなく「何も検めていない」であり、配線の壊れを緑で隠す。
    ok = result.wasSuccessful() and total > 0

    print("")
    print("=" * 60)
    print("SUMMARY: %d run, %d passed, %d failed, %d error, %d skipped"
          % (total, passed - skipped, failures, errors, skipped))
    if total == 0:
        print("NO TESTS RAN: %s に test_*.py が無い。探索先が壊れている"
              % TESTS_DIR)
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    print("=" * 60)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
