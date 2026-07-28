#!/usr/bin/env python3
"""全件監査(SessionEnd/CI)。コーパス全体を走査し、所見と要約を出す(MASTER §5.5)。

保証限界:
- 予防: 何も予防しない。per-turn では走らない。SessionEnd と CI からだけ走る(§4.2)。
- 検出: dead link・review_by 超過(DECIDED/WATCH 含む)・draft 放置・孤児
  (逆参照ゼロ∧陳腐化∧再現可能)・逆孤児・canonical_for 衝突・語彙的酷似(助言)・
  ICD依存違反・投影ドリフト・未登録/影文書(docs/ 内で登録簿ノードにならない .md)を
  全件で一覧化する。
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
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _auditcache
import _frontmatter
import _intake
import _registry
import _termcheck
import _tracescan


SCHEMA = "docs-audit/1"

# この版の監査が走らせる検査の名前の一覧(#95。検証器の実行証跡)。要約に
# checks_run として載せ、読み手(注入・生存性)が期待する検査集合を知れるようにする。
# 検査を足す・消すときは本一覧を同じ変更で更新する(TEST が凍結する)。ある検査が
# 黙って消えても、この一覧と要約の差で見えるようにする(沈黙する検証器の禁止。R11)。
# doctrine:begin SPEC-011
AUDIT_CHECKS = (
    "dead_link", "dep_cycle", "review_by_overrun", "stale_draft", "orphan",
    "reverse_orphan_req_no_spec", "reverse_orphan_spec_no_test",
    "canonical_conflict", "near_duplicate", "icd_dependency_violation",
    "projection_drift", "unregistered_document", "shadowed_document",
    "stray_document", "stale_current", "source_drift", "archive_integrity",
    "adr_not_landed", "glossary_seed_drift", "ext_anchor_broken", "memory_shadow",
    "trace_mark_error", "trace_broken_ref", "trace_deprecated_ref",
    "trace_stale", "trace_missing_impl", "trace_marker_suspect",
    "trace_scan_truncated", "trace_unexpected_impl", "trace_undeclared_impl",
    "trace_exempt_conflict", "guard_liveness_gap",
)
# doctrine:end SPEC-011

# 既定の調整値(仕様に数値が無い。すべて --config で上書きできる。slice 05 C.6)。
DEFAULT_DRAFT_STALE_DAYS = 90       # draft 放置の閾値
DEFAULT_ORPHAN_STALE_DAYS = 180     # 孤児の陳腐化の閾値
DEFAULT_JACCARD = 0.8               # 語彙的酷似(助言)の閾値
DEFAULT_TOP_FINDINGS = 20           # top_findings の上限(errors 優先)
DEFAULT_NEAR_DUP_CAP = 50           # 酷似報告の上限
DEFAULT_NEAR_DUP_MAX_DOCS = 800     # 酷似の O(n^2) 走査を許す現行文書数の上限(超過なら走査を省き助言一つを出す)

# 重大度。
SEV_ERROR = "error"
SEV_WARN = "warn"
SEV_ADVISORY = "advisory"

# 本文中の id 参照トークン(<TYPE>-<NNN>)。dead link の本文走査に使う。
_ID_TOKEN_RE = re.compile(r"\b([A-Z]+-\d+)\b")
# 単語シングル化(語彙的酷似)。英数字連なり + 連続する非ASCII。
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\x00-\x7f]+")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


# ---------------------------------------------------------------------------
# 引数解析
# ---------------------------------------------------------------------------

def _parse_args(argv):
    """argv を (opts, error_message) に解く。"""
    opts = {
        "root": None,           # 明示指定。無ければ --root-from か cwd から解決。
        "root_from": None,      # プロジェクト根。locate_docs_root で統治木を解決。
        "json": False,
        "summary_out": None,
        "fail_on": "never",     # 既定は SessionEnd 想定(非ブロッキング)
        "config": None,
        "today": None,
        "respect_docs_level": False,
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
        if a == "--root-from":
            # プロジェクト根から統治木を解決する(ADR-022)。SessionEnd の配線用。
            if i + 1 >= n:
                return None, "--root-from にはパスが必要"
            opts["root_from"] = argv[i + 1]
            i += 2
            continue
        if a == "--json":
            opts["json"] = True
            i += 1
            continue
        if a == "--respect-docs-level":
            # 段差ゲート(ADR-019)。SessionEnd の配線だけが付ける。CI は付けず、
            # Level に依らず全件監査する。
            opts["respect_docs_level"] = True
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
        "near_dup_max_docs": DEFAULT_NEAR_DUP_MAX_DOCS,
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
    """1. dead link(R4)。frontmatter の id 参照 + 本文の id トークンが解決するか。"""
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


def _check_dep_cycle(g):
    """依存の循環(R3/R8)。ADR-038 / #89。

    depends_on の循環(自己依存 A→A、多頂点循環 A→B→C→A)を warn で挙げる。
    循環の全構成員は「現行の依存が残る」と判定され続けて降格できなくなる論理的
    デッドロックを生む。追跡性の階層に循環は本来あり得ないため、存在は
    モデル化誤りの兆候である。
    """
    out = []
    for cycle in g.find_cycles():
        if len(cycle) == 1:
            v = cycle[0]
            node = g.nodes.get(v, {})
            out.append(_finding(
                "dep_cycle", SEV_WARN, v, node.get("path", ""),
                "自己依存(depends_on が自分自身 %s を指す)。循環を断つこと" % v,
                refs=[v]))
        else:
            joined = " → ".join(cycle + [cycle[0]])
            head = cycle[0]
            node = g.nodes.get(head, {})
            out.append(_finding(
                "dep_cycle", SEV_WARN, head, node.get("path", ""),
                "depends_on の循環(%s)。全構成員が降格不能になる。循環を断つこと"
                % joined, refs=list(cycle)))
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
        if node["status"] == "archived":
            # アーカイブ済みは §3.8 の階段を終えた証跡。孤児(取り除き候補)に
            # 数えない(ADR-027。倉庫の中身を削除候補へ昇格させない)。
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


def _check_stale_current(g, today):
    """12. 陳腐化の疑い(R2, ADR-025)。型の既定点検周期で全現行文書に実効期限を張る。

    明示の review_by を持つ文書は review_by 検査(2)が見る。持たない現行文書は
    updated + 型既定周期(_registry.TYPE_REVIEW_CYCLE_DAYS)を実効期限とし、
    超過を warn で挙げる。周期の無い型(投影・ADR・DECIDED/WATCH 等)は対象外。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if not _registry.is_current(node["status"]):
            continue
        if node["review_by"]:
            continue  # 明示期限は review_by 検査が見る。
        cycle = _registry.review_cycle_days(node["type"])
        if cycle is None:
            continue
        d = _parse_date(node["updated"])
        overdue = (d is None) or ((today - d).days >= cycle)
        if overdue:
            out.append(_finding(
                "stale_current", SEV_WARN, doc_id, node["path"],
                "型 %s の既定点検周期 %d 日を超えた(updated %s)。内容を確かめて "
                "updated を更新するか、review_by を付ける(ADR-025)"
                % (node["type"], cycle, node["updated"] or "?")))
    return out


def _check_source_drift(g):
    """13. 上流更新の伝播(R2/R4)。依存先が自分より後に更新されていれば追随疑い。

    対象は現行の文書。ADR(不変の決定)と投影は対象外。判定は depends_on の
    端だけ(impacts は前向きの波及であり、上流ではない)。助言に留める
    (追随済みで updated だけ古い場合があるため。確認して updated を上げれば消える)。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if not _registry.is_current(node["status"]):
            continue
        t = node["type"]
        if t == "ADR" or _registry.is_projection(t):
            continue
        own = _parse_date(node["updated"])
        if own is None:
            continue  # updated 壊れは必須キー/陳腐化側の話。
        for dep in sorted(node["depends_on"]):
            target = g.nodes.get(dep)
            if target is None:
                continue  # dead link 検査が見る。
            td = _parse_date(target["updated"])
            if td is None:
                continue
            if td > own:
                out.append(_finding(
                    "source_drift", SEV_ADVISORY, doc_id, node["path"],
                    "上流 %s(updated %s)が %s(updated %s)より後に更新された。"
                    "追随したかを確かめ、確かめたら updated を上げる"
                    % (dep, target["updated"], doc_id, node["updated"]),
                    refs=[dep]))
    return out


def _check_archive_integrity(g):
    """14. アーカイブ整合(§3.8, ADR-027)。status:archived ⇔ <domain>/archive/。

    - archived なのに path が archive/ 配下でない → error(倉庫の外の archived)。
    - archived の非 RESEARCH に superseded_by が無い → advisory(後継の記録が無い。
      RESEARCH の証跡は後継を持たないことがあるため対象外)。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["status"] != "archived":
            continue
        parts = [p for p in node["path"].replace("\\", "/").split("/") if p]
        if "archive" not in parts[:-1]:
            out.append(_finding(
                "archive_integrity", SEV_ERROR, doc_id, node["path"],
                "status『archived』だが <domain>/archive/ の外に在る。"
                "倉庫へ移す(§3.8。不変ガードの保護もパスに掛かる)"))
        if node["type"] != "RESEARCH" and not node["superseded_by"]:
            out.append(_finding(
                "archive_integrity", SEV_ADVISORY, doc_id, node["path"],
                "アーカイブ済みだが superseded_by(後継の記録)が無い。"
                "後継が在るなら付ける(§3.8)"))
    return out


def _check_adr_not_landed(g):
    """15. ADR の帰結の着地(R3/R8)。accepted の ADR は現行文書から参照されること。

    「文書上の宣言に留まる」欠陥類型(ADR-019/020/014 で三度再発)を機械検出に
    変える。参照元に数えるのは、現行かつ ADR でも投影でもない文書の
    depends_on・impacts・superseded_by・本文の id 参照。どこからも参照されない
    accepted ADR は、決定が SPEC/ICD に落ちていない疑いとして warn。
    """
    referenced = set()
    for doc_id, node in g.nodes.items():
        if not _registry.is_current(node["status"]):
            continue
        t = node["type"]
        if t == "ADR" or _registry.is_projection(t):
            continue
        for field in ("depends_on", "impacts"):
            referenced.update(node[field])
        if node["superseded_by"]:
            referenced.add(node["superseded_by"])
        referenced |= _body_id_refs(g, node)
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["type"] != "ADR" or node["status"] != "accepted":
            continue
        if doc_id in referenced:
            continue
        out.append(_finding(
            "adr_not_landed", SEV_WARN, doc_id, node["path"],
            "accepted の %s を、現行の文書(ADR と投影を除く)が一つも参照して"
            "いない。決定を SPEC/ICD へ反映し、そこから引く(欠陥類型: "
            "文書上の宣言に留まる)" % doc_id))
    return out


_EXT_TARGET_RE = re.compile(r"対象[:：]\s*`([^`]+)`")
_EXT_CHECK_RE = re.compile(r"検査[:：]\s*(\S+)")


def _check_ext_anchors(g, root):
    """17. 外部アンカーの存在(ADR-026, R11)。EXT の対象が実在するかを検査する。

    本文の「- 対象: `<パス>`」を読み、「- 検査:」が exists を含むアンカーだけ、
    プロジェクト根(統治木の親)からの相対で存在を確かめる。URL と
    「review_by のみ」のアンカーは機械検査の対象外(期限の再検証は review_by
    検査が見る)。対象の行が無い EXT は書きかけとして warn。
    """
    out = []
    proj = os.path.dirname(os.path.abspath(root))
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["type"] != "EXT":
            continue
        if not _registry.is_current(node["status"]):
            continue
        body = node.get("_body")
        if body is None:
            body = _read_body(os.path.join(g.root, node["path"]))
        m = _EXT_TARGET_RE.search(body)
        if m is None:
            out.append(_finding(
                "ext_anchor_broken", SEV_WARN, doc_id, node["path"],
                "EXT に「対象: `<パス>`」の行が無い(アンカーが何も指していない)"))
            continue
        target = m.group(1).strip()
        cm = _EXT_CHECK_RE.search(body)
        check = cm.group(1) if cm else "exists"
        wants_exists = "exists" in check
        wants_hash = "hash" in check
        if not wants_exists and not wants_hash:
            continue  # review_by のみ は機械検査しない(期限は review_by 検査)。
        if target.startswith("http://") or target.startswith("https://"):
            continue  # 通信はしない(ADR-031)。URL は review_by で見る。
        abspath = target if os.path.isabs(target) else os.path.join(proj, target)
        if not os.path.exists(abspath):
            # exists でも hash でも、対象の不在は最も重い(error)。
            out.append(_finding(
                "ext_anchor_broken", SEV_ERROR, doc_id, node["path"],
                "外部アンカーの対象 %s が実在しない。依存先が消えたか動いた。"
                "対象を直すか、依存元とともに整理する(ADR-026)" % target,
                refs=[]))
            continue
        if wants_hash:
            out.extend(_check_ext_hash(doc_id, node, body, target, abspath))
    return out


_EXT_HASH_RE = re.compile(r"指紋[:：]\s*sha256:([0-9a-fA-F]{64})")


def _check_ext_hash(doc_id, node, body, target, abspath):
    """EXT の hash 検査(ADR-039, #70)。対象の sha256 を本文の期待値と照合する。

    本文に `- 指紋: sha256:<64桁>` があれば、対象ファイルの sha256 を計算して
    照合する。一致すれば無言、不一致は warn(内容が変わった。依存文書の追随を
    確かめよ)。期待値の行が無ければ warn(hash 指定だが期待値が無い=検査できない)。
    決して沈黙して素通りしない(旧実装は hash 指定を警告なく飛ばし、exists すら
    無効化していた)。
    """
    hm = _EXT_HASH_RE.search(body)
    if hm is None:
        return [_finding(
            "ext_anchor_broken", SEV_WARN, doc_id, node["path"],
            "EXT の検査に hash を指定したが、本文に期待値『- 指紋: sha256:<64桁>』"
            "が無い。期待値を書くか、検査を exists にする(ADR-039)")]
    expected = hm.group(1).lower()
    try:
        h = hashlib.sha256()
        with open(abspath, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
    except OSError:
        return [_finding(
            "ext_anchor_broken", SEV_WARN, doc_id, node["path"],
            "外部アンカーの対象 %s を読めず指紋を計算できない" % target)]
    if actual != expected:
        return [_finding(
            "ext_anchor_broken", SEV_WARN, doc_id, node["path"],
            "外部アンカーの対象 %s の内容が期待の指紋と一致しない(変わった)。"
            "依存文書が追随すべきか確かめ、確認後に指紋を更新する(ADR-039)。"
            "期待 sha256:%s… 実際 sha256:%s…"
            % (target, expected[:12], actual[:12]), refs=[])]
    return []


_TRACE_SECTION_RE = re.compile(r"(?m)^#{1,6}\s*実装の指紋\s*$")
_TRACE_FP_RE = re.compile(r"(?m)^\s*-\s*(sha256:[0-9a-fA-F]{64})\s*$")

# 印の対応付けの誤り(走査が返す code)。すべて error に畳む(ADR-056)。
_TRACE_MARK_CODES = frozenset({
    "trace_nested", "trace_id_mismatch", "trace_unclosed",
    "trace_unopened", "trace_empty_range"})


_TRACE_NOCODE_RE = re.compile(r"(?m)^\s*-\s*コード対応なし\s*[:：]")


def _trace_declaration(body):
    """本文の `## 実装の指紋` 節から、コードとの関係の宣言を読む(ADR-056/ADR-061)。

    節が無ければ None(未宣言。追跡の対象外)。`- コード対応なし: <理由>` の行が
    あれば {"kind": "none"}(意図してコードと結ばない明示宣言)。それ以外は
    {"kind": "fps", "fps": 指紋の集合}(節はあるが指紋の行が無ければ空集合 =
    対象だが記録が空)。
    """
    m = _TRACE_SECTION_RE.search(body or "")
    if m is None:
        return None
    tail = body[m.end():]
    nxt = re.search(r"(?m)^#{1,6}\s", tail)
    section = tail[:nxt.start()] if nxt else tail
    if _TRACE_NOCODE_RE.search(section):
        return {"kind": "none"}
    return {"kind": "fps",
            "fps": {fp.lower() for fp in _TRACE_FP_RE.findall(section)}}


def _check_guard_liveness(root):
    """拒否経路の欠落の疑い(ADR-062)。判定は _auditcache に一度だけ在る。

    ガード(PreToolUse)とリンタ(PostToolUse)の発火の印の食い違いを見る。
    印が無ければ何も出さない(CI や、古い版からの更新直後は印が育つまで沈黙
    する — 前方寛容)。advisory に留める(印は間接の証跡であり、拒否できない
    ことの直接の証明ではない)。
    """
    proj = os.path.dirname(os.path.abspath(root))
    gap = _auditcache.liveness_gap(_auditcache.read_stamps(proj))
    if gap is None:
        return []
    return [_finding(
        "guard_liveness_gap", SEV_ADVISORY, "",
        ".claude/.cache/" + _auditcache.STAMPS_NAME, gap)]


def _check_code_traces(g, root):
    """コードと仕様の追跡(ADR-056、SPEC-026)。

    `## 実装の指紋` の節を持つ文書が一つでもあるときだけ効く。門は節の有無だけで
    判じ、状態を問わない(ADR-060)。節を持つ文書が一つも無ければ、コードの走査
    そのものを行わない(使っていない機能の費用を払わせない)。上向きの検査
    (注釈→文書)は走査が走れば常に効き、下向きの照合(記録した指紋)は現行の
    文書だけに掛ける。「根拠を持たないコード」は挙げない — 注釈は任意であり、
    原理的に判じられない(ADR-054 の既知の限界)。
    """
    # 走査の門は「節の有無」だけで判じ、状態を問わない(ADR-060)。廃止された
    # 仕様だけが opt-in している木でも、上向きの検査(注釈への warn)は生きる。
    # 以前は現行の opt-in に門を掛けており、opt-in した仕様の廃止が「廃止を
    # 指す注釈」の検査そのものを殺す自己矛盾があった。
    sections = {}   # doc_id -> 宣言(状態を問わない)
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        decl = _trace_declaration(node.get("_body") or "")
        if decl is not None:
            sections[doc_id] = decl
    if not sections:
        return [], None   # 節を持つ文書が無い → 走査しない(ADR-056 の静けさ)

    # 下向きの照合は現行の文書だけに掛ける(現行でない記録は歴史。ADR-060)。
    expect = {doc_id: decl for doc_id, decl in sections.items()
              if _registry.is_current(g.nodes[doc_id].get("status", ""))}

    scan_root = os.path.dirname(os.path.abspath(root))
    try:
        ranges, scan_findings, coverage = _tracescan.scan_tree(
            scan_root, docs_root=root)
    except Exception:
        return [], None   # 走査で監査を落とさない

    out = []
    for f in scan_findings:
        if f["code"] in _TRACE_MARK_CODES:
            out.append(_finding(
                "trace_mark_error", SEV_ERROR, "", f["path"],
                "%s(%d 行目)。印の対を直す(SPEC-026)" % (f["message"], f["line"])))
        elif f["code"] == "trace_marker_suspect":
            # 打ったつもりの印の兆候(ADR-059)。誤検出がありうるので advisory。
            out.append(_finding(
                "trace_marker_suspect", SEV_ADVISORY, "", f["path"],
                "%s(%d 行目)" % (f["message"], f["line"])))
        elif f["code"] == "trace_scan_truncated":
            # 走査が告げた切り詰めを読み手が握らない(ADR-059)。
            out.append(_finding(
                "trace_scan_truncated", SEV_ADVISORY, "", f["path"],
                f["message"]))
        elif f["code"] == "trace_exempt_conflict":
            # 統治外の宣言と実態の矛盾(ADR-067)。宣言したファイルにしか
            # 発火しない(版を上げただけの利用者には何も起きない)。
            out.append(_finding(
                "trace_exempt_conflict", SEV_WARN, "", f["path"],
                "%s(%d 行目)" % (f["message"], f["line"])))

    by_id = {}
    for r in ranges:
        by_id.setdefault(r["id"], []).append(r)

    # 注釈が指す先の不備(上向き)。
    for doc_id in sorted(by_id):
        where = by_id[doc_id][0]["path"]
        node = g.nodes.get(doc_id)
        if node is None:
            out.append(_finding(
                "trace_broken_ref", SEV_ERROR, doc_id, where,
                "注釈が実在しない id %s を指している。id を直すか印を消す" % doc_id))
        elif not _registry.is_current(node.get("status", "")):
            out.append(_finding(
                "trace_deprecated_ref", SEV_WARN, doc_id, where,
                "注釈が %s の id %s を指している。後継へ張り替えるか印を消す"
                % (node.get("status", "?"), doc_id)))

    # 記録した確認との照合(下向き)。
    for doc_id in sorted(expect):
        decl = expect[doc_id]
        found = by_id.get(doc_id, [])
        node = g.nodes[doc_id]
        if decl["kind"] == "none":
            # 「コード対応なし」の宣言と実態の矛盾(ADR-061)。宣言した文書に
            # しか発火しないので、版を上げただけの利用者には何も起きない。
            if found:
                out.append(_finding(
                    "trace_unexpected_impl", SEV_WARN, doc_id, node["path"],
                    "「コード対応なし」と宣言しているが、この仕様を指す範囲が"
                    "コードにある(%s)。宣言が古いか注釈が誤り。宣言を指紋の"
                    "記録に替えるか、印を消す(ADR-061)"
                    % ", ".join(sorted(r["path"] for r in found))))
            continue
        recorded = decl["fps"]
        if not found:
            out.append(_finding(
                "trace_missing_impl", SEV_WARN, doc_id, node["path"],
                "実装の指紋を記録しているが、対応する範囲がコードに一つも無い。"
                "印を打つか、節を消して追跡の対象から外す(ADR-056)"))
            continue
        actual = {r["fingerprint"].lower() for r in found}
        if actual != recorded:
            out.append(_finding(
                "trace_stale", SEV_WARN, doc_id, node["path"],
                "記録した実装の指紋と、いまのコードの指紋が食い違う(%s)。"
                "変更を確かめ、確認したら節の指紋を更新する"
                % ", ".join(sorted(r["path"] for r in found))))

    # 欠陥D(ADR-061): 節の無い現行の SPEC を、コードの範囲が指している。
    # 節を消して注釈だけ残った/節を書かずに注釈だけ打った紐の可視化。合否は
    # 変えない(advisory)。現行でない文書は上の trace_deprecated_ref が指す。
    for doc_id in sorted(by_id):
        if doc_id in sections:
            continue
        node = g.nodes.get(doc_id)
        if node is None or not _registry.is_current(node.get("status", "")):
            continue
        if node.get("type") != "SPEC":
            continue
        out.append(_finding(
            "trace_undeclared_impl", SEV_ADVISORY, doc_id, node["path"],
            "コードの範囲(%s)がこの仕様を指しているが、仕様は実装の指紋の節を"
            "持たない。指紋を記録して追跡を結ぶか、「コード対応なし」を宣言する"
            "(ADR-061)" % ", ".join(sorted(r["path"] for r in by_id[doc_id]))))

    # 仕様側の三分類(ADR-061)。現行の SPEC がコードとの関係を宣言しているかを
    # 数える。無宣言は数えるだけで所見にしない(義務化は別の ADR)。
    if coverage is not None:
        spec_cov = {"traced": 0, "no_code": 0, "undeclared": 0}
        next_undeclared = None
        for doc_id in sorted(g.nodes):
            node = g.nodes[doc_id]
            if node.get("type") != "SPEC":
                continue
            if not _registry.is_current(node.get("status", "")):
                continue
            decl = sections.get(doc_id)
            if decl is None:
                spec_cov["undeclared"] += 1
                if next_undeclared is None:
                    # キャンペーン(ADR-065)が運ぶ「次の一件」。整列順の先頭で
                    # 決定的。一覧は載せない(要約を肥やさない)。
                    next_undeclared = doc_id
            elif decl["kind"] == "none":
                spec_cov["no_code"] += 1
            else:
                spec_cov["traced"] += 1
        if next_undeclared is not None:
            spec_cov["next_undeclared"] = next_undeclared
        coverage["spec_coverage"] = spec_cov
    return out, coverage


def _check_memory_shadow(g, root):
    """18. メモリの影(R8, ADR-035)。ハーネスのメモリが統治文書に言及していたら点検を促す。

    メモリの置き場は CLAUDE_CONFIG_DIR(無ければ ~/.claude)/projects/<プロジェクト根の
    絶対パスの / を - に置換した名前>/memory/。無ければ何も出さない(CI では通常無い)。
    中身の真偽・矛盾の判定はしない(§7)。統治文書への言及の検出まで(advisory)。
    メモリを統治はしない(中身は写さない・強制しない)。影の正本化だけを見張る。
    """
    out = []
    proj = os.path.dirname(os.path.abspath(root))
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    munged = proj.replace("\\", "/").replace("/", "-")
    mdir = os.path.join(cfg, "projects", munged, "memory")
    if not os.path.isdir(mdir):
        return out
    try:
        names = sorted(os.listdir(mdir))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".md") or name == "MEMORY.md":
            continue
        body = _read_body(os.path.join(mdir, name))
        ids = sorted({m.group(1) for m in _ID_TOKEN_RE.finditer(body)
                      if m.group(1) in g.nodes})
        if ids:
            out.append(_finding(
                "memory_shadow", SEV_ADVISORY, "", "memory/" + name,
                "ハーネスのメモリ %s が統治文書(%s)に言及している。正本と矛盾して"
                "いないか点検し、残すべき事実は正本(DECIDED・ADR)へ移す(ADR-035)"
                % (name, ", ".join(ids[:5]))))
    return out


def _check_glossary_seed(root):
    """16. 辞書シードの退行(R6, ADR-005)。運用正本 ⊇ 同梱シードを機械で守る。

    運用正本(<root>/_system/glossary.md)が同梱テンプレートのシードに在る
    承認語・カルク行を落としていたら warn(シードからの成長は正しい。欠落は退行)。
    運用正本が無い・読めないときは何も出さない(シードで運用中)。
    """
    out = []
    try:
        op = _termcheck.load_glossary(root)
    except Exception:
        return out
    if op is None or getattr(op, "source", "") != "operational":
        return out
    try:
        seed = _termcheck._load_template_seed()
    except Exception:
        return out
    if seed is None or getattr(seed, "parse_error", False):
        return out
    missing_terms = sorted(set(seed.approved_terms) - set(op.approved_terms))
    if missing_terms:
        out.append(_finding(
            "glossary_seed_drift", SEV_WARN, "", "_system/glossary.md",
            "運用正本の承認語の表からシードの語が欠けている: %s(シードは最小集合。"
            "落とすなら ADR で決める)" % ", ".join(missing_terms[:10])))
    seed_calques = {s for s, _f, _e in seed.calque_table}
    op_calques = {s for s, _f, _e in op.calque_table}
    missing_calques = sorted(seed_calques - op_calques)
    if missing_calques:
        out.append(_finding(
            "glossary_seed_drift", SEV_WARN, "", "_system/glossary.md",
            "運用正本のカルク表からシードの行が欠けている: %s"
            % ", ".join(missing_calques[:10])))
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


def _check_near_duplicate(g, jaccard_threshold, cap, max_docs):
    """7. 語彙的酷似(助言)。現行文書対の Jaccard が閾値以上。

    トークンのシングル集合(unigram)の Jaccard。標準ライブラリのみ。
    決定的: doc_id の組で整列、上限で切る。常に advisory。

    規模ガード: 走査は O(n^2)。現行文書数が max_docs を超えたら対走査を
    省き、省いた事実を助言一つで正直に告げる(黙って切り詰めない)。
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
    if len(ids) > max_docs:
        out.append(_finding(
            "near_duplicate", SEV_ADVISORY, "", "",
            "現行文書 %d 件が規模上限 %d を超えたため語彙的酷似の走査を省いた。"
            "near_dup_max_docs を上げるか対象を絞って再実行する" % (len(ids), max_docs)))
        return out
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

    ctx_node = _find_projection_node(g, "CTXMAP", "context-map.md")
    if ctx_node is not None:
        out += _ctxmap_drift(g, ctx_node)
    return out


_CTX_BEGIN = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
_CTX_END = "<!-- END PROJECTION:context-map-skeleton -->"
_CTX_DOMAIN_RE = re.compile(r"^- (\S+): (.+)$")
_CTX_EDGE_RE = re.compile(r"^- (\S+) --depends_on--> (\S+?)( \(境界違反\))?$")


def _ctxmap_drift(g, node):
    """Context Map の印内骨格を再導出と突き合わせる(ICD-005)。

    構造の差(ドメインの過不足・ドメイン越え依存端の過不足)→ error。
    ラベルの差(ドメイン行の ICD 列挙、端の境界違反マーク)→ warn。
    導出は render-projection の骨格描画と同じ規則(ドメイン集合、
    ドメイン越え depends_on の ICD 端と違反端)を内部で再現する。
    """
    out = []
    body = _read_body(os.path.join(g.root, node["path"]))
    if _CTX_BEGIN not in body:
        out.append(_finding(
            "projection_drift", SEV_ERROR, node["id"], node["path"],
            "Context Map に描画の印の区間が無い(未描画。render-projection で描く)"))
        return out
    region = body.split(_CTX_BEGIN, 1)[1]
    if _CTX_END in region:
        region = region.split(_CTX_END, 1)[0]

    # 期待: ドメイン → ICD 列挙、ドメイン越え depends_on 端(違反マーク付き)。
    expected_domains = {}
    for doc_id in sorted(g.nodes):
        n = g.nodes[doc_id]
        dom = n["domain"] or _depgraph.UNKNOWN
        expected_domains.setdefault(dom, [])
        if n["type"] == "ICD":
            expected_domains[dom].append(doc_id)
    expected_edges = {}
    for e in g.classify_edges():
        if e["field"] != "depends_on":
            continue
        if e["kind"] == _depgraph.KIND_CROSS_ICD:
            expected_edges[(e["src"], e["dst"])] = False
        elif e["kind"] == _depgraph.KIND_CROSS_VIOLATION:
            expected_edges[(e["src"], e["dst"])] = True

    have_domains = {}
    have_edges = {}
    for raw in region.splitlines():
        line = raw.strip()
        m = _CTX_EDGE_RE.match(line)
        if m:
            have_edges[(m.group(1), m.group(2))] = bool(m.group(3))
            continue
        m = _CTX_DOMAIN_RE.match(line)
        if m:
            have_domains[m.group(1)] = m.group(2).strip()

    for dom in sorted(set(expected_domains) - set(have_domains)):
        out.append(_finding(
            "projection_drift", SEV_ERROR, node["id"], node["path"],
            "Context Map にドメイン %s の項目が無い(投影ドリフト)" % dom))
    for dom in sorted(set(have_domains) - set(expected_domains)):
        out.append(_finding(
            "projection_drift", SEV_ERROR, node["id"], node["path"],
            "Context Map に存在しないドメイン %s が載っている(投影ドリフト)" % dom))
    for dom in sorted(set(expected_domains) & set(have_domains)):
        icds = sorted(expected_domains[dom])
        want = ", ".join(icds) if icds else "(ICD 未公開)"
        if have_domains[dom] != want:
            out.append(_finding(
                "projection_drift", SEV_WARN, node["id"], node["path"],
                "Context Map のドメイン %s の ICD 列挙がずれている(ラベル差)" % dom))
    for src, dst in sorted(set(expected_edges) - set(have_edges)):
        out.append(_finding(
            "projection_drift", SEV_ERROR, node["id"], node["path"],
            "Context Map にドメイン越えの依存 %s→%s が無い(投影ドリフト)" % (src, dst),
            refs=[src, dst]))
    for src, dst in sorted(set(have_edges) - set(expected_edges)):
        out.append(_finding(
            "projection_drift", SEV_ERROR, node["id"], node["path"],
            "Context Map に存在しない依存 %s→%s が載っている(投影ドリフト)" % (src, dst),
            refs=[src, dst]))
    for key in sorted(set(expected_edges) & set(have_edges)):
        if expected_edges[key] != have_edges[key]:
            out.append(_finding(
                "projection_drift", SEV_WARN, node["id"], node["path"],
                "Context Map の依存 %s→%s の境界違反マークがずれている(ラベル差)"
                % key))
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


def _check_unregistered(g):
    """10. 未登録/影文書(R1/R8)。docs/ 内の .md が登録簿ノードにならない二経路。

    他の全検査は g.nodes 上の述語なので、ノードにならないファイルはどの検査からも
    見えない。build_graph が既に埋めている二つのリストを読むだけで、新たな走査は
    しない(スケール無依存・決定的)。
    - parse_warnings: frontmatter か id が無く、どのノードにもならなかった .md。
    - dup_ids: 同じ id を持つ別ファイル。一つだけがノードになり、残りは影に隠れて
      見えない(採用先は _registry.resolve_duplicate_id が定める。先勝ち。ADR-049)。
    どちらも取り除きではなく、型を与えて登録するか archive/ へ退避する候補。
    未登録は登録簿に id が無いので doc_id は空文字にする(整列キーが str のため)。
    """
    out = []
    for relpath in sorted(g.parse_warnings):
        out.append(_finding(
            "unregistered_document", SEV_ERROR, "", relpath,
            "docs/ 内の .md にフロントマターと id が無く、登録されない。"
            "型を与えて登録するか archive/ へ退避する。"))
    for doc_id in sorted(g.dup_ids):
        paths = sorted(g.dup_ids[doc_id])
        # 採用先は登録簿の規則から引く(ADR-049)。案内が告げる採用先と、グラフ・注入が
        # 実際に採る文書を一致させる。
        keep = _registry.resolve_duplicate_id(paths)
        for shadowed in [p for p in paths if p != keep]:
            out.append(_finding(
                "shadowed_document", SEV_ERROR, doc_id, shadowed,
                "id %s が既存文書と衝突し、登録されず影に隠れている(採用 %s)。"
                "別 id を与えるか archive/ へ退避する。" % (doc_id, keep)))
    return out


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
    findings += _check_dep_cycle(g)
    findings += _check_review_by(g, today)
    findings += _check_stale_draft(g, today, knobs["draft_stale_days"])
    findings += _check_orphan(g, today, knobs["orphan_stale_days"])
    findings += _check_reverse_orphan(g)
    findings += _check_canonical_conflict(g)
    findings += _check_near_duplicate(g, knobs["jaccard"], knobs["near_dup_cap"], knobs["near_dup_max_docs"])
    findings += _check_icd_violation(g)
    findings += _check_projection_drift(g)
    findings += _check_unregistered(g)
    findings += _check_stray_documents(root, today)
    findings += _check_stale_current(g, today)
    findings += _check_source_drift(g)
    findings += _check_archive_integrity(g)
    findings += _check_adr_not_landed(g)
    findings += _check_glossary_seed(root)
    findings += _check_ext_anchors(g, root)
    findings += _check_memory_shadow(g, root)
    findings += _check_guard_liveness(root)
    trace_findings, trace_coverage = _check_code_traces(g, root)
    findings += trace_findings

    # 停滞の勘定(ADR-065)。直前の要約と比べ、印なし+未宣言の和が動かない監査が
    # 続いた回数を数える。読むのは監査自身の前回成果物だけで、環境変数に依存
    # しない(試験と CI で決定的にするため、パスは監査対象の木の親から導く)。
    if trace_coverage is not None:
        prev = None
        try:
            ppath = os.path.join(
                os.path.dirname(os.path.abspath(root)),
                ".claude", ".cache", "last-audit.json")
            with open(ppath, "r", encoding="utf-8-sig") as fh:
                cand = json.load(fh)
            if (isinstance(cand, dict)
                    and cand.get("schema") == _auditcache.SCHEMA
                    and _auditcache.same_root(cand.get("root"), root)):
                prev = cand
        except Exception:
            prev = None

        def _open_total(cov):
            sc = cov.get("spec_coverage")
            und = sc.get("undeclared", 0) if isinstance(sc, dict) else 0
            unm = cov.get("unmarked_files", 0)
            try:
                return int(unm) + int(und)
            except (TypeError, ValueError):
                return 0

        streak = 0
        prev_cov = prev.get("trace_coverage") if isinstance(prev, dict) else None
        if isinstance(prev_cov, dict):
            cur = _open_total(trace_coverage)
            if cur > 0 and cur == _open_total(prev_cov):
                ps = prev_cov.get("stagnation_streak")
                streak = (ps if isinstance(ps, int) and ps >= 0 else 0) + 1
        trace_coverage["stagnation_streak"] = streak

    findings.sort(key=lambda f: (f["check"], f["doc_id"], f["message"]))
    return findings, trace_coverage


# ---------------------------------------------------------------------------
# 11. 体系外 .md(ADR-021)。docs/ の外の .md を分類の記録と突き合わせる。
# ---------------------------------------------------------------------------

# 記録の読み取り・照合は共有コア _intake に一本化する(ADR-024)。リンタと
# 同じコードで読むことで、同じファイルへの分類が食い違うのを構造的に防ぐ。
_INTAKE_LEDGER = _intake.LEDGER_NAME
_STRAY_SKIP_DIRS = ("node_modules", "__pycache__")
_STRAY_LIST_CAP = 50


def _load_intake_ledger(root):
    """共有コアに委ねる。(entries, bad_lines) を返す。"""
    return _intake.load_ledger(root)


def _ledger_entry_for(relpath, entries):
    """共有コアに委ねる。relpath に効く記録の項目、無ければ None。"""
    return _intake.entry_for(relpath, entries)


def _check_stray_documents(root, today):
    """11. 体系外 .md(ADR-021, R1/R8)。

    docs ルートの親(=プロジェクト根)から .md を走査し、次だけを挙げる。
    ①登録簿の型を持つ .md → warn(置き場所の誤り)
    ②分類の記録に無い .md → advisory(未分類。external-md-intake へ)
    ③期限を過ぎた「保留」 → warn(再浮上)
    ④実在しないパスを指す記録の項目 → advisory(掃除の合図)
    dot ディレクトリ・node_modules・__pycache__ と、監査対象の docs ルート
    自身は走査しない。決定的(整列走査)。一覧は上限で正直に切り詰める。
    """
    out = []
    docs_root = os.path.abspath(root)
    proj = os.path.dirname(docs_root)
    if not proj or proj == docs_root or not os.path.isdir(proj):
        return out
    entries, bad_lines = _load_intake_ledger(root)
    for lineno, line in bad_lines:
        out.append(_finding(
            "stray_document", SEV_ADVISORY, "", "_system/" + _INTAKE_LEDGER,
            "分類の記録の %d 行目が読めない(『パス: 非文書|投影|保留 日付』の形): %s"
            % (lineno, line[:80])))

    strays = []
    for dirpath, dirnames, filenames in os.walk(proj):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d not in _STRAY_SKIP_DIRS
            and os.path.abspath(os.path.join(dirpath, d)) != docs_root)
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            abspath = os.path.join(dirpath, name)
            rel = os.path.relpath(abspath, proj).replace(os.sep, "/")
            strays.append((rel, abspath))
    strays.sort()

    seen_rel = set()
    listed = 0
    for rel, abspath in strays:
        seen_rel.add(rel)
        if rel in _registry.ROOT_POINTER_FILES:
            # 根の案内(CLAUDE.md/AGENTS.md)は仕様がプロジェクト根に置くと
            # 定める投影(§3.7/§5)。未分類として挙げない。
            continue
        try:
            fm, _body, _errs = _frontmatter.parse_file(abspath)
        except (OSError, UnicodeError):
            continue
        type_code = fm.get("type")
        typed = isinstance(type_code, str) and _registry.is_known_type(type_code)
        entry = _ledger_entry_for(rel, entries)
        if typed:
            out.append(_finding(
                "stray_document", SEV_WARN, _coerce_id(fm), rel,
                "登録簿の型 %s を持つ文書が docs/ の外に在る。doc-author で "
                "docs/<domain>/ の置き場所へ移すか、型を外す" % type_code))
            continue
        if entry is None:
            if listed < _STRAY_LIST_CAP:
                out.append(_finding(
                    "stray_document", SEV_ADVISORY, "", rel,
                    "統治木の外の .md が未分類。docs-curate(external-md-intake)"
                    "で三分類し %s/_system/%s へ記録する"
                    % (os.path.basename(docs_root), _INTAKE_LEDGER)))
                listed += 1
            continue
        _epath, kind, due = entry
        if kind == "保留" and due is not None and _parse_date(due) is not None \
                and _parse_date(due) < today:
            out.append(_finding(
                "stray_document", SEV_WARN, "", rel,
                "保留の期限(%s)を過ぎた。取り込むか、非文書と決めて記録を更新する"
                % due))
    if listed >= _STRAY_LIST_CAP:
        over = sum(1 for rel, _a in strays
                   if _ledger_entry_for(rel, entries) is None) - listed
        if over > 0:
            out.append(_finding(
                "stray_document", SEV_ADVISORY, "", "_system/" + _INTAKE_LEDGER,
                "未分類の一覧を %d 件で切り詰めた(残り %d 件。黙って隠さない)"
                % (_STRAY_LIST_CAP, over)))

    for path, kind, _due in entries:
        if path.endswith("/"):
            if not os.path.isdir(os.path.join(proj, path.rstrip("/"))):
                out.append(_finding(
                    "stray_document", SEV_ADVISORY, "",
                    "_system/" + _INTAKE_LEDGER,
                    "分類の記録が実在しない場所 %s を指している(記録を掃除する)"
                    % path))
        elif path not in seen_rel and not os.path.isfile(os.path.join(proj, path)):
            out.append(_finding(
                "stray_document", SEV_ADVISORY, "", "_system/" + _INTAKE_LEDGER,
                "分類の記録が実在しないファイル %s を指している(記録を掃除する)"
                % path))
    return out


def _coerce_id(fm):
    v = fm.get("id")
    return v if isinstance(v, str) else ""


def _attach_bodies(g):
    for doc_id, node in g.nodes.items():
        node["_body"] = _read_body(os.path.join(g.root, node["path"]))


def build_summary(root, findings, today, knobs, generated_at=None,
                  trace_coverage=None):
    """docs-audit/1 スキーマの要約 dict を組み立てる。決定的。

    trace_coverage は走査が走ったときだけ渡る勘定(ADR-058)。None なら載せない
    (opt-in が無く走査していない)。キーの追加であり schema は据え置く — 読み手
    (注入・鼓動)は未知のキーを無視する前方寛容を持つ。
    """
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

    out = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "today": today.isoformat(),
        # root は絶対パスに正規化して書く。読む側(inject-contract)は相対 root を
        # 照合不能として捨てるため(越境注入の防止)、相対のまま書くと正当な
        # 要約まで「前回監査なし」に劣化する。
        "root": os.path.abspath(root),
        "totals": totals,
        "counts_by_check": counts_by_check,
        # この版が走らせた検査の一覧(#95。検証器の実行証跡)。counts_by_check は
        # 所見のある検査しか載らないため、0 件の検査と「走らなかった検査」を
        # 区別できない。checks_run は走った検査集合を明示し、黙って消えた検査を
        # 読み手が見つけられるようにする(R11)。
        "checks_run": list(AUDIT_CHECKS),
        "top_findings": top,
        "findings": findings,
    }
    if trace_coverage is not None:
        # 走査の勘定(ADR-058)。何を見て何を見なかったかを数として毎回残す。
        out["trace_coverage"] = trace_coverage
    return out


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
            "docs-audit.py [--root PATH | --root-from PROJ] [--json] "
            "[--summary-out PATH] [--fail-on error|never] [--config PATH] "
            "[--today YYYY-MM-DD] [--respect-docs-level]\n")
        return 2

    root = opts["root"]
    if root is None and opts["root_from"]:
        # プロジェクト根から統治木を解決(ADR-022): doctrine_docs 優先、docs は
        # _system を持つ場合だけ。素の docs は他所の土地なので監査しない。
        root = _registry.locate_docs_root(opts["root_from"])
        if root is None:
            sys.stdout.write(
                "統治木なし: %s(doctrine_docs も docs/_system も無い)。飛ばした。\n"
                % opts["root_from"])
            return 0
    if root is None:
        root = _registry.locate_docs_root(os.getcwd()) or _registry.DOCS_DIR_NAMES[0]
    if not os.path.isdir(root):
        sys.stdout.write("root not found: %s\n" % root)
        # 監査が走れないのは利用者の誤り(usage に近い)。CI も SessionEnd も
        # ここで止めない方が安全側: ルート不在は所見ゼロと同義に扱い 0 を返す。
        # ただし fail-on error でも誤検知を増やさないため、明示的に 3 ではなく 0。
        return 0

    if opts["respect_docs_level"] and _registry.docs_level(root) < 3:
        # 段差ゲート(ADR-019): Level 2 に全件監査は無い(Level 3 から)。要約も
        # 書かない(前回要約を古いまま残すより、無い方が正直)。
        sys.stdout.write("docs-level 2: 全件監査は Level 3 から。飛ばした。\n")
        return 0

    knobs = _load_config(opts["config"])
    # today の解決は監査本体の前に行う。供給された today が解せないのは使用法エラー
    # (壁時計に黙って退避しない、§日付ユーティリティの保証)→ 終了コード 2。
    try:
        today = _resolve_today(opts, knobs)
    except _TodayError as exc:
        sys.stdout.write("usage error: %s\n" % exc)
        sys.stdout.write(
            "docs-audit.py [--root PATH | --root-from PROJ] [--json] "
            "[--summary-out PATH] [--fail-on error|never] [--config PATH] "
            "[--today YYYY-MM-DD] [--respect-docs-level]\n")
        return 2

    try:
        findings, trace_coverage = run_audit(root, today, knobs)
        summary = build_summary(root, findings, today, knobs,
                                trace_coverage=trace_coverage)
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
