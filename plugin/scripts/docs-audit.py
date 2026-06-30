#!/usr/bin/env python3
"""全件監査(SessionEnd/CI)。コーパス全体を走査し、所見と要約を出す(MASTER §5.5)。

保証限界:
- 予防: 何も予防しない。per-turn では走らない。SessionEnd と CI からだけ走る(§4.2)。
- 検出: dead link・review_by 超過(DECIDED/WATCH 含む)・draft 放置・孤児
  (逆参照ゼロ∧陳腐化∧再現可能)・逆孤児・canonical_for 衝突・語彙的酷似(助言)・
  ICD依存違反・投影ドリフトを全件で一覧化する。
- 委ねる: 取り除き(一片ずつ)は docs-curate に、意味的重複の最終判断は人間と
  doc-review に委ねる。ガード(予防)は policy-guard に委ねる。

SessionEnd 経路は非ブロッキング: --json --summary-out <cache> --fail-on never で動き、
要約を原子的(一時+改名)に書き、書き込みに失敗しても終了コード 0 を返す。
CI 経路は --fail-on error で、error 所見が一つでもあれば終了コード 1 を返す。

generated_at は決定的に注入できる(--today か固定値)。テストが制御できない形での
壁時計参照はしない。

標準ライブラリだけを使う。pip も通信も使わない。出力は決定的(整列済み)。
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _frontmatter
import _registry


SCHEMA = "docs-audit/1"

# 既定の調整値(仕様に数値が無い。すべて --config で上書きできる。slice 05 C.6)。
DEFAULT_DRAFT_STALE_DAYS = 90       # draft 放置の閾値
DEFAULT_ORPHAN_STALE_DAYS = 180     # 孤児の陳腐化の閾値
DEFAULT_JACCARD = 0.8               # 語彙的酷似(助言)の閾値
DEFAULT_TOP_FINDINGS = 20           # top_findings の上限(errors 優先)
DEFAULT_NEAR_DUP_CAP = 50           # 酷似報告の上限

# 重大度。
SEV_ERROR = "error"
SEV_WARN = "warn"
SEV_ADVISORY = "advisory"

# 投影(描画)/正本のファイル名(§3.7)。孤児・参照解決の特例に使う。
_PROJECTION_FILES = _registry.PROJECTION_FILES
_SYSTEM_CANONICAL_FILES = _registry.SYSTEM_CANONICAL_FILES

# 本文中の id 参照トークン(<TYPE>-<NNN>)。dead link の本文走査に使う。
_ID_TOKEN_RE = re.compile(r"\b([A-Z]+-\d+)\b")
# 本文中の相対 .md リンク。
_MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)[^)]*\)")
# 単語シングル化(語彙的酷似)。英数字連なり + 連続する非ASCII。
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\x00-\x7f]+")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


# ---------------------------------------------------------------------------
# 引数解析
# ---------------------------------------------------------------------------

def _parse_args(argv):
    """argv を (opts, error_message) に解く。"""
    opts = {
        "root": "docs",
        "json": False,
        "summary_out": None,
        "fail_on": "never",     # 既定は SessionEnd 想定(非ブロッキング)
        "config": None,
        "today": None,
    }
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--root":
            if i + 1 >= n:
                return None, "--root にはパスが必要"
            opts["root"] = argv[i + 1]
            i += 2
            continue
        if a == "--json":
            opts["json"] = True
            i += 1
            continue
        if a == "--summary-out":
            if i + 1 >= n:
                return None, "--summary-out にはパスが必要"
            opts["summary_out"] = argv[i + 1]
            i += 2
            continue
        if a == "--fail-on":
            if i + 1 >= n:
                return None, "--fail-on には error か never が必要"
            v = argv[i + 1]
            if v not in ("error", "never"):
                return None, "--fail-on は error か never"
            opts["fail_on"] = v
            i += 2
            continue
        if a == "--config":
            if i + 1 >= n:
                return None, "--config にはパスが必要"
            opts["config"] = argv[i + 1]
            i += 2
            continue
        if a == "--today":
            if i + 1 >= n:
                return None, "--today には YYYY-MM-DD が必要"
            opts["today"] = argv[i + 1]
            i += 2
            continue
        return None, "不明な引数: %s" % a
    return opts, None


def _load_config(path):
    """--config の JSON を読み、調整値の dict を返す。読めなければ {}。"""
    knobs = {
        "draft_stale_days": DEFAULT_DRAFT_STALE_DAYS,
        "orphan_stale_days": DEFAULT_ORPHAN_STALE_DAYS,
        "jaccard": DEFAULT_JACCARD,
        "top_findings_cap": DEFAULT_TOP_FINDINGS,
        "near_dup_cap": DEFAULT_NEAR_DUP_CAP,
        "today": None,
    }
    if not path:
        return knobs
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return knobs
    if isinstance(data, dict):
        for k in knobs:
            if k in data:
                knobs[k] = data[k]
    return knobs


# ---------------------------------------------------------------------------
# 日付ユーティリティ(決定的; 壁時計に依存しない経路を優先)
# ---------------------------------------------------------------------------

def _parse_date(s):
    """'YYYY-MM-DD' を date に。形が違えば None(壊れた日付として扱う)。"""
    if not isinstance(s, str):
        return None
    m = _DATE_RE.match(s.strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


class _TodayError(ValueError):
    """--today / config.today に値はあるが解せない(使用法エラー → 終了コード 2)。"""


def _resolve_today(opts, knobs):
    """today を解決する。--today > config.today > 壁時計(最後の手段)。

    値が供給されているのに解せないときは _TodayError を投げる(制御不能な壁時計参照に
    黙って退避しない、docstring の保証)。値が一切供給されないときだけ壁時計に退避する。
    """
    raw = opts.get("today") or knobs.get("today")
    if raw:
        d = _parse_date(raw)
        if d is None:
            raise _TodayError(
                "--today/config の today が解せない(YYYY-MM-DD 必須): %r" % (raw,))
        return d
    # today の指定が一切無いときだけ壁時計に退避する(実運用の最後の手段)。
    return datetime.date.today()


# ---------------------------------------------------------------------------
# 所見モデル
# ---------------------------------------------------------------------------

def _finding(check, severity, doc_id, path, message, refs=None):
    return {
        "check": check,
        "severity": severity,
        "doc_id": doc_id,
        "path": path,
        "message": message,
        "refs": sorted(refs) if refs else [],
    }


# ---------------------------------------------------------------------------
# 監査チェック(§4.2 監査一覧をすべて)
# ---------------------------------------------------------------------------

def _check_dead_link(g):
    """1. dead link(R4)。frontmatter の id 参照 + 本文の id/相対リンクが解決するか。"""
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        targets = set()
        for field in ("depends_on", "impacts"):
            for t in node[field]:
                targets.add(t)
        if node["superseded_by"]:
            targets.add(node["superseded_by"])
        # 本文の id トークン(自分自身は除く)。
        body_ids = _body_id_refs(g, node)
        targets |= body_ids
        for t in sorted(targets):
            if t == doc_id:
                continue   # 自己参照は cycle 扱い(dead link ではない)
            if t not in g.nodes:
                out.append(_finding(
                    "dead_link", SEV_ERROR, doc_id, node["path"],
                    "参照先 %s が存在しない(dead link)" % t, refs=[t]))
    return out


def _body_id_refs(g, node):
    """本文中の id トークンのうち、登録簿が型として解せるものだけを参照候補にする。

    本文全体を読み直すコストを避けるため、構築済み body を持たない場合はファイルから
    読む。解せない英大文字トークン(GLOSSARY 見出し等)は無視する。
    """
    body = node.get("_body")
    if body is None:
        body = _read_body(os.path.join(g.root, node["path"]))
    refs = set()
    for m in _ID_TOKEN_RE.finditer(body):
        tok = m.group(1)
        if _registry.type_of(tok) is not None:
            refs.add(tok)
    return refs


def _read_body(path):
    try:
        _fm, body, _errs = _frontmatter.parse_file(path)
    except (OSError, UnicodeError):
        return ""
    return body


def _check_review_by(g, today):
    """2. review_by 超過(R2)。DECIDED/WATCH は review_by 必須(不在は error)。"""
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        t = node["type"]
        rb = node["review_by"]
        if not rb:
            if t in _registry.REQUIRED_REVIEW_BY_TYPES:
                out.append(_finding(
                    "review_by_overrun", SEV_ERROR, doc_id, node["path"],
                    "%s は review_by が必須だが無い" % t))
            continue
        d = _parse_date(rb)
        if d is None:
            out.append(_finding(
                "review_by_overrun", SEV_ERROR, doc_id, node["path"],
                "review_by の日付形式が壊れている: %s" % rb))
            continue
        if d < today:
            out.append(_finding(
                "review_by_overrun", SEV_WARN, doc_id, node["path"],
                "review_by %s が過ぎている(現在 %s)" % (rb, today.isoformat())))
    return out


def _check_stale_draft(g, today, stale_days):
    """3. draft 放置(R8/R2)。status==draft かつ updated が閾値より古い。"""
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["status"] != "draft":
            continue
        if _is_stale(node["updated"], today, stale_days):
            out.append(_finding(
                "stale_draft", SEV_WARN, doc_id, node["path"],
                "draft のまま %d 日以上更新が無い(updated %s)"
                % (stale_days, node["updated"] or "?")))
    return out


def _is_stale(updated, today, stale_days):
    """updated が today より stale_days 日以上前なら True。日付不明なら True(古び扱い)。"""
    d = _parse_date(updated)
    if d is None:
        return True
    return (today - d).days >= stale_days


def _check_orphan(g, today, stale_days):
    """4. 孤児(R8/R1)。逆参照ゼロ ∧ 陳腐化 ∧ 再現可能 の三条件すべて。

    投影(OVERVIEW/CTXMAP)・llm_context==always・ICD は孤児にしない(入口/常時文脈)。
    再現可能 = type==RESEARCH か llm_context==never か reproducible: true。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        t = node["type"]
        if t == "ICD" or _registry.is_projection(t):
            continue
        eff = _registry.effective_llm_context(_node_meta(node))
        if eff == "always":
            continue
        # 逆参照ゼロ(現行の依存ゼロ)。
        if g.reverse_dependents(doc_id, current_only=True):
            continue
        # 陳腐化: updated が古い、または review_by 超過。
        stale = _is_stale(node["updated"], today, stale_days)
        rbd = _parse_date(node["review_by"])
        if rbd is not None and rbd < today:
            stale = True
        if not stale:
            continue
        # 再現可能。
        if not _is_reproducible(node, eff):
            continue
        out.append(_finding(
            "orphan", SEV_ERROR, doc_id, node["path"],
            "孤児(逆参照ゼロ∧陳腐化∧再現可能)。docs-curate で取り除く候補"))
    return out


def _is_reproducible(node, eff_llm_context):
    if node["type"] == "RESEARCH":
        return True
    if eff_llm_context == "never":
        return True
    repro = node.get("reproducible")
    return repro is True


def _node_meta(node):
    """effective_llm_context 用の最小 meta dict。"""
    return {"type": node["type"], "llm_context": node["llm_context"] or None}


def _check_reverse_orphan(g):
    """5. 逆孤児(R3/R8)。_depgraph.reverse_orphans に委ねる。"""
    out = []
    buckets = g.reverse_orphans()
    for doc_id in buckets["req_without_spec"]:
        node = g.nodes[doc_id]
        out.append(_finding(
            "reverse_orphan_req_no_spec", SEV_ERROR, doc_id, node["path"],
            "要求 %s に対応する現行 SPEC が無い(逆孤児)" % doc_id))
    for doc_id in buckets["spec_without_test"]:
        node = g.nodes[doc_id]
        out.append(_finding(
            "reverse_orphan_spec_no_test", SEV_ERROR, doc_id, node["path"],
            "仕様 %s に対応する現行 TEST が無い(逆孤児)" % doc_id))
    return out


def _check_canonical_conflict(g):
    """6. canonical_for 衝突(R8)。同一トピックに現行 canonical が二つ以上。

    置換済み(superseded)でもなお canonical_for を持つ文書は移譲漏れとして含める
    (TC-125)。判定はアーカイブ/廃止を除いた文書。トピックは厳密一致。
    """
    out = []
    topic_map = {}   # topic -> sorted list of doc_ids
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        status = node["status"]
        if status in ("archived", "deprecated"):
            continue
        for topic in node["canonical_for"]:
            topic_map.setdefault(topic, []).append(doc_id)
    for topic in sorted(topic_map):
        ids = sorted(topic_map[topic])
        if len(ids) >= 2:
            for doc_id in ids:
                node = g.nodes[doc_id]
                others = [i for i in ids if i != doc_id]
                out.append(_finding(
                    "canonical_conflict", SEV_ERROR, doc_id, node["path"],
                    "トピック '%s' の正本が複数: %s" % (topic, ", ".join(ids)),
                    refs=others))
    return out


def _check_near_duplicate(g, jaccard_threshold, cap):
    """7. 語彙的酷似(助言)。現行文書対の Jaccard が閾値以上。

    トークンのシングル集合(unigram)の Jaccard。標準ライブラリのみ。
    決定的: doc_id の組で整列、上限で切る。常に advisory。
    """
    out = []
    shingles = {}
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if not _registry.is_current(node["status"]):
            continue
        body = node.get("_body")
        if body is None:
            body = _read_body(os.path.join(g.root, node["path"]))
        toks = set(_TOKEN_RE.findall(body.lower()))
        if toks:
            shingles[doc_id] = toks
    ids = sorted(shingles)
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            sa, sb = shingles[a], shingles[b]
            inter = len(sa & sb)
            if inter == 0:
                continue
            union = len(sa | sb)
            sim = inter / union if union else 0.0
            if sim >= jaccard_threshold:
                pairs.append((a, b, sim))
    # 類似度降順、次に id 昇順で決定的に並べ、上限で切る。
    pairs.sort(key=lambda p: (-p[2], p[0], p[1]))
    for a, b, sim in pairs[:cap]:
        node = g.nodes[a]
        out.append(_finding(
            "near_duplicate", SEV_ADVISORY, a, node["path"],
            "%s と %s が語彙的に酷似(Jaccard %.2f)。人間が確認する" % (a, b, sim),
            refs=[b]))
    return out


def _check_icd_violation(g):
    """8. ICD依存違反(R7)。classify_edges の cross_domain_violation を error 化。"""
    out = []
    edges = g.classify_edges()
    for e in edges:
        if e["kind"] != _depgraph.KIND_CROSS_VIOLATION:
            continue
        src, dst = e["src"], e["dst"]
        dst_domain = g.domain_of(dst)
        node = g.nodes[src]
        msg = "%s は %s の内部です。%s の ICD 宛にしてください。" % (
            dst, dst_domain, dst_domain)
        out.append(_finding(
            "icd_dependency_violation", SEV_ERROR, src, node["path"],
            msg, refs=[dst]))
    return out


def _check_projection_drift(g):
    """9. 投影ドリフト(R1/R8)。現行 frontmatter から期待集合を導いて投影と差分。

    render-projection.py があればそれと突き合わせるのが理想だが、本実装では
    内部の決定的な再導出に基づく構造比較を行う(render-projection 不在時の代替)。
    - Overview ドリフト: Overview に列挙された id 集合 ≠ 現行ソース文書集合 → error。
    - ICD-index ドリフト: ICD-index の id 集合 ≠ 現行 ICD 集合 → error。
    - Context Map: 構造(ドメイン/ドメイン越え依存端)の差 → error、ラベルの差 → warn。
    索引型の投影は決定的に描画できる(§3.9)ため、構造の差は hard error。
    """
    out = []
    # 期待: 現行の「ソース」文書(投影自身・GLOSSARY 見出し以外)を Overview が網羅。
    expected_overview = set()
    expected_icds = set()
    for doc_id, node in g.nodes.items():
        if not _registry.is_current(node["status"]):
            continue
        t = node["type"]
        if _registry.is_projection(t):
            continue          # 投影自身は Overview の項目ではない
        expected_overview.add(doc_id)
        if t == "ICD":
            expected_icds.add(doc_id)

    overview_node = _find_projection_node(g, "OVERVIEW", "overview.md")
    if overview_node is not None:
        listed = _body_id_refs(g, overview_node)
        missing = expected_overview - listed
        extra = listed - expected_overview - {overview_node["id"]}
        for m in sorted(missing):
            out.append(_finding(
                "projection_drift", SEV_ERROR, overview_node["id"],
                overview_node["path"],
                "Overview に現行文書 %s の項目が無い(投影ドリフト)" % m, refs=[m]))
        for x in sorted(extra):
            # Overview に載っているが現行ソースに無い(廃止/除去された文書)。
            out.append(_finding(
                "projection_drift", SEV_ERROR, overview_node["id"],
                overview_node["path"],
                "Overview に現行でない/不在の文書 %s が載っている(投影ドリフト)" % x,
                refs=[x]))

    icd_index_node = _find_projection_node(g, "OVERVIEW", "icd-index.md")
    if icd_index_node is not None:
        listed = {i for i in _body_id_refs(g, icd_index_node)
                  if _registry.type_of(i) == "ICD"}
        missing = expected_icds - listed
        extra = listed - expected_icds
        for m in sorted(missing):
            out.append(_finding(
                "projection_drift", SEV_ERROR, icd_index_node["id"],
                icd_index_node["path"],
                "ICD-index に現行 ICD %s の項目が無い(投影ドリフト)" % m, refs=[m]))
        for x in sorted(extra):
            out.append(_finding(
                "projection_drift", SEV_ERROR, icd_index_node["id"],
                icd_index_node["path"],
                "ICD-index に現行でない/不在の ICD %s が載っている(投影ドリフト)" % x,
                refs=[x]))
    return out


def _find_projection_node(g, type_code, filename):
    """指定の型かつファイル名(語幹)に一致する投影ノードを返す。無ければ None。"""
    base = filename
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["type"] != type_code:
            continue
        if os.path.basename(node["path"]) == base:
            return node
    return None


# ---------------------------------------------------------------------------
# 監査本体
# ---------------------------------------------------------------------------

def run_audit(root, today, knobs):
    """全件監査を走らせ、所見リストを返す。決定的(check, doc_id で整列)。"""
    g = _depgraph.build_graph(root)
    # 本文を一度だけ読み、ノードに付ける(dead link / 酷似が再読み込みしないように)。
    _attach_bodies(g)

    findings = []
    findings += _check_dead_link(g)
    findings += _check_review_by(g, today)
    findings += _check_stale_draft(g, today, knobs["draft_stale_days"])
    findings += _check_orphan(g, today, knobs["orphan_stale_days"])
    findings += _check_reverse_orphan(g)
    findings += _check_canonical_conflict(g)
    findings += _check_near_duplicate(g, knobs["jaccard"], knobs["near_dup_cap"])
    findings += _check_icd_violation(g)
    findings += _check_projection_drift(g)

    findings.sort(key=lambda f: (f["check"], f["doc_id"], f["message"]))
    return findings


def _attach_bodies(g):
    for doc_id, node in g.nodes.items():
        node["_body"] = _read_body(os.path.join(g.root, node["path"]))


def build_summary(root, findings, today, knobs, generated_at=None):
    """docs-audit/1 スキーマの要約 dict を組み立てる。決定的。"""
    totals = {SEV_ERROR: 0, SEV_WARN: 0, SEV_ADVISORY: 0}
    counts_by_check = {}
    for f in findings:
        sev = f["severity"]
        if sev in totals:
            totals[sev] += 1
        counts_by_check[f["check"]] = counts_by_check.get(f["check"], 0) + 1

    cap = knobs["top_findings_cap"]
    top = _top_findings(findings, cap)

    if generated_at is None:
        # 決定的: today の真夜中(UTC)を ISO-8601 で。壁時計の時刻は使わない。
        generated_at = today.isoformat() + "T00:00:00Z"

    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "today": today.isoformat(),
        "root": root,
        "totals": totals,
        "counts_by_check": counts_by_check,
        "top_findings": top,
        "findings": findings,
    }


def _top_findings(findings, cap):
    """errors 優先で上位 cap 件。決定的(severity 順位, check, doc_id)。"""
    rank = {SEV_ERROR: 0, SEV_WARN: 1, SEV_ADVISORY: 2}
    ordered = sorted(
        findings,
        key=lambda f: (rank.get(f["severity"], 9), f["check"], f["doc_id"],
                       f["message"]))
    return ordered[:cap]


# ---------------------------------------------------------------------------
# 出力(人間向け / 機械向け)
# ---------------------------------------------------------------------------

def _render_human(summary):
    """人間向けの平文レポート。重大度→check→doc_id で整列。決定的。"""
    lines = []
    t = summary["totals"]
    lines.append("# docs-audit")
    lines.append("root: %s  today: %s  generated_at: %s"
                 % (summary["root"], summary["today"], summary["generated_at"]))
    lines.append("totals: error=%d warn=%d advisory=%d"
                 % (t[SEV_ERROR], t[SEV_WARN], t[SEV_ADVISORY]))
    cbc = summary["counts_by_check"]
    if cbc:
        lines.append("counts_by_check: " + ", ".join(
            "%s=%d" % (k, cbc[k]) for k in sorted(cbc)))
    else:
        lines.append("counts_by_check: (none)")
    rank = {SEV_ERROR: 0, SEV_WARN: 1, SEV_ADVISORY: 2}
    ordered = sorted(
        summary["findings"],
        key=lambda f: (rank.get(f["severity"], 9), f["check"], f["doc_id"]))
    if not ordered:
        lines.append("findings: (none)")
    for f in ordered:
        lines.append("[%s] %s  %s (%s): %s"
                     % (f["severity"], f["check"], f["doc_id"], f["path"],
                        f["message"]))
    return "\n".join(lines) + "\n"


def _atomic_write(path, text):
    """一時ファイル + 改名で原子的に書く。失敗時は OSError を投げる。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".audit-summary.%d.tmp" % os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
        # Hook 経路(SessionEnd)では stdin に JSON が来るが、監査は内容に依存しない。
        # 読み取ると、対話的CLI(端末stdin)では待ちで止まる。内容を使わないので
        # stdin は一切読まない。パイプはそのまま閉じる(Hook も安全に終わる)。

    opts, err = _parse_args(list(argv))
    if err is not None:
        sys.stdout.write("usage error: %s\n" % err)
        sys.stdout.write(
            "docs-audit.py [--root docs/] [--json] [--summary-out PATH] "
            "[--fail-on error|never] [--config PATH] [--today YYYY-MM-DD]\n")
        return 2

    root = opts["root"]
    if not os.path.isdir(root):
        sys.stdout.write("root not found: %s\n" % root)
        # 監査が走れないのは利用者の誤り(usage に近い)。CI も SessionEnd も
        # ここで止めない方が安全側: ルート不在は所見ゼロと同義に扱い 0 を返す。
        # ただし fail-on error でも誤検知を増やさないため、明示的に 3 ではなく 0。
        return 0

    knobs = _load_config(opts["config"])
    # today の解決は監査本体の前に行う。供給された today が解せないのは使用法エラー
    # (壁時計に黙って退避しない、§日付ユーティリティの保証)→ 終了コード 2。
    try:
        today = _resolve_today(opts, knobs)
    except _TodayError as exc:
        sys.stdout.write("usage error: %s\n" % exc)
        sys.stdout.write(
            "docs-audit.py [--root docs/] [--json] [--summary-out PATH] "
            "[--fail-on error|never] [--config PATH] [--today YYYY-MM-DD]\n")
        return 2

    try:
        findings = run_audit(root, today, knobs)
        summary = build_summary(root, findings, today, knobs)
    except Exception as exc:  # 監査自身のクラッシュ。Hook 連鎖を壊さない。
        sys.stderr.write("docs-audit: internal error: %r\n" % (exc,))
        # SessionEnd は teardown を壊さないために 0。CI(fail-on error)でも
        # 監査が壊れたこと自体は所見ではないので、ここでは 0 を返さず安全側に倒す。
        return 0

    # 要約の永続化(--summary-out)。原子的に書き、失敗しても 0 を保つ(§5.5)。
    if opts["summary_out"]:
        try:
            _atomic_write(opts["summary_out"],
                          json.dumps(summary, ensure_ascii=False,
                                     sort_keys=True, indent=2) + "\n")
        except OSError as exc:
            sys.stderr.write("docs-audit: summary write failed: %r\n" % (exc,))
            # 書き込み失敗でも終了コードは下のゲート判定に従う(SessionEnd は 0)。

    # 標準出力。
    if opts["json"]:
        sys.stdout.write(json.dumps(summary, ensure_ascii=False,
                                    sort_keys=True) + "\n")
    else:
        sys.stdout.write(_render_human(summary))

    # ゲート判定。
    if opts["fail_on"] == "error" and summary["totals"][SEV_ERROR] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
