#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""規範3冊のレジストリと、行番号を保つチャンク分割（標準ライブラリのみ）。

冊子の抽出テキスト(output.md)にはページの印が無い。引用の再現性は
「ファイルの sha256 + 1起点の行範囲」で持つ（外部仕様の記録と同じ流儀）。
Reference_material/ は gitignore 済みの複製なので、存在しない環境では
UNASSESSED へ倒す（黙って空を返さない）。
"""
import hashlib
import os

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)

# 観点レーンの正本。fires_on 等の発火条件は orchestrator が持つ（二重定義しない）。
BOOKS = {
    "jerg": {
        "title": "JERG-2-610C 宇宙機ソフトウェア開発標準（JAXA）",
        "path": "Reference_material/spec_jaxa_jerg2_610c_ja/output.md",
        "viewpoint": "検証計画と客観的証拠",
    },
    "stpa": {
        "title": "STPA ハンドブック（日本語版）",
        "path": "Reference_material/techbook_stpa_handbook_ja/output.md",
        "viewpoint": "事故候補と相互作用の創出",
    },
    "cast": {
        "title": "CAST ハンドブック（日本語版）",
        "path": "Reference_material/techbook_cast_handbook_ja/output.md",
        "viewpoint": "失敗後の保証体系更新",
    },
}


class BookMissing(Exception):
    """冊子の複製が無い（= この環境では規範抽出は UNASSESSED）。"""


def load_book(book_id):
    """冊子の全文と指紋を返す。無ければ BookMissing。"""
    if book_id not in BOOKS:
        raise ValueError("未知の冊子 %r（許すのは %s）" % (book_id, sorted(BOOKS)))
    path = os.path.join(REPO_DIR, BOOKS[book_id]["path"])
    if not os.path.isfile(path):
        raise BookMissing(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {
        "book_id": book_id,
        "title": BOOKS[book_id]["title"],
        "path": BOOKS[book_id]["path"],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
    }


def chunk_lines(text, max_chars=14000, overlap_lines=8):
    """行を保ったままチャンクへ割る。決定論（同じ入力なら同じ割り方）。

    返り値: [{"index", "start_line", "end_line", "text", "sha256"}]
    行番号は 1 起点・ファイル絶対。チャンク間は overlap_lines 行重ねる
    （原則が境界で切れて失われるのを減らす。重複抽出は dedupe_key で畳む）。
    """
    lines = text.splitlines()
    chunks = []
    start = 0
    while start < len(lines):
        size = 0
        end = start
        while end < len(lines) and size + len(lines[end]) + 1 <= max_chars:
            size += len(lines[end]) + 1
            end += 1
        if end == start:            # 1行が上限超え: その行だけで1チャンク
            end = start + 1
        body = "\n".join(lines[start:end])
        chunks.append({
            "index": len(chunks),
            "start_line": start + 1,
            "end_line": end,
            "text": body,
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
        if end >= len(lines):
            break
        start = max(end - overlap_lines, start + 1)
    return chunks


def numbered(chunk):
    """チャンク本文へ絶対行番号を付ける（引用 source_lines の根拠）。"""
    base = chunk["start_line"]
    return "\n".join(
        "L%d: %s" % (base + i, line)
        for i, line in enumerate(chunk["text"].splitlines()))
