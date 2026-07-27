#!/usr/bin/env python3
"""コード注釈の走査(SPEC-026)。注釈の対が囲む範囲と、その内容の指紋を集める。

ADR-054 が定めた追跡の終点は「注釈の対が囲むコードのテキストの範囲」であり、
コードそのものでも言語のシンボルでもない。構文解析はしない。言語ごとに手段を
分けない — 「範囲はどこか」の答えを二つ持つと、重複 id(ADR-049)や監査要約の
読み取り(ADR-053)で二度直した欠陥類型を、設計の時点で作り込むことになる。

印は、行から前後の空白と非語文字を取り除いた残りが `doctrine:begin <id>` /
`doctrine:end <id>` に一致する行である。前後の非語文字を無視するので、# // --
; % /* */ <!-- --> のいずれの注釈記号でも同じ規則が効き、言語を知る必要がない。

保証限界:
- 予防: 何も予防しない。走査して集めるだけである。
- 検出: 対応付けの誤り(入れ子・両端の id の不一致・閉じ忘れ・開いていない end)
  を四種に分けて挙げる。範囲の内容が変わったかは、指紋の照合に委ねる。
- 委ねる: 印が意味の上で正しい場所に打たれているかは判定しない(NONGOAL 第1項と
  同じ形で、判断は人に残す)。改名・移動は追わない(git の受け持ち)。印を打って
  いないコードは追跡の外にある。

標準ライブラリのみ。決して例外を外へ出さない。
"""
import hashlib
import os
import re

# 印の綴り。走査対象の判定にも使う(この語を含まないファイルは早期に飛ばす)。
MARKER_WORD = "doctrine:"

# 行から前後の空白と非語文字を落とした残りが印そのものであること。
# 先頭に語文字があれば一致しない(コードの途中の文字列は印にならない)。
_MARK_RE = re.compile(
    r"^[^\w]*doctrine:(begin|end)\s+([A-Z]+-\d+)[^\w]*$")

# 走査しないディレクトリ名(監査の体系外 .md 走査と同じ規約。SPEC-011)。
SKIP_DIR_NAMES = frozenset({"node_modules", "__pycache__"})

# 走査しない拡張子。.md は、この書式を説明する文書自身が印として読まれるのを
# 断つため(自己言及を構造で断ち切る)。
SKIP_SUFFIXES = (".md",)

DEFAULT_MAX_FILE_BYTES = 1024 * 1024      # 一ファイルの上限
DEFAULT_MAX_FILES = 5000                  # 走査するファイル数の上限
_NUL_PROBE_BYTES = 8192                   # バイナリ判定で覗く先頭のバイト数


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
              max_file_bytes=DEFAULT_MAX_FILE_BYTES):
    """root 以下を走査し、(範囲の一覧, 所見の一覧) を返す。決定的(整列順)。

    統治木(docs_root)の中は走査しない — 文書は追跡の終点にならない。
    上限を超えたら、飛ばした事実を所見一つで正直に告げる(黙って切り詰めない。
    SPEC-011 の語彙的酷似と同じ作法)。決して例外を外へ出さない。
    """
    ranges, findings = [], []
    if not root or not os.path.isdir(root):
        return ranges, findings
    docs_abs = os.path.realpath(docs_root) if docs_root else None

    paths = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIR_NAMES)
        if docs_abs:
            # 統治木そのものへは降りない。
            dirnames[:] = [
                d for d in dirnames
                if os.path.realpath(os.path.join(dirpath, d)) != docs_abs]
            if os.path.realpath(dirpath) == docs_abs:
                continue
        for name in sorted(filenames):
            if name.startswith(".") or _should_skip_name(name):
                continue
            paths.append(os.path.join(dirpath, name))
            if len(paths) > max_files:
                truncated = True
                break
        if truncated:
            break
    paths.sort()
    if truncated:
        paths = paths[:max_files]
        findings.append(_finding(
            "trace_scan_truncated", "", 0,
            "走査するファイル数の上限 %d を超えたため、以降を見ていない。"
            "上限を上げるか対象を絞って走らせ直す" % max_files))

    for path in paths:
        rel = _relposix(path, root)
        try:
            if os.path.getsize(path) > max_file_bytes:
                findings.append(_finding(
                    "trace_scan_truncated", rel, 0,
                    "ファイルの大きさが上限 %d バイトを超えるため見ていない"
                    % max_file_bytes))
                continue
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if b"\x00" in data[:_NUL_PROBE_BYTES]:
            continue                      # バイナリは読まない
        if MARKER_WORD.encode("utf-8") not in data:
            continue                      # 印を含まない(読んで確かめてから飛ばす)
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            continue                      # 復号できないファイルは飛ばす
        r, f = scan_text(text, rel)
        ranges.extend(r)
        findings.extend(f)

    ranges.sort(key=lambda x: (x["path"], x["begin_line"], x["id"]))
    findings.sort(key=lambda x: (x["path"], x["line"], x["code"]))
    return ranges, findings
