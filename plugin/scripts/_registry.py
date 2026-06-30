#!/usr/bin/env python3
"""Shared registry: the single in-code copy of spec §3.2/§3.3/§3.4.

保証限界:
- 予防: 規則(型・status・llm_context・必須キー・置き場所)をここに一度だけ定義し、
  他のスクリプトが二重定義するのを防ぐ(§3「コードに規則を二重定義しない」)。
- 検出: ここでは何も検出しない。純粋なデータと純粋な関数だけを提供する。
- 委ねる: 違反の検出と報告はリンタ・ガード・監査に委ねる。ドメイン解決は
  dep-graph(_depgraph.resolve)に委ねる。IDだけではドメインは決まらないため。

このモジュールは標準ライブラリだけを使う。pip も通信も使わない。決定的に動く。
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# §3.2 型登録簿 — 18 types, registry order (= spec table row order)
# ---------------------------------------------------------------------------

TYPES = (
    "ICD", "OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH",
    "REQ", "SPEC", "DATA", "API", "ADR", "CHANGE", "IMPACT", "IMPL", "TEST",
    "RESEARCH", "ARCHIVE",
)

# 既定status — one value per type (§3.2 「既定status」 column).
TYPE_DEFAULT_STATUS = {
    "ICD": "current",
    "OVERVIEW": "current",
    "GLOSSARY": "current",
    "CTXMAP": "current",
    "DECIDED": "current",
    "NONGOAL": "current",
    "WATCH": "current",
    "REQ": "current",
    "SPEC": "current",
    "DATA": "current",
    "API": "current",
    "ADR": "accepted",
    "CHANGE": "proposed",
    "IMPACT": "current",
    "IMPL": "current",
    "TEST": "current",
    "RESEARCH": "draft",
    "ARCHIVE": "archived",
}

# 既定 llm_context — always|task|never (§3.2 「llm_context」 column).
TYPE_DEFAULT_LLM_CONTEXT = {
    "ICD": "task",
    "OVERVIEW": "always",
    "GLOSSARY": "always",
    "CTXMAP": "task",
    "DECIDED": "always",
    "NONGOAL": "always",
    "WATCH": "always",
    "REQ": "task",
    "SPEC": "task",
    "DATA": "task",
    "API": "task",
    "ADR": "task",
    "CHANGE": "task",
    "IMPACT": "task",
    "IMPL": "task",
    "TEST": "task",
    "RESEARCH": "never",
    "ARCHIVE": "never",
}

# 置き場所 — allowed directories relative to docs/ (set of patterns).
# "<domain>" is a placeholder segment substituted with the doc's domain.
# WATCH is the only type with two allowed locations (§3.2).
TYPE_LOCATION = {
    "ICD": ["<domain>/"],            # file MUST be ICD.md
    "OVERVIEW": ["_system/"],
    "GLOSSARY": ["_system/"],
    "CTXMAP": ["_system/"],
    "DECIDED": ["_system/"],
    "NONGOAL": ["_system/"],
    "WATCH": ["_system/", "<domain>/test/"],   # two allowed (§3.2)
    "REQ": ["<domain>/"],
    "SPEC": ["<domain>/spec/"],
    "DATA": ["<domain>/spec/"],
    "API": ["<domain>/spec/"],
    "ADR": ["<domain>/decisions/"],
    "CHANGE": ["<domain>/decisions/"],
    "IMPACT": ["<domain>/decisions/"],
    "IMPL": ["<domain>/implementation/"],
    "TEST": ["<domain>/test/"],
    "RESEARCH": ["<domain>/research/"],
    "ARCHIVE": ["<domain>/archive/"],
}

# 投影 (projections) — rendered, "手で編集しない". ICD-index reuses type OVERVIEW (C8),
# so it is NOT a separate type here ("空の型を先に作らない", §3.2).
PROJECTION_TYPES = ("OVERVIEW", "CTXMAP")

# Types whose canonical instance lives in the _system tier (WATCH also lives
# under <domain>/test/, see TYPE_LOCATION).
SYSTEM_TIER_TYPES = ("OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH")

# Types that form the always-injected contract residue (§3.9 / inject-contract).
ALWAYS_CONTRACT_TYPES = ("DECIDED", "NONGOAL", "WATCH", "GLOSSARY")

# ---------------------------------------------------------------------------
# §3.3 status 統制語彙
# ---------------------------------------------------------------------------

# The seven §3.3 vocabulary values, plus 'draft' (C5: legal for RESEARCH only;
# audit "draft放置" keys on it). Registry order = §3.3 table row order, draft last.
ALL_STATUSES = (
    "proposed", "accepted", "current", "deprecated",
    "superseded", "archived", "open", "draft",
)

# 現行 (current) per §1 glossary = status in {current, accepted}. ADR 'accepted'
# 現行に相当 (§3.3). Other slices MUST use this, never a bare `== "current"`.
CURRENT_STATUSES = frozenset({"current", "accepted"})


def status_allowed(type_code):
    """Per-type allowed status set (§3.3 + C5).

    - ADR: exactly {proposed, accepted, superseded, deprecated}.
    - every other type: the six "accepted を除く" values
      {proposed, current, deprecated, superseded, archived, open}.
    - RESEARCH additionally allows 'draft' (C5 carve-out; its own default).

    'accepted' is therefore legal ONLY for ADR (R2). Returns a fresh set so
    callers may not mutate the registry. Unknown type -> empty set (caller's
    BAD_STATUS/UNKNOWN_TYPE finding is the linter's job; this stays pure).
    """
    if type_code == "ADR":
        return {"proposed", "accepted", "superseded", "deprecated"}
    if type_code not in TYPE_DEFAULT_STATUS:
        return set()
    base = {"proposed", "current", "deprecated", "superseded", "archived", "open"}
    if type_code == "RESEARCH":
        base = base | {"draft"}            # C5
    return base


def is_current(status):
    """True iff `status` counts as 現行 (§1 glossary: current/accepted)."""
    return status in CURRENT_STATUSES


# ---------------------------------------------------------------------------
# §3.4 メタデータ・スキーマ
# ---------------------------------------------------------------------------

# Linter-required keys at Level 2 and above (§3.4). Exactly these eight;
# 'created' is NOT required (C11) though templates still include it.
REQUIRED_KEYS_L2 = (
    "id", "title", "type", "domain", "status", "owner", "updated", "sources",
)

# DECIDED/WATCH additionally require `review_by` (古びの検出に使う, §3.4).
REQUIRED_REVIEW_BY_TYPES = ("DECIDED", "WATCH")

# Keys introduced at Level 3 (permitted/meaningful, NOT required) — §3.4/§4.4.
LEVEL3_KEYS = ("depends_on", "impacts", "review_by")

# Keys introduced at Level 4 (permitted/optional, NEVER required) — §3.4.
LEVEL4_KEYS = ("canonical_for",)

# Legal llm_context values (§3.4).
LLM_CONTEXT_VALUES = ("always", "task", "never")


def required_keys(level, type_code):
    """Required frontmatter keys for (level, type) per §3.4.

    Returns the base eight (REQUIRED_KEYS_L2), plus `review_by` for DECIDED/WATCH.
    `level` only gates which keys are PERMITTED (depends_on/impacts at L3+,
    canonical_for at L4+); the REQUIRED set does NOT grow with level except for
    review_by. `level` is accepted for API stability and is validated to be one
    of {2,3,4}; it does not currently change the result beyond that.

    Raises ValueError if level not in {2,3,4}.
    """
    if level not in (2, 3, 4):
        raise ValueError("level must be one of 2, 3, 4")
    keys = list(REQUIRED_KEYS_L2)
    if type_code in REQUIRED_REVIEW_BY_TYPES:
        keys.append("review_by")
    return tuple(keys)


# ---------------------------------------------------------------------------
# Fixed _system filenames (§3.7) — these carry frontmatter with an id of form
# <TYPE>-<NNN>, but their FILENAME is fixed and does NOT encode the id, so the
# linter skips id<->filename matching for them.
# ---------------------------------------------------------------------------

# 投影 (描画) files — rendered projections, fixed names (§3.9 / C8).
PROJECTION_FILES = frozenset({"overview.md", "icd-index.md", "context-map.md"})

# 正本 (canonical) + the overview projection seeded by scaffold.py (§3.7 / §5.8).
# watchlist.md is the spec-mandated fixed path for the WATCH 正本 (§3.7 layout):
# its filename does NOT encode the id (WATCH-N), so id<->filename matching must
# be skipped for it — but ONLY when it lives under _system/ (see linter's
# _is_system_singleton, which requires rel_parts[0] == "_system").
SYSTEM_CANONICAL_FILES = frozenset({
    "glossary.md", "decided-facts.md", "non-goals.md", "overview.md",
    "watchlist.md",
})

# ---------------------------------------------------------------------------
# Helper API (frozen — consumed by guard, linter, audit, dep-graph, context)
# ---------------------------------------------------------------------------

# An id is <TYPE>-<NNN>: an uppercase prefix, a hyphen, then one or more digits.
# Digit width is NOT fixed at 3 (§3.4 gives an example, not a width rule).
_ID_RE = re.compile(r"^([A-Z]+)-(\d+)$")


def type_of(doc_id):
    """Extract the TYPE prefix from an id (<TYPE>-<NNN>).

    Returns the type code if the id is well-formed AND the prefix is a known
    registry type. Returns None for a malformed id (no hyphen, no digits, empty,
    non-str) OR an unknown prefix (e.g. 'XYZ-1'). Examples:
        'SPEC-014' -> 'SPEC'
        'XYZ-1'    -> None   (unknown prefix)
        'SPEC'     -> None   (malformed: no -NNN)
        ''         -> None
    """
    if not isinstance(doc_id, str):
        return None
    m = _ID_RE.match(doc_id)
    if not m:
        return None
    prefix = m.group(1)
    return prefix if prefix in TYPE_DEFAULT_STATUS else None


def is_known_type(type_code):
    """True iff `type_code` is one of the 18 registry types."""
    return type_code in TYPE_DEFAULT_STATUS


def default_status(type_code):
    """Default status for a type (§3.2). None for an unknown type."""
    return TYPE_DEFAULT_STATUS.get(type_code)


def default_llm_context(type_code):
    """Default llm_context ('always'|'task'|'never') for a type (§3.2).
    None for an unknown type."""
    return TYPE_DEFAULT_LLM_CONTEXT.get(type_code)


def effective_llm_context(meta):
    """Resolve the effective llm_context for a document.

    Frontmatter 'llm_context' wins when present and non-empty; otherwise the
    per-type default (TYPE_DEFAULT_LLM_CONTEXT[type]) applies. The "never渡さない"
    rule (R5) must be applied to THIS resolved value, not just the default.

    Returns the resolved value, or None if neither a frontmatter value nor a
    known type is available. Robust to a missing/odd `meta` (returns None).
    """
    if isinstance(meta, dict):
        override = meta.get("llm_context")
        if isinstance(override, str) and override:
            return override
        type_code = meta.get("type")
    else:
        type_code = None
    return TYPE_DEFAULT_LLM_CONTEXT.get(type_code)


def allowed_locations(type_code):
    """Allowed location pattern(s) relative to docs/ for a type (§3.2).

    Returns a fresh list (callers may not mutate the registry). Patterns use the
    literal '<domain>' and '_system/' tokens. WATCH returns two patterns; every
    other type returns one. Unknown type -> empty list.
    """
    return list(TYPE_LOCATION.get(type_code, []))


def is_projection(type_code):
    """True iff `type_code` is a projection type (OVERVIEW or CTXMAP, §1.5/C8)."""
    return type_code in PROJECTION_TYPES


# domain_of is intentionally NOT defined here: an id alone does not encode a
# domain (§3.4). Domain resolution requires the doc index and is owned by
# dep-graph.py (_depgraph.resolve). The registry only resolves what an id's
# PREFIX encodes: its type (type_of above).
