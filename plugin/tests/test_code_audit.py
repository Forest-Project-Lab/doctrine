#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""code-audit — コード層の検算(ADR-068)の単体試験。

凍らせる不変条件:
1. 検査名と上限の転記表凍結(ADR-060 の様式。生成で埋めない)。
2. import 境界の三条が、それぞれ error になる。
3. 二重定義リテラルと肥大が advisory で挙がり、合否(--fail-on error)を変えない。
4. 解析不能を黙って飛ばさない(error)。
5. 自分自身のリポジトリで error ゼロ(境界規律の実測凍結)。
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

# ADR-068 から独立に転記した検査名と上限(モジュールの読み直しではない)。
EXPECTED_CODE_CHECKS = (
    "code_import_violation",
    "code_duplicate_literal",
    "code_oversize_function",
    "code_oversize_file",
    "code_parse_error",
)
EXPECTED_LIMIT_KEYS = (
    "function_lines", "file_lines", "min_str_len", "min_collection_len",
)


def _mod():
    return _util.load_script("code-audit")


class FreezeTest(unittest.TestCase):
    def test_checks_match_the_transcribed_table(self):
        self.assertEqual(tuple(_mod().CODE_CHECKS), EXPECTED_CODE_CHECKS,
                         "検査を足した/消したら転記表と ADR-068 を同じ変更で更新")

    def test_limit_keys_match_both_ways(self):
        self.assertEqual(set(_mod().LIMITS), set(EXPECTED_LIMIT_KEYS))


class CodeAuditBase(unittest.TestCase):
    def _repo(self, files):
        """root/plugin/scripts と root/scripts の下に対象を置く。"""
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for rel, body in files.items():
            p = os.path.join(root, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(body)
        return root

    def _run(self, root, extra=None):
        argv = ["--root", root, "--json"] + (extra or [])
        out, code = _util.invoke("code-audit", argv)
        return json.loads(out), code

    def checks_for(self, data, check):
        return [f for f in data["findings"] if f["check"] == check]


class ImportBoundaryTest(CodeAuditBase):
    def test_registry_must_not_import_internal(self):
        root = self._repo({
            "plugin/scripts/_registry.py": "import _helper\n",
            "plugin/scripts/_helper.py": "import os\n",
        })
        data, _ = self._run(root)
        hits = self.checks_for(data, "code_import_violation")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "error")
        self.assertIn("_registry", hits[0]["message"])

    def test_core_must_not_import_an_entry(self):
        # 入口はハイフン名が普通だが、識別子名の入口も規則の対象に含める。
        root = self._repo({
            "plugin/scripts/_helper.py": "import runner\n",
            "plugin/scripts/runner.py": "import os\n",
        })
        data, _ = self._run(root)
        hits = self.checks_for(data, "code_import_violation")
        self.assertEqual(len(hits), 1)
        self.assertIn("共有コアが入口", hits[0]["message"])

    def test_entry_must_not_import_an_entry(self):
        root = self._repo({
            "plugin/scripts/alpha.py": "import beta\n",
            "plugin/scripts/beta.py": "import os\n",
        })
        data, _ = self._run(root)
        hits = self.checks_for(data, "code_import_violation")
        self.assertEqual(len(hits), 1)
        self.assertIn("他の入口", hits[0]["message"])

    def test_lawful_layering_is_silent(self):
        root = self._repo({
            "plugin/scripts/_helper.py": "import os\n",
            "plugin/scripts/alpha.py": "import _helper\nimport json\n",
            "scripts/tool.py": "import sys\n",
        })
        data, code = self._run(root, ["--fail-on", "error"])
        self.assertEqual(self.checks_for(data, "code_import_violation"), [])
        self.assertEqual(code, 0)


class DuplicateLiteralTest(CodeAuditBase):
    def test_same_tuple_in_two_files_is_advisory(self):
        body = 'SKIP = ("node_modules", "__pycache__")\n'
        root = self._repo({
            "plugin/scripts/_a.py": body,
            "plugin/scripts/_b.py": body,
        })
        data, code = self._run(root, ["--fail-on", "error"])
        hits = self.checks_for(data, "code_duplicate_literal")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "advisory")
        self.assertIn("_a.py", hits[0]["message"])
        self.assertIn("_b.py", hits[0]["message"])
        self.assertEqual(code, 0, "advisory は合否を変えない")

    def test_long_string_constant_duplicated_is_advisory(self):
        body = 'NAME = ".governance-state"\n'
        root = self._repo({
            "plugin/scripts/_a.py": body,
            "plugin/scripts/_b.py": body,
        })
        data, _ = self._run(root)
        self.assertEqual(
            len(self.checks_for(data, "code_duplicate_literal")), 1)

    def test_short_or_single_site_literals_are_ignored(self):
        root = self._repo({
            "plugin/scripts/_a.py": 'X = "ab"\nY = ("one", "two")\n',
            "plugin/scripts/_b.py": 'X = "ab"\n',
        })
        data, _ = self._run(root)
        self.assertEqual(self.checks_for(data, "code_duplicate_literal"), [])


class OversizeAndParseTest(CodeAuditBase):
    def test_oversize_function_and_file_are_advisories(self):
        mod = _mod()
        fn_lines = mod.LIMITS["function_lines"] + 1
        body = "def big():\n" + "".join(
            "    x%d = %d\n" % (i, i) for i in range(fn_lines))
        filler = "\n".join("# 行 %d" % i
                           for i in range(mod.LIMITS["file_lines"] + 1))
        root = self._repo({
            "plugin/scripts/big.py": body,
            "plugin/scripts/long.py": filler + "\n",
        })
        data, code = self._run(root, ["--fail-on", "error"])
        self.assertEqual(
            len(self.checks_for(data, "code_oversize_function")), 1)
        self.assertEqual(len(self.checks_for(data, "code_oversize_file")), 1)
        self.assertEqual(code, 0)

    def test_unparseable_target_is_an_error_not_silence(self):
        root = self._repo({"plugin/scripts/bad.py": "def broken(:\n"})
        data, code = self._run(root, ["--fail-on", "error"])
        hits = self.checks_for(data, "code_parse_error")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "error")
        self.assertEqual(code, 1, "error は --fail-on error で門を閉じる")


class SelfApplicationTest(unittest.TestCase):
    def test_own_repository_has_no_import_violations(self):
        """境界規律の実測凍結: 自分のリポジトリで error ゼロ。"""
        repo = _util.require_repo_root(self)
        out, code = _util.invoke("code-audit", ["--root", repo, "--json",
                                                "--fail-on", "error"])
        data = json.loads(out)
        errors = [f for f in data["findings"] if f["severity"] == "error"]
        self.assertEqual(errors, [], "import 境界か解析の error が発生した")
        self.assertEqual(code, 0)
        self.assertGreater(data["targets"], 20, "対象の取り違えを検める")


if __name__ == "__main__":
    unittest.main()
