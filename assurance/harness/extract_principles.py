#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""規範冊子から検証原則カタログを抽出する（venv の python で動かす）。

- 役割は model_policy の evaluation（最低線 opus / effort high。所有者指示 2026-08-04）。
- チャンクごとに一回限りの隔離セッション。引用はチャンク本文と機械照合し、
  実在しない引用の原則は却下する（出典なき候補は実装へ渡さない）。
- 再開可能: カタログに残っているチャンク（同じ sha256）は飛ばす。
- 費用の上限: 一回ごと(--budget-per-call)と累計(--budget-total)の二段。
  超えたら止めて部分カタログを保存する（黙って続けない）。

終了コード: 0=全チャンク完了 / 2=一部FAIL / 3=UNASSESSED(前提欠如) / 4=途中停止(UNKNOWN/予算)。
"""
import argparse
import datetime
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import books, model_policy, prompts, schemas, sdk_lane  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(LANE_DIR, "ledger", "catalogs")


def catalog_path(book_id):
    return os.path.join(CATALOG_DIR, "%s-principles.json" % book_id)


def load_catalog(book_id, book):
    path = catalog_path(book_id)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cat = json.load(f)
        if cat.get("book_sha256") != book["sha256"]:
            # 冊子が変わった。古いカタログへ黙って継ぎ足さない。
            raise SystemExit(
                "冊子の指紋が変わっている（%s）。旧カタログを退避してから再抽出する"
                % book_id)
        return cat
    return {
        "doctrine:exempt": "保証レーンの規範カタログ。仕様との対応なし(ADR-114)",
        "kind": "principle-catalog",
        "book_id": book_id,
        "book_title": book["title"],
        "book_path": book["path"],
        "book_sha256": book["sha256"],
        "role": "evaluation",
        "chunks": [],
        "principles": [],
        "totals": {"cost_usd": 0.0, "principles": 0, "rejected": 0},
    }


def save_catalog(cat):
    os.makedirs(CATALOG_DIR, exist_ok=True)
    with open(catalog_path(cat["book_id"]), "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=sorted(books.BOOKS))
    parser.add_argument("--max-chunks", type=int, default=None,
                        help="この実行で扱うチャンク数の上限（既定: 全部）")
    parser.add_argument("--budget-per-call", type=float, default=3.0)
    parser.add_argument("--budget-total", type=float, default=25.0)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-chars", type=int, default=14000)
    args = parser.parse_args(argv)

    try:
        book = books.load_book(args.book)
    except books.BookMissing as exc:
        print(json.dumps({"status": "UNASSESSED",
                          "reason": "冊子の複製が無い: %s" % exc}, ensure_ascii=False))
        return 3

    run_opts = model_policy.options_for("evaluation")
    model_policy.assert_evaluation_floor(run_opts["model"], run_opts["effort"])

    cat = load_catalog(args.book, book)
    done_shas = {c["sha256"] for c in cat["chunks"]}
    chunks = books.chunk_lines(book["text"], max_chars=args.max_chars)
    todo = [c for c in chunks if c["sha256"] not in done_shas]
    if args.max_chunks is not None:
        todo = todo[: args.max_chunks]

    print("book=%s chunks_total=%d done=%d todo=%d model=%s effort=%s"
          % (args.book, len(chunks), len(done_shas), len(todo),
             run_opts["model"], run_opts["effort"]), flush=True)

    spent = float(cat["totals"]["cost_usd"])
    had_fail = False
    stopped = None
    for chunk in todo:
        if spent >= args.budget_total:
            stopped = "累計予算 %.2f USD に到達" % args.budget_total
            break
        prompt = prompts.build_extract_principles_prompt(
            book["title"], chunk, books.numbered(chunk))
        record = sdk_lane.run_one_shot(
            prompt,
            schema=schemas.PRINCIPLES_SCHEMA,
            model=run_opts["model"],
            effort=run_opts["effort"],
            max_budget_usd=args.budget_per_call,
            max_turns=1,
            timeout_s=args.timeout,
            cwd=None,
        )
        cost = ((record.get("result_meta") or {}).get("total_cost_usd")) or 0.0
        spent += float(cost)

        if record["status"] == "UNASSESSED":
            stopped = "レーン前提の欠如: %s" % record["errors"]
            break
        if record["status"] in ("UNKNOWN",):
            stopped = "観測不能(チャンク %d): %s" % (chunk["index"], record["errors"])
            break

        accepted, rejected = [], []
        if record["status"] == "PASS":
            out = record["structured_output"] or {}
            accepted, rejected = prompts.verify_principles(
                chunk["text"], out.get("principles", []))
        else:
            had_fail = True

        for p in accepted:
            p["book"] = args.book
            p["chunk_index"] = chunk["index"]
            p["chunk_sha256"] = chunk["sha256"]
            cat["principles"].append(p)
        cat["chunks"].append({
            "index": chunk["index"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "sha256": chunk["sha256"],
            "status": record["status"],
            "cost_usd": cost,
            "accepted": len(accepted),
            "rejected": len(rejected),
            "prompt_sha256": record["prompt_sha256"],
            "sdk_version": record["sdk_version"],
            "model": record["options"]["model"],
            "effort": record["options"]["effort"],
        })
        cat["totals"] = {
            "cost_usd": round(spent, 4),
            "principles": len(cat["principles"]),
            "rejected": cat["totals"]["rejected"] + len(rejected),
        }
        cat["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_catalog(cat)   # チャンクごとに保存（途中終了しても失わない）
        print("chunk %d/%d L%d-L%d status=%s accepted=%d rejected=%d cost=%.3f spent=%.2f"
              % (chunk["index"], len(chunks) - 1, chunk["start_line"],
                 chunk["end_line"], record["status"], len(accepted),
                 len(rejected), cost, spent), flush=True)

    remaining = len(chunks) - len({c["sha256"] for c in cat["chunks"]})
    summary = {
        "book": args.book,
        "principles": cat["totals"]["principles"],
        "rejected": cat["totals"]["rejected"],
        "cost_usd": cat["totals"]["cost_usd"],
        "chunks_remaining": remaining,
        "stopped": stopped,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if stopped:
        return 4
    if had_fail:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
