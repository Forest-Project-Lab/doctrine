#!/usr/bin/env python3
"""単一文書のリンタ(PostToolUse, 助言のみ). 仕様 §4.2 / MASTER §5.1 を実装する。

保証限界:
- 予防: 何も予防しない。決して decision/permissionDecision/deny を出さない。
  違反は additionalContext で指摘し、Claude に自己修正させる(§4.2)。
- 検出: 編集された一つの文書だけを点検する。必須キー・status・id↔ファイル名・
  型↔置き場所・llm_context・SPEC 4節・用語・前向き追跡性・ICD依存(事後検出)を出す。
- 委ねる: 全件走査(参照整合・孤児・逆孤児・正本衝突・投影ドリフト・review_by超過)は
  監査に委ねる。拒否(不変・削除安全・ICD依存の事前拒否)はガードに委ねる。
  ドメイン解決(IDだけでは決まらない, §3.4)は dep-graph に委ねる。

入力は PostToolUse の Hook JSON(stdin)。出力は §3.3 の助言 JSON か空。終了コードは常に 0。
標準ライブラリのみ。pip も通信も使わない。一つのファイルだけを読む(全件走査しない)。
"""
import json
import os
import re
import sys

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hookio
import _frontmatter
import _intake
import _model
import _registry
import _termcheck


# ---------------------------------------------------------------------------
# Finding object (shared internal type; slice 04 §7). Rendered into §2.2 block.
# ---------------------------------------------------------------------------
class Finding(object):
    """One advisory finding. (code, severity, message, spec_ref)."""

    __slots__ = ("code", "severity", "message", "spec_ref")

    def __init__(self, code, severity, message, spec_ref):
        self.code = code
        self.severity = severity
        self.message = message
        self.spec_ref = spec_ref


ERROR = "ERROR"
WARN = "WARN"


# ---------------------------------------------------------------------------
# Path resolution from the hook envelope (§5.1 fallbacks; argv[1] for tests).
# ---------------------------------------------------------------------------
def resolve_path(stdin_text, argv):
    """Resolve the single edited file path from stdin JSON, else argv[1].

    Field lookup order (defensive against payload shape, §5.1):
      tool_input.file_path -> tool_input.path -> tool_response.filePath
      -> top-level file_path. Falls back to argv[0] (the script's argv[1]) when
      stdin is empty / not JSON / carries no path.
    """
    path = None
    if stdin_text and stdin_text.strip():
        try:
            payload = json.loads(stdin_text)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            ti = payload.get("tool_input")
            if isinstance(ti, dict):
                path = ti.get("file_path") or ti.get("path")
            if not path:
                tr = payload.get("tool_response")
                if isinstance(tr, dict):
                    path = tr.get("filePath")
            if not path:
                path = payload.get("file_path")
    if not path and argv:
        path = argv[0]
    if isinstance(path, str) and path.strip():
        return path
    return None


# ---------------------------------------------------------------------------
# Scope filtering (§1.3): cheaply decide whether to lint at all.
# ---------------------------------------------------------------------------
def _split_parts(path):
    """Normalized, split path parts (handles both separators)."""
    norm = path.replace("\\", "/")
    return [p for p in norm.split("/") if p not in ("", ".")]


def in_scope(path):
    """True iff the path is even a candidate to parse: any .md.

    ここは「.md か否か」だけを安く判じる入口。実際に統治するか否か
    (体系外は無発火、登録済み非文書は schema 強制せず用語助言のみ)は
    lint_text が統治木と intake を見て決める(ADR-024)。
    A deleted file (absent on disk) is handled by the caller (emit nothing).
    """
    return path.endswith(".md")


def _docs_root_of(path):
    """Nearest governed docs root of `path` (for glossary lookup), or None.

    ADR-022: doctrine_docs 優先。docs は _system を持つ場合だけ統治木と認める
    (見つからなければ None → 同梱テンプレートの辞書へ退避)。
    """
    return _registry.walkup_docs_root(path)


def _rel_under_docs(path):
    """Path parts relative to the nearest 'docs'/'_system'-rooted tree.

    Returns the list of segments AFTER the docs root (the directory layout the
    §3.2 置き場所 rules describe), or None if no docs root can be located. For
    '.../docs/billing/spec/SPEC-1-x.md' -> ['billing', 'spec', 'SPEC-1-x.md'].
    For '.../docs/_system/glossary.md' -> ['_system', 'glossary.md'].
    """
    parts = _split_parts(path)
    # Prefer the last docs-root segment (doctrine_docs first, ADR-022).
    for name in _registry.DOCS_DIR_NAMES:
        idx = None
        for i, p in enumerate(parts):
            if p == name:
                idx = i
        if idx is not None:
            return parts[idx + 1:]
    # No literal docs-root ancestor: anchor on '_system' if present.
    if "_system" in parts:
        j = parts.index("_system")
        return parts[j:]
    return None


# ---------------------------------------------------------------------------
# Filename / id helpers
# ---------------------------------------------------------------------------
_JP_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿＀-￯]")
_VERSION_SUFFIX_RE = re.compile(r"(?:[-_]v\d+|-\d+\.\d+)(?=\.md$|$)")


def _stem(path):
    return os.path.basename(path)[:-3] if path.endswith(".md") else os.path.basename(path)


def _is_system_singleton(rel_parts):
    """True iff this is a fixed _system filename whose name does NOT encode id.

    Covers the projection files and the scaffolded _system canonical files
    (§3.7 / MASTER §2): overview.md, icd-index.md, context-map.md, glossary.md,
    decided-facts.md, non-goals.md. For these the id<->filename check is skipped
    (filename is positional, not id-derived) — MASTER residual-risk whitelist.
    """
    if not rel_parts or rel_parts[0] != "_system":
        return False
    fname = rel_parts[-1]
    return (fname in _registry.PROJECTION_FILES
            or fname in _registry.SYSTEM_CANONICAL_FILES)


# ---------------------------------------------------------------------------
# Individual checks. Each appends Finding(s) in §3 order.
# ---------------------------------------------------------------------------
def _check_required_keys(meta, findings):
    """§3.1 MISSING_KEY (ERROR) + EMPTY_KEY (ERROR; empty sources:[] allowed)."""
    type_code = meta.get("type")
    # 必須キーの規則の正本は登録簿(確定事実1。ADR-106)。以前はここで
    # REQUIRED_KEYS_L2 と REQUIRED_REVIEW_BY_TYPES を自前で組み合わせており、
    # 同じ規則が二箇所に在った —— そして正本の側は誰にも呼ばれていなかった。
    required = _registry.required_keys(type_code)
    for key in required:
        if key not in meta:
            note = "(DECIDED/WATCH では必須)" if key == "review_by" else ""
            findings.append(Finding(
                "MISSING_KEY", ERROR,
                "必須キー『%s』が無い%s。" % (key, note), "§3.4"))
            continue
        value = meta.get(key)
        if key == "sources":
            # Empty sources:[] is allowed (some docs have no external source).
            continue
        if _is_empty_value(value):
            note = "(DECIDED/WATCH では必須)" if key == "review_by" else ""
            findings.append(Finding(
                "EMPTY_KEY", ERROR,
                "必須キー『%s』が空%s。" % (key, note), "§3.4"))



def _is_empty_value(value):
    """True iff a frontmatter value counts as empty (None / '' / [] )."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return len(value) == 0
    return False


def _check_status(meta, findings):
    """§3.2 BAD_STATUS (ERROR) — status must be in the per-type allow-list."""
    type_code = meta.get("type")
    status = meta.get("status")
    if not _registry.is_known_type(type_code):
        # type itself unknown -> reported by _check_type; skip status here.
        return
    if status is not None and not isinstance(status, str) \
            and not _is_empty_value(status):
        # Non-string, non-empty status (e.g. `status: [current]`): not
        # covered by EMPTY_KEY, so it must be flagged here.
        findings.append(Finding(
            "BAD_STATUS", ERROR,
            "status は統制語彙の文字列で書く(%r は不正)。" % (status,), "§3.3"))
        return
    if not isinstance(status, str) or status.strip() == "":
        return  # empty status already flagged as EMPTY_KEY
    status = status.strip()
    if status not in _registry.ALL_STATUSES:
        findings.append(Finding(
            "BAD_STATUS", ERROR,
            "status『%s』は統制語彙にない。" % status, "§3.3"))
        return
    allowed = _registry.status_allowed(type_code)
    if status not in allowed:
        findings.append(Finding(
            "BAD_STATUS", ERROR,
            "status『%s』は型 %s では許可されない(許可: %s)。"
            % (status, type_code, ", ".join(sorted(allowed))), "§3.3"))


def _check_type_known(meta, findings):
    """UNKNOWN_TYPE (ERROR) — the 'type' value must be a registry type."""
    type_code = meta.get("type")
    if type_code is not None and not isinstance(type_code, str):
        # e.g. the YAML-list typo `type: [SPEC]`: present, non-empty, but
        # not a string. Say so explicitly instead of passing silently.
        findings.append(Finding(
            "UNKNOWN_TYPE", ERROR,
            "型は文字列で書く(%r は登録簿の型コードでない)。" % (type_code,), "§3.2"))
        return
    if not isinstance(type_code, str) or type_code.strip() == "":
        return  # missing/empty handled by required-key check
    if not _registry.is_known_type(type_code):
        findings.append(Finding(
            "UNKNOWN_TYPE", ERROR,
            "型『%s』は登録簿にない。" % type_code, "§3.2"))


def _check_id_filename(meta, path, rel_parts, findings):
    """§3.3 ID_FILENAME_MISMATCH + BAD_FILENAME (ERROR)."""
    fname = os.path.basename(path)
    stem = _stem(path)

    # BAD_FILENAME traits: Japanese chars, spaces, embedded version suffix.
    if _JP_RE.search(fname):
        findings.append(Finding(
            "BAD_FILENAME", ERROR,
            "ファイル名に日本語を使わない: %s" % fname, "§3.7"))
    if " " in fname:
        findings.append(Finding(
            "BAD_FILENAME", ERROR,
            "ファイル名に空白を使わない: %s" % fname, "§3.7"))
    if _VERSION_SUFFIX_RE.search(fname):
        findings.append(Finding(
            "BAD_FILENAME", ERROR,
            "ファイル名に版番号を埋め込まない: %s" % fname, "§3.7"))

    # _system singletons are positional, not id-derived -> skip id<->filename.
    if rel_parts is not None and _is_system_singleton(rel_parts):
        return
    # ICD is the literal file ICD.md (filename does not encode the id serial).
    if meta.get("type") == "ICD" and fname == "ICD.md":
        return

    doc_id = meta.get("id")
    if not isinstance(doc_id, str) or doc_id.strip() == "":
        return  # missing id already flagged as MISSING_KEY
    doc_id = doc_id.strip()
    if stem == doc_id or stem.startswith(doc_id + "-"):
        return
    findings.append(Finding(
        "ID_FILENAME_MISMATCH", ERROR,
        "id『%s』はファイル名語幹『%s』と一致しない(語幹は id で始める)。"
        % (doc_id, stem), "§3.4/§3.7"))


def _check_stray_location(meta, rel_parts, findings):
    """STRAY_DOCUMENT (ERROR) — ADR-021: 登録簿の型を持つ文書が docs/ の外。

    体系の文書を名乗る(既知の型を持つ) .md が docs/ の木の外に書かれたら、
    その場で置き場所を正させる。型なしの .md は対象にしない(README 等の
    非文書は external-md-intake の分類に委ねる)。
    """
    if rel_parts is not None:
        return  # docs/ の木の中 → 置き場所は _check_type_location が見る。
    type_code = meta.get("type")
    if isinstance(type_code, str) and _registry.is_known_type(type_code):
        findings.append(Finding(
            "STRAY_DOCUMENT", ERROR,
            "登録簿の型 %s を持つ文書が統治木の外に在る。doc-author で "
            "統治木の <domain>/ 配下へ移すか、型を外す。" % type_code,
            "ADR-021"))


def _check_type_location(meta, path, rel_parts, findings):
    """§3.4 TYPE_LOCATION_MISMATCH + DOMAIN_PATH_MISMATCH (ERROR).

    ADR-027: status『archived』の文書は、型に依らず <domain>/archive/ に置く
    (§3.8 の倉庫への退避)。archived ではこの規則が型の置き場所規則より優先する。
    """
    type_code = meta.get("type")
    if not _registry.is_known_type(type_code):
        return
    if rel_parts is None or len(rel_parts) < 1:
        return  # cannot locate a docs root -> cannot judge location
    fname = rel_parts[-1]
    dir_parts = rel_parts[:-1]              # directory segments under docs/

    status = meta.get("status")
    if isinstance(status, str) and status.strip() == "archived":
        if not _location_matches(dir_parts, _registry.ARCHIVED_LOCATION):
            findings.append(Finding(
                "ARCHIVED_LOCATION_MISMATCH", ERROR,
                "status『archived』の文書は <domain>/archive/ に置く(現在: %s/)。"
                % ("/".join(dir_parts) or "."), "§3.8/ADR-027"))
            return
        _check_domain_path(meta, dir_parts, type_code, findings)
        return

    # ICD: must be the literal file ICD.md at <domain>/ root.
    if type_code == "ICD":
        if fname != "ICD.md" or len(dir_parts) != 1 or dir_parts[0] == "_system":
            findings.append(Finding(
                "TYPE_LOCATION_MISMATCH", ERROR,
                "ICD は <domain>/ICD.md に置く(現在: %s)。" % "/".join(rel_parts),
                "§3.2/§3.7"))
        else:
            _check_domain_path(meta, dir_parts, type_code, findings)
        return

    patterns = _registry.allowed_locations(type_code)
    if not _location_matches(dir_parts, patterns):
        findings.append(Finding(
            "TYPE_LOCATION_MISMATCH", ERROR,
            "型 %s は %s に置く(現在: %s/)。"
            % (type_code, " または ".join(patterns), "/".join(dir_parts) or "."),
            "§3.2"))
        return
    _check_domain_path(meta, dir_parts, type_code, findings)


def _location_matches(dir_parts, patterns):
    """True iff dir_parts (segments under docs/) matches any pattern.

    A pattern is a list-of-segments string with '<domain>' as a wildcard for one
    segment and '_system/' as the literal _system tier. '<domain>/spec/' means
    exactly [<any>, 'spec']; '_system/' means exactly ['_system'].
    """
    for pat in patterns:
        segs = [s for s in pat.split("/") if s != ""]
        if len(segs) != len(dir_parts):
            continue
        ok = True
        for want, got in zip(segs, dir_parts):
            if want == "<domain>":
                if got == "_system" or got == "":
                    ok = False
                    break
            elif want != got:
                ok = False
                break
        if ok:
            return True
    return False


def _check_domain_path(meta, dir_parts, type_code, findings):
    """DOMAIN_PATH_MISMATCH (ERROR): the path's <domain> segment must equal
    meta.domain (or _system for system-tier types)."""
    declared = meta.get("domain")
    if not isinstance(declared, str) or declared.strip() == "":
        return  # missing/empty domain already flagged as MISSING_KEY/EMPTY_KEY
    declared = declared.strip()
    if not dir_parts:
        return
    path_domain = dir_parts[0]
    if path_domain == declared:
        return
    # System-tier types legitimately live under _system with domain '_system'.
    if path_domain == "_system" and declared == "_system":
        return
    findings.append(Finding(
        "DOMAIN_PATH_MISMATCH", ERROR,
        "frontmatter の domain『%s』が置き場所の区画『%s』と一致しない。"
        % (declared, path_domain), "§3.4/§3.7"))


def _check_llm_context(meta, findings):
    """§3.5 BAD_LLM_CONTEXT (ERROR on bad value; WARN on default-override)."""
    if "llm_context" not in meta:
        return  # absent -> registry default applies, no finding
    value = meta.get("llm_context")
    if not isinstance(value, str) or value.strip() == "":
        return  # empty -> treat as absent (default applies)
    value = value.strip()
    if value not in _registry.LLM_CONTEXT_VALUES:
        findings.append(Finding(
            "BAD_LLM_CONTEXT", ERROR,
            "llm_context『%s』は {always, task, never} のいずれかにする。" % value,
            "§3.4"))
        return
    type_code = meta.get("type")
    default = _registry.default_llm_context(type_code)
    if default is not None and value != default:
        findings.append(Finding(
            "BAD_LLM_CONTEXT", WARN,
            "llm_context『%s』は型 %s の既定『%s』を上書きしている(意図的なら可)。"
            % (value, type_code, default), "§3.2"))


# 日付の鍵と、解せないときの重さ(ADR-100)。updated が読めないと鮮度の判定が全部
# 倒れるので誤り。created は機械の判定に使われないので警告(必須キーではない)。
# **この配分は見立てであり、測って出した数ではない。**
_DATE_KEYS = (("updated", ERROR), ("review_by", ERROR), ("created", WARN))


def _check_dates(meta, findings):
    """§3.4 BAD_DATE — 日付の鍵が解せない(ADR-100)。

    日付の解釈は共有コア `_frontmatter.parse_date` が正本(ADR-099)。ここは
    「解せなかったときに何と言うか」だけを受け持つ。不在は必須キーの検査の領分。
    """
    for key, severity in _DATE_KEYS:
        raw = meta.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str) or raw.strip() == "":
            continue          # 空は必須キーの検査が見る。
        if _frontmatter.parse_date(raw) is not None:
            continue
        findings.append(Finding(
            "BAD_DATE", severity,
            "%s が日付として解せない(『%s』)。YYYY-MM-DD の実在する日付を書く。"
            % (key, raw), "§3.4"))


def _check_placeholder(meta, findings):
    """§3.4 PLACEHOLDER_VALUE (ERROR) — 雛形の指示文が残っている(ADR-098)。

    判定は共有コア `_frontmatter.placeholder_fields` に一度だけ在り、全件監査も
    同じコアを呼ぶ(答えが割れない)。本文は見ない —— 正当な山括弧が出るからである。
    """
    for key, value in _frontmatter.placeholder_fields(meta):
        findings.append(Finding(
            "PLACEHOLDER_VALUE", ERROR,
            "%s が雛形の指示文のままである(『%s』)。値を書く。" % (key, value),
            "§3.4"))


def _check_subdomain(meta, findings):
    """§3.5 BAD_SUBDOMAIN (ERROR on bad value) — ADR-092.

    省略・空は「未分類」であり所見を出さない(既存の木で所見が増えないこと)。
    既定値は無いので、llm_context のような「既定の上書き」の WARN も持たない。
    """
    if "subdomain" not in meta:
        return  # absent -> unclassified, no finding
    value = meta.get("subdomain")
    if not isinstance(value, str) or value.strip() == "":
        return  # empty -> treat as absent (unclassified)
    value = value.strip()
    if value not in _registry.SUBDOMAIN_KINDS:
        findings.append(Finding(
            "BAD_SUBDOMAIN", ERROR,
            "subdomain『%s』は {core, supporting, generic} のいずれかにする。" % value,
            "§3.4"))


# Markdown heading whose text mentions 決定.
# 行内の空白だけを見る(ADR-075)。\s は改行を跨ぐため `.*` と組んで二次の
# バックトラックを生み、同一行に空白 20 万字を置くと 14 秒かかった。
# 『決定』を延ばして別語にする接尾は除く(ADR-082)。『決定的な一点』のような見出しは
# 決定を書いたものではない。否定の先読みは後戻りを増やさないので、上の性能の実測
# (長い空白行で 14 秒)を悪くしない。二語だけに限る —— 『決定木』は引き続き咎める。
_DECISION_HEADING_RE = re.compile(r"(?m)^#{1,6}[ \t]*.*決定(?![的論])")


def _check_research_decision(meta, body, findings):
    """§3.6 RESEARCH_HAS_DECISION (WARN) — RESEARCH must not hold a 決定 heading."""
    if meta.get("type") != "RESEARCH":
        return
    if _DECISION_HEADING_RE.search(body or ""):
        findings.append(Finding(
            "RESEARCH_HAS_DECISION", WARN,
            "RESEARCH に『決定』見出しがある。決定は ADR に移す。", "§3.2/§4.2"))


# 型ごとの必須節の正本は登録簿が持つ(確定事実1。ADR-090)。ここには持たない ——
# 以前は SPEC の四節だけがこのファイルに在り、他の型は雛形が定めるのに誰も検めて
# いなかった。
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s*(.*?)\s*$")


# doctrine:begin SPEC-007
def _check_spec_sections(meta, body, findings):
    """§3.7 MISSING_SECTION / EMPTY_SECTION (ERROR)。全型を検める(ADR-090)。

    節の一覧は `_registry.required_sections(type)` から取る。課さない型
    (RESEARCH・投影)では空が返り、何も検めない。
    """
    sections = _registry.required_sections(meta.get("type"))
    if not sections:
        return
    raw_type = meta.get("type")
    type_code = raw_type.strip().upper() if isinstance(raw_type, str) else ""
    headings = list(_HEADING_RE.finditer(body or ""))
    # Map each required token to the heading match that contains it (first one).
    for token in sections:
        match_idx = None
        for i, h in enumerate(headings):
            if token in h.group(2):
                match_idx = i
                break
        if match_idx is None:
            findings.append(Finding(
                "MISSING_SECTION", ERROR,
                "%s の必須節『%s』が無い。" % (type_code, token), "§3.2/§4.2"))
            continue
        # 節の中身は、同レベル以下の次の見出しまで(ADR-075)。以前は階層を見ず
        # 「次の見出し」で切っていたため、`## 入出力` の直後に `### 受け取る値`
        # を置くと中身が空と読まれ、正しい文書が EMPTY_SECTION(ERROR)で
        # 落ちて --batch が exit 1 になった。
        start = headings[match_idx].end()
        level = len(headings[match_idx].group(1))
        end = len(body or "")
        for nxt in headings[match_idx + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        section = (body or "")[start:end]
        if _section_is_empty(section):
            findings.append(Finding(
                "EMPTY_SECTION", ERROR,
                "%s の必須節『%s』が空。" % (type_code, token), "§4.2"))
# doctrine:end SPEC-007


def _section_is_empty(section):
    """True iff a section body has no non-whitespace, non-comment content."""
    # Strip HTML comments, then whitespace.
    stripped = re.sub(r"<!--.*?-->", "", section, flags=re.S)
    return stripped.strip() == ""


def _check_term_check(meta, body, path, findings, text=None):
    """§3.8 delegate to _termcheck.check. Codes pass through verbatim.

    The spec-mandated SPEC/API compounds that contain a banned synonym
    (『入出力』⊃『出力』, 『現在形』⊃『現在』) are masked inside the shared core
    (_termcheck._mask_approved_compounds), so EVERY caller (this linter, the
    term-check CLI, doc-review) benefits — no linter-only neutralization here.

    行番号はファイルの行へ換算する(ADR-083)。換算に要る本文の開始行は共有の
    `_frontmatter.body_start_line` から取り、ここで数えない —— 呼び手は二つ
    (このリンタと term-check の CLI)あり、別々に数えれば片方だけ直したときに
    同じファイルへ別の行を言う状態が生まれる。
    """
    docs_root = _docs_root_of(path)
    start = _frontmatter.body_start_line(text, body) if text is not None else 1
    try:
        glossary = _termcheck.load_glossary(docs_root)
        tfindings = _termcheck.check(body, meta, glossary, start)
    except Exception:  # never break the hook chain on a term-check error
        return
    for tf in tfindings:
        findings.append(Finding(tf.code, tf.severity, tf.message, "§1"))


# A requirement tag like [R3] anywhere in body or a value.
_REQ_TAG_RE = re.compile(r"\[R\d+\]")
_REQ_ID_RE = re.compile(r"\bREQ-\d+\b")


def _check_model(meta, body, findings):
    """MODEL の本文の構造(ADR-163 決定7)。規則の実体は共有コア `_model` が持つ。

    JSON の側が要する構造を .md の側で機械的に担保する口である。**兄弟文書は
    読まない** —— 検めるのはこの一文書の中だけで、参照の実在も文書の中に限る。
    意味の正しさは検めない(出所の実在は map-draft-check、確定は人)。
    """
    if meta.get("type") != "MODEL":
        return
    status = meta.get("status") or _registry.default_status("MODEL")
    body = body or ""
    repos = meta.get("repos")
    if repos is not None:
        repos = _frontmatter.as_list(repos)
    for finding in _model.check_document(body, status, repos):
        where = finding.where
        if finding.line:
            where = "%s(行 %d)" % (where, finding.line)
        findings.append(Finding(
            finding.code,
            ERROR if finding.severity == "ERROR" else WARN,
            "%s: %s" % (where, finding.message),
            "ADR-163"))
    _check_model_prose(meta, body, findings)


def _check_model_prose(meta, body, findings):
    """MODEL の塊の中の散文へ、用語の門を届かせる(ADR-164)。

    用語チェッカーは囲みの中を丸ごと覆う(`_termcheck.mask_body`)。MODEL は値の
    ほとんどが囲みの中に在るので、そのままでは**この型にだけ門が効かない**。
    掛けるのは散文の欄の値だけとし(`_model.PROSE_FIELDS`)、id・種別・パス・日付の
    ような機械の値には掛けない。段は用語チェッカーの返すものをそのまま使う。
    """
    model, _errs = _model.parse_model(body)
    values = _model.prose_values(model)
    if not values:
        return
    try:
        docs_root = _registry.walkup_docs_root(os.getcwd())
        glossary = _termcheck.load_glossary(docs_root)
    except Exception:                                     # pragma: no cover
        return
    for where, line, text in values:
        for f in _termcheck.check(text, meta, glossary):
            findings.append(Finding(
                f.code, ERROR if f.severity == "ERROR" else WARN,
                "%s(行 %d): %s" % (where, line, f.message), "§1"))


def _check_trace(meta, body, findings):
    """§3.10 MISSING_TRACE (ERROR) — SPEC/IMPL/TEST needs [R]/REQ/depends_on."""
    type_code = meta.get("type")
    if type_code not in ("SPEC", "IMPL", "TEST"):
        return
    depends_on = _frontmatter.as_list(meta.get("depends_on"))
    if depends_on:
        return
    body = body or ""
    if _REQ_TAG_RE.search(body):
        return
    if _REQ_ID_RE.search(body):
        return
    # A REQ id may also ride in any frontmatter scalar/list value.
    for v in meta.values():
        for s in _frontmatter.as_list(v):
            if _REQ_ID_RE.search(s):
                return
    findings.append(Finding(
        "MISSING_TRACE", ERROR,
        "%s は要求への追跡を持たねばならない。本文に [R番号] を書くか、depends_on に "
        "REQ の id を載せる(title の [R番号] は数えない。本文か depends_on に置く)。"
        % type_code,
        "§4.2/§6"))


def _check_frontmatter_syntax(errs, findings):
    """§3.4 FRONTMATTER_SYNTAX (ERROR)。解析器が返した構文の誤りを表に出す。

    parse は三要素 (frontmatter, body, errors) を返すが(DECIDED-001 事実2)、
    errors を読む消費者がどこにも無く、構文の誤りが全ての門を素通りしていた。
    実害: `sources: [Issue #60]` は流フローの閉じ ']' を欠いて `['Issue']` に
    化け、値を静かに失ったまま監査もリンタも 0 件を報告した(ADR-075)。

    黙って値を捨てる誤りだけを挙げる。行と鍵を添えて、直す場所を一意にする。
    """
    if not errs:
        return
    seen = set()
    for e in errs:
        if not isinstance(e, dict):
            continue
        code = e.get("code")
        key = e.get("key")
        sig = (code, key)
        if sig in seen:
            continue
        seen.add(sig)
        where = "鍵『%s』" % key if key else "フロントマター"
        line = e.get("line")
        at = "(%d 行目)" % line if isinstance(line, int) else ""
        findings.append(Finding(
            "FRONTMATTER_SYNTAX", ERROR,
            "%s%s の構文が読めない: %s。値が黙って落ちる。"
            % (where, at, e.get("detail") or code),
            "§3.4"))


def _check_icd_dep(meta, path, findings):
    """§3.9 ICD_DEP_VIOLATION (advisory ERROR) / ICD_DEP_UNVERIFIED (WARN).

    Best-effort, single-doc: resolve each depends_on target's DOMAIN from the
    target's *path* — never by reading sibling documents (ADR-075).

    以前はここで依存グラフを丸ごと組んでいた。per-turn の Hook は編集された一つの
    文書だけを点検する(NONGOAL 第5項・仕様 §4.2)という約束に反し、`depends_on` を
    持つ文書を編集するたび木の全文書を読んで解析していた(実測 O(N): 木 8000 文書で
    リンタ 0.53 秒、`depends_on` 無しなら 0.14 秒で平坦)。

    ドメインは置き場所そのものが持つ(<docs_root>/<domain>/…、§3.7)。id は
    ファイル名の接頭辞である(§3.4)。よって「その id で始まるファイルを名前で探す」
    だけで解け、本文もフロントマターも読まなくてよい。解けなければ従来どおり
    UNVERIFIED(WARN)へ落ちる — 権威は事前のガードと事後の監査にある。
    """
    depends_on = _frontmatter.as_list(meta.get("depends_on"))
    if not depends_on:
        return
    self_domain = meta.get("domain")
    if not isinstance(self_domain, str) or self_domain.strip() == "":
        return
    self_domain = self_domain.strip()

    docs_root = _docs_root_of(path)
    for dep in depends_on:
        dep_type = _registry.type_of(dep)
        # 登録簿だけで ICD と判る依存は、木を触らずに合格(§3.6)。
        if dep_type == "ICD":
            continue
        dep_domain = _domain_of_dep(docs_root, dep)
        if not dep_domain:
            findings.append(Finding(
                "ICD_DEP_UNVERIFIED", WARN,
                "依存先『%s』のドメインを解決できない。別ドメインなら ICD 宛にする。"
                " 監査が確認する。" % dep, "§3.6/§4.2"))
            continue
        if dep_domain != self_domain:
            findings.append(Finding(
                "ICD_DEP_VIOLATION", ERROR,
                "%s は %s の内部です。%s の ICD 宛にしてください。"
                % (dep, dep_domain, dep_domain), "§3.6/§4.2"))


def _domain_of_dep(docs_root, dep_id):
    """依存先 id のドメインを、置き場所の名前だけから解く。無ければ None。

    §3.7 の配置は <docs_root>/<domain>/[<layer>/]<id>-<slug>.md であり、
    ドメインは docs_root 直下の一階層目そのものである。§3.4 は id とファイル名の
    一致を課すので、ファイル名の接頭辞で目当ての一件を選べる。

    決して開かない・読まない・解析しない(ADR-075)。走るのはディレクトリ項目の
    列挙だけで、per-turn の費用は木の文書数ではなくドメイン数に比例する。
    複数のドメインに同じ id が現れたら曖昧なので None を返し、UNVERIFIED へ落とす
    (どちらが正かは監査の canonical_conflict と shadowed_document が判じる)。
    """
    if not docs_root or not isinstance(dep_id, str) or not dep_id.strip():
        return None
    dep_id = dep_id.strip()
    if os.sep in dep_id or "/" in dep_id or dep_id.startswith("."):
        return None                      # id にパスを書かせない(走査の外へ出さない)。
    found = set()
    try:
        domains = [e for e in os.scandir(docs_root) if e.is_dir()
                   and not e.name.startswith(".")]
    except OSError:
        return None
    for dom in domains:
        for base, _dirs, names in os.walk(dom.path):
            hit = any(n.startswith(dep_id + "-") and n.endswith(".md")
                      for n in names)
            if hit or (dep_id.startswith("ICD-") and "ICD.md" in names):
                found.add(dom.name)
                break
        if len(found) > 1:
            return None                  # 曖昧(影文書)。監査に委ねる。
    if len(found) != 1:
        return None
    return found.pop()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def lint_text(text, path):
    """Run all checks over a parsed document. Returns list[Finding].

    ADR-024: 判定の前に統治木を探す。①統治木が無ければ(体系外)何も出さない。
    ②型付きは従来どおり全点検(統治木外なら STRAY)。③型なしで intake に
    「非文書/投影/ビュー」と登録されたファイルは schema 強制を飛ばし、用語助言
    だけを WARN で残す(「ビュー」は刻印の欠落の助言 VIEW_MISSING_STAMP も出す。
    ADR-073)。④それ以外は従来どおり。intake の読み取りは監査と同じ共有コア
    (_intake)を使い、同じファイルへの分類が食い違わないようにする。
    """
    findings = []

    # ⓪ 統治の走査から外す範囲(ADR-075)。根の案内(CLAUDE.md/AGENTS.md)と
    # dot ディレクトリ配下は、監査が明示的に免除しているのにリンタだけが知らず、
    # 従うと ADR-029 に反する要求(CLAUDE.md にフロントマターを付ける、
    # スラッシュコマンド定義を壊す)を出し続けていた。判定は _registry に一本化。
    if _registry.is_outside_governance(path):
        return findings

    # ① 統治木の外(体系外)。doctrine は統治しない。何も出さない。
    docs_root = _docs_root_of(path)
    if docs_root is None:
        return findings

    meta, body, errs = _frontmatter.parse(text)
    type_code = meta.get("type") if meta else None
    typed = isinstance(type_code, str) and _registry.is_known_type(type_code)

    # ③ 型なしで intake に「非文書/投影/ビュー」と登録 → schema 強制せず
    # 用語助言のみ。「ビュー」は刻印の欠落も助言する(ADR-073)。
    # 型付きは統治木外で STRAY を出したいので、この分岐に入れない(②)。
    if not typed:
        disp = _intake.disposition_for(path, docs_root)
        if disp in ("非文書", "投影", "ビュー"):
            _check_term_check(meta or {}, body, path, findings, text)
            for f in findings:
                if f.severity == ERROR:
                    f.severity = WARN
            if disp == "ビュー":
                stamp, err = _intake.parse_view_stamp(text)
                if stamp is None or err is not None:
                    findings.append(Finding(
                        "VIEW_MISSING_STAMP", WARN,
                        "ビューに刻印が無い、または読めない(%s)。ファイル内に "
                        "<!-- doctrine:view src=<出所> as-of=<版> "
                        "date=YYYY-MM-DD refs=<id,…> --> の一行を打つ"
                        "(書式の正本は ICD-005)。" % (err or "刻印の行なし"),
                        "ADR-073"))
            return findings

    # ④ 従来フロー(型付き、または型なし・未登録)。
    # Missing/empty frontmatter: emit one MISSING_FRONTMATTER and stop (every
    # other check needs `type`). §1.4.
    if not meta:
        findings.append(Finding(
            "MISSING_FRONTMATTER", ERROR,
            "フロントマターが無い、または読み取れない。", "§3.4"))
        return findings

    rel_parts = _rel_under_docs(path)

    _check_frontmatter_syntax(errs, findings)
    _check_required_keys(meta, findings)
    _check_type_known(meta, findings)
    _check_status(meta, findings)
    _check_id_filename(meta, path, rel_parts, findings)
    _check_stray_location(meta, rel_parts, findings)
    _check_type_location(meta, path, rel_parts, findings)
    _check_llm_context(meta, findings)
    _check_subdomain(meta, findings)
    _check_placeholder(meta, findings)
    _check_dates(meta, findings)
    _check_research_decision(meta, body, findings)
    _check_spec_sections(meta, body, findings)
    _check_model(meta, body, findings)
    _check_term_check(meta, body, path, findings, text)
    _check_icd_dep(meta, path, findings)
    _check_trace(meta, body, findings)
    return findings


def render_additional_context(path, findings):
    """Render findings into the §2.2 human-readable advisory block.

    path と message は注入境界のサニタイザを通す(ADR-040 の射程拡張。ADR-075)。
    どちらも攻撃者制御になりうる: ファイル名に改行を仕込めば本物と同じ書式の偽
    所見行を捏造でき、フロントマターの値は逐語で埋め込まれる。ADR-040 の決定は
    inject-contract と gov-heartbeat を名指ししていたため、同じ境界を持つ
    リンタだけが素通しだった。
    """
    lines = ["Self-correct the following before continuing.",
             "docs-linter: %s" % _frontmatter.sanitize_inline(path, 300)]
    for f in findings:
        lines.append("  [%s] %s: %s  (%s)"
                     % (f.severity, f.code,
                        _frontmatter.sanitize_inline(f.message, 300),
                        f.spec_ref))
    return "\n".join(lines)


def build_response(path, findings):
    """Build the §3.3 advisory JSON, or None for no findings (empty stdout)."""
    if not findings:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": render_additional_context(path, findings),
        }
    }


def _resolve_tree(root):
    """--batch の root から統治木を解決する(ADR-022)。無ければ None。"""
    if _registry.is_doctrine_tree(root):
        return root
    return _registry.locate_docs_root(root)


_BATCH_USAGE = ("docs-linter.py --batch [ROOT]\n"
                "  ROOT は統治木、またはそれを含むプロジェクトの場所(既定: .)\n")


def _parse_batch_args(rest):
    """--batch の後ろを (root, error) に解く。旗を場所として飲まない(ADR-110)。

    兄弟の門(全件監査・追跡の索引・依存グラフ・語の抽出)は、知らない旗を終了コード
    2 で拒む。この門だけが規約の外に在り、旗を場所として飲んで 0 を返していた
    —— 綴り違いで門が静かに無効になる(利用者側で実際に起きた)。
    """
    rest = list(rest)
    for word in rest:
        if word.startswith("-"):
            return None, "不明な引数: %s" % word
    if len(rest) > 1:
        return None, "余分な引数: %s" % " ".join(rest[1:])
    if not rest:
        return ".", None
    return rest[0], None


def _run_batch(root):
    """統治木の全 .md を点検し、ERROR があれば終了コード 1(#91)。

    per-file の lint_text をそのまま各文書に当てる(規則の二重定義をしない)。
    ERROR を stderr でなく stdout に一覧し、件数を末尾に出す。

    終了コードは 0(ERROR なし)・1(ERROR あり)・3(場所が実在しない。ADR-110)。
    実在するが統治木でない場所は 0 のまま —— 素の docs/ を持つ導入先を CI で
    誤って落とさないための配慮であり、そこだけを指している。**点検した文書の数を
    必ず出す**(見ていない門を緑と読む余地を減らす。ADR-110)。
    """
    if not os.path.exists(root):
        sys.stdout.write("docs-linter --batch: 場所が実在しない(%s)。\n" % root)
        return 3
    tree = _resolve_tree(root)
    if not tree or not os.path.isdir(tree):
        sys.stdout.write("docs-linter --batch: 統治木が無い(%s)。点検 0 文書。\n"
                         % root)
        return 0
    scanned = 0
    error_docs = 0
    error_count = 0
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames.sort()
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = _frontmatter.read_text(path)
            except Exception:
                continue
            scanned += 1
            findings = [f for f in lint_text(text, path) if f.severity == ERROR]
            if findings:
                error_docs += 1
                rel = os.path.relpath(path, tree)
                for f in findings:
                    error_count += 1
                    sys.stdout.write("[ERROR] %s: %s (%s)\n"
                                     % (rel, f.message, f.code))
    if error_count:
        sys.stdout.write("docs-linter --batch: %d 文書を点検し、%d 文書に %d 件の"
                         " ERROR。\n" % (scanned, error_docs, error_count))
        return 1
    sys.stdout.write("docs-linter --batch: %d 文書を点検し、ERROR なし。\n"
                     % scanned)
    return 0


def main(argv=None):
    """Entry point (PostToolUse). Advisory only. Exit ALWAYS 0.

    NEVER emits a 'decision' key. On any internal error, emits an advisory note
    and exits 0 — a crashing PostToolUse hook must not break the agent (§4.2).
    """
    _hookio.harden_stdout()
    if argv is None:
        argv = sys.argv[1:]

    # CI 用バッチモード(#91): 統治木の全 .md を一括点検し、ERROR があれば終了
    # コード 1 を返す。per-file の点検ロジック(lint_text)をそのまま再利用するので、
    # 規則の正本は一つ(_registry)のまま。フックを迂回した経路(GitHub Web UI・
    # 別エージェント・一括スクリプト)で入った不正文書を、マージ前に止められる。
    if argv and argv[0] == "--batch":
        root, err = _parse_batch_args(argv[1:])
        if err:
            sys.stdout.write("usage error: %s\n%s" % (err, _BATCH_USAGE))
            return 2
        return _run_batch(root)

    stdin_text = ""
    try:
        stdin_text = sys.stdin.read()
    except Exception:
        stdin_text = ""

    # 発火の印(ADR-062)。PostToolUse の経路のときだけ残す(ADR-075)。
    # 事象を見ずに書いていたため、CLI から保守で走らせるだけで印が立ち、
    # 対の PreToolUse が無いことを監査が「拒否経路の欠落」と読んで
    # 偽の advisory を上げていた。対のガードは同じ門を持っている。
    # 最善努力であり、失敗しても本務(点検)を妨げない。
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
    except (ValueError, TypeError):
        payload = {}
    if isinstance(payload, dict) and payload.get("hook_event_name") == "PostToolUse":
        try:
            import _auditcache
            _auditcache.write_stamp("hook_docs_linter")
        except Exception:
            pass

    try:
        path = resolve_path(stdin_text, argv)
        if not path:
            return 0
        if not in_scope(path):
            return 0
        # Deleted file (no longer on disk): emit nothing.
        if not os.path.isfile(path):
            return 0

        text = _frontmatter.read_text(path)
        findings = lint_text(text, path)
        response = build_response(path, findings)
        if response is not None:
            _hookio.emit(response, component="docs-linter")
    except Exception as exc:  # never raise out of a PostToolUse hook
        try:
            import _auditcache
            _auditcache.record_error("docs-linter", exc)
        except Exception:
            pass
        try:
            note = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext":
                        "docs-linter: internal error: %r; skipped checks" % (exc,),
                }
            }
            _hookio.emit(note, component="docs-linter")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
