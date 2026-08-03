#!/usr/bin/env python3
"""Shared flat-YAML frontmatter parser for doctrine.

保証限界:
- 予防: 解析は内容で例外を投げない。半端な編集中の内容でも最善解析と構造化エラーを返し、
  毎ターンの Hook が落ちないことを保証する（MASTER §1, 仕様 §4.2/§7）。
- 検出: 必須キーの不在・status/type/id↔ファイル名の整合・ICD依存規則などの意味検査は
  この層では行わない。errors チャネルで構文上の問題だけを伝える。
- 委ねる: ドメイン検証（必須キー・status・type・id一致・用語）は各呼び出し側に委ねる。

MASTER §1 の API をそのまま実装する。仕様 §3.4 のフロントマターはフラット
（スカラとスカラのリストのみ。入れ子・アンカー・ブロックスカラ・フローマップは無い）であり、
"外部pip依存を作らない。フロントマターはフラットなので最小パーサで読む"（仕様 §4.3）に従う。
標準ライブラリのみ。PyYAML は使わない。
"""
import os
import re
import stat

FRONTMATTER_VERSION = 1  # bump if parse semantics change

# 制御文字(C0 + DEL + C1)。改行・タブ・復帰を含む。注入境界で空白へ畳む。
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WS_RE = re.compile(r"\s+")


def sanitize_inline(value, limit=200):
    """注入境界(additionalContext へ挿入する各フィールド)の一行サニタイザ。ADR-040。

    文書内容やファイル名は攻撃者制御になりうる(#96)。逐語挿入すると、title の
    改行で偽のセクション見出しを捏造したり、巨大な値で注入上限を回避したりできる。
    ここで一律に、(1) 制御文字(改行・タブ含む)を空白へ、(2) 連続空白を畳み、
    (3) 前後を削り、(4) limit で長さを hard-bound する。決して例外を投げない。

    これはデータ境界の一段目である(provenance フェンスが二段目)。
    """
    s = "" if value is None else (value if isinstance(value, str) else str(value))
    s = _CONTROL_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s

# ---------------------------------------------------------------------------
# Tunables (single, documented). See MASTER §1 frozen semantics.
# ---------------------------------------------------------------------------
COERCE_BOOL = True  # only unquoted true/false coerce to bool (never yes/no/on/off)

# Closed set of error codes (MASTER §1). `missing_open` is reserved for strict
# callers (e.g. the linter, which DOES require frontmatter per §3.4); parse()
# never emits it because absence of frontmatter is legal/empty.
# doctrine:begin SPEC-002
_ERROR_CODES = frozenset({
    "missing_open", "missing_close", "bad_line", "empty_key",
    "orphan_list_item", "unterminated_quote", "unterminated_flow",
    "bad_flow_list", "duplicate_key",
})
# doctrine:end SPEC-002

_BOM = "﻿"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse(text):
    """Parse a document string into (frontmatter, body, errors).

    NEVER raises on malformed *content*. Returns the best-effort mapping, the
    body (with original newlines preserved verbatim), and a list of structured
    non-fatal error records (see _err / MASTER §1).

    frontmatter: dict[str, str | list[str] | bool | None]
    body:        str
    errors:      list[dict]  (empty list == clean parse)
    """
    if text is None:
        return ({}, "", [])
    if not isinstance(text, str):
        # Defensive: never raise on content. Coerce to str best-effort.
        text = str(text)

    # §3.1.1 BOM: strip exactly one leading BOM before any other processing.
    if text.startswith(_BOM):
        text = text[len(_BOM):]

    errors = []

    # Split on universal newlines for *scanning* only; body is sliced from the
    # ORIGINAL text so its newline style (CRLF/CR/LF) is untouched.
    lines = text.splitlines()  # keepends=False, universal-newline semantics

    # §3.2 Opening delimiter: line 0 must be exactly '---' (trailing ws ok).
    if not lines or not _is_open_fence(lines[0]):
        return ({}, text, [])  # no frontmatter — NOT an error

    # §3.3 Closing delimiter: first '---' or '...' on lines 1..n.
    close_idx = None
    for i in range(1, len(lines)):
        if _is_close_fence(lines[i]):
            close_idx = i
            break

    if close_idx is None:
        # §3.4 missing closer: parse all remaining lines, body="", record error.
        fm_lines = list(enumerate(lines[1:], start=2))  # (1-based orig line, raw)
        body = ""
        errors.append(_err("missing_close", None, None,
                           "フロントマターの閉じ '---' が見つからない"))
    else:
        fm_lines = list(enumerate(lines[1:close_idx], start=2))
        body = _slice_body(text, lines, close_idx)

    fm = _parse_lines(fm_lines, errors)
    return (fm, body, errors)


def ensure_regular(path):
    """通常ファイルでなければ OSError。開く前に必ず通す門(ADR-075)。

    名前付きパイプ・デバイス・ソケットを open すると書き手を待って戻らない。
    統治の読み手は per-turn の Hook から呼ばれるため、一つの非通常ファイルが
    ガード・リンタ・注入・監査を無言で止める(拒否が届かない fail-open)。
    走査層(_tracescan)にだけ在った種別の検査を、共有の読み手へ一本化する。
    """
    p = os.fspath(path)
    st = os.stat(p)          # 追跡しないリンクは stat が解決する。壊れた先は OSError。
    if not stat.S_ISREG(st.st_mode):
        raise OSError("通常ファイルではない(統治の読み手は開かない): %s" % p)
    return p


def read_text(path, newline=""):
    """統治対象を UTF-8(utf-8-sig)で読む。種別の門を通す唯一の入口(ADR-075)。

    parse_file を経由しない読み手(--batch・体系外 .md・辞書・コード層)も、
    ここを通ることで同じ守りを受ける。例外は I/O と復号の失敗だけ。
    """
    with open(ensure_regular(path), "r", encoding="utf-8-sig",
              newline=newline) as fh:
        return fh.read()


def parse_file(path):
    """Read 'path' (str | os.PathLike) as UTF-8 (utf-8-sig) and delegate to parse().

    Opens with encoding='utf-8-sig' (transparently strips a real file BOM) and
    newline='' (no newline translation, so CRLF survives into the body).

    Raises ONLY on I/O / decoding failure (FileNotFoundError, IsADirectoryError,
    PermissionError, UnicodeDecodeError, OSError). NEVER raises on content;
    content malformation flows through the errors list. No latin-1 fallback.

    通常ファイルでなければ開かずに OSError を送出する(ensure_regular。ADR-075)。
    """
    return parse(read_text(path))


def parse_frontmatter(text):
    """Return only the mapping. Mirrors the §4.2 pseudo-spec name
    (`proposed = parse_frontmatter(tool_input.content)`). Discards body+errors."""
    fm, _body, _errs = parse(text)
    return fm


def body_start_line(text, body):
    """本文が元のテキストの何行目から始まるか(1 起点)。決して例外を投げない。

    助言の行番号をファイルの行番号へ換算する**唯一の権限**である(ADR-083)。
    呼び手(リンタと CLI)は自分で数えない —— 二つある呼び手が別々に数えれば、
    片方だけ直したときに同じファイルへ別の行を言う状態が生まれる。

    `parse` は本文を元のテキストの末尾から切り出すので、長さの差が本文の開始位置に
    なる。フロントマターが無ければ本文＝全文なので 1 を返す(いまと同じ挙動)。
    BOM の除去は先頭行の中で起きるため、行数には影響しない。
    """
    if not isinstance(text, str) or not isinstance(body, str):
        return 1
    offset = len(text) - len(body)
    if offset <= 0:
        return 1
    return text.count("\n", 0, offset) + 1


def as_list(value):
    """Coerce a frontmatter value to a list of non-empty strings. Never raises.

    None/'' -> []; 'x' -> ['x']; ['a','b'] -> ['a','b']; scalar int 5 -> ['5'].
    List elements are stringified and empty/whitespace-only elements dropped.
    """
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for v in value:
            if v is None:
                continue
            s = v if isinstance(v, str) else str(v)
            if s.strip() != "":
                out.append(s)
        return out
    if isinstance(value, str):
        return [value] if value.strip() != "" else []
    if isinstance(value, bool):
        # bool before int check is moot here (handled by str() path) — keep
        # explicit so True -> ['True'] not ['1'].
        return [str(value)]
    # Any other scalar (int, float, etc.)
    s = str(value)
    return [s] if s.strip() != "" else []


# 雛形の指示文の形(ADR-098)。山括弧に囲まれた非空の並び。雛形も語彙の表も読まない
# —— 雛形は配布物であり導入先で差し替えられるので、正本が動くものになる(ADR-090 が
# 同じ理由で「節の一覧を雛形から読む」案を却下している)。形そのものが指示文の印である。
_PLACEHOLDER_RE = re.compile(r"<[^<>\s][^<>]*>")


def placeholder_fields(meta):
    """フロントマターに残った雛形の指示文を [(鍵, 値)] で返す。例外は投げない。

    値の一部でも一致とする —— 雛形は `id: ADR-<連番>` のように値の一部に指示文を
    置くからである。一覧は要素ごとに見る。**本文は見ない** —— 本文には `<svg>`・
    置き場所の記法・id の書式が正当に出るので、誤検知が多すぎる(ADR-098)。

    判定はここに一度だけ置き、リンタ(予防)と監査(検出)が同じコアを呼ぶ。
    読み手ごとに答えが割れないようにするためである(ADR-053 と同じ原理)。
    """
    out = []
    if not isinstance(meta, dict):
        return out
    for key in sorted(meta):
        value = meta[key]
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, str):
                continue
            if _PLACEHOLDER_RE.search(item):
                out.append((str(key), item))
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _err(code, line, key, detail):
    """Build a structured error record. JSON-serializable; never raises."""
    return {"code": code, "line": line, "key": key, "detail": detail}


def _strip_fence(line):
    """Strip a trailing CR and trailing horizontal whitespace for fence checks."""
    if line.endswith("\r"):
        line = line[:-1]
    return line.rstrip(" \t")


def _is_open_fence(line):
    # §3.2: opener is exactly '---' (trailing ws/tabs ok). Leading ws => body.
    # '--- foo' is NOT an opener (it is body).
    return _strip_fence(line) == "---"


def _is_close_fence(line):
    # §3.3: closer is '---' or '...' (trailing ws/tabs ok).
    return _strip_fence(line) in ("---", "...")


def _slice_body(original_text, lines, close_idx):
    """Return the substring of original_text after the newline that terminates
    the closing fence line. Preserves original newline style verbatim.

    `lines` is the universal-newline split of original_text. We walk the
    original text counting line terminators to find the start of the body.
    """
    # Reconstruct the character offset just past the (close_idx)-th line's
    # terminator by re-splitting the original text WITH keepends. Universal
    # newline semantics: splitlines(keepends=True) yields each line including
    # its terminator, matching the indices of splitlines() above.
    kept = original_text.splitlines(keepends=True)
    # kept has the same length as `lines` (one element per logical line).
    # Body begins immediately after element [close_idx] (the fence line + its
    # terminator). Any trailing blank lines are part of the body, verbatim.
    if close_idx + 1 >= len(kept):
        return ""
    return "".join(kept[close_idx + 1:])


def _parse_lines(numbered_lines, errors):
    """Parse the frontmatter lines (list of (orig_line_no, raw)) into a dict.

    Honors: comments, block-list items (attach to most-recent empty key),
    KEY:VALUE split on first unquoted colon, flow lists, quoting, bool/null
    coercion, duplicate-key last-wins+error. Records non-fatal errors.
    """
    fm = {}
    open_list_key = None  # most recent key whose value was empty (eligible list)

    for lineno, raw in numbered_lines:
        line = raw[:-1] if raw.endswith("\r") else raw  # drop lone trailing CR
        s = line.strip()

        if s == "":
            continue
        if s.startswith("#"):
            continue

        # Block-list item: '-' followed by space or end-of-line.
        if _is_block_item(s):
            if open_list_key is None:
                errors.append(_err("orphan_list_item", lineno, None,
                                   "対応するリストキーの無い '- ' 行"))
                continue
            item_text = _block_item_value(s)
            val, ierrs = _scalar(item_text, lineno, open_list_key)
            errors.extend(ierrs)
            # Convert the open key from None to [] on first item.
            if not isinstance(fm.get(open_list_key), list):
                fm[open_list_key] = []
            fm[open_list_key].append(val)
            continue

        # Key line: split on first unquoted colon.
        split = _split_first_unquoted_colon(line)
        if split is None:
            errors.append(_err("bad_line", lineno, None,
                               "コロンを含まない行（リスト項目でもコメントでもない）"))
            open_list_key = None
            continue

        key, rawval = split
        key = key.strip()
        if key == "":
            errors.append(_err("empty_key", lineno, None, "キーが空の行"))
            open_list_key = None
            continue

        if key in fm:
            errors.append(_err("duplicate_key", lineno, key,
                               "キーの重複（後勝ち）"))

        # Strip inline comment from the raw value region (only when unquoted),
        # then classify.
        val_region = _strip_inline_comment(rawval)
        vstripped = val_region.strip()

        if _looks_like_flow_list(vstripped):
            parsed, ferrs = _parse_flow_list(vstripped, lineno, key)
            errors.extend(ferrs)
            fm[key] = parsed
            open_list_key = None
        elif vstripped == "":
            # Empty scalar -> None for now; may become a block list if the next
            # line is a '- ' item (handled above by open_list_key).
            fm[key] = None
            open_list_key = key
        else:
            sval, serrs = _scalar(vstripped, lineno, key)
            errors.extend(serrs)
            fm[key] = sval
            open_list_key = None

    return fm


def _is_block_item(s):
    """True if stripped line `s` is a block-list item ('-' then space or EOL)."""
    if s == "-":
        return True
    return s.startswith("- ")


def _block_item_value(s):
    """Return the scalar text of a block-list item (after the leading '- ')."""
    if s == "-":
        return ""
    return s[2:]  # after '- '


def _split_first_unquoted_colon(line):
    """Split `line` on the first colon NOT inside quotes.

    Returns (key, rawval) or None if there is no unquoted colon. The colon must
    be followed by whitespace or end-of-line OR appear before any quote opens
    for the key region; per the flat schema, the first colon at top level is the
    separator. We scan char by char tracking quote state on the KEY side only.
    """
    in_single = False
    in_double = False
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_double:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_double = False
        elif in_single:
            if c == "'":
                in_single = False
        else:
            if c == '"':
                in_double = True
            elif c == "'":
                in_single = True
            elif c == ":":
                return (line[:i], line[i + 1:])
        i += 1
    return None


def _strip_inline_comment(rawval):
    """Strip an unquoted inline '#' comment from a raw value region.

    A '#' begins a comment only when at value start (after leading ws) or
    preceded by whitespace, and not inside quotes. '#' with no preceding space
    (e.g. SPEC-014#3) is literal. '#' inside quotes is literal.
    """
    in_single = False
    in_double = False
    i = 0
    n = len(rawval)
    prev = None  # previous raw char (to test 'preceded by whitespace')
    while i < n:
        c = rawval[i]
        if in_double:
            if c == "\\":
                i += 2
                prev = "\\"
                continue
            if c == '"':
                in_double = False
        elif in_single:
            if c == "'":
                in_single = False
        else:
            if c == '"':
                in_double = True
            elif c == "'":
                in_single = True
            elif c == "#":
                # Comment iff at value-region start (only ws before) or
                # preceded by whitespace.
                if prev is None or prev in (" ", "\t"):
                    return rawval[:i]
        prev = c
        i += 1
    return rawval


def _looks_like_flow_list(vstripped):
    return vstripped.startswith("[")


def _parse_flow_list(vstripped, lineno, key):
    """Parse an inline flow list '[a, b, c]' into a list of scalars.

    Splits on top-level commas (not inside quotes). Records unterminated_flow
    if no closing ']'. Records bad_flow_list if an element still has an
    unbalanced bracket after split. Drops empty elements silently.
    """
    errors = []
    inner = vstripped[1:]  # drop leading '['
    if inner.endswith("]"):
        inner = inner[:-1]
    else:
        # find a ']' somewhere; if present, take up to it; else unterminated.
        rb = inner.rfind("]")
        if rb >= 0:
            inner = inner[:rb]
        else:
            errors.append(_err("unterminated_flow", lineno, key,
                               "フローリストの閉じ ']' が無い"))

    elements = _split_top_level_commas(inner)
    out = []
    for el in elements:
        el = el.strip()
        if el == "":
            continue
        # Detect leftover unbalanced brackets (nested flow not supported).
        if "[" in el or "]" in el:
            errors.append(_err("bad_flow_list", lineno, key,
                               "入れ子のフローリストは未対応（最善解析）"))
        sval, serrs = _scalar(el, lineno, key)
        errors.extend(serrs)
        # Only append non-empty stringified scalars; None elements dropped.
        if sval is None:
            continue
        out.append(sval)
    return out, errors


def _split_top_level_commas(s):
    """Split `s` on commas that are not inside single/double quotes."""
    parts = []
    buf = []
    in_single = False
    in_double = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_double:
            if c == "\\":
                buf.append(c)
                if i + 1 < n:
                    buf.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_double = False
            buf.append(c)
        elif in_single:
            if c == "'":
                in_single = False
            buf.append(c)
        else:
            if c == '"':
                in_double = True
                buf.append(c)
            elif c == "'":
                in_single = True
                buf.append(c)
            elif c == ",":
                parts.append("".join(buf))
                buf = []
            else:
                buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _scalar(raw, lineno, key):
    """Convert a raw scalar string to its typed value (str/bool/None).

    Handles quoting (double w/ escapes, single w/ '' escape). Quoted values are
    NEVER coerced. Unquoted true/false -> bool (if COERCE_BOOL); null/~/empty ->
    None; everything else stays str verbatim. Returns (value, errors).
    """
    errors = []
    s = raw.strip()

    if s == "":
        return None, errors

    first = s[0]

    # Double-quoted.
    if first == '"':
        if len(s) >= 2 and s.endswith('"') and not _ends_with_escaped_quote(s):
            inner = s[1:-1]
            return _unescape_double(inner), errors
        # Unterminated: take the rest literally (after the opening quote).
        errors.append(_err("unterminated_quote", lineno, key,
                           "二重引用符が閉じていない"))
        return _unescape_double(s[1:]), errors

    # Single-quoted.
    if first == "'":
        if len(s) >= 2 and s.endswith("'") and _single_quote_balanced(s):
            inner = s[1:-1]
            return inner.replace("''", "'"), errors
        errors.append(_err("unterminated_quote", lineno, key,
                           "単一引用符が閉じていない"))
        return s[1:].replace("''", "'"), errors

    # Unquoted: null / bool / string.
    low = s.lower()
    if s == "~" or low == "null":
        return None, errors
    if COERCE_BOOL and low in ("true", "false"):
        return (low == "true"), errors
    return s, errors


def _ends_with_escaped_quote(s):
    """True if the final '"' of s is escaped (odd run of backslashes before it).

    Used to decide whether a trailing '"' actually closes the string.
    """
    if not s.endswith('"'):
        return False
    # Count backslashes immediately before the final quote.
    i = len(s) - 2
    bs = 0
    while i >= 0 and s[i] == "\\":
        bs += 1
        i -= 1
    return (bs % 2) == 1


def _single_quote_balanced(s):
    """Heuristic: for a single-quoted scalar, treat '' as an escaped quote.

    Returns True when the string from index 1..-1 has all internal quotes
    paired as ''. We accept the simple case where s starts and ends with a
    single quote and the inner content's lone quotes are all doubled.
    """
    inner = s[1:-1]
    # Replace doubled quotes, then there should be no stray single quote.
    return "'" not in inner.replace("''", "")


def _unescape_double(inner):
    """Process standard double-quote escapes: \\" \\\\ \\n \\t \\r \\uXXXX."""
    out = []
    i = 0
    n = len(inner)
    while i < n:
        c = inner[i]
        if c == "\\" and i + 1 < n:
            nxt = inner[i + 1]
            if nxt == '"':
                out.append('"'); i += 2; continue
            if nxt == "\\":
                out.append("\\"); i += 2; continue
            if nxt == "n":
                out.append("\n"); i += 2; continue
            if nxt == "t":
                out.append("\t"); i += 2; continue
            if nxt == "r":
                out.append("\r"); i += 2; continue
            if nxt == "u" and i + 5 < n + 1 and i + 6 <= n:
                hexpart = inner[i + 2:i + 6]
                try:
                    out.append(chr(int(hexpart, 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            # Unknown escape: keep backslash literally.
            out.append("\\")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Tiny self-test (harmless; the authoritative suite is tests/test_frontmatter.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _fm, _body, _errs = parse("---\nid: SPEC-014\nsources: [a, b]\n---\n# Body\n")
    assert _fm == {"id": "SPEC-014", "sources": ["a", "b"]}, _fm
    assert _body == "# Body\n", repr(_body)
    assert _errs == [], _errs
    assert as_list(None) == [] and as_list("x") == ["x"] and as_list(["a", "b"]) == ["a", "b"]
    assert parse_frontmatter("---\nid: A\n---\n") == {"id": "A"}
    print("FRONTMATTER_VERSION=%d self-test OK" % FRONTMATTER_VERSION)
