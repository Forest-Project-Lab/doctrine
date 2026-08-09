#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""台帳の入出力を一本化する（原子的な書き込みと、壊れを名指しする読み）。

事象 INC-027 の修正。レーンの台帳は最大 351KB あり、素の `open(path,"w")`
+ `json.dump` は書き込みの途中で殺されると**前の全文を壊す**。読み手の側も
`ValueError` を握り潰していたため、切り詰められた台帳が「空」として読まれ、
次の行動が黙って消えていた（INC-006 と同じ形）。

ここは配布物ではない。`plugin/scripts/` の原子書き込みを import しない
（レーンは配布物のコードを取り込まない。ADR-114・PROC-001）。配布側には
同じ主旨の実装が三つあるが、統合はあちらの主題であり、ここでは真似ない。

INC-008（書き戻しの取りこぼし）とは別の故障様相である。あちらは
「二人とも書き切って、片方が論理的に古い」——整形式のまま消える。こちらは
「一人が書き切れない」——JSON でなくなる。原子化はこちらだけを直す。
同時に走る二つの走らせ手の read-modify-write は残余リスクとして残る。
"""
import json
import os

__all__ = ["LedgerCorrupt", "write_json", "read_json"]


class LedgerCorrupt(Exception):
    """台帳が読めない。欠落ではなく破損（空として読み替えてはならない）。

    **`ValueError` を継がない。**継ぐと、既存の読み手が広く持つ
    `except (OSError, ValueError)` に黙って飲まれ、破損がまた「空」に化ける
    —— この事象（INC-027）が直そうとしている当のことが戻る。
    独立検証（2026-08-09）がこの穴を指した。飲みたい呼び手は明示的に
    `LedgerCorrupt` を捕まえること。
    """


def write_json(path, doc, sort_keys=False):
    """台帳へ原子的に書く。

    同じディレクトリの一時ファイルへ書き、`fsync` してから `os.replace` する。
    途中で殺されても、読み手が見るのは「前の全文」か「新しい全文」だけになる。

    一時名には pid を混ぜる。固定名だと二つの走らせ手が同時に書いたとき互いの
    一時ファイルを上書きし、片方の書き込みが消える（配布側で実測 60 回に 1 回。
    ADR-075 が同じ判断をしている）。

    置き場が無ければ作る。失敗は握り潰さず `OSError` で上へ返す —— 台帳の
    書き込みは最善努力ではない（フックの印とは違う）。
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2,
                      sort_keys=sort_keys)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(directory)


def _fsync_dir(directory):
    """改名そのものを永続させる。できない環境では黙って諦める。"""
    if not directory:
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def read_json(path, default=None, required=False):
    """台帳を読む。無ければ `default`、壊れていれば `LedgerCorrupt`。

    **切り詰められた台帳を「空」と読み替えない。**欠落と破損は別の事実であり、
    黙って空と読むと、正本が導く次の行動がその分だけ消える（INC-006）。
    呼び手が「無くてもよい」と決めているときだけ `default` が返る。
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        if required:
            raise LedgerCorrupt("台帳が無い: %s" % path)
        return default
    except (OSError, ValueError) as exc:
        raise LedgerCorrupt("台帳が読めない: %s (%s)" % (path, exc))
