#!/usr/bin/env python3
"""巨大な台帳 PR の差分要約（機械生成）と、その添付の義務の検め。

リポジトリ内の自己適用であり、配布するプラグインの一部ではない
（`release-check.py` と同じ位置づけ）。標準ライブラリだけで動く。

## なぜ在るか

保証レーンの台帳（`assurance/ledger/**.json`）は一件が数百 KB になる。再判定を
一度回すと数千行が動き、その diff を人が読んで「何が変わったか」を掴むことは
できない。実際、本再監査キャンペーンは 600 件規模の台帳を書き換える PR を何本も
自律で merge しており、**誰も中身を見ていない merge** が積み上がった。

そこで、閾値を超える台帳の差分を持つ PR には次のどちらかを要求する。

1. 作成者以外の**独立レビュー**（承認）が付いていること、または
2. **機械生成の差分要約**が PR 本文に貼られていること

2 の「貼られている」は、本スクリプトが計算する **digest の一行**が本文に
そのまま在るかで判ずる。要約の散文は書き手が自由に書いてよいが、数は機械が出す
—— 書き手が数を打ち直せる形にすると、要約は主張になってしまう。

## 使い方

    ledger-diff-summary.py --diff-base <sha>              要約を出す
    ledger-diff-summary.py --diff-base <sha> --check \\
        --pr-body-file <path> [--approved]                義務を検める

終了コード: 0 = 適合 / 1 = 違反 / 2 = 使い方の誤り
"""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

LEDGER_PREFIX = "assurance/ledger/"

# この行数を超える台帳の差分を「巨大」とする。一件の推奨を処遇する差分（数十行）は
# 素通りし、再判定や一括トリアージ（数百〜数千行）だけが掛かるところに置く。
BIG_DIFF_LINES = 200

DIGEST_PREFIX = "ledger-diff-digest:"


class DiffError(Exception):
    """差分を取れなかった。判定を書けないので、黙って通さない。"""


def _git(args):
    try:
        r = subprocess.run(["git", "-C", REPO] + args,
                           capture_output=True, text=True, timeout=120)
    except Exception as exc:                              # noqa: BLE001
        raise DiffError("git の呼び出しに失敗: %r" % exc)
    if r.returncode != 0:
        raise DiffError("git が失敗(終了コード %d): %s"
                        % (r.returncode, r.stderr.strip()))
    return r.stdout


def ledger_files(base):
    """変わった台帳ファイルの相対パス（並び順は固定）。"""
    out = _git(["diff", "--name-only", base, "HEAD"])
    return sorted(f.strip() for f in out.splitlines()
                  if f.strip().startswith(LEDGER_PREFIX)
                  and f.strip().endswith(".json"))


def diff_line_count(base, paths):
    """台帳だけに絞った差分の行数（追加＋削除）。"""
    if not paths:
        return 0
    out = _git(["diff", "--numstat", base, "HEAD", "--"] + list(paths))
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        for n in parts[:2]:
            if n.isdigit():
                total += int(n)
    return total


def _load_at(rev, path):
    """rev 時点のファイルを dict/list で返す。無ければ None、壊れていれば例外。

    「無い」と「読めない」を混ぜない —— 混ぜると、壊れた台帳を持ち込む PR が
    「新規ファイル」に見えて素通りする。
    """
    try:
        raw = _git(["show", "%s:%s" % (rev, path)])
    except DiffError:
        return None
    return json.loads(raw)


# 件の中で「どれが名か」。上から順に当たる。
ID_KEYS = ("id", "incident_id", "scenario_id", "key", "token", "name")
# 件の中で「どれが状態か」。上から順に当たる。
STATE_KEYS = ("state", "status", "disposition", "verdict", "phase")


def _one_record(prefix, i, item):
    """一件を (名, 状態) にする。名が無ければ位置を名の代わりにする。"""
    if not isinstance(item, dict):
        return "%s#%d" % (prefix, i), None
    ident = None
    for key in ID_KEYS:
        v = item.get(key)
        if isinstance(v, str) and v:
            ident = v
            break
    if ident is None:
        ident = "#%d" % i
    elif "index" in item:
        ident = "%s#%s" % (ident, item.get("index"))
    state = None
    for key in STATE_KEYS:
        v = item.get(key)
        if isinstance(v, str) and v:
            state = v
            break
    return "%s%s" % (prefix, ident), state


def _records(doc):
    """台帳の中の「件」を (名, 状態) の辞書に均す。形は台帳ごとに違う。

    **一覧の鍵は選ばない。列に見えるものを全部数える。**最初に見つけた一つを
    採る形にしていたら、網羅台帳（`dispositions` 5 件と `entries` 338 件を
    両方持つ）で 338 件の側を丸ごと落とした —— 再判定で 21 件が動いた PR が
    「動いた件 0」と要約された。**要約が黙って過少に出るのは、要約が無いより
    悪い**（読み手は「見た」と思う）。名は鍵で名前空間を分け、別の列の同名が
    衝突しないようにする。
    """
    if isinstance(doc, list):
        out = {}
        for i, item in enumerate(doc):
            k, v = _one_record("", i, item)
            out[k] = v
        return out
    if not isinstance(doc, dict):
        return {}
    out = {}
    for key in sorted(doc):
        seq = doc[key]
        if not isinstance(seq, list) or not seq:
            continue
        if not any(isinstance(x, dict) for x in seq):
            continue        # 文字列の列（sources 等）は「件」ではない
        for i, item in enumerate(seq):
            k, v = _one_record("%s/" % key, i, item)
            out[k] = v
    return out


def summarize(base):
    """台帳の差分を機械が読める形に畳む。判断は入れない。"""
    paths = ledger_files(base)
    lines = diff_line_count(base, paths)
    added, removed, moved = [], [], []
    unreadable = []
    for path in paths:
        try:
            before = _load_at(base, path)
        except ValueError:
            before = None
            unreadable.append("%s(前)" % path)
        try:
            after = _load_at("HEAD", path)
        except ValueError:
            after = None
            unreadable.append("%s(後)" % path)
        b = _records(before) if before is not None else {}
        a = _records(after) if after is not None else {}
        for ident in sorted(set(a) - set(b)):
            added.append("%s:%s" % (path, ident))
        for ident in sorted(set(b) - set(a)):
            removed.append("%s:%s" % (path, ident))
        for ident in sorted(set(a) & set(b)):
            if a[ident] != b[ident]:
                moved.append("%s:%s %s→%s" % (path, ident, b[ident], a[ident]))
    return {
        "files": paths,
        "diff_lines": lines,
        "is_big": lines > BIG_DIFF_LINES,
        "added": added,
        "removed": removed,
        "transitions": moved,
        "unreadable": unreadable,
    }


def digest_line(summary):
    """本文へ貼る一行。書き手が打ち直せない形の唯一の錨。"""
    return ("%s files=%d lines=%d added=%d removed=%d transitions=%d"
            % (DIGEST_PREFIX, len(summary["files"]), summary["diff_lines"],
               len(summary["added"]), len(summary["removed"]),
               len(summary["transitions"])))


def render(summary):
    out = [digest_line(summary), ""]
    out.append("台帳 %d 件 / 差分 %d 行%s"
               % (len(summary["files"]), summary["diff_lines"],
                  "（巨大）" if summary["is_big"] else ""))
    for path in summary["files"]:
        out.append("  - %s" % path)
    if summary["unreadable"]:
        out.append("読めなかった台帳（破損の疑い。空として扱わない）:")
        for u in summary["unreadable"]:
            out.append("  - %s" % u)
    for label, key in (("新しい件", "added"), ("消えた件", "removed"),
                       ("状態が動いた件", "transitions")):
        items = summary[key]
        out.append("%s: %d 件" % (label, len(items)))
        for item in items[:20]:
            out.append("  - %s" % item)
        if len(items) > 20:
            out.append("  …ほか %d 件（全件は本スクリプトを手で走らせて見る）"
                       % (len(items) - 20))
    return "\n".join(out) + "\n"


def check(summary, pr_body, approved):
    """義務の違反を列挙して返す。適合なら空。"""
    if not summary["is_big"]:
        return []
    if approved:
        return []
    want = digest_line(summary)
    if want in (pr_body or ""):
        return []
    return [
        "巨大な台帳の差分（%d 行 > %d 行）に、独立レビューも機械生成の差分要約も"
        "付いていない。作成者以外の承認を得るか、次の一行を含む要約を PR 本文へ"
        "貼ること:\n    %s" % (summary["diff_lines"], BIG_DIFF_LINES, want)]


def main(argv):
    base = None
    body_file = None
    do_check = False
    approved = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--diff-base" and i + 1 < len(argv):
            base = argv[i + 1]; i += 2; continue
        if a == "--pr-body-file" and i + 1 < len(argv):
            body_file = argv[i + 1]; i += 2; continue
        if a == "--check":
            do_check = True; i += 1; continue
        if a == "--approved":
            approved = True; i += 1; continue
        sys.stdout.write("usage error: 不明な引数: %s\n" % a)
        sys.stdout.write(__doc__.split("## 使い方")[1])
        return 2
    if not base:
        sys.stdout.write("usage error: --diff-base が要る\n")
        return 2
    try:
        summary = summarize(base)
    except DiffError as exc:
        # 判定を書けないときは沈黙して開かない（DECIDED-001 第12項）。
        sys.stdout.write("台帳の差分を取れなかった: %s\n" % exc)
        return 2
    sys.stdout.write(render(summary))
    if not do_check:
        return 0
    body = ""
    if body_file:
        try:
            with open(body_file, encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            sys.stdout.write("PR 本文を読めなかった: %r\n" % exc)
            return 2
    problems = check(summary, body, approved)
    for p in problems:
        sys.stdout.write("[ERROR] %s\n" % p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
