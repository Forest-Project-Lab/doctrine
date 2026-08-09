#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""台帳の入出力の決定論試験（SDK 不要・通信不要）。

事象 INC-027 の修正前再現。凍結したいこと:

- 素の `open(path,"w")` + `json.dump` は、書き込みの途中で殺されると
  **前の全文を壊す**。この害を一度だけ名指しして固定する。
- `write_json` は原子的である —— 途中で殺されても、読み手が見るのは
  「前の全文」か「新しい全文」だけとする。
- 一時名に pid を混ぜる。固定名だと二つの走らせ手が同時に書いたとき
  互いの一時ファイルを上書きする（配布側で実測 60 回に 1 回。ADR-075）。
- `read_json` は、切り詰められた台帳を「空」と読み替えない。
  欠落と破損は別の事実である（黙って空と読むと次の行動が消える。INC-006）。
- 台帳へ書く経路が `ledger_io` の外に生えない（軸で凍結する。15 箇所目を防ぐ）。

時計は読まない。`time.sleep` は使わない。殺す位置は継ぎ目の patch で決める。
"""
import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import ledger_io  # noqa: E402

HARNESS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness")

# テンプレートは後段で % 展開するので、doc 側の % は二重にしておく。
_BIG_DOC = ('{"kind": "incident-queue",'
            ' "incidents": [{"id": "INC-%%03d" %% i, "summary": "x" * 400}'
            ' for i in range(200)]}')

# 子プロセスで「改名の直前に殺す」。sleep も時計も使わない。
_KILL_AT_RENAME = """
import os, signal, sys
sys.path.insert(0, %(lane)r)
from harness import ledger_io
def kill(src, dst):
    os.kill(os.getpid(), signal.SIGKILL)
ledger_io.os.replace = kill
ledger_io.write_json(%(path)r, """ + _BIG_DOC + """)
"""

# 製品の呼び口（triage_candidates.write_doc）を書き込みの途中で殺す。
# 「呼び口が write_json に変わった ⇒ 前の全文が残る」は diff の読みからの推論に
# すぎない、という独立検証（2026-08-09）の指摘への応答。推論ではなく観測を置く。
_KILL_MID_PRODUCT_CALL = """
import os, signal, sys
sys.path.insert(0, %(lane)r)
from harness import ledger_io, triage_candidates
_real_open = open
class Killing:
    def __init__(self, fh): self._fh = fh; self._n = 0
    def write(self, s):
        self._n += len(s)
        if self._n > 5000:
            self._fh.flush(); os.fsync(self._fh.fileno())
            os.kill(os.getpid(), signal.SIGKILL)
        return self._fh.write(s)
    def __getattr__(self, name): return getattr(self._fh, name)
    def __enter__(self): return self
    def __exit__(self, *a): return self._fh.__exit__(*a)
def patched(*a, **kw):
    fh = _real_open(*a, **kw)
    if len(a) > 1 and "w" in str(a[1]):
        return Killing(fh)
    return fh
ledger_io.open = patched
triage_candidates.SCENARIO_DIR = os.path.dirname(%(path)r)
triage_candidates.write_doc(%(path)r, """ + _BIG_DOC + """)
"""

# 子プロセスで「json.dump の途中で殺す」。赤で実測した害そのものの形。
# 一時ファイルへ 5000 バイト書いた時点で落とす（赤の断片と同じ大きさ）。
_KILL_MID_DUMP = """
import os, signal, sys
sys.path.insert(0, %(lane)r)
from harness import ledger_io
_real_open = open
class Killing:
    def __init__(self, fh): self._fh = fh; self._n = 0
    def write(self, s):
        self._n += len(s)
        if self._n > 5000:
            self._fh.flush(); os.fsync(self._fh.fileno())
            os.kill(os.getpid(), signal.SIGKILL)
        return self._fh.write(s)
    def __getattr__(self, name): return getattr(self._fh, name)
    def __enter__(self): return self
    def __exit__(self, *a): return self._fh.__exit__(*a)
def patched(*a, **kw):
    fh = _real_open(*a, **kw)
    if len(a) > 1 and "w" in str(a[1]):
        return Killing(fh)
    return fh
ledger_io.open = patched
ledger_io.write_json(%(path)r, """ + _BIG_DOC + """)
"""


def _lane_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NaiveWriteLosesThePreviousLedgerTest(unittest.TestCase):
    """害の対照。原子的でない書き方だと前の全文が消えることを一度だけ示す。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ledgerio-naive-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, "incidents.json")

    def test_a_truncated_naive_write_is_not_valid_json(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"kind": "incident-queue", "incidents": [{"id": "INC-001"}]},
                      fh, ensure_ascii=False)
        big = {"kind": "incident-queue",
               "incidents": [{"id": "INC-%03d" % i, "summary": "x" * 400}
                             for i in range(200)]}
        text = json.dumps(big, ensure_ascii=False, indent=2)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text[:5000])          # 途中で殺された姿
        with self.assertRaises(ValueError):
            with open(self.path, encoding="utf-8") as fh:
                json.load(fh)


class AtomicLedgerWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ledgerio-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, "incidents.json")
        self.previous = {"kind": "incident-queue", "incidents": [{"id": "INC-001"}]}
        ledger_io.write_json(self.path, self.previous)

    def test_write_json_round_trips(self):
        doc = {"kind": "incident-queue", "incidents": [{"id": "INC-002"}]}
        ledger_io.write_json(self.path, doc)
        self.assertEqual(ledger_io.read_json(self.path), doc)

    def test_write_json_ends_with_a_newline(self):
        with open(self.path, encoding="utf-8") as fh:
            self.assertTrue(fh.read().endswith("\n"))

    def test_a_failed_rename_leaves_the_previous_ledger_readable(self):
        real = ledger_io.os.replace

        def boom(src, dst):
            raise OSError("disk full")

        ledger_io.os.replace = boom
        try:
            with self.assertRaises(OSError):
                ledger_io.write_json(self.path, {"kind": "incident-queue",
                                                 "incidents": [{"id": "INC-999"}]})
        finally:
            ledger_io.os.replace = real
        self.assertEqual(ledger_io.read_json(self.path), self.previous)
        self.assertEqual(
            [n for n in os.listdir(self.dir) if n.endswith(".tmp")], [],
            "改名に失敗したら一時ファイルを残さない")

    def _kill_child(self, script):
        proc = subprocess.Popen([sys.executable, "-c", script],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        child_pid = proc.pid
        proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertEqual(ledger_io.read_json(self.path), self.previous,
                         "殺されても前の全文が読めること")
        leftovers = [n for n in os.listdir(self.dir) if n.endswith(".tmp")]
        for name in leftovers:
            self.assertIn(str(child_pid), name,
                          "残骸があるなら pid 付きの一時ファイルだけ")

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "SIGKILL のある環境だけ")
    def test_a_real_sigkill_before_the_rename_keeps_the_old_ledger(self):
        self._kill_child(_KILL_AT_RENAME
                         % {"lane": _lane_dir(), "path": self.path})

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "SIGKILL のある環境だけ")
    def test_a_real_sigkill_in_the_middle_of_the_dump_keeps_the_old_ledger(self):
        """赤で実測した害そのものの形（json.dump の途中で殺す）を再観測する。

        改名の直前だけを突く継ぎ目試験は、書き出しの途中で殺された場合を
        観測していない —— 独立検証（2026-08-09）の指摘。本体を触らないという
        設計は diff から推論できるが、推論は観測ではない。
        """
        self._kill_child(_KILL_MID_DUMP
                         % {"lane": _lane_dir(), "path": self.path})

    @unittest.skipUnless(hasattr(signal, "SIGKILL"), "SIGKILL のある環境だけ")
    def test_a_product_call_path_killed_mid_write_keeps_the_old_ledger(self):
        """製品の呼び口を突く。移送が効いていることを推論でなく観測で示す。

        `triage_candidates.write_doc` は移送した 14 箇所の一つである。
        `ledger_io.write_json` 単体ではなく、実際に台帳を書く関数を
        書き込みの途中で殺して、前の全文が残ることを確かめる。
        """
        self._kill_child(_KILL_MID_PRODUCT_CALL
                         % {"lane": _lane_dir(), "path": self.path})

    def test_the_temp_name_carries_the_pid(self):
        seen = []
        real = ledger_io.os.replace

        def watch(src, dst):
            seen.append(os.path.basename(src))
            return real(src, dst)

        ledger_io.os.replace = watch
        try:
            ledger_io.write_json(self.path, self.previous)
        finally:
            ledger_io.os.replace = real
        self.assertTrue(seen)
        self.assertIn(str(os.getpid()), seen[0])

    def test_write_json_creates_the_parent_directory(self):
        deep = os.path.join(self.dir, "a", "b", "c.json")
        ledger_io.write_json(deep, {"k": 1})
        self.assertEqual(ledger_io.read_json(deep), {"k": 1})

    def test_sort_keys_is_available(self):
        path = os.path.join(self.dir, "sorted.json")
        ledger_io.write_json(path, {"b": 1, "a": 2}, sort_keys=True)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertLess(text.index('"a"'), text.index('"b"'))


class ReadJsonSeparatesAbsenceFromCorruptionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ledgerio-read-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_a_truncated_ledger_is_named_not_read_as_empty(self):
        path = os.path.join(self.dir, "trunc.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"plans": [{"scenario_id": "SCN-1", "verd')
        with self.assertRaises(ledger_io.LedgerCorrupt) as caught:
            ledger_io.read_json(path)
        self.assertIn("trunc.json", str(caught.exception),
                      "壊れた台帳は場所を名指しする")

    def test_a_missing_ledger_returns_the_default(self):
        path = os.path.join(self.dir, "nope.json")
        self.assertEqual(ledger_io.read_json(path, default=[]), [])

    def test_a_missing_ledger_is_an_error_when_required(self):
        path = os.path.join(self.dir, "nope.json")
        with self.assertRaises(ledger_io.LedgerCorrupt):
            ledger_io.read_json(path, required=True)

    def test_absence_and_corruption_are_different(self):
        missing = os.path.join(self.dir, "absent.json")
        broken = os.path.join(self.dir, "broken.json")
        with open(broken, "w", encoding="utf-8") as fh:
            fh.write("{")
        self.assertIsNone(ledger_io.read_json(missing))
        with self.assertRaises(ledger_io.LedgerCorrupt):
            ledger_io.read_json(broken)

    def test_corruption_is_not_swallowed_by_the_usual_reader_guard(self):
        """既存の読み手が広く持つ `except (OSError, ValueError)` に飲まれないこと。

        独立検証（2026-08-09）の指摘。`LedgerCorrupt` が `ValueError` を継ぐと、
        正本の読み手がそのまま握り潰し、破損がまた「空」に化ける ——
        この事象が直そうとしている当のことが戻る。
        """
        self.assertFalse(issubclass(ledger_io.LedgerCorrupt, ValueError))
        self.assertFalse(issubclass(ledger_io.LedgerCorrupt, OSError))
        broken = os.path.join(self.dir, "swallow.json")
        with open(broken, "w", encoding="utf-8") as fh:
            fh.write('{"a":')
        swallowed = False
        try:
            ledger_io.read_json(broken)
        except (OSError, ValueError):
            swallowed = True
        except ledger_io.LedgerCorrupt:
            pass
        self.assertFalse(swallowed, "破損が既存の握り潰しに飲まれてはならない")


class EveryLedgerWriteGoesThroughTheHelperTest(unittest.TestCase):
    """軸で凍結する。15 箇所目の素の書き込みが黙って生えないこと。"""

    @staticmethod
    def _naive_write_sites(source, filename):
        """台帳を直に書きうる形を数える。

        覆う形は四つ:
        (a) `with open(x, "w") as f: ... *.dump(...)`
        (b) `f = open(x, "w")`（with を使わない形。モードが変数でも数える）
        (c) `Path(...).write_text(...)` / `x.write_text(...)`
        (d) `os.replace(...)`（原子化を各所で真似る形。正本は ledger_io だけ）

        **限界を明示する**: 別名 import・動的な属性引き・他の直列化器は
        素通りする（独立検証 2026-08-09 の指摘）。この試験が凍結するのは
        上の四形状であって、「台帳を直に書く経路が無い」ことの証明ではない。
        """
        found = []
        tree = ast.parse(source, filename=filename)

        def is_open(call):
            return (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "open")

        def opens_for_write(call):
            for arg in call.args[1:]:
                if isinstance(arg, ast.Constant):
                    if "w" in str(arg.value) or "a" in str(arg.value):
                        return True
                else:
                    return True          # モードが変数 —— 安全側に数える
            for kw in call.keywords:
                if kw.arg == "mode":
                    return True
            return False

        for node in ast.walk(tree):
            # (a) with open(..., "w") ... *.dump(...)
            if isinstance(node, ast.With):
                if any(is_open(i.context_expr) and opens_for_write(i.context_expr)
                       for i in node.items):
                    for inner in ast.walk(node):
                        if (isinstance(inner, ast.Call)
                                and isinstance(inner.func, ast.Attribute)
                                and inner.func.attr == "dump"):
                            found.append(getattr(node, "lineno", 0))
                            break
                continue
            # (b) f = open(..., "w")
            if isinstance(node, ast.Assign) and is_open(node.value):
                if opens_for_write(node.value):
                    found.append(getattr(node, "lineno", 0))
                continue
            # (c) 何かの write_text / (d) os.replace
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "write_text":
                    found.append(getattr(node, "lineno", 0))
                elif (node.func.attr == "replace"
                      and isinstance(node.func.value, ast.Name)
                      and node.func.value.id == "os"):
                    found.append(getattr(node, "lineno", 0))
        return sorted(set(found))

    def test_no_harness_module_writes_a_file_directly(self):
        """軸は事象より広い —— それは意図である。

        レーンがファイルへ出すものは台帳しかない。だから「台帳へ書く経路」ではなく
        **「ファイルへ書く経路」**を一本化する。`os.replace` も咎めるので、
        原子化を各所で真似ることもできない（配布側に三つの実装が散った轍を踏まない）。
        独立検証（2026-08-09）が「軸が主題より広い」と指したので、名前と文言を
        実際に凍結している内容へ合わせた。台帳以外を書きたくなったら、この試験を
        緩めるのではなく `ledger_io` に口を足すこと。
        """
        offenders = {}
        for name in sorted(os.listdir(HARNESS_DIR)):
            if not name.endswith(".py") or name == "ledger_io.py":
                continue
            path = os.path.join(HARNESS_DIR, name)
            with open(path, encoding="utf-8") as fh:
                sites = self._naive_write_sites(fh.read(), path)
            if sites:
                offenders[name] = sites
        self.assertEqual(
            offenders, {},
            "台帳へ書く経路は harness/ledger_io.py に一本化する"
            "（見つかった素の書き込み: %r）" % (offenders,))

    def test_the_oracle_can_fail(self):
        """空の緑にしない —— 検出器が四形状すべてで働くことを示す。"""
        shapes = {
            "with-open-dump": (
                "import json\n"
                "def save(path, doc):\n"
                "    with open(path, \"w\", encoding=\"utf-8\") as f:\n"
                "        json.dump(doc, f)\n"),
            "bare-open": (
                "def save(path):\n"
                "    f = open(path, \"w\")\n"),
            "variable-mode": (
                "def save(path, mode):\n"
                "    f = open(path, mode)\n"),
            "write-text": (
                "import json\n"
                "def save(p, doc):\n"
                "    p.write_text(json.dumps(doc))\n"),
            "os-replace": (
                "import os\n"
                "def save(a, b):\n"
                "    os.replace(a, b)\n"),
        }
        for name, src in shapes.items():
            with self.subTest(shape=name):
                self.assertTrue(self._naive_write_sites(src, "<%s>" % name),
                                "検出器が %s を見逃す" % name)

    def test_the_oracle_does_not_flag_a_clean_module(self):
        """逆側 —— 読むだけの module を咎めない（偽陽性で軸を鈍らせない）。"""
        clean = (
            "import json\n"
            "def load(path):\n"
            "    with open(path, encoding=\"utf-8\") as f:\n"
            "        return json.load(f)\n")
        self.assertEqual(self._naive_write_sites(clean, "<clean>"), [])


class ValidateNamesACorruptLedgerTest(unittest.TestCase):
    """正本の側。切り詰めを「空」と読み替えず、validate が名指して赤にする。

    本物の台帳には触らない（一時ディレクトリへ複製してから壊す）。
    """

    def setUp(self):
        from harness import orchestrator
        self.orchestrator = orchestrator
        self.dir = tempfile.mkdtemp(prefix="h1-validate-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.ledger = os.path.join(self.dir, "ledger")
        os.makedirs(self.ledger)
        ledger_io.write_json(os.path.join(self.ledger, "incidents.json"),
                             {"kind": "incident-queue", "incidents": []})
        ledger_io.write_json(os.path.join(self.ledger, "smoke-latest.json"),
                             {"kind": "smoke", "status": "PASS"})

    def _problems(self):
        return self.orchestrator._validate_ledger_readability(self.ledger)

    def test_a_healthy_ledger_has_no_problems(self):
        self.assertEqual(self._problems(), [])

    def test_a_truncated_ledger_is_named(self):
        with open(os.path.join(self.ledger, "incidents.json"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"kind": "incident-queue", "incid')
        problems = self._problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("incidents.json", problems[0])

    def test_every_declared_ledger_file_is_covered(self):
        """軸で持つ —— 一件ずつ壊せば、その一件だけが名指される。

        自分で置いた二件では「宣言された台帳を全件覆う」ことの証明にならない
        （独立検証 2026-08-09 の指摘）。**本物の台帳の複製**に対して回す。
        本物には触らない。
        """
        real = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ledger")
        if not os.path.isdir(real):
            self.skipTest("本物の台帳が無い環境")
        copied = os.path.join(self.dir, "real-ledger")
        shutil.copytree(real, copied,
                        ignore=shutil.ignore_patterns("runs", ".*"))
        names = [n for n in self.orchestrator.ledger_files(copied)
                 if n.endswith(".json")]
        self.assertGreater(len(names), 10, "複製に十分な種別があること")
        self.assertEqual(
            self.orchestrator._validate_ledger_readability(copied), [],
            "本物の台帳の複製は全件読める")
        for name in names:
            path = os.path.join(copied, name)
            with open(path, encoding="utf-8") as fh:
                keep = fh.read()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{")
            problems = self.orchestrator._validate_ledger_readability(copied)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(keep)
            self.assertEqual(len(problems), 1, "壊した %s だけが挙がる" % name)
            self.assertIn(name, problems[0])

    def test_validate_is_wired_to_the_readability_check(self):
        """配線そのものを試験する（diff に一行見えるだけ、にしない）。"""
        import inspect
        src = inspect.getsource(self.orchestrator.validate)
        self.assertIn("_validate_ledger_readability", src)

    def test_an_absent_ledger_is_not_a_problem(self):
        os.unlink(os.path.join(self.ledger, "smoke-latest.json"))
        self.assertEqual(self._problems(), [],
                         "欠落は破損ではない（無い台帳は咎めない）")


if __name__ == "__main__":
    unittest.main()
