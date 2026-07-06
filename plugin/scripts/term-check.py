#!/usr/bin/env python3
"""用語チェッカーのCLI. _termcheck の薄い前面(リンタからも呼ばれる中核の単体実行)。

保証限界:
- 予防: 何も予防しない。助言のみ(リンタの一機能。§4.2)。
- 検出: 与えられたファイルの本文を §1 辞書で点検し、禁止同義語・カルク・
  一語訳の罠・未定義語の初出を出力する。
- 委ねる: 一覧に無い訳語臭の判定は doc-review に、辞書の定義は GLOSSARY 正本に
  委ねる。全件走査・参照整合は監査に委ねる。

標準ライブラリのみ。常に終了コード 0(リンタの一機能として Hook 連鎖を壊さない)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter
import _termcheck


def _resolve_docs_root(file_path, explicit):
    """Resolve the target repo docs/ root for glossary lookup.

    Uses --docs-root when given; otherwise walks up from the file looking for a
    'docs' directory (the tree that holds _system/glossary.md). Returns the docs
    dir path or None (None -> _termcheck falls back to the template seed).
    """
    if explicit:
        return explicit
    if not file_path:
        return None
    cur = os.path.dirname(os.path.abspath(file_path))
    # Walk up; stop at filesystem root.
    while True:
        base = os.path.basename(cur)
        if base == "docs":
            return cur
        cand = os.path.join(cur, "docs")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _parse_args(argv):
    """Minimal arg parse: [--docs-root R] FILE... . Returns (docs_root, files)."""
    docs_root = None
    files = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--docs-root":
            i += 1
            docs_root = argv[i] if i < len(argv) else None
        elif a.startswith("--docs-root="):
            docs_root = a.split("=", 1)[1]
        else:
            files.append(a)
        i += 1
    return docs_root, files


def check_file(path, docs_root_opt):
    """Check one file; return (findings, rendered_text). Never raises."""
    try:
        meta, body, _errs = _frontmatter.parse_file(path)
    except (OSError, UnicodeError):
        return [], ""
    docs_root = _resolve_docs_root(path, docs_root_opt)
    glossary = _termcheck.load_glossary(docs_root)
    findings = _termcheck.check(body, meta, glossary)
    return findings, _termcheck.render_findings(findings, path)


def main(argv=None):
    """Entry point. Prints findings per file. Exit always 0."""
    if argv is None:
        argv = sys.argv[1:]
    try:
        docs_root, files = _parse_args(argv)
        blocks = []
        for path in files:
            if not os.path.isfile(path):
                continue
            findings, rendered = check_file(path, docs_root)
            if findings and rendered:
                blocks.append(rendered)
        if blocks:
            sys.stdout.write("\n".join(blocks) + "\n")
    except Exception as exc:  # never raise out of a linter-adjacent CLI
        sys.stdout.write("term-check: internal error: %r\n" % (exc,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
