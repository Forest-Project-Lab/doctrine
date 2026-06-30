#!/usr/bin/env python3
"""SessionStart 最小契約の描画と注入。常時集合(DECIDED・NONGOAL・WATCH・廃止事実・
GLOSSARY見出し)を要点だけに絞り、上限を守って additionalContext で渡す(仕様 §3.9/§4.2)。

保証限界:
- 予防: 常時投入を最小に保つ。never群(RESEARCH・ARCHIVE等)の本文も、どの文書の本文全量も
  注入に混ぜない(R5「never群が渡らない」「廃止文書の本文をLLMに渡さない」)。注入量の上限を
  ハード天井として守る。
- 検出: 常時集合が上限を超えたら、その旨と推定量を出し、docs-curate の起動を促す。上限は
  肥大を機械的に検出する歯止めである(§3.9)。
- 委ねる: 何を残すかの最終判断・統合・期限切れの整理は docs-curate(人間)に委ねる。古び・孤児
  などの全件検査は監査(docs-audit)に委ねる。前回監査の要約は監査が書いた成果物を読むだけ。

セッションを落とさないため、内容由来の例外は決して main から外へ出さない。常に終了コード 0。
標準ライブラリだけを使う。pip も通信も使わない。決定的に動く(壁時計に依らない)。
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter
import _registry

# 既定の注入量上限(トークン)。仕様は数値を固定せず「上限を設ける」とだけ言う(§3.9/§7)。
# 12000 は運用既定。config の injection_token_cap または --cap で上書きできる。
DEFAULT_CAP = 12000

# トークン推定は文字数 / 4.0 の天井(MASTER §5.4)。英語の標準近似であり、日本語では
# 過大評価ぎみ = 安全側(本物の窓を超える前に curate を促す)。この偏りは意図的。
DEFAULT_CHARS_PER_TOKEN = 4.0


# ---------------------------------------------------------------------------
# トークン推定(純粋・決定的)
# ---------------------------------------------------------------------------
def estimate_tokens(text, chars_per_token=DEFAULT_CHARS_PER_TOKEN):
    """文字数 / chars_per_token の天井。純粋関数、決定的(MASTER §5.4)。"""
    if not text:
        return 0
    try:
        cpt = float(chars_per_token)
    except (TypeError, ValueError):
        cpt = DEFAULT_CHARS_PER_TOKEN
    if cpt <= 0:
        cpt = DEFAULT_CHARS_PER_TOKEN
    return int(math.ceil(len(text) / cpt))


# ---------------------------------------------------------------------------
# 引数解析
# ---------------------------------------------------------------------------
def _parse_args(argv):
    """[--docs-root R] [--cap N] [--config PATH] [--format json|text] [--today YMD]。

    返り値は opts dict。未知の引数は無視する(セッション開始を落とさない)。--cap の値が
    整数でなければ None のまま(=config/既定にゆだねる)。
    """
    opts = {
        "docs_root": None,
        "cap": None,
        "config": None,
        "format": "json",
        "today": None,
    }
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--docs-root" and i + 1 < n:
            opts["docs_root"] = argv[i + 1]; i += 2; continue
        if a.startswith("--docs-root="):
            opts["docs_root"] = a.split("=", 1)[1]; i += 1; continue
        if a == "--cap" and i + 1 < n:
            opts["cap"] = _to_int(argv[i + 1]); i += 2; continue
        if a.startswith("--cap="):
            opts["cap"] = _to_int(a.split("=", 1)[1]); i += 1; continue
        if a == "--config" and i + 1 < n:
            opts["config"] = argv[i + 1]; i += 2; continue
        if a.startswith("--config="):
            opts["config"] = a.split("=", 1)[1]; i += 1; continue
        if a == "--format" and i + 1 < n:
            opts["format"] = argv[i + 1]; i += 2; continue
        if a.startswith("--format="):
            opts["format"] = a.split("=", 1)[1]; i += 1; continue
        if a == "--today" and i + 1 < n:
            opts["today"] = argv[i + 1]; i += 2; continue
        if a.startswith("--today="):
            opts["today"] = a.split("=", 1)[1]; i += 1; continue
        i += 1
    if opts["format"] not in ("json", "text"):
        opts["format"] = "json"
    return opts


def _to_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# docs ルート / 設定 / 監査キャッシュの解決
# ---------------------------------------------------------------------------
def _resolve_docs_root(explicit):
    """docs/ ルートを解決する。--docs-root → $CLAUDE_PROJECT_DIR/docs → ./docs。

    どれも存在しなければ None(呼び側はブートストラップ通知だけを出す)。
    """
    if explicit:
        return explicit if os.path.isdir(explicit) else explicit  # 明示は存在チェックを呼び側に任せる
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cand = os.path.join(proj, "docs")
        if os.path.isdir(cand):
            return cand
    cand = os.path.join(os.getcwd(), "docs")
    if os.path.isdir(cand):
        return cand
    return None


def _load_config(docs_root, config_path):
    """設定 JSON を読む。既定は <docs-root>/_system/.context-config.json。

    キー: injection_token_cap(int), model_chars_per_token(float),
    head_tail_priority([id...])。読めなければ空 dict。決して例外を投げない。
    """
    path = config_path
    if not path and docs_root:
        path = os.path.join(docs_root, "_system", ".context-config.json")
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _plugin_root_cache_candidates():
    """前回監査の要約成果物の候補パスを優先順で返す(C3)。

    第一は ${CLAUDE_PLUGIN_ROOT}/.cache/last-audit.json。CLAUDE_PLUGIN_ROOT は Hook 実行時に
    Claude Code がプラグインの絶対パスとして注入する環境変数である。フォールバックは
    .claude/.cache/last-audit.json(CLAUDE_PROJECT_DIR 基準、無ければ cwd 基準)。
    docs-audit.py が SessionEnd でここへ docs-audit/1 スキーマで書き、inject-contract が
    次の SessionStart でちょうどこのパスから読む(両者の握手)。
    """
    cands = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(os.path.join(plugin_root, ".cache", "last-audit.json"))
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cands.append(os.path.join(proj, ".claude", ".cache", "last-audit.json"))
    cands.append(os.path.join(os.getcwd(), ".claude", ".cache", "last-audit.json"))
    return cands


def _load_audit_summary():
    """前回監査の要約(docs-audit/1)を読む。無ければ None。決して例外を投げない。"""
    for path in _plugin_root_cache_candidates():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, ValueError, UnicodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


# ---------------------------------------------------------------------------
# コーパス読み込み
# ---------------------------------------------------------------------------
class _Doc(object):
    """注入に必要な最小の文書情報。本文全量は決して持たない(headline だけ抽出)。"""
    __slots__ = ("id", "type", "domain", "status", "title", "updated",
                 "review_by", "superseded_by", "llm_context", "headline", "relpath")

    def __init__(self):
        self.id = ""
        self.type = ""
        self.domain = ""
        self.status = ""
        self.title = ""
        self.updated = ""
        self.review_by = ""
        self.superseded_by = ""
        self.llm_context = ""
        self.headline = ""
        self.relpath = ""


def _coerce_str(value):
    if value is None or isinstance(value, bool):
        return ""
    return value if isinstance(value, str) else str(value)


def _first_fact_line(body):
    """本文から「事実一行」だけを取り出す(本文全量は決して渡さない)。

    フロントマター除去後の本文で、見出し(#)・コメント・空行・HTMLコメント・引用記号を飛ばし、
    最初の非空の散文行か箇条書き項目を返す。長すぎる場合は切り詰める。これは headline 抽出で
    あって本文転載ではない。
    """
    if not body:
        return ""
    for raw in body.splitlines():
        s = raw.strip()
        if s == "":
            continue
        if s.startswith("#"):
            continue
        if s.startswith("<!--"):
            continue
        # 箇条書きの記号だけ落として中身を使う。
        if s.startswith("- "):
            s = s[2:].strip()
        elif s.startswith("* "):
            s = s[2:].strip()
        elif s.startswith(">"):
            s = s.lstrip(">").strip()
        if s == "":
            continue
        return _truncate(s, 160)
    return ""


def _truncate(s, limit):
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "…(切り詰め)"


def _load_corpus(docs_root, warn):
    """docs ルート配下の全 .md から _Doc の一覧を組み立てる。

    決定的にファイルを整列走査する。frontmatter の無い/id の無いファイル、解析に失敗した
    ファイルは飛ばす(復元力 > 完全性、§1.10)。重複 id は最初(整列パス順)を採り警告する。
    本文は first-fact 抽出にだけ使い、全量は保持しない(R5)。
    """
    docs = []
    if not docs_root or not os.path.isdir(docs_root):
        return docs
    paths = []
    for dirpath, dirnames, filenames in os.walk(docs_root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".md"):
                paths.append(os.path.join(dirpath, name))
    paths.sort()

    seen_ids = set()
    for path in paths:
        relpath = os.path.relpath(path, docs_root)
        try:
            fm, body, _errs = _frontmatter.parse_file(path)
        except (OSError, UnicodeError) as exc:
            warn("skip(unreadable): %s (%r)" % (relpath, exc))
            continue
        doc_id = _coerce_str(fm.get("id")).strip()
        if not doc_id:
            # frontmatter が無い/id が無い → 飛ばす。
            continue
        if doc_id in seen_ids:
            warn("duplicate id, kept first by path order: %s (%s)" % (doc_id, relpath))
            continue
        seen_ids.add(doc_id)

        d = _Doc()
        d.id = doc_id
        d.type = _coerce_str(fm.get("type")).strip() or (_registry.type_of(doc_id) or "")
        d.domain = _coerce_str(fm.get("domain")).strip()
        d.status = (_coerce_str(fm.get("status")).strip()
                    or _registry.default_status(d.type) or "")
        d.title = _coerce_str(fm.get("title")).strip()
        d.updated = _coerce_str(fm.get("updated")).strip()
        d.review_by = _coerce_str(fm.get("review_by")).strip()
        d.superseded_by = _coerce_str(fm.get("superseded_by")).strip()
        d.llm_context = _coerce_str(fm.get("llm_context")).strip()
        d.relpath = relpath
        d.headline = _first_fact_line(body)
        docs.append(d)
    return docs


def _effective_ctx(d):
    """この文書の実効 llm_context(frontmatter 優先、無ければ型既定)。"""
    meta = {"type": d.type}
    if d.llm_context:
        meta["llm_context"] = d.llm_context
    return _registry.effective_llm_context(meta)


# ---------------------------------------------------------------------------
# ブロック描画(各ブロックは本文全量を決して含まない)
# ---------------------------------------------------------------------------
def _decided_current(docs):
    """現行 DECIDED を新しい順(updated 降順、次に id 降順)に。never は混ざらない。

    置換を記録する(superseded_by を持つ)現行 DECIDED は「廃止事実」節で一度だけ描く
    ので、ここ(素の DECIDED 節)からは除く。一つの事実が契約中に一度しか現れず、
    注入上限の二重計上を防ぐ(finding #18)。
    """
    out = []
    for d in docs:
        if d.type != "DECIDED":
            continue
        if not _registry.is_current(d.status):
            continue
        if _effective_ctx(d) == "never":
            continue
        if d.superseded_by:
            continue  # 廃止事実節でのみ描く(一度だけ)。
        out.append(d)
    out.sort(key=lambda d: (d.updated, d.id), reverse=True)
    return out


def _nongoals(docs):
    out = [d for d in docs if d.type == "NONGOAL" and _effective_ctx(d) != "never"]
    out.sort(key=lambda d: d.id)
    return out


def _watches(docs):
    """WATCH の要点。review_by が近い/過ぎたものを先に(古び前方)。"""
    out = [d for d in docs if d.type == "WATCH" and _effective_ctx(d) != "never"]
    out.sort(key=lambda d: (d.review_by or "9999-99-99", d.id))
    return out


def _glossary_headings(docs):
    """GLOSSARY 見出し(承認語+一行の意味)だけ。禁止同義語の表は注入しない(§1.8)。"""
    return [d for d in docs if d.type == "GLOSSARY" and _effective_ctx(d) != "never"]


def _deprecated_facts(docs):
    """廃止事実の残滓 = 廃止/置換された決定に対の DECIDED 事実。

    §3.8 step2「事実だけを DECIDED の対の記録に残し、本文は LLM に渡さない」。出所は
    現行の DECIDED のうち、superseded_by を持つ(=置換を記録する)もの。廃止文書の本文は
    読まない。対の DECIDED 事実が無ければ何も足さない(本文を漏らさないため正しい)。
    """
    out = []
    for d in docs:
        if d.type != "DECIDED":
            continue
        if not _registry.is_current(d.status):
            continue
        if _effective_ctx(d) == "never":
            continue
        if d.superseded_by:
            out.append(d)
    out.sort(key=lambda d: (d.updated, d.id), reverse=True)
    return out


def _headline_of(d):
    """1文書の一行表現(headline)。本文全量ではない。"""
    bits = []
    if d.title:
        bits.append(d.title)
    elif d.headline:
        bits.append(d.headline)
    elif d.id:
        bits.append(d.id)
    tail = []
    if d.review_by:
        tail.append("review_by %s" % d.review_by)
    line = "- %s" % " ".join(bits) if bits else "- %s" % d.id
    extra = []
    if d.headline and d.title and d.headline != d.title:
        extra.append(d.headline)
    suffix = ""
    if extra:
        suffix += " — " + " / ".join(extra)
    if tail:
        suffix += "（%s）" % "・".join(tail)
    return "〔%s〕%s%s" % (d.id, line[2:], suffix)


# ---------------------------------------------------------------------------
# 監査要約の描画
# ---------------------------------------------------------------------------
def _render_audit_summary(summary):
    """前回監査の要約を一行群に。None/不正 → 「前回監査なし」。本文は転載しない。"""
    if not isinstance(summary, dict):
        return ["前回監査なし。"]
    schema = summary.get("schema")
    if schema != "docs-audit/1":
        # スキーマが合わなくても落とさない。最低限のことだけ伝える。
        return ["前回監査の要約を読めなかった（スキーマ不一致）。"]
    lines = []
    totals = summary.get("totals") or {}
    gen = summary.get("generated_at") or summary.get("today") or ""
    head = "前回監査: error %s / warn %s / advisory %s" % (
        _num(totals.get("error")), _num(totals.get("warn")), _num(totals.get("advisory")))
    if gen:
        head += "（%s）" % gen
    lines.append(head)
    top = summary.get("top_findings")
    if isinstance(top, list) and top:
        for f in top[:5]:
            if not isinstance(f, dict):
                continue
            check = _coerce_str(f.get("check")).strip() or "?"
            sev = _coerce_str(f.get("severity")).strip() or "?"
            did = _coerce_str(f.get("doc_id")).strip()
            msg = _coerce_str(f.get("message")).strip()
            line = "- [%s/%s]" % (sev, check)
            if did:
                line += " %s" % did
            if msg:
                line += ": " + _truncate(msg, 120)
            lines.append(line)
    return lines


def _num(v):
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "0"


# ---------------------------------------------------------------------------
# 注入文字列の組み立て + 上限の強制
# ---------------------------------------------------------------------------
_OVERFLOW_TEMPLATE = (
    "⚠ 常時集合が注入上限（{cap} トークン）を超えた。推定 {est} トークン。\n"
    "docs-curate を起動し、統合と期限切れ（review_by）の整理で縮小すること。\n"
    "本注入は要点に切り詰めた。"
)

_BOOTSTRAP_NOTICE = (
    "文書統治の _system 層がまだ無い。docs-system-init を起動して、"
    "glossary・decided-facts・non-goals・overview の最小構成を用意すること。"
)


def _recap_block_lines(decided, nongoals, watches):
    """冒頭の復唱ブロックの行群(§3.9 要点の復唱)。最も載荷の高い見出しだけを並べる。

    先頭行は節マーカー。続く一行が指示、その後に要点の箇条書き。行ごとのリストで返すので、
    極小の上限のときに trim が箇条書きを削れる(先頭マーカーは残す)。各要点の見出しは
    短く切り詰めて、保護節の最小フロアを小さく保つ。
    """
    lines = [
        "## セッション開始（要点復唱）",
        "まず以下の要点を自分の言葉で復唱してから作業を始めること。",
    ]
    for d in decided[:3]:
        lines.append("- 確定: %s" % _truncate(d.title or d.headline or d.id, 48))
    for d in nongoals[:2]:
        lines.append("- 非目標: %s" % _truncate(d.title or d.headline or d.id, 48))
    for d in watches[:2]:
        lines.append("- 戻さない: %s" % _truncate(d.title or d.headline or d.id, 48))
    if len(lines) == 2:
        lines.append("- （常時集合に確定事実・非目標・WATCH はまだ無い）")
    return lines


def _priority_headlines(docs, config):
    """HEAD/TAIL に置く優先文書の headline 群(§3.9 位置の配慮)。

    config の head_tail_priority に挙げた id を優先。無ければ最新 DECIDED と全 NONGOAL 見出し。
    決定的: id で整列。
    """
    by_id = {d.id: d for d in docs}
    pins = config.get("head_tail_priority") if isinstance(config, dict) else None
    chosen = []
    if isinstance(pins, list) and pins:
        for pid in pins:
            d = by_id.get(_coerce_str(pid).strip())
            if d is not None and _effective_ctx(d) != "never":
                chosen.append(d)
    if not chosen:
        decided = _decided_current(docs)
        if decided:
            chosen.append(decided[0])
        chosen.extend(_nongoals(docs))
    # 重複除去、id 整列で決定的に。
    seen = set()
    uniq = []
    for d in chosen:
        if d.id in seen:
            continue
        seen.add(d.id)
        uniq.append(d)
    uniq.sort(key=lambda d: d.id)
    return uniq


def _build_sections(docs, audit_summary, config):
    """全ブロックを (タイトル, [行...], tier) の順序付きリストで返す。

    tier はトリム時の落とす順(大きいほど先に詳細を落とす)。RECAP・最新 DECIDED・全 NONGOAL
    見出し・監査要約は保護(tier 0)で、節は残し詳細だけ削る。本文全量はどこにも入れない。
    """
    decided = _decided_current(docs)
    nongoals = _nongoals(docs)
    watches = _watches(docs)
    glossary = _glossary_headings(docs)
    deprecated = _deprecated_facts(docs)
    pinned = _priority_headlines(docs, config)

    sections = []

    # 1. RECAP(保護)
    sections.append({
        "key": "recap",
        "title": None,
        "lines": _recap_block_lines(decided, nongoals, watches),
        "tier": 0,
        "protected": True,
    })

    # 2. HEAD priority(重要文書を冒頭へ)
    if pinned:
        sections.append({
            "key": "head",
            "title": "## 重要文書（冒頭）",
            "lines": [_headline_of(d) for d in pinned],
            "tier": 3,
            "protected": False,
        })

    # 3. GLOSSARY 見出し(承認語+一行の意味のみ)
    if glossary:
        glines = []
        for d in glossary:
            meaning = d.headline or d.title
            glines.append("〔%s〕%s%s" % (d.id, d.title or d.id,
                          (" — " + meaning) if meaning and meaning != d.title else ""))
        sections.append({
            "key": "glossary",
            "title": "## 用語（見出し）",
            "lines": glines,
            "tier": 5,
            "protected": False,
        })

    # 4. DECIDED(現行)
    if decided:
        dlines = [_headline_of(d) for d in decided]
        sections.append({
            "key": "decided",
            "title": "## 確定事実（現行 DECIDED）",
            "lines": dlines,
            "tier": 4,
            "protected": False,
            # 最新 DECIDED の一行は保護(常に残す)。
            "protect_first": True,
        })

    # 5. NONGOAL
    if nongoals:
        sections.append({
            "key": "nongoal",
            "title": "## 非目標（NONGOAL）",
            "lines": [_headline_of(d) for d in nongoals],
            "tier": 1,
            "protected": True,  # 全 NONGOAL 見出しは落とさない
        })

    # 6. 廃止事実(対の DECIDED 残滓。本文は決して載せない)
    if deprecated:
        sections.append({
            "key": "deprecated",
            "title": "## 廃止事実（対の記録の事実のみ）",
            "lines": [_headline_of(d) for d in deprecated],
            "tier": 6,
            "protected": False,
        })

    # 7. WATCH の要点
    if watches:
        sections.append({
            "key": "watch",
            "title": "## 戻してはならない事項（WATCH 要点）",
            "lines": [_headline_of(d) for d in watches],
            "tier": 7,
            "protected": False,
        })

    # 8. 前回監査の要約(保護)
    sections.append({
        "key": "audit",
        "title": "## 前回監査の要約",
        "lines": _render_audit_summary(audit_summary),
        "tier": 0,
        "protected": True,
    })

    # 9. TAIL priority(重要文書を末尾へ繰り返す。見出しのみ)
    if pinned:
        sections.append({
            "key": "tail",
            "title": "## 重要文書（末尾・再掲）",
            "lines": [_headline_of(d) for d in pinned],
            "tier": 2,
            "protected": False,
        })

    return sections


def _render_sections(sections):
    """節の一覧を一本の文字列に。空行で節を区切る。"""
    blocks = []
    for sec in sections:
        parts = []
        if sec.get("title"):
            parts.append(sec["title"])
        parts.extend(sec["lines"])
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _trim_to_fit(sections, budget, chars_per_token):
    """`budget` トークンに収めるため、節の詳細を段階的に削る。決定的。

    `budget` は上限から overflow 通知の分を引いた実効予算(_assemble が渡す)。
    削る順:
      1) 保護されない節を tier の大きい順に行ごと削る(見出しは残す)。protect_first の
         節は先頭一行を残す。
      2) それでも超えるなら、最終手段として保護節(recap・audit など)の詳細も先頭一行まで
         削る。節マーカー(見出し/先頭一行)は決して消さない(§1.6)。極小の上限でも天井を守る。
    返り値は新しい sections。
    """
    work = []
    for sec in sections:
        s = dict(sec)
        s["lines"] = list(sec["lines"])
        work.append(s)

    def total():
        return estimate_tokens(_render_sections(work), chars_per_token)

    if budget is None or budget <= 0:
        return work

    # 第1段: 保護されない節を tier 降順(同 tier は key)で削る。
    order = sorted(
        [i for i, s in enumerate(work) if not s.get("protected")],
        key=lambda i: (-work[i]["tier"], work[i]["key"]),
    )
    for idx in order:
        if total() <= budget:
            return work
        sec = work[idx]
        keep = 1 if sec.get("protect_first") else 0
        if len(sec["lines"]) > keep:
            sec["lines"] = sec["lines"][:keep]

    if total() <= budget:
        return work

    # 第2段(最終手段): 保護節の詳細を先頭一行まで削る。recap → audit の順(key で決定的)。
    prot = sorted(
        [i for i, s in enumerate(work) if s.get("protected")],
        key=lambda i: work[i]["key"],
    )
    for idx in prot:
        if total() <= budget:
            break
        sec = work[idx]
        if len(sec["lines"]) > 1:
            sec["lines"] = sec["lines"][:1]

    return work


def _assemble(docs, audit_summary, config, cap, chars_per_token, had_docs_root):
    """注入文字列を組み立て、上限を強制し、超過時に通知を付ける。

    返り値: (context_string, overflow_bool, untrimmed_estimate)。
    オーバーフローは「未トリムの推定」で判定する(MASTER §5.4)。トリムで収まっても
    通知は出す(上限は肥大検出の歯止め)。
    """
    if not had_docs_root:
        # _system が無い → ブートストラップ通知だけ(空文字列にしない、§1.3)。
        return (_BOOTSTRAP_NOTICE, False, estimate_tokens(_BOOTSTRAP_NOTICE, chars_per_token))

    sections = _build_sections(docs, audit_summary, config)
    untrimmed = _render_sections(sections)
    untrimmed_est = estimate_tokens(untrimmed, chars_per_token)

    no_cap = (cap is None or cap <= 0)
    overflow = (not no_cap) and (untrimmed_est > cap)

    if not overflow:
        return (_render_sections(sections), False, untrimmed_est)

    # overflow 通知は常に残す(実行可能な信号)。通知の分を予算から差し引いてから本体を
    # トリムし、本体+通知が上限に収まる天井を守る(MASTER §5.4)。
    notice = _OVERFLOW_TEMPLATE.format(cap=cap, est=untrimmed_est)
    notice_cost = estimate_tokens("\n\n" + notice, chars_per_token)
    budget = cap - notice_cost
    if budget < 0:
        budget = 0

    sections = _trim_to_fit(sections, budget, chars_per_token)
    body = _render_sections(sections) + "\n\n" + notice
    return (body, True, untrimmed_est)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    """SessionStart のエントリ。stdin(SessionStart イベント)は無視。常に終了コード 0。

    内容由来の例外は決して外へ出さない。最悪でも空でない有効な JSON を返し、セッションを
    落とさない。
    """
    if argv is None:
        argv = sys.argv[1:]

    # SessionStart の stdin は読み捨てる(空 stdin でもブロックしない)。
    try:
        if not sys.stdin.isatty():
            sys.stdin.read()
    except (OSError, ValueError):
        pass

    try:
        opts = _parse_args(list(argv))
        docs_root = _resolve_docs_root(opts["docs_root"])
        had_docs_root = bool(docs_root) and os.path.isdir(docs_root)

        config = _load_config(docs_root, opts["config"])

        # 上限: --cap > config.injection_token_cap > 既定 12000。
        cap = opts["cap"]
        if cap is None:
            cfg_cap = config.get("injection_token_cap") if isinstance(config, dict) else None
            cap = _to_int(cfg_cap) if cfg_cap is not None else None
        if cap is None:
            cap = DEFAULT_CAP

        cpt = DEFAULT_CHARS_PER_TOKEN
        if isinstance(config, dict):
            mcpt = config.get("model_chars_per_token")
            try:
                if mcpt is not None and float(mcpt) > 0:
                    cpt = float(mcpt)
            except (TypeError, ValueError):
                pass

        warnings = []
        docs = _load_corpus(docs_root, warnings.append) if had_docs_root else []
        audit_summary = _load_audit_summary()

        context, _overflow, _est = _assemble(
            docs, audit_summary, config, cap, cpt, had_docs_root)

        for w in warnings:
            sys.stderr.write("inject-contract: %s\n" % w)

        if opts["format"] == "text":
            sys.stdout.write(context + "\n")
            return 0

        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
        return 0

    except Exception as exc:  # noqa: BLE001 — セッションを決して落とさない
        sys.stderr.write("inject-contract: internal error: %r\n" % (exc,))
        # フェイルオープン: 最小の有効な SessionStart 応答を返す。
        fallback = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "（契約の描画に失敗した。docs-system-init と "
                                     "docs-curate を確認すること。）",
            }
        }
        try:
            sys.stdout.write(json.dumps(fallback, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            sys.stdout.write("{}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
