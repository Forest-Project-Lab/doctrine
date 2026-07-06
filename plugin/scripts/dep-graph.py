#!/usr/bin/env python3
"""依存グラフの問い合わせCLI。_depgraph の薄い覆い(MASTER §5.2)。

保証限界:
- 予防: 何も予防しない。問い合わせ専用の道具であり、ゲートではない。
- 検出: 影響集合・逆依存・端の分類・逆孤児・逆参照を表に出す。
- 委ねる: 拒否や合否の判定はガード(policy-guard)とCI(docs-audit)に委ねる。
  そのため所見が空でなくても終了コードは 0 のまま(ゲートと取り違えないため)。

CLI(slice 05 A.6):
  dep-graph.py [--root docs/] <mode> [--json] [--current-only] [--transitive]
  modes:
    --impacts ID         ID の前向き影響集合(impacts 端の推移閉包)
    --dependents ID      ID への直接の逆依存(depends_on 端)。--transitive で閉包
    --classify-edges     全端を分類(R7 のドメイン越え報告)
    --reverse-orphans    逆孤児の二バケツ(REQ無SPEC / SPEC無TEST)
    --reverse-refs ID    ID に依存する現行文書(削除安全ガードが呼ぶ正確な形。既定 current-only)
終了コード: 0 問い合わせ成立(所見が非空でも0)。2 使い方の誤り。3 ルート不在。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph


def _parse_args(argv):
    """argv を (opts, error_message) に解く。error があれば usage 終了に回す。"""
    opts = {
        "root": "docs",
        "mode": None,
        "id": None,
        "json": False,
        "current_only": False,
        "transitive": False,
    }
    modes = {
        "--impacts": "impacts",
        "--dependents": "dependents",
        "--classify-edges": "classify-edges",
        "--reverse-orphans": "reverse-orphans",
        "--reverse-refs": "reverse-refs",
    }
    needs_id = {"impacts", "dependents", "reverse-refs"}

    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--root":
            if i + 1 >= n:
                return None, "--root にはパスが必要"
            opts["root"] = argv[i + 1]
            i += 2
            continue
        if a == "--json":
            opts["json"] = True
            i += 1
            continue
        if a == "--current-only":
            opts["current_only"] = True
            i += 1
            continue
        if a == "--transitive":
            opts["transitive"] = True
            i += 1
            continue
        if a in modes:
            if opts["mode"] is not None:
                return None, "モードは一つだけ指定する"
            opts["mode"] = modes[a]
            if modes[a] in needs_id:
                if i + 1 >= n:
                    return None, "%s には ID が必要" % a
                opts["id"] = argv[i + 1]
                i += 2
            else:
                i += 1
            continue
        return None, "不明な引数: %s" % a

    if opts["mode"] is None:
        return None, "モードを一つ指定する(--impacts/--dependents/--classify-edges/--reverse-orphans/--reverse-refs)"
    return opts, None


def _usage(msg):
    sys.stdout.write("usage error: %s\n" % msg)
    sys.stdout.write(
        "dep-graph.py [--root docs/] "
        "(--impacts ID | --dependents ID | --classify-edges | "
        "--reverse-orphans | --reverse-refs ID) "
        "[--json] [--current-only] [--transitive]\n"
    )
    return 2


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    root = opts["root"]
    if not os.path.isdir(root):
        sys.stdout.write("root not found: %s\n" % root)
        return 3

    g = _depgraph.build_graph(root)
    mode = opts["mode"]

    if mode == "impacts":
        result = sorted(g.forward_impacts(opts["id"]))
        _emit(opts, {"mode": "impacts", "id": opts["id"], "result": result}, g)
        return 0

    if mode == "dependents":
        deps = g.reverse_dependents(
            opts["id"],
            current_only=opts["current_only"],
            transitive=opts["transitive"],
        )
        result = sorted(deps)
        _emit(opts, {"mode": "dependents", "id": opts["id"], "result": result}, g)
        return 0

    if mode == "reverse-refs":
        # 削除安全ガードの正確な呼び出し。常に current-only(降格は現行の依存ゼロを問う)。
        deps = g.reverse_dependents(opts["id"], current_only=True)
        result = sorted(deps)
        _emit(opts, {"mode": "reverse-refs", "id": opts["id"],
                     "count": len(result), "result": result}, g)
        return 0

    if mode == "classify-edges":
        edges = [dict(e) for e in g.classify_edges()]
        _emit(opts, {"mode": "classify-edges", "result": edges}, g)
        return 0

    if mode == "reverse-orphans":
        result = g.reverse_orphans()
        _emit(opts, {"mode": "reverse-orphans", "result": result}, g)
        return 0

    return _usage("内部エラー: 未対応モード")


def _emit(opts, payload, g):
    if opts["json"]:
        out = {
            "nodes": [dict(n) for n in g.to_json()["nodes"]],
            "edges": [dict(e) for e in g.classify_edges()],
            "result": payload["result"] if "result" in payload else payload,
        }
        # mode 固有の付加情報(count, id 等)も載せる。
        for k, v in payload.items():
            if k not in ("result",):
                out[k] = v
        sys.stdout.write(json.dumps(out, ensure_ascii=False, sort_keys=True) + "\n")
        return
    _emit_text(payload)


def _emit_text(payload):
    mode = payload["mode"]
    if mode in ("impacts", "dependents"):
        ids = payload["result"]
        if not ids:
            sys.stdout.write("(none)\n")
        else:
            for i in ids:
                sys.stdout.write(i + "\n")
        return
    if mode == "reverse-refs":
        sys.stdout.write("count: %d\n" % payload["count"])
        for i in payload["result"]:
            sys.stdout.write(i + "\n")
        return
    if mode == "classify-edges":
        for e in payload["result"]:
            sys.stdout.write("%s --%s--> %s  [%s]\n"
                             % (e["src"], e["field"], e["dst"], e["kind"]))
        if not payload["result"]:
            sys.stdout.write("(no edges)\n")
        return
    if mode == "reverse-orphans":
        r = payload["result"]
        sys.stdout.write("req_without_spec:\n")
        for i in r["req_without_spec"]:
            sys.stdout.write("  " + i + "\n")
        sys.stdout.write("spec_without_test:\n")
        for i in r["spec_without_test"]:
            sys.stdout.write("  " + i + "\n")
        return


if __name__ == "__main__":
    sys.exit(main())
