#!/usr/bin/env python3
"""linter と audit の整合点検 — 支え③の最初の一本。

不変条件(これが破れたら赤):
    audit が「登録済みの非文書」(.md-intake に 非文書/投影 として記録)と
    見なすファイルに、linter が ERROR を出してはならない。

audit(全体を見る)と linter(一件を見る)は、同じファイルへの判定が
食い違ってはいけない。食い違えば、それは 2026-07 に見つけた欠陥クラス
(同じ入力を二つの道具が別々に裁き、意味的に矛盾する)の再発である。

やること:
    1. 統治木(doctrine_docs)を見つけ、その親(プロジェクト根)を走査する。
    2. .md-intake を読む(audit の実ロジックをそのまま再利用)。
    3. 「非文書/投影」と登録された各 .md に linter を実際に走らせる。
    4. linter が ERROR を出したら食い違いとして挙げる。

食い違いが 1 件でもあれば終了コード 1、無ければ 0。決定的。標準ライブラリのみ。
"""
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PLUGIN_SCRIPTS = os.path.join(REPO, "plugin", "scripts")
LINTER = os.path.join(PLUGIN_SCRIPTS, "docs-linter.py")


def _load(name, filename):
    """ハイフン入りファイル名のスクリプトをモジュールとして読む。"""
    path = os.path.join(PLUGIN_SCRIPTS, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _linter_errors(path):
    """path に linter を走らせ、ERROR 行のコードだけ返す(空なら [])。"""
    try:
        r = subprocess.run([sys.executable, LINTER, path], input="",
                           capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return ["(点検不能: %r)" % exc]
    out = (r.stdout or "").strip()
    if not out:
        return []
    try:
        payload = json.loads(out)
        ctx = payload["hookSpecificOutput"]["additionalContext"]
    except Exception:
        return []
    codes = []
    for line in ctx.splitlines():
        s = line.strip()
        if s.startswith("[ERROR]"):
            # 形: [ERROR] CODE: メッセージ  (spec_ref)
            rest = s[len("[ERROR]"):].strip()
            code = rest.split(":", 1)[0].strip()
            codes.append(code)
    return codes


def main():
    if not os.path.isdir(PLUGIN_SCRIPTS) or not os.path.isfile(LINTER):
        sys.stderr.write("plugin/scripts が見つからない: %s\n" % PLUGIN_SCRIPTS)
        return 2

    sys.path.insert(0, PLUGIN_SCRIPTS)
    registry = _load("_registry", "_registry.py")
    audit = _load("_docs_audit", "docs-audit.py")

    docs_root = registry.walkup_docs_root(os.getcwd())
    if not docs_root:
        sys.stderr.write("統治木(doctrine_docs)が見つからない。\n")
        return 2
    proj = os.path.dirname(os.path.abspath(docs_root))

    entries, bad = audit._load_intake_ledger(docs_root)
    skip_dirs = set(getattr(audit, "_STRAY_SKIP_DIRS", ("node_modules", "__pycache__")))
    pointers = getattr(registry, "ROOT_POINTER_FILES", set())

    # プロジェクト根を走査し、「非文書/投影」登録の .md を集める。
    registered = []
    for dirpath, dirnames, filenames in os.walk(proj):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and d not in skip_dirs
            and os.path.abspath(os.path.join(dirpath, d)) != os.path.abspath(docs_root))
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            abspath = os.path.join(dirpath, name)
            rel = os.path.relpath(abspath, proj).replace(os.sep, "/")
            if rel in pointers:
                continue
            entry = audit._ledger_entry_for(rel, entries)
            if entry and entry[1] in ("非文書", "投影"):
                registered.append((rel, abspath, entry[1]))

    # 各登録ファイルに linter を走らせ、ERROR を食い違いとして挙げる。
    disagreements = []
    for rel, abspath, kind in sorted(registered):
        errs = _linter_errors(abspath)
        if errs:
            disagreements.append((rel, kind, errs))

    # 報告
    print("=" * 60)
    print("整合点検: linter ⇔ audit(登録済み非文書への ERROR)")
    print("統治木: %s" % os.path.relpath(docs_root, proj))
    print("対象(非文書/投影 登録): %d 件" % len(registered))
    print("=" * 60)
    if not disagreements:
        print("食い違いなし。linter と audit は一致している。")
        return 0
    print("食い違い %d 件 — audit は非文書と認めているのに linter が ERROR:" % len(disagreements))
    print("")
    for rel, kind, errs in disagreements:
        print("  ● %s  (intake: %s)" % (rel, kind))
        for code in errs:
            print("      linter ERROR: %s" % code)
    print("")
    print("→ これは 2026-07 の欠陥クラスの再発/残存。SPEC-007 §エラー時挙動の")
    print("  条件化(登録済み非文書では schema ERROR を抑止)で解消する。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
