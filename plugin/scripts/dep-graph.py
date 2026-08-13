#!/usr/bin/env python3
"""依存グラフの問い合わせCLI。_depgraph の薄い覆い(MASTER §5.2)。

保証限界:
- 予防: 何も予防しない。問い合わせ専用の道具であり、ゲートではない。
- 検出: 影響集合・逆依存・端の分類・逆孤児・逆参照を表に出す。
- 委ねる: 拒否や合否の判定はガード(policy-guard)とCI(docs-audit)に委ねる。
  そのため所見が空でなくても終了コードは 0 のまま(ゲートと取り違えないため)。

CLI(slice 05 A.6 / ADR-153):
  dep-graph.py [--root docs/] <mode> [--json] [--current-only] [--transitive]
  modes:
    --impacts ID         ID の前向き影響集合(impacts 端の推移閉包)
    --dependents ID      ID への直接の逆依存(depends_on 端)。--transitive で閉包
    --classify-edges     全端を分類(R7 のドメイン越え報告)
    --reverse-orphans    逆孤児の二バケツ(REQ無SPEC / SPEC無TEST)
    --reverse-refs ID    ID に依存する現行文書(削除安全ガードが呼ぶ正確な形。既定 current-only)
    --find-root [START]  統治木を探して絶対パスを返す(ADR-154。規則は ADR-022。グラフは組まない)
--json の返す値はスキーマ dep-graph/1(ICD-002)。最上位に schema・root(名前だけ)・
source_revision・source_dirty・generator(ADR-155)・mode・nodes・edges・result。
診断は標準エラーへ出し、stdout を汚さない(ADR-153)。
終了コード: 0 問い合わせ成立(所見が非空でも0)。2 使い方の誤り。3 ルート不在。
"""
import json
import os
import sys

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# doctrine:begin IMPL-006
import _depgraph
import _registry
# doctrine:end IMPL-006
import _revinfo

SCHEMA = "dep-graph/1"


def _parse_args(argv):
    """argv を (opts, error_message) に解く。error があれば usage 終了に回す。"""
    opts = {
        "root": None,   # 無指定なら cwd から統治木を解決(ADR-022)
        "mode": None,
        "id": None,
        "start": None,  # --find-root の開始位置(任意)
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
        "--find-root": "find-root",
    }
    needs_id = {"impacts", "dependents", "reverse-refs"}
    takes_optional_path = {"find-root"}

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
            elif modes[a] in takes_optional_path:
                # 開始位置は任意。次がフラグでなければ開始位置として読む。
                if i + 1 < n and not argv[i + 1].startswith("--"):
                    opts["start"] = argv[i + 1]
                    i += 2
                else:
                    i += 1
            else:
                i += 1
            continue
        return None, "不明な引数: %s" % a

    if opts["mode"] is None:
        return None, ("モードを一つ指定する(--impacts/--dependents/--classify-edges/"
                      "--reverse-orphans/--reverse-refs/--find-root)")
    return opts, None


def _usage(msg):
    # 診断は標準エラーへ。stdout を汚さない(ADR-153)。
    sys.stderr.write("usage error: %s\n" % msg)
    sys.stderr.write(
        "dep-graph.py [--root docs/] "
        "(--impacts ID | --dependents ID | --classify-edges | "
        "--reverse-orphans | --reverse-refs ID | --find-root [START]) "
        "[--json] [--current-only] [--transitive]\n"
    )
    return 2


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    if opts["mode"] == "find-root":
        # 統治木の発見(ADR-154)。グラフは組まない。規則の正本は ADR-022 で、
        # 実装は登録簿の遡りをそのまま呼ぶ(規則を写さない)。
        start = os.path.abspath(opts["start"] or os.getcwd())
        found = _registry.walkup_docs_root(start)
        found_abs = os.path.abspath(found) if found else None
        if opts["json"]:
            rev = _revinfo.revision_of(found_abs) if found_abs else {
                "source_revision": None, "source_dirty": None}
            out = {
                "schema": SCHEMA,
                "root": os.path.basename(found_abs) if found_abs else None,
                "source_revision": rev["source_revision"],
                "source_dirty": rev["source_dirty"],
                "generator": _revinfo.generator_info("dep-graph.py"),
                "mode": "find-root",
                "nodes": [],
                "edges": [],
                "result": found_abs,
            }
            sys.stdout.write(json.dumps(out, ensure_ascii=False,
                                        sort_keys=True) + "\n")
        elif found_abs:
            sys.stdout.write(found_abs + "\n")
        if found_abs:
            return 0
        sys.stderr.write("root not found: %s\n" % start)
        return 3

    root = opts["root"]
    if root is None:
        # 無指定なら cwd から統治木を解決(ADR-022: doctrine_docs 優先)。
        root = (_registry.walkup_docs_root(os.getcwd())
                or _registry.DOCS_DIR_NAMES[0])
    if not os.path.isdir(root):
        # 診断は標準エラーへ(ADR-153)。
        sys.stderr.write("root not found: %s\n" % root)
        return 3

    g = _depgraph.build_graph(root)
    mode = opts["mode"]
    opts["_root"] = root

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
        # dep-graph/1 の外部条項(ADR-153)。schema と root(名前だけ)と
        # 測った木の版・作り手(ADR-155)を最上位に名乗る。鍵の追加は互換
        # (確定事実13)。result は classify-edges では edges と重複する
        # (互換のため残す。読み手はどちらか一方だけを読む)。
        root_abs = os.path.abspath(opts.get("_root") or ".")
        rev = _revinfo.revision_of(root_abs)
        out = {
            "schema": SCHEMA,
            "root": os.path.basename(root_abs),
            "source_revision": rev["source_revision"],
            "source_dirty": rev["source_dirty"],
            "generator": _revinfo.generator_info("dep-graph.py"),
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
