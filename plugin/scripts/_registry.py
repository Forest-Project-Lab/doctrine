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

import os
import re
import stat

# ---------------------------------------------------------------------------
# §3.2 型登録簿 — registry order (= spec table row order)。件数は書かない
# (ADR-075: 「19 types」と書いたまま 20 になっていた)。数は len(TYPES) が持つ。
# ---------------------------------------------------------------------------

# doctrine:begin SPEC-001
TYPES = (
    "ICD", "OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH",
    "REQ", "SPEC", "DATA", "API", "ADR", "CHANGE", "IMPACT", "IMPL", "PROC",
    "TEST", "RESEARCH", "ARCHIVE", "EXT",
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
    "PROC": "current",
    "TEST": "current",
    "RESEARCH": "draft",
    "ARCHIVE": "archived",
    "EXT": "current",
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
    "PROC": "task",
    "TEST": "task",
    "RESEARCH": "never",
    "ARCHIVE": "never",
    "EXT": "task",
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
    "PROC": ["<domain>/procedures/"],
    "TEST": ["<domain>/test/"],
    "RESEARCH": ["<domain>/research/"],
    "ARCHIVE": ["<domain>/archive/"],
    "EXT": ["<domain>/external/"],
}

# status:archived の文書は、型に依らず <domain>/archive/ 配下に置く(ADR-027)。
# §3.2(型で置き場所)と §3.8(アーカイブは倉庫へ移す)の衝突をこの一行で解く。
ARCHIVED_LOCATION = ["<domain>/archive/"]
# 置き場所の名前の正本。判定の実体もここに置く(ADR-075)。監査が
# `"archive" not in parts[:-1]` と独自に持っており、規則の二重定義だった。
ARCHIVE_DIR_NAME = "archive"


def is_archived_path(dir_parts):
    """統治木からの相対の途中経路が <domain>/archive/ 配下か。

    dir_parts は docs_root からの相対のディレクトリ列(ファイル名は含めない)。
    深さは問わない(<domain>/archive/<年>/ のような年別の棚も倉庫の中と見る)。
    """
    return ARCHIVE_DIR_NAME in list(dir_parts or [])

# 投影 (projections) — rendered, "手で編集しない". ICD-index reuses type OVERVIEW (C8),
# so it is NOT a separate type here ("空の型を先に作らない", §3.2).
PROJECTION_TYPES = ("OVERVIEW", "CTXMAP")

# Types whose canonical instance lives in the _system tier (WATCH also lives
# under <domain>/test/, see TYPE_LOCATION).
SYSTEM_TIER_TYPES = ("OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH")

# Types that form the always-injected contract residue (§3.9 / inject-contract).
ALWAYS_CONTRACT_TYPES = ("DECIDED", "NONGOAL", "WATCH", "GLOSSARY")
# doctrine:end SPEC-001

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
    if not isinstance(type_code, str) or type_code not in TYPE_DEFAULT_STATUS:
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

# 型ごとの必須節(本文の見出し)の正本(ADR-090)。構造規則はここに一度だけ持つ
# (確定事実1)。以前は SPEC の四節だけがリンタの中に在り、他の型は雛形が定めるのに
# 誰も検めていなかった。
#
# 一覧は**実態を測って決めた**。統治木 203 文書で雛形と本文を突き合わせ、ある型の
# 文書が 100% ずれているなら雛形が誤りと判じた:
#   - CHANGE は六件すべてが『理由』と『要求元』を『理由（要求元）』に統合していた。
#   - RESEARCH は四件すべてが主題ごとの見出しで書かれ、出所と日付はフロントマターに
#     在った。調査は探索であり形が先に決まらないので、節を課さない。
# 次に実態がずれたら、また測って直す(雛形を守らせるのではなく、雛形と実態のどちらが
# 正しいかを毎回問う)。
REQUIRED_SECTIONS = {
    "ADR": ("背景", "却下した選択肢", "決定", "帰結"),
    "API": ("エンドポイント", "入出力", "エラー"),
    "ARCHIVE": ("アーカイブ理由", "アーカイブ日", "後継ID"),
    "CHANGE": ("変更内容", "理由（要求元）", "影響の初期見積"),
    "DATA": ("エンティティ", "保存方針", "保持期間"),
    "DECIDED": ("確定方針", "決定日", "根拠ADR", "再点検期限"),
    "EXT": ("何に依存しているか", "期待", "動いたら何が壊れるか"),
    "ICD": ("公開する用語", "正本である事実", "データ契約", "依存してよい入口"),
    "IMPACT": ("影響する文書", "影響する実装", "影響するテスト", "工数見積"),
    "IMPL": ("実装制約", "注意点", "対象部品"),
    "NONGOAL": ("やらないこと", "理由"),
    "PROC": ("目的と発動条件", "前提", "手順", "切り戻し"),
    "REQ": ("要求文", "優先度", "受入基準参照", "出所"),
    "SPEC": ("入出力", "制約", "エラー時挙動", "受入基準"),
    "TEST": ("受入基準への対応", "退行観点", "合否基準"),
    "WATCH": ("戻してはならない事項", "撤回日", "根拠", "再点検期限"),
    # RESEARCH は節を課さない(上記のとおり)。投影(OVERVIEW/CTXMAP/GLOSSARY/
    # ICDINDEX)も課さない —— 機械が描くものであり、人が節を書かない。
}


def required_sections(type_code):
    """型の必須節を返す。課さない型は空(ADR-090)。決して例外を投げない。"""
    if not isinstance(type_code, str):
        return ()
    return REQUIRED_SECTIONS.get(type_code.strip().upper(), ())

# 型ごとの既定点検周期(日)。review_by を持たない現行文書の実効期限は
# updated + この日数とする(ADR-025)。None の型は周期の対象外:
# 投影は描画物、ADR は不変の決定、DECIDED/WATCH は明示 review_by が必須、
# CHANGE/IMPACT は変更フローの一時物、RESEARCH は draft 放置検査、
# ARCHIVE は不変。明示の review_by は常にこの既定より優先する。
TYPE_REVIEW_CYCLE_DAYS = {
    "ICD": 180,
    "GLOSSARY": 180,
    "NONGOAL": 365,
    "REQ": 365,
    "SPEC": 180,
    "DATA": 180,
    "API": 180,
    "IMPL": 365,
    "PROC": 180,
    "TEST": 365,
    "EXT": 180,
}


def review_cycle_days(type_code):
    """型の既定点検周期(日)。対象外の型・未知の型は None(ADR-025)。"""
    if not isinstance(type_code, str):
        return None
    return TYPE_REVIEW_CYCLE_DAYS.get(type_code)

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

# Context Map 骨組みの差し替え区間を囲む印(§3.9/slice 06 §3.5)。描き手
# (render-projection)と読み手(docs-audit の投影ドリフト検査)が同じ印で
# 区間を判じるため、正本はここ一つ(DECIDED-001 事実1)。
CTXMAP_BEGIN = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
CTXMAP_END = "<!-- END PROJECTION:context-map-skeleton -->"

# 正本 (canonical) + the overview projection seeded by scaffold.py (§3.7 / §5.8).
# watchlist.md is the spec-mandated fixed path for the WATCH 正本 (§3.7 layout):
# its filename does NOT encode the id (WATCH-N), so id<->filename matching must
# be skipped for it — but ONLY when it lives under _system/ (see linter's
# _is_system_singleton, which requires rel_parts[0] == "_system").
SYSTEM_CANONICAL_FILES = frozenset({
    "glossary.md", "decided-facts.md", "non-goals.md", "overview.md",
    "watchlist.md",
})

# 根の案内 — spec-fixed projection pointers that LIVE at the project root by
# design (§3.7/§5: CLAUDE.md/AGENTS.md are 投影・入口 and are NOT docs/ files).
# stray-document scanning (ADR-021) must not report them as unclassified.
ROOT_POINTER_FILES = frozenset({"CLAUDE.md", "AGENTS.md"})

# 走査から外すディレクトリ名。dot ディレクトリ(.claude/ .github/ .devcontainer/)
# はハーネスと道具の領分であり、統治の対象ではない。
_DOT_PREFIX = "."


def is_outside_governance(path, proj=None):
    """統治の点検を当ててはいけないファイルか(ADR-075)。決して例外を投げない。

    二つを見る。(1) 根の案内(CLAUDE.md/AGENTS.md)は仕様が根に置くと定める入口で
    あり、フロントマターを持たない(ADR-029)。(2) dot ディレクトリの配下は
    ハーネスと道具の設定であり、統治の走査対象でない。

    この判定はこれまで監査(_audit_stray)にしか無く、リンタは同じ範囲を知らな
    かった。その結果 CLAUDE.md に MISSING_FRONTMATTER、`.claude/commands/*.md` に
    MISSING_KEY を出し続け、指示に従えば ADR-029 に反しスラッシュコマンドが壊れる
    という、構造的に修正不能な要求になっていた。判定をここへ一本化する。
    """
    if not path:
        return False
    try:
        norm = os.path.abspath(path).replace("\\", "/")
    except Exception:
        return False
    base = os.path.basename(norm)
    if base in ROOT_POINTER_FILES:
        return True
    rel = norm
    if proj:
        try:
            rel = os.path.relpath(norm, os.path.abspath(proj)).replace("\\", "/")
        except Exception:
            rel = norm
    return any(seg.startswith(_DOT_PREFIX) and seg not in (".", "..")
               for seg in rel.split("/")[:-1])

# 統治木のディレクトリ名 — 優先順(ADR-022)。既定は doctrine_docs。docs は
# doctrine が初期化した印(_system)を持つ場合だけ統治木と認める(後方互換)。
# _system を持たない素の docs/ は他所の土地であり、決して統治木として扱わない。
DOCS_DIR_NAMES = ("doctrine_docs", "docs")


def is_doctrine_tree(path, name=None):
    """`path` を統治木として扱ってよいか(ADR-022)。決して例外を投げない。

    doctrine_docs は存在すれば統治木(初期化前のブートストラップ先を含む)。
    docs は `_system` を持つ場合だけ統治木(素の docs は他所の土地)。
    """
    if not path or not os.path.isdir(path):
        return False
    base = name or os.path.basename(os.path.normpath(path))
    if base == "doctrine_docs":
        return True
    if base == "docs":
        return os.path.isdir(os.path.join(path, "_system"))
    return False


def locate_docs_root(project_dir):
    """プロジェクト根から統治木を解決する(ADR-022)。無ければ None。"""
    if not project_dir:
        return None
    for name in DOCS_DIR_NAMES:
        cand = os.path.join(project_dir, name)
        if is_doctrine_tree(cand, name):
            return cand
    return None


def walkup_docs_root(start_path, cwd=None):
    """start_path(ファイルでもよい)から上へたどって統治木を探す(ADR-022)。

    各階層で、自身が統治木か、直下に統治木を持つかを DOCS_DIR_NAMES の
    優先順で見る。見つからなければ cwd 側も同様に試し、無ければ None。
    """
    candidates = []
    if start_path:
        p = os.path.abspath(start_path)
        candidates.append(p if os.path.isdir(p) else os.path.dirname(p))
    if cwd:
        candidates.append(os.path.abspath(cwd))
    for cur in candidates:
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            if is_doctrine_tree(cur):
                return cur
            found = locate_docs_root(cur)
            if found is not None:
                return found
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None

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
    """True iff `type_code` is one of the registry types (see TYPES).

    Non-string values (e.g. a YAML-list typo `type: [SPEC]`) are simply
    unknown — they must not raise, or a single malformed frontmatter key
    would take down every check that runs after this one.
    """
    if not isinstance(type_code, str):
        return False
    return type_code in TYPE_DEFAULT_STATUS


def resolve_duplicate_id(paths):
    """Pick the one adopted document when several files share an id (ADR-049).

    First by sorted order wins. The rule lives here once (DECIDED-001 fact 1):
    dep-graph, the SessionStart injection and the audit all call this, so
    "which one is canonical" has a single answer across the system. First-wins
    means a newly added colliding file cannot steal the id from the document
    that already holds it — the newcomer is the one that must be renamed, and
    that is where the audit points its remediation.

    Non-string entries are ignored. Returns None for an empty/None input.
    """
    if not paths:
        return None
    usable = sorted(p for p in paths if isinstance(p, str))
    return usable[0] if usable else None


def default_status(type_code):
    """Default status for a type (§3.2). None for an unknown/non-string type."""
    if not isinstance(type_code, str):
        return None
    return TYPE_DEFAULT_STATUS.get(type_code)


def default_llm_context(type_code):
    """Default llm_context ('always'|'task'|'never') for a type (§3.2).
    None for an unknown/non-string type."""
    if not isinstance(type_code, str):
        return None
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
    if not isinstance(type_code, str):
        return None
    return TYPE_DEFAULT_LLM_CONTEXT.get(type_code)


def allowed_locations(type_code):
    """Allowed location pattern(s) relative to docs/ for a type (§3.2).

    Returns a fresh list (callers may not mutate the registry). Patterns use the
    literal '<domain>' and '_system/' tokens. WATCH returns two patterns; every
    other type returns one. Unknown/non-string type -> empty list.
    """
    if not isinstance(type_code, str):
        return []
    return list(TYPE_LOCATION.get(type_code, []))


def is_projection(type_code):
    """True iff `type_code` is a projection type (OVERVIEW or CTXMAP, §1.5/C8)."""
    if not isinstance(type_code, str):
        return False
    return type_code in PROJECTION_TYPES


# ---------------------------------------------------------------------------
# §4.4 段階導入 — the active level marker (C9 / ICD-008 level-staging)
# ---------------------------------------------------------------------------

_DOCS_LEVEL_RE = re.compile(r"^\s*level\s*[:：]\s*([234])\s*$")


def docs_level(docs_root):
    """Read the active Level from <docs_root>/_system/.docs-level (ADR-019).

    The marker is a single line 'level: N' with N in {2,3,4}, written by
    scaffold.py. Hook scripts read it to self-gate the parts a trimmed Level
    excludes (SessionEnd audit, post-apply guard, review nudge below 3).
    Missing / unreadable / malformed -> 4: dropping a stage is a lightening,
    not a protection, so uncertainty falls toward FULL governance. Never
    raises.
    """
    if not docs_root:
        return 4
    path = os.path.join(docs_root, "_system", ".docs-level")
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            return None      # 通常ファイルでなければ開かない(ADR-075)
        with open(path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                m = _DOCS_LEVEL_RE.match(line)
                if m:
                    return int(m.group(1))
    except (OSError, UnicodeError, ValueError):
        return 4
    return 4


# domain_of is intentionally NOT defined here: an id alone does not encode a
# domain (§3.4). Domain resolution requires the doc index and is owned by
# dep-graph.py (_depgraph.resolve). The registry only resolves what an id's
# PREFIX encodes: its type (type_of above).
