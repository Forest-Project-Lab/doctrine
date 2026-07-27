#!/usr/bin/env python3
"""トレース索引の問い合わせ(SPEC-026 / ADR-055)。`_tracescan` の薄い前面。

索引はファイルに置かない。問い合わせのたびに走査して導出する(ADR-055)。
版管理に生成物を置かないので、取り込み依頼の衝突も、行番号がずれただけの
差分も生じない。

保証限界:
- 予防: 何も予防しない。問い合わせのための CLI であって、違反を止めるゲート
  ではない(dep-graph と同じ規約)。
- 検出: 範囲の一覧と、対応付けの誤り(入れ子・両端の id の不一致・閉じ忘れ・
  開いていない end)を返す。古びの判定は監査に委ねる(記録した指紋との照合)。
- 委ねる: 印が意味の上で正しい場所に打たれているかは判定しない。改名・移動は
  追わない。印を打っていないコードは追跡の外にある。

標準ライブラリのみ。決して例外を外へ出さない。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _registry  # noqa: E402
import _tracescan  # noqa: E402

SCHEMA = "trace-index/1"
USAGE = ("trace-index.py [--root PATH] [--docs-root PATH] [--id ID] "
         "[--format json|text] [--max-files N]")


def _parse_args(argv):
    """最小の引数解析。誤りがあれば (None, 理由) を返す。"""
    opts = {"root": None, "docs_root": None, "doc_id": None,
            "format": "text", "max_files": _tracescan.DEFAULT_MAX_FILES}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            opts["root"] = argv[i + 1]; i += 2
        elif a == "--docs-root" and i + 1 < len(argv):
            opts["docs_root"] = argv[i + 1]; i += 2
        elif a == "--id" and i + 1 < len(argv):
            opts["doc_id"] = argv[i + 1].strip(); i += 2
        elif a == "--format" and i + 1 < len(argv):
            if argv[i + 1] not in ("json", "text"):
                return None, "不明な形式: %s" % argv[i + 1]
            opts["format"] = argv[i + 1]; i += 2
        elif a == "--max-files" and i + 1 < len(argv):
            try:
                opts["max_files"] = int(argv[i + 1])
            except ValueError:
                return None, "--max-files は整数"
            i += 2
        else:
            return None, "不明な引数: %s" % a
    return opts, None


def _resolve_roots(opts):
    """(走査の根, 統治木) を決める。統治木の親を走査の根の既定にする。"""
    docs_root = opts["docs_root"]
    if not docs_root:
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        docs_root = _registry.locate_docs_root(proj)
    root = opts["root"]
    if not root:
        root = os.path.dirname(os.path.abspath(docs_root)) if docs_root else None
    return root, docs_root


def _render_text(ranges, findings, doc_id):
    out = ["# trace-index"]
    if doc_id:
        out.append("id: %s" % doc_id)
    out.append("範囲: %d 件 / 所見: %d 件" % (len(ranges), len(findings)))
    for r in ranges:
        out.append("  %s  %s:%d-%d  %s"
                   % (r["id"], r["path"], r["begin_line"], r["end_line"],
                      r["fingerprint"]))
    for f in findings:
        where = ("%s:%d" % (f["path"], f["line"])) if f["path"] else "(全体)"
        out.append("  [%s] %s  %s" % (f["code"], where, f["message"]))
    if not ranges and not findings:
        out.append("  (印のある範囲は無い)")
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    opts, err = _parse_args(argv)
    if opts is None:
        sys.stderr.write("usage error: %s\n%s\n" % (err, USAGE))
        return 2

    root, docs_root = _resolve_roots(opts)
    if not root or not os.path.isdir(root):
        sys.stderr.write("走査の根が見つからない\n")
        return 3

    ranges, findings = _tracescan.scan_tree(
        root, docs_root=docs_root, max_files=opts["max_files"])
    if opts["doc_id"]:
        ranges = [r for r in ranges if r["id"] == opts["doc_id"]]

    if opts["format"] == "json":
        # root は名前だけを載せる。絶対パスを外へ出さない(機械をまたいで
        # 共有できる形を保つ。ADR-055)。
        payload = {"schema": SCHEMA, "root": os.path.basename(
            os.path.abspath(root)), "ranges": ranges, "findings": findings}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(_render_text(ranges, findings, opts["doc_id"]) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 問い合わせで会話を止めない
        sys.stderr.write("trace-index: internal error: %r\n" % (exc,))
        sys.exit(3)
