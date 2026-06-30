#!/usr/bin/env python3
"""用語チェッカーの中核(importable core). 仕様 §1 / MASTER §6 を実装する。

保証限界:
- 予防: ここでは何も予防しない。検出だけを行う(リンタは助言のみ。§4.2)。
- 検出: 承認辞書(§1)に対する禁止同義語・カルク・一語訳の罠・未定義語の初出を
  機械的に照合して指摘する。辞書はこのモジュールに二重定義せず、
  GLOSSARY 正本(または同梱テンプレート)から読み込む(§4.3「辞書を二重定義しない」)。
- 委ねる: 一覧に無い訳語臭の判定、文意の良し悪しは doc-review(逆翻訳テル)に委ねる。
  文書単位を超える点検(参照整合・孤児)は監査に委ねる。

標準ライブラリだけを使う。pip も通信も使わない。決定的に動く。

辞書の単一の出所(§1 の表)は templates/glossary.md.tmpl にある。このモジュールは
承認語・禁止同義語・カルク表をハードコードしない。`load_glossary` が運用版
(対象リポジトリの docs/_system/glossary.md)を読み、無ければ同梱テンプレートに
退避する。これにより §1 はこの体系の中で一度だけ符号化される。
"""
from __future__ import annotations

import os
import re
from collections import namedtuple

# Finding shape — consumed by docs-linter.py and doc-review. (line may be None.)
Finding = namedtuple("Finding", ("code", "severity", "message", "line"))
Finding.__new__.__defaults__ = (None,)  # line defaults to None

ERROR = "ERROR"
WARN = "WARN"

# 構造語彙は体系の別の正本で既に定義されている。未定義語として扱わない。
# 型コード(SPEC・REQ・TEST 等)は登録簿(§3.2, _registry)で一度だけ定義する
# (辞書に書くと二重定義になる, §4.3)。[R番号](R1〜R10 等)は §2 の要求への参照で、
# 用語ではない。両者の定義の在処は登録簿と §2 であり、用語チェッカーはそこを正本と認める。
try:
    import _registry as _registry_mod
    _STRUCTURAL_TYPE_CODES = frozenset(_registry_mod.TYPES)
except Exception:                       # _registry が無くても落ちない(助言層)
    _STRUCTURAL_TYPE_CODES = frozenset()
_REQ_TAG_RE = re.compile(r"^R\d+$")

# ---------------------------------------------------------------------------
# Loanword allow-list and wordtrap — these are §1 prose lines, parsed from the
# glossary body when present; the constants below are ONLY the fallback default
# used when the glossary body carries no matching line. They are NOT an
# independent re-encoding of the approved-term TABLE (that lives in the
# template/glossary and is always parsed, never hardcoded here).
# ---------------------------------------------------------------------------

# 定着した借用語(§1「擬陽性を避ける」). Never flagged as calque/undefined.
_DEFAULT_LOANWORD_ALLOWLIST = ("データ", "リスク")

# 一語訳の罠(§1). English source word appearing in JP prose -> JP fix. WARN.
_DEFAULT_WORDTRAP = {
    "status": "位置づけ・区分",
    "native": "標準で・組み込みで",
    "robust": "壊れにくい",
    "leverage": "活かす",
}

# Path of the plugin-shipped §1 seed (single encoding of the tables).
_TEMPLATE_GLOSSARY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "templates", "glossary.md.tmpl"
)


class Glossary(object):
    """Parsed, enforced dictionary (§1). Built by `load_glossary` / `parse_glossary`.

    - approved_terms:   set[str]            承認語(表Aの第1列)
    - banned_synonyms:  list[(syn, approved)]  禁止同義語 -> 承認語(順序保持)
    - calque_table:     list[(surface, fix, en)]
    - wordtrap:         dict[en_word -> jp_fix]   一語訳の罠
    - loanwords:        tuple[str]          定着した借用語(擬陽性回避)
    - source:           'operational' | 'template' | 'seed'
    - parse_error:      bool  (True -> caller should surface GLOSSARY_PARSE_ERROR)
    """

    def __init__(self, approved_terms, banned_synonyms, calque_table,
                 wordtrap, loanwords, source, parse_error=False):
        self.approved_terms = approved_terms
        self.banned_synonyms = banned_synonyms
        self.calque_table = calque_table
        self.wordtrap = wordtrap
        self.loanwords = loanwords
        self.source = source
        self.parse_error = parse_error


# ---------------------------------------------------------------------------
# Glossary parsing
# ---------------------------------------------------------------------------

# A banned-synonym cell is "context-only" (no literal token) when it is wholly
# parenthetical — i.e. it is one full-width パーレン group and nothing else.
_PARENS_ONLY_RE = re.compile(r"^（[^）]*）$")

# Synonym separators inside a cell: 、 , ，
_SYN_SPLIT_RE = re.compile(r"[、,，]")

# A trailing full-width parenthetical on a calque surface is a usage qualifier
# (e.g. '（過剰）', '（資源量の意味で）'), not part of the literal phrase.
_TRAILING_PARENS_RE = re.compile(r"（[^）]*）$")


def _split_table_row(line):
    """Split a markdown table row '| a | b | c |' into stripped cells.

    Returns the list of cell strings (without the leading/trailing pipe cells),
    or None if the line is not a table row.
    """
    s = line.strip()
    if not s.startswith("|"):
        return None
    # Drop the leading and trailing pipe, then split on the rest.
    inner = s[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    cells = [c.strip() for c in inner.split("|")]
    return cells


def _is_separator_row(cells):
    """True for the |---|---| markdown header separator row."""
    for c in cells:
        t = c.replace(":", "").replace("-", "").strip()
        if t != "":
            return False
    return bool(cells)


def parse_glossary(text):
    """Parse a GLOSSARY body (markdown) into a Glossary. Never raises.

    Recognizes two tables by their header columns:
      A: 承認語 | 唯一の意味 | 禁止する同義語
      B: 使わない（カルク） | 直す | なぞった英語
    plus the 一語訳の罠 line and the 定着した借用語 line.

    Returns (glossary | None). Returns None when the approved-term table cannot
    be found (caller treats this as a parse error -> seed fallback + WARN).
    """
    if not isinstance(text, str):
        return None

    lines = text.splitlines()

    approved_terms = set()
    banned_synonyms = []        # list[(syn, approved)]
    calque_table = []           # list[(surface, fix, en)]
    wordtrap = {}
    loanwords = []

    mode = None                 # 'A' (approved) | 'B' (calque) | None
    found_table_a = False

    for raw in lines:
        cells = _split_table_row(raw)
        if cells is not None and len(cells) >= 3:
            head0, head1, head2 = cells[0], cells[1], cells[2]
            # Header detection (start of a table).
            if head0 == "承認語" and "禁止する同義語" in head2:
                mode = "A"
                found_table_a = True
                continue
            if "カルク" in head0 and "なぞった英語" in head2:
                mode = "B"
                continue
            if _is_separator_row(cells):
                continue
            # Data row under the active table.
            if mode == "A":
                approved = cells[0].strip()
                if approved == "":
                    continue
                approved_terms.add(approved)
                syn_cell = cells[2].strip()
                if syn_cell == "" or _PARENS_ONLY_RE.match(syn_cell):
                    # Parenthetical-only / blank cell -> context-only, no literal.
                    continue
                for syn in _SYN_SPLIT_RE.split(syn_cell):
                    syn = syn.strip()
                    # A wholly parenthetical part is a note, not a literal token.
                    if syn == "" or _PARENS_ONLY_RE.match(syn):
                        continue
                    # A concrete token may carry a trailing （...） usage note, e.g.
                    # 'インターフェース（単独語）'. Surface the concrete token so it is
                    # matched literally. But a note signalling conditional acceptance
                    # (「可」, e.g. 差し替え（操作名としては可。状態名は置換）) means the
                    # token is context-dependent — keep it context-only, no literal.
                    note = _TRAILING_PARENS_RE.search(syn)
                    if note is not None:
                        if "可" in note.group(0):
                            continue
                        syn = _TRAILING_PARENS_RE.sub("", syn).strip()
                    if syn == "":
                        continue
                    banned_synonyms.append((syn, approved))
                continue
            if mode == "B":
                surface = cells[0].strip()
                fix = cells[1].strip()
                en = cells[2].strip()
                if surface == "":
                    continue
                calque_table.append((surface, fix, en))
                continue
            continue

        # Not a table row -> leaving any table; parse prose lines.
        mode = None
        line = raw.strip()
        if line.startswith("一語訳の罠"):
            wordtrap.update(_parse_wordtrap_line(line))
        elif line.startswith("定着した借用語") or "借用語" in line and "カルク" in line:
            loanwords.extend(_parse_loanword_line(line))

    if not found_table_a or not approved_terms:
        return None

    if not wordtrap:
        wordtrap = dict(_DEFAULT_WORDTRAP)
    if not loanwords:
        loanwords = list(_DEFAULT_LOANWORD_ALLOWLIST)

    return Glossary(
        approved_terms=approved_terms,
        banned_synonyms=banned_synonyms,
        calque_table=calque_table,
        wordtrap=wordtrap,
        loanwords=tuple(loanwords),
        source="parsed",
    )


# '一語訳の罠 ... : status→位置づけ・区分、native→標準で... '
_WORDTRAP_PAIR_RE = re.compile(r"([A-Za-z][A-Za-z]+)\s*[→\->]+\s*([^、,，。]+)")


def _parse_wordtrap_line(line):
    out = {}
    # Take the part after the first colon if present.
    if ":" in line:
        line = line.split(":", 1)[1]
    elif "：" in line:
        line = line.split("：", 1)[1]
    for m in _WORDTRAP_PAIR_RE.finditer(line):
        en = m.group(1).strip().lower()
        jp = m.group(2).strip()
        if en and jp:
            out[en] = jp
    return out


# Established loanwords inside （...）, separated by ・ or 、
def _parse_loanword_line(line):
    out = []
    m = re.search(r"（([^）]*)）", line)
    if not m:
        return out
    body = m.group(1)
    # Drop a trailing 等/など marker.
    for tok in re.split(r"[・、,，]", body):
        tok = tok.strip().rstrip("等").rstrip("など").strip()
        if tok and tok not in ("",):
            out.append(tok)
    return out


def _read_text(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return fh.read()


def load_glossary(docs_root):
    """Load the enforced glossary for a target repo.

    Resolution (MASTER §6):
      1. operational: <docs_root>/_system/glossary.md (authoritative, extends seed)
      2. fallback:    plugin templates/glossary.md.tmpl (so §1 lives once)
      3. parse failure of (1): fall back wholly to template + mark parse_error
         (caller surfaces GLOSSARY_PARSE_ERROR WARN).

    `docs_root` is the target repo's docs/ directory (may be None for "use seed").
    Never raises; on any I/O error of the operational glossary it falls back to
    the template seed.
    """
    parse_error = False

    # 1. Operational glossary.
    if docs_root:
        op_path = os.path.join(docs_root, "_system", "glossary.md")
        if os.path.isfile(op_path):
            try:
                op_text = _read_text(op_path)
            except (OSError, UnicodeError):
                op_text = None
                parse_error = True
            if op_text is not None:
                g = parse_glossary(op_text)
                if g is not None:
                    g.source = "operational"
                    g.parse_error = False
                    return g
                # Present but unparsable -> seed + WARN.
                parse_error = True

    # 2/3. Template seed (the single §1 encoding).
    g = _load_template_seed()
    g.parse_error = parse_error
    return g


def _load_template_seed():
    """Parse the plugin-shipped template glossary. This is the §1 single source.

    If even the template cannot be parsed (should never happen in a correct
    install), return a minimal empty glossary marked parse_error so the checker
    degrades to a no-op rather than crashing the hook chain.
    """
    try:
        text = _read_text(_TEMPLATE_GLOSSARY)
    except (OSError, UnicodeError):
        text = None
    if text is not None:
        g = parse_glossary(text)
        if g is not None:
            g.source = "template"
            return g
    # Last-resort empty glossary (no checks fire). parse_error set by caller path.
    return Glossary(
        approved_terms=set(),
        banned_synonyms=[],
        calque_table=[],
        wordtrap=dict(_DEFAULT_WORDTRAP),
        loanwords=tuple(_DEFAULT_LOANWORD_ALLOWLIST),
        source="seed",
        parse_error=True,
    )


# ---------------------------------------------------------------------------
# Masking (擬陽性回避): hide code fences, inline code, URLs, frontmatter.
# The masker replaces masked spans with U+3000-safe spaces of equal length so
# that line numbers and offsets are preserved.
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^(\s*)(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _blank(match_or_str):
    s = match_or_str if isinstance(match_or_str, str) else match_or_str.group(0)
    # Preserve newlines so line counting stays correct; blank the rest.
    return "".join("\n" if ch == "\n" else " " for ch in s)


def mask_body(body):
    """Return `body` with code fences, inline code, and URLs blanked out.

    Length and newline positions are preserved so a finding's line number maps
    back to the original. Frontmatter is NOT masked here (the linter passes the
    already-split body); callers pass body only.
    """
    if not body:
        return body or ""
    out_lines = []
    in_fence = False
    for line in body.split("\n"):
        m = _FENCE_RE.match(line)
        if m:
            in_fence = not in_fence
            out_lines.append(_blank(line))
            continue
        if in_fence:
            out_lines.append(_blank(line))
            continue
        line = _INLINE_CODE_RE.sub(_blank, line)
        line = _URL_RE.sub(_blank, line)
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# The undefined-term heuristic
# ---------------------------------------------------------------------------

# Specialized-term candidate: a Latin acronym (>=2 upper) or Latin+digit token.
_SPECIAL_TERM_RE = re.compile(r"\b([A-Z]{2,}[0-9]*|[A-Za-z]+[0-9]+)\b")


def _line_of_offset(text, offset):
    """1-based line number of `offset` within `text`."""
    return text.count("\n", 0, offset) + 1


def _is_defined_at(masked, orig, term, start):
    """Heuristic: is `term` defined at its first occurrence `start`?

    Defined when followed by a gloss: '<term>（...）' / '<term>とは' / '<term>:'
    / '<term> (...)'. Approved glossary terms are handled by the caller.
    """
    after = orig[start + len(term): start + len(term) + 3]
    if after[:1] in ("（", "(", ":", "："):
        return True
    if after.startswith("とは"):
        return True
    return False


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def check(body, meta, glossary):
    """Run the four term-check rules over `body`. Returns list[Finding].

    - body:     the document body (NOT including frontmatter).
    - meta:     parsed frontmatter dict (used to skip GLOSSARY正本 / projections).
    - glossary: a Glossary (from load_glossary). If None, only structural skips
                apply and an empty list is returned.

    Skips entirely (returns []):
      - the GLOSSARY 正本 body (type == GLOSSARY): it *contains* the banned words.
      - projection docs (type in {OVERVIEW, CTXMAP}): body is rendered.
    Emits GLOSSARY_PARSE_ERROR WARN when the glossary degraded to seed.
    """
    findings = []
    if glossary is None:
        return findings

    meta = meta if isinstance(meta, dict) else {}
    doc_type = meta.get("type")

    if glossary.parse_error:
        findings.append(Finding(
            "GLOSSARY_PARSE_ERROR", WARN,
            "用語辞書の正本を解析できなかった。同梱の既定辞書(§1)で点検した。", None))

    # Skip body-level term checks on the glossary正本 and on projections.
    if doc_type == "GLOSSARY":
        return findings
    if doc_type in ("OVERVIEW", "CTXMAP"):
        return findings

    masked = mask_body(body or "")

    findings.extend(_check_banned_synonyms(masked, glossary))
    findings.extend(_check_calque(masked, glossary))
    findings.extend(_check_wordtrap(masked, glossary))
    findings.extend(_check_undefined(masked, glossary))
    return findings


# Spec-mandated compounds that LITERALLY CONTAIN a banned synonym but are
# themselves required by the spec, so an occurrence inside them must NOT be
# flagged (§3.2/付録B SPEC heading『入出力』contains『出力』(banned for 投影);
# the API guidance『中立・現在形』contains『現在』(banned for 現行)). These are
# masked length-preservingly BEFORE substring matching, so a standalone『出力』/
# 『現在』in ordinary prose is still caught. Japanese has no word boundaries, so
# this approved-compound mask is the only way to avoid the false positive.
_APPROVED_COMPOUNDS = ("入出力", "現在形")


def _mask_approved_compounds(masked):
    """Blank the exact spec-mandated compounds (length-preserving) so a banned
    synonym that is only a substring of an approved compound is not flagged,
    while a standalone synonym in prose still matches. (#03/#09)"""
    for compound in _APPROVED_COMPOUNDS:
        if compound in masked:
            masked = masked.replace(compound, _blank(compound))
    return masked


def _check_banned_synonyms(masked, glossary):
    """BANNED_SYNONYM (ERROR) — §1 / R6. Literal substring on masked body.

    Japanese has no word boundaries, so a banned synonym is matched as a raw
    substring. A few spec-MANDATED compounds literally contain a banned synonym
    (『入出力』⊃『出力』, 『現在形』⊃『現在』); those compounds are masked length-
    preservingly first so a compliant SPEC/API template is not false-flagged,
    while a standalone synonym in ordinary prose is still caught.
    Ordered by (synonym order in glossary, first occurrence).
    """
    masked = _mask_approved_compounds(masked)
    out = []
    for syn, approved in glossary.banned_synonyms:
        idx = masked.find(syn)
        if idx < 0:
            continue
        out.append(Finding(
            "BANNED_SYNONYM", ERROR,
            "禁止同義語『%s』→ 承認語『%s』を使う。" % (syn, approved),
            _line_of_offset(masked, idx)))
    return out


def _check_calque(masked, glossary):
    """CALQUE (ERROR) — §1 calque dict / R10. Literal substring on masked body."""
    out = []
    for surface, fix, en in glossary.calque_table:
        # A surface cell may list two variants separated by the full-width
        # slash '／'; each variant is its own literal to match. A leading 〜
        # placeholder (a phrase leader) is stripped so the literal token is the
        # concrete tail of the phrase.
        for variant in surface.split("／"):
            # A trailing （...） on a surface is a usage qualifier (過剰 / 意味),
            # not part of the literal phrase: '〜を可能にする（過剰）' matches the
            # phrase 'を可能にする'. doc-review judges the borderline overuse.
            token = _TRAILING_PARENS_RE.sub("", variant.strip()).strip().lstrip("〜")
            if token == "":
                continue
            idx = masked.find(token)
            if idx < 0:
                continue
            msg = "カルク『%s』→『%s』に直す。" % (surface, fix)
            if en:
                msg += "（なぞった英語: %s）" % en
            out.append(Finding("CALQUE", ERROR, msg, _line_of_offset(masked, idx)))
            break   # one finding per calque row
    return out


def _check_wordtrap(masked, glossary):
    """CALQUE_WORDTRAP (WARN) — 一語訳の罠. English source word in JP prose.

    WARN (not ERROR): heuristic, prone to false positives in code/IDs — but code
    is already masked. Matched case-insensitively as a Latin word boundary.
    """
    out = []
    low = masked.lower()
    for en, jp in glossary.wordtrap.items():
        en_low = en.lower()
        pat = re.compile(r"\b" + re.escape(en_low) + r"\b")
        m = pat.search(low)
        if not m:
            continue
        out.append(Finding(
            "CALQUE_WORDTRAP", WARN,
            "一語訳の罠『%s』→『%s』を検討する。" % (en, jp),
            _line_of_offset(masked, m.start())))
    return out


def _check_undefined(masked, glossary):
    """UNDEFINED_TERM (WARN) — §1「専門語・略語は初出で定義する」.

    Heuristic first-use: a Latin acronym / Latin+digit token that is NOT an
    approved glossary term, NOT a loanword, NOT a wordtrap source, and is not
    glossed at its first occurrence. First occurrence only.
    """
    out = []
    seen = set()
    wordtrap_words = {w.lower() for w in glossary.wordtrap}
    loanwords = set(glossary.loanwords)
    for m in _SPECIAL_TERM_RE.finditer(masked):
        term = m.group(1)
        if term in seen:
            continue
        seen.add(term)
        if term in glossary.approved_terms:
            continue
        if term in _STRUCTURAL_TYPE_CODES:   # 型コードは登録簿(§3.2)で定義済み
            continue
        if _REQ_TAG_RE.match(term):          # [R番号] は §2 の要求への参照
            continue
        if term in loanwords:
            continue
        if term.lower() in wordtrap_words:
            continue
        if _is_defined_at(masked, masked, term, m.start()):
            continue
        out.append(Finding(
            "UNDEFINED_TERM", WARN,
            "未定義語『%s』を初出で定義する(§1)。" % term,
            _line_of_offset(masked, m.start())))
    return out


# ---------------------------------------------------------------------------
# Rendering (shared with the CLI)
# ---------------------------------------------------------------------------

def render_findings(findings, path=None):
    """Render a list[Finding] as a deterministic human-readable block."""
    lines = []
    if path:
        lines.append("term-check: %s" % path)
    for f in findings:
        loc = (" (行 %d)" % f.line) if f.line else ""
        lines.append("  [%s] %s: %s%s" % (f.severity, f.code, f.message, loc))
    return "\n".join(lines)
