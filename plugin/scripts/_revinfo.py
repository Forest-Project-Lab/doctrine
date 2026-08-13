#!/usr/bin/env python3
"""測った木の版と作り手(ADR-155/ADR-156)。宣言済みの読み口が共有する解決。

返す値の最上位に載る三つの鍵(`source_revision`・`source_dirty`・`generator`)の
解決を一箇所に置く。各スクリプトで再実装しない(SPEC-026/SPEC-006/SPEC-011)。

- `source_revision`: 測った木の HEAD の完全 SHA。git で解決できなければ None。
- `source_dirty`: 未コミットの変更(無視されないファイルの追加を含む)の有無。
  git で解決できなければ None。dirty でも SHA は解決できる限り書く —— 読み手が
  版の証拠を割り引けるように、嘘をつく代わりに印を添える(ADR-155)。
- `generator`: {"name": <スクリプト名>, "version": <plugin.json の版 | None>}。

標準ライブラリのみ。git は subprocess で呼ぶ(map-draft-check の D2 と同じ作法)。
決して例外を外へ出さない。
"""
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _auditcache  # noqa: E402

# doctrine:begin SPEC-026
_GIT_TIMEOUT_SEC = 10


def _git(path, *args):
    """git を一度呼ぶ。(returncode, stdout) を返し、呼べなければ (None, "")。"""
    try:
        proc = subprocess.run(
            ["git", "-C", path] + list(args),
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SEC)
        return proc.returncode, (proc.stdout or "")
    except Exception:
        return None, ""


def revision_of(path):
    """測った木の版の二鍵を返す(ADR-155)。

    {"source_revision": <完全SHA|None>, "source_dirty": <bool|None>}
    解決できない(git が無い・リポジトリでない・コミットが無い)ときは両方 None。
    "分からない" を空文字や欄の省略にしない(#294 の規律)。
    """
    out = {"source_revision": None, "source_dirty": None}
    if not path or not os.path.isdir(path):
        return out
    code, text = _git(path, "rev-parse", "HEAD")
    if code != 0:
        return out
    sha = text.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
        return out
    out["source_revision"] = sha
    code, text = _git(path, "status", "--porcelain")
    if code == 0:
        out["source_dirty"] = bool(text.strip())
    return out


def generator_info(name):
    """作り手の自己記述(ADR-155)。version は plugin.json の版か None。"""
    return {"name": name, "version": _auditcache.plugin_version()}
# doctrine:end SPEC-026
