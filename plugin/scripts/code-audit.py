#!/usr/bin/env python3
"""コード層の検算(ADR-068)。方法論の機械化残差だけを検める。

対象は plugin/scripts/*.py と scripts/*.py(試験は対象外 — 試験は全てを
取り込んでよい)。検査は五つで、正本は CODE_CHECKS。

- import 境界(error): 入口は入口を取り込まない/共有コアは入口を取り込まない/
  _registry は体系内の何も取り込まない。ドメイン駆動の境界(ADR-047)の機械化。
- 二重定義リテラル(advisory): 二つ以上のファイルに現れる同一のタプル・集合・
  長い文字列定数の代入。「規則を二重定義しない」の機械化。
- 肥大(advisory): 上限(LIMITS)を超える関数・ファイル。分割の判断は人に残す。
- 解析不能(error): 構文解析に失敗した対象を黙って飛ばさない。

保証限界:
- 予防: 何も予防しない。CI の門(--fail-on error)が止めるのは error だけ。
- 検出: 上の五つ。字面の一致に限る(意味的に同じで綴りが違う重複は見えない)。
- 委ねる: 分割・統合・設計の良し悪し・test-first の順序・抽象の先取りの判定
  (PROC-001 が保証限界として持つ)。

標準ライブラリのみ。決して例外を外へ出さない(解析不能は所見で返す)。
"""
import ast
import json
import os
import sys

SCHEMA = "code-audit/1"

# 検査名の正本(ADR-068)。足す・消すときは転記表の試験を同じ変更で更新する。
CODE_CHECKS = (
    "code_import_violation",
    "code_duplicate_literal",
    "code_oversize_function",
    "code_oversize_file",
    "code_parse_error",
)

# 上限の正本(ADR-068)。転記表の試験が凍結する。
LIMITS = {
    "function_lines": 120,     # 関数の行数の上限(超過は advisory)
    "file_lines": 1300,        # ファイルの行数の上限(超過は advisory)
    "min_str_len": 10,         # 二重定義とみなす文字列定数の最小長
    "min_collection_len": 2,   # 二重定義とみなすタプル/集合の最小要素数
}

SEV_ERROR = "error"
SEV_ADVISORY = "advisory"


def _finding(check, severity, path, line, message):
    return {"check": check, "severity": severity, "path": path,
            "line": line, "message": message}


def default_root():
    """既定の対象の根(このスクリプトが属するリポジトリの根)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def target_files(root):
    """検査対象の一覧(root からの相対、整列)。無いディレクトリは無視する。"""
    out = []
    for sub in ("plugin/scripts", "scripts"):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                out.append(os.path.join(sub, name).replace(os.sep, "/"))
    return out


def _stem(relpath):
    return os.path.basename(relpath)[:-3]


def _parse(root, rel):
    """(tree, 行数, 所見) を返す。読めない/解析できないときは tree が None。"""
    try:
        with open(os.path.join(root, rel), "r", encoding="utf-8-sig") as fh:
            src = fh.read()
        return ast.parse(src), src.count("\n") + 1, None
    except SyntaxError as exc:
        return None, 0, _finding(
            "code_parse_error", SEV_ERROR, rel, exc.lineno or 0,
            "構文解析に失敗した(%s)。黙って飛ばさず error で告げる" % exc.msg)
    except (OSError, UnicodeError, ValueError) as exc:
        return None, 0, _finding(
            "code_parse_error", SEV_ERROR, rel, 0,
            "読めない(%r)。黙って飛ばさず error で告げる" % (exc,))


def _imported_names(tree):
    """import 文が指すモジュール名(先頭の一語)と行番号の対を返す。"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def check_import_boundaries(parsed):
    """import 境界の三条(ADR-068)。違反は error。"""
    stems = {_stem(rel) for rel in parsed}
    out = []
    for rel in sorted(parsed):
        tree = parsed[rel]
        me = _stem(rel)
        me_is_core = me.startswith("_")
        for name, line in _imported_names(tree):
            if name not in stems:
                continue                      # 体系の外(標準ライブラリ等)。
            target_is_core = name.startswith("_")
            if me == "_registry":
                out.append(_finding(
                    "code_import_violation", SEV_ERROR, rel, line,
                    "_registry は最下層であり、体系内の %s を取り込めない"
                    "(ADR-068)" % name))
            elif me_is_core and not target_is_core:
                out.append(_finding(
                    "code_import_violation", SEV_ERROR, rel, line,
                    "共有コアが入口スクリプト %s を取り込んでいる。共有コアは"
                    "入口の利用者ではない(ADR-047/ADR-068)" % name))
            elif not me_is_core and not target_is_core:
                out.append(_finding(
                    "code_import_violation", SEV_ERROR, rel, line,
                    "入口スクリプトが他の入口 %s を取り込んでいる。共通部は"
                    "共有コアへ出す(ADR-068)" % name))
    return out


def _literal_key(value):
    """二重定義の照合キー。対象外の形なら None。"""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        if len(value.value) >= LIMITS["min_str_len"]:
            return "str:" + value.value
        return None
    if isinstance(value, (ast.Tuple, ast.Set)):
        if len(value.elts) < LIMITS["min_collection_len"]:
            return None
        try:
            return "col:" + ast.dump(value)
        except Exception:
            return None
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset" and len(value.args) == 1):
        return _literal_key(value.args[0])
    return None


def check_duplicate_literals(parsed):
    """二重定義リテラル(advisory)。二つ以上のファイルに同じ代入値。"""
    seen = {}   # key -> [(rel, line)]
    for rel in sorted(parsed):
        for node in ast.walk(parsed[rel]):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if value is None:
                continue
            key = _literal_key(value)
            if key is None:
                continue
            seen.setdefault(key, []).append((rel, node.lineno))
    out = []
    for key in sorted(seen):
        places = seen[key]
        files = sorted({rel for rel, _ in places})
        if len(files) < 2:
            continue
        rel, line = sorted(places)[0]
        out.append(_finding(
            "code_duplicate_literal", SEV_ADVISORY, rel, line,
            "同一のリテラルが複数ファイルに定義されている(%s)。正本を一つに"
            "して import で共有する(DECIDED-001 事実1)" % ", ".join(
                "%s:%d" % (r, l) for r, l in sorted(places))))
    return out


def check_oversize(parsed, line_counts):
    """肥大(advisory)。関数とファイルの上限超過を名指しする。"""
    out = []
    for rel in sorted(parsed):
        if line_counts[rel] > LIMITS["file_lines"]:
            out.append(_finding(
                "code_oversize_file", SEV_ADVISORY, rel, 0,
                "ファイルが %d 行で上限 %d を超える。分割の判断を促す兆候"
                "(判断は人に残す)" % (line_counts[rel], LIMITS["file_lines"])))
        for node in ast.walk(parsed[rel]):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > LIMITS["function_lines"]:
                out.append(_finding(
                    "code_oversize_function", SEV_ADVISORY, rel, node.lineno,
                    "関数 %s が %d 行で上限 %d を超える(判断は人に残す)"
                    % (node.name, length, LIMITS["function_lines"])))
    return out


def run(root):
    """全検査を走らせ、(所見, 対象数) を返す。決定的(整列済み)。"""
    findings = []
    parsed = {}
    line_counts = {}
    targets = target_files(root)
    for rel in targets:
        tree, n, err = _parse(root, rel)
        if err is not None:
            findings.append(err)
            continue
        parsed[rel] = tree
        line_counts[rel] = n
    findings += check_import_boundaries(parsed)
    findings += check_duplicate_literals(parsed)
    findings += check_oversize(parsed, line_counts)
    findings.sort(key=lambda f: (f["check"], f["path"], f["line"]))
    return findings, len(targets)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = None
    as_json = False
    fail_on = "never"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            root = argv[i + 1]; i += 2
        elif a == "--json":
            as_json = True; i += 1
        elif a == "--fail-on" and i + 1 < len(argv):
            if argv[i + 1] not in ("error", "never"):
                sys.stderr.write("usage: --fail-on error|never\n")
                return 2
            fail_on = argv[i + 1]; i += 2
        else:
            sys.stderr.write(
                "usage: code-audit.py [--root PATH] [--json] "
                "[--fail-on error|never]\n")
            return 2
    if root is None:
        root = default_root()

    findings, total = run(root)
    totals = {SEV_ERROR: 0, SEV_ADVISORY: 0}
    for f in findings:
        totals[f["severity"]] = totals.get(f["severity"], 0) + 1

    if as_json:
        payload = {"schema": SCHEMA, "checks_run": list(CODE_CHECKS),
                   "targets": total, "totals": totals, "findings": findings}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write("code-audit: 対象 %d / error %d / advisory %d\n"
                         % (total, totals[SEV_ERROR], totals[SEV_ADVISORY]))
        for f in findings:
            where = "%s:%d" % (f["path"], f["line"]) if f["line"] else f["path"]
            sys.stdout.write("  [%s] %s  %s\n"
                             % (f["severity"], where, f["message"]))
    if fail_on == "error" and totals[SEV_ERROR] > 0:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:   # 決して例外で終わらない(CI の读めない失敗を防ぐ)。
        sys.stderr.write("code-audit: internal error: %r\n" % (exc,))
        sys.exit(0)
