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

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _config
import _registry  # noqa: E402
import _tracescan  # noqa: E402

# doctrine:begin SPEC-026
SCHEMA = "trace-index/1"
USAGE = ("trace-index.py [--root PATH] [--docs-root PATH] [--id ID] "
         "[--coverage] [--term TERM] [--format json|text] [--max-files N]")
# doctrine:end SPEC-026


def _valid_terms():
    """--term に許す項の一覧(ADR-058/ADR-067)。勘定の枠と同じ正本から導く。"""
    terms = ["annotated", "unmarked", "exempt"]
    terms += ["excluded:%s" % rid
              for rid, kind in _tracescan.EXCLUSION_RULES if kind == "file"]
    terms += ["pruned:%s" % rid
              for rid, kind in _tracescan.EXCLUSION_RULES if kind == "dir"]
    return terms


def _parse_args(argv):
    """最小の引数解析。誤りがあれば (None, 理由) を返す。"""
    opts = {"root": None, "docs_root": None, "doc_id": None,
            "format": "text", "max_files": _tracescan.DEFAULT_MAX_FILES,
            "coverage": False, "term": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root" and i + 1 < len(argv):
            opts["root"] = argv[i + 1]; i += 2
        elif a == "--docs-root" and i + 1 < len(argv):
            opts["docs_root"] = argv[i + 1]; i += 2
        elif a == "--id" and i + 1 < len(argv):
            opts["doc_id"] = argv[i + 1].strip(); i += 2
        elif a == "--coverage":
            opts["coverage"] = True; i += 1
        elif a == "--term" and i + 1 < len(argv):
            term = argv[i + 1].strip()
            if term not in _valid_terms():
                return None, ("不明な項: %s(許す項: %s)"
                              % (term, ", ".join(_valid_terms())))
            opts["term"] = term; i += 2
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
    if opts["term"] and not opts["coverage"]:
        return None, "--term は --coverage と共に使う"
    return opts, None


def _resolve_roots(opts):
    """(走査の根, 統治木) を決める。統治木の親を走査の根の既定にする。"""
    docs_root = opts["docs_root"]
    if not docs_root:
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        docs_root = (_registry.locate_docs_root(proj)
                     or _registry.walkup_docs_root(proj))
    root = opts["root"]
    if not root:
        root = os.path.dirname(os.path.abspath(docs_root)) if docs_root else None
    return root, docs_root


def _exempt_paths(docs_root):
    """設定 `_system/.context-config.json` の trace_exempt を読む(ADR-075)。

    監査は同じ設定を読んで「印なし」を数えるのに、この問い合わせ CLI は読んで
    いなかった。そのため監査が「印なし 0 / exempt 51」と告げる木で、監査自身が
    是正の案内として指す `trace-index --coverage --term unmarked` が 24 件を
    並べるという食い違いが起きていた。同じ設定を読み、同じ答えを返す。
    """
    if not docs_root:
        return []
    # 読み取りは共有コアが正本(ADR-104)。道も符号化も自前に持たない。
    cfg = _config.load(docs_root)
    exempt = cfg.get("trace_exempt")
    if not isinstance(exempt, dict):
        return []
    return [p for p, reason in exempt.items()
            if isinstance(p, str) and p.strip()
            and isinstance(reason, str) and reason.strip()]


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

    ranges, findings, coverage = _tracescan.scan_tree(
        root, docs_root=docs_root, max_files=opts["max_files"],
        collect_members=bool(opts["term"]),
        exempt_paths=_exempt_paths(docs_root))
    if opts["doc_id"]:
        ranges = [r for r in ranges if r["id"] == opts["doc_id"]]

    if opts["coverage"]:
        # 勘定の問い合わせ(ADR-058)。既定は件数、--term で当該の一覧をその場で
        # 導出する(保存しない。ADR-055 と同じ原理)。
        if opts["term"]:
            names = coverage.get("members", {}).get(opts["term"], [])
            if opts["format"] == "json":
                payload = {"schema": SCHEMA, "root": os.path.basename(
                    os.path.abspath(root)), "term": opts["term"],
                    "count": len(names), "paths": names}
                sys.stdout.write(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            else:
                out = ["# trace-index coverage", "項: %s" % opts["term"],
                       "件数: %d" % len(names)]
                out += ["  %s" % p for p in names]
                sys.stdout.write("\n".join(out) + "\n")
            return 0
        cov = {k: v for k, v in coverage.items() if k != "members"}
        if opts["format"] == "json":
            payload = {"schema": SCHEMA, "root": os.path.basename(
                os.path.abspath(root)), "coverage": cov}
            sys.stdout.write(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        else:
            out = ["# trace-index coverage",
                   "到達: %d / 寄与: %d / 印なし: %d / 明示管理外: %d / 打ち切り: %s"
                   % (cov["reached_files"], cov["annotated_files"],
                      cov["unmarked_files"], cov.get("exempt_files", 0),
                      cov["truncated"])]
            for rid in sorted(cov["excluded"]):
                out.append("  除外 %-12s %d" % (rid, cov["excluded"][rid]))
            for rid in sorted(cov["pruned_dirs"]):
                out.append("  刈り %-12s %d" % (rid, cov["pruned_dirs"][rid]))
            sys.stdout.write("\n".join(out) + "\n")
        return 0

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
