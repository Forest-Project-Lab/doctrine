#!/usr/bin/env python3
"""ドメイン特徴語の候補を出す c-TF-IDF 抽出器(読み取り専用)。

保証限界:
- 予防: 何も予防しない。
- 検出: 各ドメイン(フォルダ)を1クラスとした class-based TF-IDF(c-TF-IDF, 付録C)で、
  あるドメインを他と分ける語の候補を出す。辞書の素案づくりに使う。
- 委ねる: 採否は人間に委ねる。何も書き込まない。承認語の確定は人間が行い、辞書への
  追加は別の編集手順(doc-author)で行う(§4.3「採否は人間」, §7「付与は人間に依る」)。

設計上の単純化(標準ライブラリのみ。形態素解析器は使えない):
  トークン化は正規表現と文字バイグラムによる近似であり、語の切り出しではない。
  日本語の連なりは長さ2の文字バイグラムに分解する。英数字は単語として取る。
  候補は構造上ノイズを含む。確定は人間の承認が要る(§7)。

c-TF-IDF(BERTopic, 付録C):
  tf(t,c)  = クラス c 内の t の出現数 / クラス c の総トークン数(クラス内 L1 正規化)
  idf(t)   = log(1 + A / f(t))  A=クラス平均トークン数, f(t)=全クラス合計の t 出現数
  c-tf-idf = tf(t,c) * idf(t)
  クラス(ドメイン)内で c-tf-idf 降順に並べ、上位 N を候補にする。ドメインが1つだと
  対比が無く idf が縮退するため、低信頼の注意を出す。

CLI:
  term-extract.py [--root PATH] [--domain NAME ...] [--top 25] [--min-df 2]
                  [--format text|json|csv] [--include-system] [--all]
既定の除外: _system, archive/, llm_context:never(ARCHIVE/RESEARCH)。--include-system /
--all で広げられる。書き込みは一切しない(読み取り専用)。決定的(同点は語の昇順で割る)。

標準ライブラリのみ。pip も通信も使わない。終了コード 0(問い合わせ専用)。
"""
import json
import math
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter
import _registry

# Stable disclaimer carried in every output (B.2 / B.6 human-approval contract).
DISCLAIMER = (
    "トークン化は標準ライブラリの正規表現とバイグラムによる近似であり、形態素解析では"
    "ない。候補は構造上ノイズを含み、人間の承認が要る(§7)。"
)
HUMAN_NOTE = "注意: これは候補。採否は人間。未承認語の自動追加はしない(§4.3, §7)。"
LOW_CONFIDENCE = (
    "注意: 特徴語の抽出には2ドメイン以上が要る。1ドメインだけでは対比が無く、"
    "クラス内のtf順位を低信頼で出す(§7)。"
)
TOKENIZATION_TAG = "stdlib-bigram-approx"

# ---------------------------------------------------------------------------
# Tokenization (B.2) — stdlib regex + Japanese character bigrams.
# ---------------------------------------------------------------------------

# ASCII word run: a letter then 1+ letters/digits/_/- ; min length 2 overall.
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")

# Maximal runs of Japanese script characters (CJK ideographs, Hiragana,
# Katakana incl. 長音符). Each run is bigram-decomposed.
_JP_RUN_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿー]+")

# Fenced code blocks (``` ... ``` and ~~~ ... ~~~) — stripped before tokenizing
# (code pollutes term stats; documented decision B.4).
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})", re.MULTILINE)

# A SHORT, conservative stoplist (B.2). c-TF-IDF already de-weights cross-class
# common terms; a heavy list risks dropping real domain terms.
_STOP_ASCII = frozenset({
    "the", "and", "of", "to", "is", "for", "in", "on", "at", "by", "with",
    "as", "an", "or", "be", "this", "that", "it", "are", "from", "was",
})
_STOP_JP_BIGRAMS = frozenset({
    "こと", "する", "ため", "など", "より", "から", "また", "その", "この",
    "れる", "られ", "という", "ある", "なる", "いる",
})


def _strip_code_fences(text):
    """Remove fenced code blocks from `text` (lines between matching fences).

    Conservative: drops everything between an opening fence line and the next
    fence line of the same marker family. Unclosed fence drops to end-of-text.
    """
    lines = text.splitlines()
    out = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def tokenize(text):
    """Tokenize `text` into a list of tokens (B.2 documented approximation).

    - NFKC normalize, then lowercase.
    - Strip fenced code blocks.
    - ASCII runs -> word tokens (min length 2), stoplisted, pure-digit dropped.
    - Japanese runs -> sliding length-2 character bigrams (single-char run ->
      the unigram), stoplisted.
    Order of tokens follows their position in the text (counting is order-free,
    but a stable order keeps the function easy to reason about/test).
    """
    if not text:
        return []
    text = unicodedata.normalize("NFKC", text)
    text = _strip_code_fences(text)
    text = text.lower()

    tokens = []
    # ASCII word tokens.
    for m in _ASCII_RE.finditer(text):
        tok = m.group(0)
        if tok in _STOP_ASCII:
            continue
        if tok.isdigit():
            continue
        tokens.append(tok)
    # Japanese bigram tokens. NFKC+lower lowercases ASCII but leaves the JP
    # script ranges intact; the run regex matches the original ranges.
    for m in _JP_RUN_RE.finditer(text):
        run = m.group(0)
        if len(run) == 1:
            tokens.append(run)
            continue
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg in _STOP_JP_BIGRAMS:
                continue
            tokens.append(bg)
    return tokens


# ---------------------------------------------------------------------------
# Corpus scan (B.4).
# ---------------------------------------------------------------------------
def _read_text(path):
    """Read a file as UTF-8 with errors='replace' (B.7 non-UTF8 robustness).

    Returns (text, warning_or_None). Never raises on a readable file.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
            return fh.read(), None
    except OSError as exc:
        return None, "読めない: %s (%s)" % (path, exc)


def _doc_is_excluded(meta, relpath, include_system, include_all):
    """Decide whether a doc is excluded from the c-TF-IDF corpus (B.4).

    Default excludes: anything under an 'archive/' segment, and any doc whose
    effective llm_context is 'never' (ARCHIVE/RESEARCH). --all keeps everything.
    _system handling is done by the caller (it is not a domain). Returns
    (excluded: bool, reason: str|None).
    """
    if include_all:
        return False, None
    parts = relpath.replace("\\", "/").split("/")
    if "archive" in parts:
        return True, "archive/"
    if _registry.effective_llm_context(meta) == "never":
        return True, "llm_context:never"
    return False, None


def _domain_of_relpath(relpath):
    """Infer the domain (class) for a doc path relative to docs/.

    The first path segment is the domain folder (§3.1). '_system' is the
    cross-cutting tier, not a domain. Returns the domain string, or '_system'
    for the system tier, or None when there is no domain segment (a stray file
    directly under docs/).
    """
    norm = relpath.replace("\\", "/").strip("/")
    if not norm:
        return None
    segs = norm.split("/")
    if len(segs) < 2:
        # A file directly under docs/ with no domain folder — not a class.
        return None
    return segs[0]


def scan_corpus(root, include_system, include_all):
    """Walk docs/ under `root`; return (classes, warnings).

    classes: dict[domain] -> list of token lists (one per included doc).
    warnings: list[str] (skipped/odd files; never aborts the run).
    """
    docs_dir = os.path.join(root, "docs")
    classes = {}
    warnings = []
    if not os.path.isdir(docs_dir):
        warnings.append("docs/ が無い: %s" % docs_dir)
        return classes, warnings

    for dirpath, dirnames, filenames in os.walk(docs_dir):
        # Deterministic traversal order.
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            abspath = os.path.join(dirpath, fn)
            relpath = os.path.relpath(abspath, docs_dir)
            domain = _domain_of_relpath(relpath)
            if domain is None:
                continue
            if domain == "_system" and not include_system:
                continue

            text, werr = _read_text(abspath)
            if werr is not None:
                warnings.append(werr)
                continue
            try:
                meta, body, _errs = _frontmatter.parse(text)
            except Exception:  # never abort the whole run on one odd file
                warnings.append("解析できない(本文だけ使う): %s" % relpath)
                meta, body = {}, text

            excluded, _reason = _doc_is_excluded(meta, relpath, include_system,
                                                 include_all)
            if excluded:
                continue

            toks = tokenize(body)
            if not toks:
                continue
            classes.setdefault(domain, []).append(toks)
    return classes, warnings


# ---------------------------------------------------------------------------
# c-TF-IDF (B.3).
# ---------------------------------------------------------------------------
def compute_ctfidf(classes, top, min_df):
    """Compute c-TF-IDF per class (B.3).

    `classes`: dict[domain] -> list of token lists.
    Returns dict[domain] -> list of dicts {term, c_tf_idf, df} sorted by
    descending c_tf_idf then ascending term (deterministic tie-break).
    `top` caps candidates per domain; `min_df` drops terms whose document
    frequency (number of docs in the class containing the term) is below it.

    Note the distinction: c-TF-IDF scoring uses the collection term frequency
    (total occurrences in the class), while `df` and `--min-df` use the
    document frequency (how many docs in the class contain the term). A term
    that appears 5 times in ONE doc has df=1 and is dropped at --min-df 2.
    """
    from collections import Counter

    # Per-class token totals and per-class term counts.
    class_counts = {}      # domain -> Counter(term -> count in class)
    class_totals = {}      # domain -> total tokens in class
    class_docfreq = {}     # domain -> Counter(term -> #docs in class with term)
    global_counts = Counter()  # term -> total count across ALL classes
    for domain, doclists in classes.items():
        cc = Counter()
        df = Counter()
        for toks in doclists:
            cc.update(toks)
            df.update(set(toks))  # each doc contributes 1 per distinct term
        class_counts[domain] = cc
        class_totals[domain] = sum(cc.values())
        class_docfreq[domain] = df
        global_counts.update(cc)

    num_classes = len(classes)
    total_tokens = sum(class_totals.values())
    # A = average tokens per class (BERTopic c-TF-IDF idf component).
    avg_tokens = (total_tokens / num_classes) if num_classes else 0.0

    result = {}
    for domain in sorted(classes.keys()):
        cc = class_counts[domain]
        df_counter = class_docfreq[domain]
        ctotal = class_totals[domain] or 1  # avoid divide-by-zero
        rows = []
        for term, cnt in cc.items():
            df = df_counter[term]  # document frequency: #docs in class with term
            if df < min_df:        # --min-df filters on document frequency
                continue
            tf = cnt / ctotal      # collection term frequency (for scoring)
            f_t = global_counts[term] or 1
            idf = math.log(1.0 + (avg_tokens / f_t))
            score = tf * idf
            rows.append({"term": term, "c_tf_idf": score, "df": df})
        # Sort: c_tf_idf desc, then term asc (deterministic, B.6/B.7-10).
        rows.sort(key=lambda r: (-r["c_tf_idf"], r["term"]))
        result[domain] = rows[:top]
    return result


# ---------------------------------------------------------------------------
# Output rendering (B.6).
# ---------------------------------------------------------------------------
def _format_text(result, classes, num_classes, warnings, single_domain):
    """Render the human-readable per-domain report (B.6 text format)."""
    lines = []
    lines.append("# term-extract 候補 (c-TF-IDF)")
    lines.append(DISCLAIMER)
    if single_domain:
        lines.append(LOW_CONFIDENCE)
    for w in warnings:
        lines.append("警告: %s" % w)
    lines.append("")
    if not result:
        lines.append("(候補なし。docs/ にドメインの文書が無い。)")
        lines.append(HUMAN_NOTE)
        return "\n".join(lines) + "\n"

    for domain in sorted(result.keys()):
        rows = result[domain]
        ndocs = len(classes.get(domain, []))
        ntokens = sum(len(t) for t in classes.get(domain, []))
        lines.append("## domain: %s  (docs=%d, tokens=%d, classes_in_contrast=%d)"
                     % (domain, ndocs, ntokens, num_classes))
        lines.append("rank  term            c-tf-idf   df")
        for i, r in enumerate(rows, start=1):
            lines.append("%4d  %-14s  %.6f  %d"
                         % (i, r["term"], r["c_tf_idf"], r["df"]))
        lines.append("")
    lines.append(HUMAN_NOTE)
    return "\n".join(lines) + "\n"


def _format_json(result, classes, num_classes, warnings, single_domain):
    """Render the stable JSON form for docs-curate ingestion (B.6 json)."""
    domains = {}
    for domain in sorted(result.keys()):
        domains[domain] = [
            {"term": r["term"], "c_tf_idf": r["c_tf_idf"], "df": r["df"]}
            for r in result[domain]
        ]
    payload = {
        "tokenization": TOKENIZATION_TAG,
        "human_approval_required": True,
        "note": HUMAN_NOTE,
        "classes_in_contrast": num_classes,
        "single_domain_low_confidence": single_domain,
        "warnings": list(warnings),
        "domains": domains,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _format_csv(result, classes, num_classes, warnings, single_domain):
    """Render a flat CSV (domain,rank,term,c_tf_idf,df) for tooling (B.6)."""
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    # Leading comment rows carry the same contract as text/json so CSV is not a
    # bare table without the human-approval disclaimer (#07). Each comment row's
    # first field begins with '#'; tooling that splits on ',' and reads cols[2]
    # is unaffected (comment rows have a single field).
    writer.writerow(["# " + DISCLAIMER])
    writer.writerow(["# " + HUMAN_NOTE])
    if single_domain:
        writer.writerow(["# " + LOW_CONFIDENCE])
    for w in warnings:
        writer.writerow(["# 警告: %s" % w])
    writer.writerow(["domain", "rank", "term", "c_tf_idf", "df"])
    for domain in sorted(result.keys()):
        for i, r in enumerate(result[domain], start=1):
            writer.writerow([domain, i, r["term"],
                             "%.6f" % r["c_tf_idf"], r["df"]])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Argument parsing.
# ---------------------------------------------------------------------------
def _parse_args(argv):
    """Parse the CLI (B.5). Returns (opts, error_message)."""
    opts = {
        "root": os.getcwd(),
        "domains": [],
        "top": 25,
        "min_df": 2,
        "format": "text",
        "include_system": False,
        "all": False,
    }
    i = 0
    n = len(argv)

    def _take_value(flag, idx):
        if idx + 1 >= n:
            return None, None, "%s には値が必要" % flag
        return argv[idx + 1], idx + 2, None

    while i < n:
        a = argv[i]
        if a == "--root" or a.startswith("--root="):
            if "=" in a:
                opts["root"] = a.split("=", 1)[1]; i += 1
            else:
                v, i, err = _take_value("--root", i)
                if err:
                    return None, err
                opts["root"] = v
            continue
        if a == "--domain" or a.startswith("--domain="):
            if "=" in a:
                opts["domains"].append(a.split("=", 1)[1]); i += 1
            else:
                v, i, err = _take_value("--domain", i)
                if err:
                    return None, err
                opts["domains"].append(v)
            continue
        if a == "--top" or a.startswith("--top="):
            if "=" in a:
                val = a.split("=", 1)[1]; i += 1
            else:
                val, i, err = _take_value("--top", i)
                if err:
                    return None, err
            try:
                opts["top"] = int(val)
            except ValueError:
                return None, "--top は整数"
            continue
        if a == "--min-df" or a.startswith("--min-df="):
            if "=" in a:
                val = a.split("=", 1)[1]; i += 1
            else:
                val, i, err = _take_value("--min-df", i)
                if err:
                    return None, err
            try:
                opts["min_df"] = int(val)
            except ValueError:
                return None, "--min-df は整数"
            continue
        if a == "--format" or a.startswith("--format="):
            if "=" in a:
                val = a.split("=", 1)[1]; i += 1
            else:
                val, i, err = _take_value("--format", i)
                if err:
                    return None, err
            if val not in ("text", "json", "csv"):
                return None, "--format は text|json|csv"
            opts["format"] = val
            continue
        if a == "--include-system":
            opts["include_system"] = True; i += 1
            continue
        if a == "--all":
            opts["all"] = True; i += 1
            continue
        return None, "不明な引数: %s" % a
    return opts, None


def _usage(msg):
    sys.stdout.write("usage error: %s\n" % msg)
    sys.stdout.write(
        "term-extract.py [--root PATH] [--domain NAME ...] [--top 25] "
        "[--min-df 2] [--format text|json|csv] [--include-system] [--all]\n"
    )
    return 2


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def main(argv=None):
    """Emit domain-distinctive term candidates. Read-only; writes nothing."""
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    try:
        classes, warnings = scan_corpus(
            opts["root"], opts["include_system"], opts["all"])

        # idf contrast uses ALL scanned classes; --domain only restricts what is
        # PRINTED, so other domains still contribute distinctiveness (B.5).
        num_classes = len(classes)
        single_domain = num_classes <= 1

        result = compute_ctfidf(classes, opts["top"], opts["min_df"])

        if opts["domains"]:
            wanted = set(opts["domains"])
            # Warn in deterministic CLI order (de-duplicated), not set order,
            # so output is byte-identical regardless of PYTHONHASHSEED (#08).
            seen_unknown = set()
            for d in opts["domains"]:
                if d not in classes and d not in seen_unknown:
                    seen_unknown.add(d)
                    warnings.append("--domain で指定した未知のドメイン: %s" % d)
            result = {d: rows for d, rows in result.items() if d in wanted}

        fmt = opts["format"]
        if fmt == "json":
            out = _format_json(result, classes, num_classes, warnings,
                               single_domain)
        elif fmt == "csv":
            out = _format_csv(result, classes, num_classes, warnings,
                              single_domain)
        else:
            out = _format_text(result, classes, num_classes, warnings,
                               single_domain)
        sys.stdout.write(out)
        return 0
    except Exception as exc:  # query tool: never crash the caller
        sys.stdout.write("term-extract: internal error: %r\n" % (exc,))
        return 0


if __name__ == "__main__":
    sys.exit(main())
