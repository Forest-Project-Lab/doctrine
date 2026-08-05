#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""doctor が「前提の欠如で本当に UNASSESSED へ倒れる」ことの決定論試験。

実 HOME・実環境変数・実ネットワークに触れない（全て注入）。
時計も読まない（assess は時刻を持たない設計）。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import doctor  # noqa: E402


def _fake_run_ok(cmd, timeout=30):
    if cmd[0].endswith("python") and "-c" in cmd:
        return 0, "0.2.129", ""
    return 0, "stub-output", ""


def _fake_run_fail(cmd, timeout=30):
    return 1, "", "stub failure"


class DoctorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.empty_home = self.tmp.name
        # venv python として実在するファイルを一つ用意する
        self.fake_venv_python = os.path.join(self.tmp.name, "python")
        with open(self.fake_venv_python, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")

    def test_all_prerequisites_ok_is_pass(self):
        report = doctor.assess(
            env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=_fake_run_ok,
            version_info=(3, 12, 1))
        self.assertEqual(report["status"], "PASS")

    def test_no_auth_signal_is_unassessed(self):
        report = doctor.assess(
            env={}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=_fake_run_ok,
            version_info=(3, 12, 1))
        self.assertEqual(report["status"], "UNASSESSED")
        auth = [c for c in report["checks"] if c["name"] == "auth_signal"][0]
        self.assertEqual(auth["status"], "missing")

    def test_missing_venv_is_unassessed(self):
        report = doctor.assess(
            env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, home=self.empty_home,
            venv_python=os.path.join(self.tmp.name, "no-such-python"),
            run=_fake_run_ok, version_info=(3, 12, 1))
        self.assertEqual(report["status"], "UNASSESSED")

    def test_sdk_import_failure_is_unassessed(self):
        report = doctor.assess(
            env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=_fake_run_fail,
            version_info=(3, 12, 1))
        self.assertEqual(report["status"], "UNASSESSED")

    def test_old_python_is_unassessed(self):
        report = doctor.assess(
            env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=_fake_run_ok,
            version_info=(3, 9, 0))
        self.assertEqual(report["status"], "UNASSESSED")

    def test_credentials_file_counts_as_signal(self):
        cred_dir = os.path.join(self.empty_home, ".claude")
        os.makedirs(cred_dir, exist_ok=True)
        with open(os.path.join(cred_dir, ".credentials.json"), "w",
                  encoding="utf-8") as f:
            f.write("{}")
        report = doctor.assess(
            env={}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=_fake_run_ok,
            version_info=(3, 12, 1))
        self.assertEqual(report["status"], "PASS")

    def test_cli_absence_does_not_fail_lane(self):
        """SDK は CLI を同梱するため、PATH の claude 不在は情報止まり。"""
        def run(cmd, timeout=30):
            if cmd[0] == "claude":
                return 127, "", "not found"
            return _fake_run_ok(cmd, timeout)
        report = doctor.assess(
            env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, home=self.empty_home,
            venv_python=self.fake_venv_python, run=run,
            version_info=(3, 12, 1))
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
