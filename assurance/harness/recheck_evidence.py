#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""終端の判定を、評価を買わずに決定論で照合し直す（ADR-133）。

ADR-130 は「終端（実装・試験・証拠あり／非該当で理由あり）の古びは、証拠ポインタを
索引へ引き直せば決定論で判る」と書いたが、**その走らせ手は作っていなかった** ——
`status` が数えて出すだけだった。ここがその口である。

やること（SDK を呼ばない。費用ゼロ）:
- 「実装・試験・証拠あり」の各項の証拠ポインタを、いまの索引で引き直す。
- 解決するポインタが一つも無くなっていれば UNKNOWN へ落とす（ADR-118 の規則）。
- 解決するのが決定・仕様だけになっていれば「対応計画あり」へ落とす（ADR-133 の床）。
- どちらでもなければ、判定はそのままに指紋だけを現行へ更新する —— 証拠が現に
  解決したのだから、その判定はいまの索引に対しても成り立っている。

**この口は緑を増やさない。**決定論で言えるのは「証拠が消えた」ことだけであり、
「新たに実装された」ことは言えない（それは評価の仕事）。片方向にしか動かさない。

usage: recheck_evidence.py --book jerg [--all] [--dry-run]

終了コード: 0=変化なし / 1=落とした項が在る / 3=UNASSESSED(前提欠如)。
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, map_coverage, prompts, system_index  # noqa: E402

SETTLED_GREEN = "実装・試験・証拠あり"


def sweep(cov, idx, rubric):
    """終端の緑を索引へ引き直す。返り値は動かした項の記録の列。

    判定を消さず履歴へ積んでから書き換える（ADR-130）。指紋だけの更新でも、
    判定そのものは評価者が書いたまま保つ —— 実装者は評価者の判定を書き換えない
    （ADR-115）。ここで変えるのは「証拠が消えた」と決定論で言える場合だけである。
    """
    moved = []
    for e in cov.get("entries", []):
        if e.get("disposition") != SETTLED_GREEN or not e.get("assigned_at"):
            continue
        pointers = list(e.get("evidence") or [])
        resolved = [p for p in pointers if system_index.resolve_pointer(idx, p)]
        lost = [p for p in pointers if not system_index.resolve_pointer(idx, p)]
        enforcing = prompts._has_enforcing_pointer(
            resolved, lambda p: system_index.resolve_pointer(idx, p))

        if not resolved:
            map_coverage.push_reassessment(e)
            e["disposition"] = "UNKNOWN"
            e["reason"] = ("[決定論の再照合: 証拠ポインタが一つも解決しなくなった] "
                           + str(e.get("reason") or ""))
            e["evidence"] = []
            moved.append({"key": e["key"], "to": "UNKNOWN", "lost": lost})
        elif not enforcing:
            map_coverage.push_reassessment(e)
            e["disposition"] = "対応計画あり"
            e["reason"] = ("[決定論の再照合: 解決する証拠が決定・仕様だけになった] "
                           + str(e.get("reason") or ""))
            e["evidence"] = resolved
            moved.append({"key": e["key"], "to": "対応計画あり",
                          "kept": resolved, "lost": lost})
            continue
        else:
            # 証拠が現に解決したのだから、この判定はいまの索引に対しても
            # 成り立っている。指紋だけを現行へ揃えて古びを解く。
            e["evidence"] = resolved
            if lost:
                e["unresolved_evidence"] = lost
            by = dict(e.get("assigned_by") or {})
            by["index_sha256"] = idx["sha256"]
            by["category_sha256"] = idx["category_sha256"]
            by["category_counts"] = idx["category_counts"]
            by["rubric_sha256"] = rubric
            by["rechecked_deterministically"] = True
            e["assigned_by"] = by
            continue
        # 落とした項は未割当へは戻さない —— 決定論で結論が出ているので
        # 評価済みである（未評価と混ぜない。INC-006）。
    return moved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=sorted(books.BOOKS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.book and not args.all:
        parser.error("--book か --all のどちらかが要る")

    idx = system_index.build()
    if not idx["documents"] or not idx["scripts"]:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "現状の索引が組めない"}, ensure_ascii=False))
        return 3
    rubric = prompts.rubric_fingerprint()

    out = []
    for book_id in (sorted(books.BOOKS) if args.all else [args.book]):
        _cat, cov = map_coverage.load_pair(book_id)
        if cov is None:
            out.append({"book": book_id, "status": "UNASSESSED"})
            continue
        moved = sweep(cov, idx, rubric)
        if not args.dry_run:
            cov["index_sha256"] = idx["sha256"]
            map_coverage.save_coverage(book_id, cov)
        out.append({"book": book_id, "moved": len(moved), "detail": moved})
    print(json.dumps({"rubric_sha256": rubric[:12], "books": out},
                     ensure_ascii=False, indent=2))
    return 1 if any(b.get("moved") for b in out) else 0


if __name__ == "__main__":
    sys.exit(main())
