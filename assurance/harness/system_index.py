#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""doctrine の現状の索引（MAP_COVERAGE の入力。標準ライブラリのみ）。

網羅の割当は「規範の原則 × doctrine の現状」で決まる。現状を評価セッションへ
渡す方法は二つあり得た:

- 評価者にツールを与えて木を読ませる: 隔離（`setting_sources=[]`・空の一時 cwd・
  `allowed_tools=()`）が崩れ、何を読んだかが記録に残らない。
- 決定論で索引を組んで渡す: 入力が指紋で固定でき、返ってきた証拠ポインタを
  索引と機械照合できる。**こちらを採る。**

索引はリポジトリから毎回組み直す（写しを台帳へ置かない）。証拠ポインタの照合は
`resolve_pointer` が担い、解決できないポインタを根拠にした「実装・試験・証拠あり」は
`prompts.verify_coverage_assignments` が UNKNOWN へ落とす。
"""
import hashlib
import json
import os
import re

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
DOCS_ROOT = os.path.join(REPO_DIR, "doctrine_docs")
SCRIPTS_DIR = os.path.join(REPO_DIR, "plugin", "scripts")
TESTS_DIR = os.path.join(REPO_DIR, "plugin", "tests")
SKILLS_DIR = os.path.join(REPO_DIR, "plugin", "skills")
HOOKS_PATH = os.path.join(REPO_DIR, "plugin", "hooks", "hooks.json")

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_CODE_RE = re.compile(r'"([A-Z][A-Z0-9_]{4,})"')
_DEF_TEST_RE = re.compile(r"^def (test_[a-z0-9_]+)", re.M)


def _front_matter(text):
    """先頭のフロントマターを素朴に読む（レーン内の索引用。正本の解析器は使わない）。

    配布物 `plugin/` の解析器をレーンから import しない規律（assurance/README.md）に
    従い、ここでは id/type/domain/title/status の5キーだけを行単位で拾う。
    """
    m = _FM_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in ("id", "type", "domain", "title", "status"):
            out[key] = value.strip().strip('"').strip("'")
    return out


def _first_docstring_line(path):
    """モジュールの説明の一行目。無ければ None。"""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(4000)
    except OSError:
        return None
    m = re.search(r'"""(.+?)$', text, re.M)
    return m.group(1).strip().rstrip('"') if m else None


def documents():
    """現行の統治文書（id・型・ドメイン・題）。status が current でないものも
    区別して持つ（規範が「廃止の手続き」を要求するとき、廃止済みの存在が証拠になる）。"""
    out = []
    for root, dirs, files in os.walk(DOCS_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8") as f:
                    meta = _front_matter(f.read(4000))
            except OSError:
                continue
            if not meta.get("id"):
                continue
            meta["path"] = os.path.relpath(path, REPO_DIR)
            out.append(meta)
    return sorted(out, key=lambda m: m["id"])


def audit_checks():
    """監査の検査名。監査自身に語らせる（名の二重定義をしない）。"""
    path = os.path.join(SCRIPTS_DIR, "docs-audit.py")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    m = re.search(r"CHECKS\s*=\s*\(([^)]*)\)", text, re.S)
    names = sorted(set(re.findall(r'"([a-z][a-z0-9_]+)"', m.group(1)))) if m else []
    return names


def linter_codes():
    path = os.path.join(SCRIPTS_DIR, "docs-linter.py")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    return sorted(set(_CODE_RE.findall(text)) - {"ERROR", "WARN", "RESEARCH"})


def scripts():
    if not os.path.isdir(SCRIPTS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(SCRIPTS_DIR)):
        if not name.endswith(".py"):
            continue
        out.append({"path": "plugin/scripts/%s" % name,
                    "note": _first_docstring_line(
                        os.path.join(SCRIPTS_DIR, name))})
    return out


def test_files():
    if not os.path.isdir(TESTS_DIR):
        return []
    out = []
    for name in sorted(os.listdir(TESTS_DIR)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        path = os.path.join(TESTS_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        out.append({"path": "plugin/tests/%s" % name,
                    "tests": len(_DEF_TEST_RE.findall(text)),
                    "note": _first_docstring_line(path)})
    return out


def hooks():
    try:
        with open(HOOKS_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for event, groups in (cfg.get("hooks") or {}).items():
        names = []
        for group in groups:
            for hook in group.get("hooks", []):
                m = re.search(r"scripts/([a-z0-9-]+\.py)", hook.get("command", ""))
                if m:
                    names.append(m.group(1))
        out[event] = names
    return out


def skills():
    if not os.path.isdir(SKILLS_DIR):
        return []
    return sorted(d for d in os.listdir(SKILLS_DIR)
                  if os.path.isdir(os.path.join(SKILLS_DIR, d)))


def build():
    """索引一式。指紋つき（同じ索引に対する割当であることを台帳が示せる）。"""
    idx = {
        "documents": documents(),
        "audit_checks": audit_checks(),
        "linter_codes": linter_codes(),
        "scripts": scripts(),
        "test_files": test_files(),
        "hooks": hooks(),
        "skills": skills(),
    }
    idx["sha256"] = hashlib.sha256(
        json.dumps(idx, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return idx


def resolve_pointer(idx, pointer):
    """証拠ポインタが索引の中で解決するか。解決しないものを根拠に使わせない。

    受け付ける形:
    - 文書 id（`SPEC-011`）
    - リポジトリ相対のファイルの場所（`plugin/scripts/docs-audit.py`）
    - 監査の検査名（`adr_not_landed`）・リンタの検査コード（`MISSING_KEY`）
    - Hook のイベント名（`SessionEnd`）
    - `plugin/tests/test_x.py::test_name` の形（試験の実在を本文で照合する）
    """
    ptr = (pointer or "").strip()
    if not ptr:
        return None
    if ptr in {d["id"] for d in idx["documents"]}:
        return "document"
    if ptr in idx["audit_checks"]:
        return "audit_check"
    if ptr in idx["linter_codes"]:
        return "linter_code"
    if ptr in idx["hooks"]:
        return "hook_event"
    if ptr in idx["skills"]:
        return "skill"
    path, sep, test_name = ptr.partition("::")
    full = os.path.join(REPO_DIR, path)
    if not os.path.exists(full):
        return None
    if not sep:
        return "file"
    try:
        with open(full, encoding="utf-8") as f:
            body = f.read()
    except OSError:
        return None
    return "test" if re.search(
        r"\bdef %s\b" % re.escape(test_name), body) else None


def as_prompt_text(idx):
    """索引の平文。判断は入れず、在るものだけを並べる。"""
    lines = ["### 統治文書（id ｜ 型 ｜ ドメイン ｜ status ｜ 題）"]
    for d in idx["documents"]:
        lines.append("- %s ｜ %s ｜ %s ｜ %s ｜ %s"
                     % (d.get("id"), d.get("type"), d.get("domain"),
                        d.get("status"), d.get("title")))
    lines.append("")
    lines.append("### 監査の検査名（%d 件）" % len(idx["audit_checks"]))
    lines.append(", ".join(idx["audit_checks"]))
    lines.append("")
    lines.append("### リンタの検査コード（%d 件）" % len(idx["linter_codes"]))
    lines.append(", ".join(idx["linter_codes"]))
    lines.append("")
    lines.append("### Hook の配線（イベント → スクリプト）")
    for event, names in idx["hooks"].items():
        lines.append("- %s: %s" % (event, ", ".join(names) or "(なし)"))
    lines.append("")
    lines.append("### スクリプト")
    for s in idx["scripts"]:
        lines.append("- %s — %s" % (s["path"], s["note"] or ""))
    lines.append("")
    lines.append("### 試験ファイル（件数つき。合計 %d 件）"
                 % sum(t["tests"] for t in idx["test_files"]))
    for t in idx["test_files"]:
        lines.append("- %s（%d 件） — %s" % (t["path"], t["tests"], t["note"] or ""))
    lines.append("")
    lines.append("### 配布 Skill（7個固定）")
    lines.append(", ".join(idx["skills"]))
    return "\n".join(lines)
