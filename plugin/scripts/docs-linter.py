#!/usr/bin/env python3
"""単一文書のリンタ(PostToolUse, 助言のみ). 仕様 §4.2 / MASTER §5.1 を実装する。

保証限界:
- 予防: 何も予防しない。決して decision/permissionDecision/deny を出さない。
  違反は additionalContext で指摘し、Claude に自己修正させる(§4.2)。
- 検出: 編集された一つの文書だけを点検する。必須キー・status・id↔ファイル名・
  型↔置き場所・llm_context・SPEC 4節・用語・前向き追跡性・ICD依存(事後検出)を出す。
- 委ねる: 全件走査(参照整合・孤児・逆孤児・正本衝突・投影ドリフト・review_by超過)は
  監査に委ねる。拒否(不変・削除安全・ICD依存の事前拒否)はガードに委ねる。
  ドメイン解決(IDだけでは決まらない, §3.4)は dep-graph(_depgraph)に委ねる。

入力は PostToolUse の Hook JSON(stdin)。出力は §3.3 の助言 JSON か空。終了コードは常に 0。
標準ライブラリのみ。pip も通信も使わない。一つのファイルだけを読む(全件走査しない)。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter
import _registry
import _termcheck

try:  # _depgraph is a Level-3 core; degrade gracefully if unavailable.
    import _depgraph
except Exception:  # pragma: no cover - defensive; never break the hook chain.
    _depgraph = None


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
    """True iff the linter should examine this path.

    Skip non-.md. Skip files not under a docs/ tree AND not under a .claude/
    docs tree, UNLESS the layout is undecidable (then lint anyway — fail-open
    toward checking, §1.3). A deleted file (absent on disk) is handled by the
    caller (emit nothing).
    """
    if not path.endswith(".md"):
        return False
    parts = _split_parts(path)
    # A docs tree is signalled by a 'docs' ancestor or a '_system' segment.
    if "docs" in parts or "_system" in parts:
        return True
    if ".claude" in parts:
        return True
    # Undecidable: lint anyway (a typed doc outside docs/ is likely a doc).
    return True


def _docs_root_of(path):
    """Nearest ancestor 'docs' directory of `path` (for glossary lookup), or None."""
    cur = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.basename(cur) == "docs":
            return cur
        cand = os.path.join(cur, "docs")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _rel_under_docs(path):
    """Path parts relative to the nearest 'docs'/'_system'-rooted tree.

    Returns the list of segments AFTER the docs root (the directory layout the
    §3.2 置き場所 rules describe), or None if no docs root can be located. For
    '.../docs/billing/spec/SPEC-1-x.md' -> ['billing', 'spec', 'SPEC-1-x.md'].
    For '.../docs/_system/glossary.md' -> ['_system', 'glossary.md'].
    """
    parts = _split_parts(path)
    # Prefer the last 'docs' segment as the root.
    idx = None
    for i, p in enumerate(parts):
        if p == "docs":
            idx = i
    if idx is not None:
        return parts[idx + 1:]
    # No literal 'docs' ancestor: anchor on '_system' if present.
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
    for key in _registry.REQUIRED_KEYS_L2:
        if key not in meta:
            findings.append(Finding(
                "MISSING_KEY", ERROR,
                "必須キー『%s』が無い。" % key, "§3.4"))
            continue
        value = meta.get(key)
        if key == "sources":
            # Empty sources:[] is allowed (some docs have no external source).
            continue
        if _is_empty_value(value):
            findings.append(Finding(
                "EMPTY_KEY", ERROR,
                "必須キー『%s』が空。" % key, "§3.4"))
    # DECIDED/WATCH additionally require a non-empty review_by.
    if type_code in _registry.REQUIRED_REVIEW_BY_TYPES:
        if "review_by" not in meta:
            findings.append(Finding(
                "MISSING_KEY", ERROR,
                "必須キー『review_by』が無い(DECIDED/WATCH では必須)。", "§3.4"))
        elif _is_empty_value(meta.get("review_by")):
            findings.append(Finding(
                "EMPTY_KEY", ERROR,
                "必須キー『review_by』が空(DECIDED/WATCH では必須)。", "§3.4"))


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


def _check_type_location(meta, path, rel_parts, findings):
    """§3.4 TYPE_LOCATION_MISMATCH + DOMAIN_PATH_MISMATCH (ERROR)."""
    type_code = meta.get("type")
    if not _registry.is_known_type(type_code):
        return
    if rel_parts is None or len(rel_parts) < 1:
        return  # cannot locate a docs root -> cannot judge location
    fname = rel_parts[-1]
    dir_parts = rel_parts[:-1]              # directory segments under docs/

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


# Markdown heading whose text mentions 決定.
_DECISION_HEADING_RE = re.compile(r"(?m)^#{1,6}\s*.*決定")


def _check_research_decision(meta, body, findings):
    """§3.6 RESEARCH_HAS_DECISION (WARN) — RESEARCH must not hold a 決定 heading."""
    if meta.get("type") != "RESEARCH":
        return
    if _DECISION_HEADING_RE.search(body or ""):
        findings.append(Finding(
            "RESEARCH_HAS_DECISION", WARN,
            "RESEARCH に『決定』見出しがある。決定は ADR に移す。", "§3.2/§4.2"))


# The four mandatory SPEC headings (§3.2 / §4.2 / 付録B).
_SPEC_SECTIONS = ("入出力", "制約", "エラー時挙動", "受入基準")
_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s*(.*?)\s*$")


def _check_spec_sections(meta, body, findings):
    """§3.7 SPEC_MISSING_SECTION / SPEC_EMPTY_SECTION (ERROR)."""
    if meta.get("type") != "SPEC":
        return
    headings = list(_HEADING_RE.finditer(body or ""))
    # Map each required token to the heading match that contains it (first one).
    for token in _SPEC_SECTIONS:
        match_idx = None
        for i, h in enumerate(headings):
            if token in h.group(2):
                match_idx = i
                break
        if match_idx is None:
            findings.append(Finding(
                "SPEC_MISSING_SECTION", ERROR,
                "SPEC の必須節『%s』が無い。" % token, "§3.2/§4.2"))
            continue
        # Non-empty: content between this heading and the next heading (or EOF).
        start = headings[match_idx].end()
        end = (headings[match_idx + 1].start()
               if match_idx + 1 < len(headings) else len(body or ""))
        section = (body or "")[start:end]
        if _section_is_empty(section):
            findings.append(Finding(
                "SPEC_EMPTY_SECTION", ERROR,
                "SPEC の必須節『%s』が空。" % token, "§4.2"))


def _section_is_empty(section):
    """True iff a section body has no non-whitespace, non-comment content."""
    # Strip HTML comments, then whitespace.
    stripped = re.sub(r"<!--.*?-->", "", section, flags=re.S)
    return stripped.strip() == ""


def _check_term_check(meta, body, path, findings):
    """§3.8 delegate to _termcheck.check. Codes pass through verbatim.

    The spec-mandated SPEC/API compounds that contain a banned synonym
    (『入出力』⊃『出力』, 『現在形』⊃『現在』) are masked inside the shared core
    (_termcheck._mask_approved_compounds), so EVERY caller (this linter, the
    term-check CLI, doc-review) benefits — no linter-only neutralization here.
    """
    docs_root = _docs_root_of(path)
    try:
        glossary = _termcheck.load_glossary(docs_root)
        tfindings = _termcheck.check(body, meta, glossary)
    except Exception:  # never break the hook chain on a term-check error
        return
    for tf in tfindings:
        findings.append(Finding(tf.code, tf.severity, tf.message, "§1"))


# A requirement tag like [R3] anywhere in body or a value.
_REQ_TAG_RE = re.compile(r"\[R\d+\]")
_REQ_ID_RE = re.compile(r"\bREQ-\d+\b")


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
        "%s は要求([R番号]/REQ-id)か depends_on を持たねばならない。" % type_code,
        "§4.2/§6"))


def _check_icd_dep(meta, path, findings):
    """§3.9 ICD_DEP_VIOLATION (advisory ERROR) / ICD_DEP_UNVERIFIED (WARN).

    Best-effort, single-doc-from-the-graph: resolve each depends_on target's
    domain via _depgraph.resolve over the doc tree. When the target domain
    cannot be resolved (no graph, or target absent), degrade to UNVERIFIED WARN
    — the guard (pre-apply) and the audit (post-hoc) are the authoritative
    enforcers (§4.2/§7). The linter NEVER denies.
    """
    depends_on = _frontmatter.as_list(meta.get("depends_on"))
    if not depends_on:
        return
    self_domain = meta.get("domain")
    if not isinstance(self_domain, str) or self_domain.strip() == "":
        return
    self_domain = self_domain.strip()

    graph = _build_graph_for(path)
    for dep in depends_on:
        dep_type = _registry.type_of(dep)
        info = graph.resolve(dep) if graph is not None else None
        dep_domain = info["domain"] if info else None
        # Registry-resolvable type lets us treat an ICD target as always OK.
        if dep_type == "ICD" or (info and info.get("type") == "ICD"):
            continue
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


def _build_graph_for(path):
    """Build a dep-graph over the nearest docs/ root of `path`. None on failure.

    This is the ONE place the linter consults sibling frontmatter — purely to
    resolve a depends_on target's DOMAIN (§3.4: an id alone does not encode it).
    It reads frontmatter only (no bodies). Never raises.
    """
    if _depgraph is None:
        return None
    root = _docs_root_of(path)
    if not root:
        return None
    try:
        return _depgraph.build_graph(root)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def lint_text(text, path):
    """Run all checks over a parsed document. Returns list[Finding]."""
    findings = []
    meta, body, _errs = _frontmatter.parse(text)

    # Missing/empty frontmatter: emit one MISSING_FRONTMATTER and stop (every
    # other check needs `type`). §1.4.
    if not meta:
        findings.append(Finding(
            "MISSING_FRONTMATTER", ERROR,
            "フロントマターが無い、または読み取れない。", "§3.4"))
        return findings

    rel_parts = _rel_under_docs(path)

    _check_required_keys(meta, findings)
    _check_type_known(meta, findings)
    _check_status(meta, findings)
    _check_id_filename(meta, path, rel_parts, findings)
    _check_type_location(meta, path, rel_parts, findings)
    _check_llm_context(meta, findings)
    _check_research_decision(meta, body, findings)
    _check_spec_sections(meta, body, findings)
    _check_term_check(meta, body, path, findings)
    _check_icd_dep(meta, path, findings)
    _check_trace(meta, body, findings)
    return findings


def render_additional_context(path, findings):
    """Render findings into the §2.2 human-readable advisory block."""
    lines = ["Self-correct the following before continuing.",
             "docs-linter: %s" % path]
    for f in findings:
        lines.append("  [%s] %s: %s  (%s)"
                     % (f.severity, f.code, f.message, f.spec_ref))
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


def main(argv=None):
    """Entry point (PostToolUse). Advisory only. Exit ALWAYS 0.

    NEVER emits a 'decision' key. On any internal error, emits an advisory note
    and exits 0 — a crashing PostToolUse hook must not break the agent (§4.2).
    """
    if argv is None:
        argv = sys.argv[1:]
    try:
        stdin_text = ""
        try:
            stdin_text = sys.stdin.read()
        except Exception:
            stdin_text = ""

        path = resolve_path(stdin_text, argv)
        if not path:
            return 0
        if not in_scope(path):
            return 0
        # Deleted file (no longer on disk): emit nothing.
        if not os.path.isfile(path):
            return 0

        text = _read_text(path)
        findings = lint_text(text, path)
        response = build_response(path, findings)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False))
    except Exception as exc:  # never raise out of a PostToolUse hook
        try:
            note = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext":
                        "docs-linter: internal error: %r; skipped checks" % (exc,),
                }
            }
            sys.stdout.write(json.dumps(note, ensure_ascii=False))
        except Exception:
            pass
    return 0


def _read_text(path):
    """Read a file as UTF-8 (utf-8-sig, newline='') — mirrors _frontmatter."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return fh.read()


if __name__ == "__main__":
    sys.exit(main())
