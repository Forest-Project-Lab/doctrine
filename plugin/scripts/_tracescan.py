#!/usr/bin/env python3
"""コード注釈の走査(SPEC-026)。注釈の対が囲む範囲と、その内容の指紋を集める。

ADR-054 が定めた追跡の終点は「注釈の対が囲むコードのテキストの範囲」であり、
コードそのものでも言語のシンボルでもない。構文解析はしない。言語ごとに手段を
分けない — 「範囲はどこか」の答えを二つ持つと、重複 id(ADR-049)や監査要約の
読み取り(ADR-053)で二度直した欠陥類型を、設計の時点で作り込むことになる。

印は、行から前後の空白と非語文字を取り除いた残りが「印の語 + begin + id」
「印の語 + end + id」の厳密な形(_MARK_RE)に一致する行である。前後の非語文字を
無視するので、# // -- ; % /* */ <!-- --> のいずれの注釈記号でも同じ規則が効き、
言語を知る必要がない。書式の例示は統治文書(SPEC-026)だけが持つ — この説明文に
印の形をそのまま書くと、疑いの照合(ADR-059)が実装自身に反応する。

保証限界:
- 予防: 何も予防しない。走査して集めるだけである。
- 検出: 対応付けの誤り(入れ子・両端の id の不一致・閉じ忘れ・開いていない end)
  を四種に分けて挙げる。範囲の内容が変わったかは、指紋の照合に委ねる。
  走査が触れた対象の勘定(寄与・印なし・規則 id ごとの除外と刈り)を返し、
  何も黙って消えない(保存則。ADR-058)。
- 委ねる: 印が意味の上で正しい場所に打たれているかは判定しない(NONGOAL 第1項と
  同じ形で、判断は人に残す)。改名・移動は追わない(git の受け持ち)。印なしの
  ファイルのうち、どれが入れ忘れでどれが管理外の意思かの区別は人に残す。

標準ライブラリのみ。決して例外を外へ出さない。
"""
import hashlib
import os
import re
import stat as _stat

# 印の綴り。走査対象の判定にも使う(この語を含まないファイルは早期に飛ばす)。
MARKER_WORD = "doctrine:"

# 行から前後の空白と非語文字を落とした残りが印そのものであること。
# 先頭に語文字があれば一致しない(コードの途中の文字列は印にならない)。
_MARK_RE = re.compile(
    r"^[^\w]*doctrine:(begin|end)\s+([A-Z]+-\d+)[^\w]*$")

# 疑いの照合(ADR-059)。厳密な形に一致しない行のうち、印の語の直後(空白を許す)に
# begin/end の語が続くものは「打ったつもりの印」の兆候として挙げる。厳密な照合は
# 変えない(緩めると文字列を印として拾う)。この正規表現の原文自身が疑いに一致
# しないのは、コロンの直後に来るのが空白でも begin/end でもないからである。
_MARK_SUSPECT_RE = re.compile(r"doctrine:\s*(begin|end)\b")

# 走査しないディレクトリ名(監査の体系外 .md 走査と同じ規約。SPEC-011)。
SKIP_DIR_NAMES = frozenset({"node_modules", "__pycache__"})

# 走査しない拡張子。.md は、この書式を説明する文書自身が印として読まれるのを
# 断つため(自己言及を構造で断ち切る)。
SKIP_SUFFIXES = (".md",)

DEFAULT_MAX_FILE_BYTES = 1024 * 1024      # 一ファイルの上限
DEFAULT_MAX_FILES = 5000                  # 走査するファイル数の上限
_NUL_PROBE_BYTES = 8192                   # バイナリ判定で覗く先頭のバイト数

# 除外規則の正本(ADR-058)。除外はこの表の規則 id を経由してだけ起こる。
# kind "dir" はディレクトリ単位の刈り(配下は未到達)、"file" はファイル単位の分類。
# 規則を足す・消すときはこの表を同じ変更で更新する(TEST-026 が勘定の枠と共に凍結する)。
EXCLUSION_RULES = (
    ("dot_dir", "dir"),          # 名前が . で始まるディレクトリ
    ("skip_dir_name", "dir"),    # SKIP_DIR_NAMES(node_modules ほか)
    ("docs_root", "dir"),        # 統治木そのもの(文書は追跡の終点にならない)
    ("symlink_dir", "dir"),      # ディレクトリへのシンボリックリンク(降下しない)
    ("unreadable_dir", "dir"),   # 読めないディレクトリ(os.walk が握る誤り)
    ("dot_file", "file"),        # 名前が . で始まるファイル
    ("md_suffix", "file"),       # SKIP_SUFFIXES(自己言及の遮断)
    ("nonregular", "file"),      # 名前付きパイプ・ソケット・デバイス(開かない)
    ("oversize", "file"),        # 大きさの上限超過
    ("unreadable", "file"),      # stat/open/read の OSError
    ("binary", "file"),          # 先頭に値ゼロのバイト
    ("undecodable", "file"),     # utf-8 として復号できない
    ("truncated", "file"),       # ファイル数上限で分類せず落とした分
)

_FILE_RULES = tuple(rid for rid, kind in EXCLUSION_RULES if kind == "file")
_DIR_RULES = tuple(rid for rid, kind in EXCLUSION_RULES if kind == "dir")


def empty_coverage():
    """勘定の空枠。全規則の枠を 0 件でも含める(空欄を許さない。SPEC-025 と同じ原則)。"""
    return {
        "reached_files": 0,      # 走査が触れたファイルの全数
        "annotated_files": 0,    # 範囲を一つ以上返したファイル(寄与)
        "unmarked_files": 0,     # 読めたが範囲を一つも返さないファイル(印なし)
        "excluded": {rid: 0 for rid in _FILE_RULES},
        "pruned_dirs": {rid: 0 for rid in _DIR_RULES},
        "truncated": False,      # ファイル数上限で走査を打ち切ったか
    }


def _is_within(path, base):
    """path が base と同一か、その配下にあるか。実体パスどうしで呼ぶこと。"""
    return path == base or path.startswith(base + os.sep)


def _finding(code, path, line, message):
    """所見。path は根からの相対で区切りは / (機械をまたいで共有できる形)。"""
    return {"code": code, "path": path, "line": line, "message": message}


def _relposix(path, root):
    """root からの相対パスを、区切り / の形で返す。絶対パスを外へ出さない。"""
    try:
        rel = os.path.relpath(path, root)
    except (OSError, ValueError):
        rel = os.path.basename(path)
    return rel.replace(os.sep, "/")


def normalize_lines(text):
    """指紋のための正規化(SPEC-026)。改行を揃え、行末の空白と末尾の空行を落とす。

    正規化する理由は、内容が同じものを古びと判じないためである。改行コードは
    環境が混ざれば割れる(同じリポジトリを Windows と Linux の両方で扱うと
    起きる)。行末の空白は整形器が黙って落とす。

    EXT アンカーの指紋が生のバイト列なのは(ADR-039)、そこでは「外部のファイルが
    一バイトも変わっていないか」という別の問いを見ているからであり、規則が違うのは
    意図である。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def fingerprint(lines):
    """正規化済みの行の並びから指紋を作る。記法は EXT と同じ sha256:<64桁>。"""
    data = "\n".join(lines).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_marks(text):
    """本文から印を拾う。[(行番号(1始まり), 'begin'|'end', id)] を返す。"""
    out = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for i, line in enumerate(text.split("\n"), start=1):
        m = _MARK_RE.match(line)
        if m:
            out.append((i, m.group(1), m.group(2)))
    return out


def scan_text(text, relpath):
    """一ファイル分の本文から、範囲の一覧と対応付けの所見を返す。

    入れ子は禁じる(ADR-054/SPEC-026)。end は直前に開いた begin を閉じ、両端の
    id が食い違えば誤りとする。冗長だが、写し間違いと並べ替えの取り違えを安く
    捕まえる。誤りが出ても走査は止めない(集めて返す)。
    """
    ranges, findings = [], []
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    open_mark = None   # (行番号, id)

    # 疑いの照合(ADR-059)。厳密な印に一致しない行だけを見る。
    for i, line in enumerate(raw, start=1):
        if _MARK_RE.match(line):
            continue
        if _MARK_SUSPECT_RE.search(line):
            # 書式の綴りを原文へ直に書かない(この行自身が疑いに一致するため)。
            findings.append(_finding(
                "trace_marker_suspect", relpath, i,
                "印に見えるが読めない(綴りの揺れ)。書式は「注釈記号 + "
                + MARKER_WORD + "begin <TYPE>-<NNN>」で、id は大文字と数字、"
                "コロンの後に空白を置かない(SPEC-026)"))

    for line_no, kind, doc_id in parse_marks(text):
        if kind == "begin":
            if open_mark is not None:
                findings.append(_finding(
                    "trace_nested", relpath, line_no,
                    "範囲の入れ子は許さない(%d 行目の %s がまだ閉じていない)。"
                    "先に閉じてから次を開く" % (open_mark[0], open_mark[1])))
                continue
            open_mark = (line_no, doc_id)
            continue

        # kind == "end"
        if open_mark is None:
            findings.append(_finding(
                "trace_unopened", relpath, line_no,
                "開いていない範囲を閉じている(対応する begin が無い)"))
            continue
        begin_line, begin_id = open_mark
        if doc_id != begin_id:
            findings.append(_finding(
                "trace_id_mismatch", relpath, line_no,
                "範囲の両端の id が食い違う(begin %s / end %s)。"
                "写し間違いか並べ替えの取り違えを疑う" % (begin_id, doc_id)))
            open_mark = None
            continue
        body = raw[begin_line:line_no - 1]   # 印の行は含めない
        norm = normalize_lines("\n".join(body))
        if not norm:
            findings.append(_finding(
                "trace_empty_range", relpath, begin_line,
                "範囲が空である(印の間に内容が無い)。印を消すか、内容を囲む"))
        ranges.append({
            "id": begin_id, "path": relpath,
            "begin_line": begin_line, "end_line": line_no,
            "fingerprint": fingerprint(norm),
        })
        open_mark = None

    if open_mark is not None:
        findings.append(_finding(
            "trace_unclosed", relpath, open_mark[0],
            "範囲を閉じていない(%s の end がファイルの終端まで無い)" % open_mark[1]))
    return ranges, findings


def _should_skip_name(name):
    return name.endswith(SKIP_SUFFIXES)


def scan_tree(root, docs_root=None, max_files=DEFAULT_MAX_FILES,
              max_file_bytes=DEFAULT_MAX_FILE_BYTES, collect_members=False):
    """root 以下を走査し、(範囲の一覧, 所見の一覧, 勘定) を返す。決定的(整列順)。

    保存則(ADR-058): 触れたファイルは必ず 寄与・印なし・規則による除外 の
    どれか一つに数える。reached_files = annotated + unmarked + Σexcluded。
    刈ったディレクトリは規則 id ごとに本数を数え、配下は未到達と明示する。
    除外は EXCLUSION_RULES の規則 id を経由してだけ起こる(黙って切り詰めない)。

    統治木(docs_root)の中は走査しない — 文書は追跡の終点にならない。根が統治木と
    重なる呼び方でも包含で判じて刈る。通常ファイル以外(名前付きパイプ・ソケット・
    デバイス)は開かない(開くと戻らないことがある)。決して例外を外へ出さない。

    collect_members=True のときだけ、勘定に members(項ごとの相対パスの一覧)を
    足す。既定では件数だけを返す(一覧は求めに応じて導出する。ADR-055/ADR-058)。
    """
    ranges, findings = [], []
    cov = empty_coverage()
    members = {}

    def _member(term, relpath):
        if collect_members:
            members.setdefault(term, []).append(relpath)

    if not root or not os.path.isdir(root):
        if collect_members:
            cov["members"] = members
        return ranges, findings, cov
    docs_abs = os.path.realpath(docs_root) if docs_root else None

    def _on_walk_error(_err):
        # 読めないディレクトリ。os.walk は既定で誤りを握るので、ここで数える。
        cov["pruned_dirs"]["unreadable_dir"] += 1

    paths = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        if docs_abs and _is_within(os.path.realpath(dirpath), docs_abs):
            # 根が統治木と重なる呼び方。ここから下へは降りず、ファイルも見ない。
            dirnames[:] = []
            continue
        kept = []
        for d in sorted(dirnames):
            child = os.path.join(dirpath, d)
            child_rel = _relposix(child, root)
            if d.startswith("."):
                cov["pruned_dirs"]["dot_dir"] += 1
                _member("pruned:dot_dir", child_rel)
            elif d in SKIP_DIR_NAMES:
                cov["pruned_dirs"]["skip_dir_name"] += 1
                _member("pruned:skip_dir_name", child_rel)
            elif docs_abs and _is_within(os.path.realpath(child), docs_abs):
                cov["pruned_dirs"]["docs_root"] += 1
                _member("pruned:docs_root", child_rel)
            elif os.path.islink(child):
                # os.walk は既定でシンボリックリンクを降りない。黙らず数える。
                cov["pruned_dirs"]["symlink_dir"] += 1
                _member("pruned:symlink_dir", child_rel)
            else:
                kept.append(d)
        dirnames[:] = kept
        for name in sorted(filenames):
            paths.append(os.path.join(dirpath, name))
            if len(paths) > max_files:
                truncated = True
                break
        if truncated:
            break
    paths.sort()
    if truncated:
        dropped = paths[max_files:]
        paths = paths[:max_files]
        cov["truncated"] = True
        cov["excluded"]["truncated"] += len(dropped)
        cov["reached_files"] += len(dropped)
        for p in dropped:
            _member("excluded:truncated", _relposix(p, root))
        findings.append(_finding(
            "trace_scan_truncated", "", 0,
            "走査するファイル数の上限 %d を超えたため、以降を見ていない。"
            "上限を上げるか対象を絞って走らせ直す" % max_files))

    for path in paths:
        rel = _relposix(path, root)
        cov["reached_files"] += 1
        name = os.path.basename(path)
        if name.startswith("."):
            cov["excluded"]["dot_file"] += 1
            _member("excluded:dot_file", rel)
            continue
        if _should_skip_name(name):
            cov["excluded"]["md_suffix"] += 1
            _member("excluded:md_suffix", rel)
            continue
        try:
            st = os.stat(path)
        except OSError:
            cov["excluded"]["unreadable"] += 1
            _member("excluded:unreadable", rel)
            continue
        if not _stat.S_ISREG(st.st_mode):
            # 通常ファイル以外は開かない(名前付きパイプは open が戻らない)。
            cov["excluded"]["nonregular"] += 1
            _member("excluded:nonregular", rel)
            continue
        if st.st_size > max_file_bytes:
            cov["excluded"]["oversize"] += 1
            _member("excluded:oversize", rel)
            findings.append(_finding(
                "trace_scan_truncated", rel, 0,
                "ファイルの大きさが上限 %d バイトを超えるため見ていない"
                % max_file_bytes))
            continue
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except (OSError, MemoryError):
            # MemoryError は OSError の子ではない。通常ファイル判定と大きさの
            # 上限で実質は起きないが、保証(例外を外へ出さない)の破れを塞ぐ。
            cov["excluded"]["unreadable"] += 1
            _member("excluded:unreadable", rel)
            continue
        if b"\x00" in data[:_NUL_PROBE_BYTES]:
            cov["excluded"]["binary"] += 1
            _member("excluded:binary", rel)
            continue                      # バイナリは読まない
        if MARKER_WORD.encode("utf-8") not in data:
            cov["unmarked_files"] += 1    # 印なし(入れ忘れが住む場所)
            _member("unmarked", rel)
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            cov["excluded"]["undecodable"] += 1
            _member("excluded:undecodable", rel)
            continue                      # 復号できないファイルは飛ばす
        r, f = scan_text(text, rel)
        if r:
            cov["annotated_files"] += 1
            _member("annotated", rel)
        else:
            # 印の語はあるが範囲を一つも返さない(対応付けの誤りは所見が別に指す)。
            cov["unmarked_files"] += 1
            _member("unmarked", rel)
        ranges.extend(r)
        findings.extend(f)

    ranges.sort(key=lambda x: (x["path"], x["begin_line"], x["id"]))
    findings.sort(key=lambda x: (x["path"], x["line"], x["code"]))
    if collect_members:
        for term in members:
            members[term].sort()
        cov["members"] = members
    return ranges, findings, cov
