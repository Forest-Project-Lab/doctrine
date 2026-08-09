#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""検証原則カタログ → 網羅台帳（五値）の決定論の骨組み（標準ライブラリのみ）。

MAP_COVERAGE の評価（jerg レーン）が走るまで、全原則は UNKNOWN で立つ。
「台帳が無い」と「未対応」を区別するのが目的で、ここでは判定しない。

usage: coverage.py init --book jerg   # 骨組み生成（既存の割当は保持）
       coverage.py stats [--book jerg]
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, ledger_io, schemas  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(LANE_DIR, "ledger", "catalogs")


def _paths(book_id):
    return (os.path.join(CATALOG_DIR, "%s-principles.json" % book_id),
            os.path.join(CATALOG_DIR, "%s-coverage.json" % book_id))


def principle_key(book_id, seq, principle):
    """台帳の鍵。dedupe_key を主にし、衝突は連番で一意化する。"""
    base = (principle.get("dedupe_key") or "").strip() or "p%03d" % seq
    return "%s:%s" % (book_id.upper(), base)


def init(book_id):
    cat_path, cov_path = _paths(book_id)
    if not os.path.isfile(cat_path):
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "カタログ未抽出: %s" % book_id},
                         ensure_ascii=False))
        return 3
    with open(cat_path, encoding="utf-8") as f:
        cat = json.load(f)

    existing = {}
    if os.path.isfile(cov_path):
        with open(cov_path, encoding="utf-8") as f:
            existing = {e["key"]: e for e in json.load(f).get("entries", [])}

    entries = []
    seen = {}
    for seq, p in enumerate(cat.get("principles", []), 1):
        key = principle_key(book_id, seq, p)
        if key in seen:                     # dedupe_key 衝突は一意化して両方残す
            seen[key] += 1
            key = "%s#%d" % (key, seen[key])
        else:
            seen[key] = 1
        prev = existing.get(key)
        entries.append(prev or {
            "key": key,
            "title": p.get("title"),
            "category": p.get("category"),
            "source_lines": p.get("source_lines"),
            "disposition": "UNKNOWN",
            "reason": "MAP_COVERAGE 未実施",
            "evidence": None,
            "recheck_trigger": "MAP_COVERAGE の実行",
        })

    cov = {
        "doctrine:exempt": "保証レーンの網羅台帳。仕様との対応なし(ADR-114)",
        "kind": "coverage-ledger",
        "book_id": book_id,
        "book_sha256": cat.get("book_sha256"),
        "dispositions": schemas.COVERAGE_DISPOSITIONS,
        "entries": entries,
    }
    os.makedirs(CATALOG_DIR, exist_ok=True)
    ledger_io.write_json(cov_path, cov)
    print(json.dumps({"book": book_id, "entries": len(entries),
                      "kept_existing": sum(1 for e in entries
                                           if e["disposition"] != "UNKNOWN")},
                     ensure_ascii=False))
    return 0


def stats(book_id=None):
    out = {}
    targets = [book_id] if book_id else sorted(books.BOOKS)
    for b in targets:
        _cat, cov_path = _paths(b)
        if not os.path.isfile(cov_path):
            out[b] = {"status": "UNASSESSED"}
            continue
        with open(cov_path, encoding="utf-8") as f:
            cov = json.load(f)
        counts = {}
        for e in cov.get("entries", []):
            counts[e["disposition"]] = counts.get(e["disposition"], 0) + 1
        out[b] = {"total": len(cov.get("entries", [])), "by": counts}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--book", required=True, choices=sorted(books.BOOKS))
    p_stats = sub.add_parser("stats")
    p_stats.add_argument("--book", default=None, choices=sorted(books.BOOKS))
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return init(args.book)
    return stats(args.book)


if __name__ == "__main__":
    sys.exit(main())
