#!/usr/bin/env python3
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
import unittest

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

    print("")
    print("=" * 60)
    print("SUMMARY: %d run, %d passed, %d failed, %d error, %d skipped"
          % (total, passed - skipped, failures, errors, skipped))
    print("RESULT: %s" % ("PASS" if result.wasSuccessful() else "FAIL"))
    print("=" * 60)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
