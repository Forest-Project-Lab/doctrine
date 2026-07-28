#!/usr/bin/env python3
"""監査の追跡系検査(ADR-069 の移送先。挙動は docs-audit に在った頃と同一)。

コードと仕様の追跡(ADR-056/SPEC-026)の検査群と、仕様側の宣言(ADR-061)・
勘定への三分類・停滞計(ADR-065)を持つ。検査の名前と重大度・決定性は
ADR-069 が凍結しており、この移送で変えていない。

呼び手(docs-audit)が所見の工場 make_finding(check, severity, doc_id, path,
message) を渡す。共有コアは入口を取り込まない(ADR-068 の import 境界)ため、
所見の形の正本は入口側に残し、ここは組み立てを依頼するだけにする。

標準ライブラリのみ。決して例外を外へ出さない(走査の失敗は「無し」に畳む)。
"""
import json
import os
import re

import _auditcache
import _registry
import _tracescan

_ERROR, _WARN, _ADVISORY = "error", "warn", "advisory"

_TRACE_SECTION_RE = re.compile(r"(?m)^#{1,6}\s*実装の指紋\s*$")
_TRACE_FP_RE = re.compile(r"(?m)^\s*-\s*(sha256:[0-9a-fA-F]{64})\s*$")

# 印の対応付けの誤り(走査が返す code)。すべて error に畳む(ADR-056)。
_TRACE_MARK_CODES = frozenset({
    "trace_nested", "trace_id_mismatch", "trace_unclosed",
    "trace_unopened", "trace_empty_range"})

_TRACE_NOCODE_RE = re.compile(r"(?m)^\s*-\s*コード対応なし\s*[:：]")


def trace_declaration(body):
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


def _gate_sections(g):
    """走査の門(ADR-060)。節を持つ文書の宣言を集める。状態を問わない。"""
    sections = {}
    for doc_id in sorted(g.nodes):
        decl = trace_declaration(g.nodes[doc_id].get("_body") or "")
        if decl is not None:
            sections[doc_id] = decl
    return sections


def _fold_scan_findings(scan_findings, mk):
    """走査の所見を監査の検査名へ畳む(ADR-056/059/067)。"""
    out = []
    for f in scan_findings:
        if f["code"] in _TRACE_MARK_CODES:
            out.append(mk("trace_mark_error", _ERROR, "", f["path"],
                          "%s(%d 行目)。印の対を直す(SPEC-026)"
                          % (f["message"], f["line"])))
        elif f["code"] == "trace_marker_suspect":
            # 打ったつもりの印の兆候(ADR-059)。誤検出がありうるので advisory。
            out.append(mk("trace_marker_suspect", _ADVISORY, "", f["path"],
                          "%s(%d 行目)" % (f["message"], f["line"])))
        elif f["code"] == "trace_scan_truncated":
            # 走査が告げた切り詰めを読み手が握らない(ADR-059)。
            out.append(mk("trace_scan_truncated", _ADVISORY, "", f["path"],
                          f["message"]))
        elif f["code"] == "trace_exempt_conflict":
            # 統治外の宣言と実態の矛盾(ADR-067)。宣言したファイルにしか
            # 発火しない(版を上げただけの利用者には何も起きない)。
            out.append(mk("trace_exempt_conflict", _WARN, "", f["path"],
                          "%s(%d 行目)" % (f["message"], f["line"])))
    return out


def _upward(by_id, g, mk):
    """注釈が指す先の不備(上向き)。走査が走れば常に効く(ADR-060)。"""
    out = []
    for doc_id in sorted(by_id):
        where = by_id[doc_id][0]["path"]
        node = g.nodes.get(doc_id)
        if node is None:
            out.append(mk("trace_broken_ref", _ERROR, doc_id, where,
                          "注釈が実在しない id %s を指している。id を直すか"
                          "印を消す" % doc_id))
        elif not _registry.is_current(node.get("status", "")):
            out.append(mk("trace_deprecated_ref", _WARN, doc_id, where,
                          "注釈が %s の id %s を指している。後継へ張り替えるか"
                          "印を消す" % (node.get("status", "?"), doc_id)))
    return out


def _downward(expect, by_id, g, mk):
    """記録した確認との照合(下向き)。現行の文書だけに掛ける(ADR-060/061)。"""
    out = []
    for doc_id in sorted(expect):
        decl = expect[doc_id]
        found = by_id.get(doc_id, [])
        node = g.nodes[doc_id]
        if decl["kind"] == "none":
            # 「コード対応なし」の宣言と実態の矛盾(ADR-061)。宣言した文書に
            # しか発火しない。
            if found:
                out.append(mk(
                    "trace_unexpected_impl", _WARN, doc_id, node["path"],
                    "「コード対応なし」と宣言しているが、この仕様を指す範囲が"
                    "コードにある(%s)。宣言が古いか注釈が誤り。宣言を指紋の"
                    "記録に替えるか、印を消す(ADR-061)"
                    % ", ".join(sorted(r["path"] for r in found))))
            continue
        if not found:
            out.append(mk(
                "trace_missing_impl", _WARN, doc_id, node["path"],
                "実装の指紋を記録しているが、対応する範囲がコードに一つも無い。"
                "印を打つか、節を消して追跡の対象から外す(ADR-056)"))
            continue
        actual = {r["fingerprint"].lower() for r in found}
        if actual != decl["fps"]:
            out.append(mk(
                "trace_stale", _WARN, doc_id, node["path"],
                "記録した実装の指紋と、いまのコードの指紋が食い違う(%s)。"
                "変更を確かめ、確認したら節の指紋を更新する"
                % ", ".join(sorted(r["path"] for r in found))))
    return out


def _undeclared(by_id, sections, g, mk):
    """欠陥D(ADR-061): 節の無い現行 SPEC を範囲が指す。合否は変えない。"""
    out = []
    for doc_id in sorted(by_id):
        if doc_id in sections:
            continue
        node = g.nodes.get(doc_id)
        if node is None or not _registry.is_current(node.get("status", "")):
            continue
        if node.get("type") != "SPEC":
            continue
        out.append(mk(
            "trace_undeclared_impl", _ADVISORY, doc_id, node["path"],
            "コードの範囲(%s)がこの仕様を指しているが、仕様は実装の指紋の節を"
            "持たない。指紋を記録して追跡を結ぶか、「コード対応なし」を宣言する"
            "(ADR-061)" % ", ".join(sorted(r["path"] for r in by_id[doc_id]))))
    return out


def _spec_coverage(g, sections, coverage):
    """仕様側の三分類と「次の一件」(ADR-061/065)。無宣言は数えるだけ。"""
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
                # キャンペーン(ADR-065)が運ぶ「次の一件」。整列順の先頭で決定的。
                next_undeclared = doc_id
        elif decl["kind"] == "none":
            spec_cov["no_code"] += 1
        else:
            spec_cov["traced"] += 1
    if next_undeclared is not None:
        spec_cov["next_undeclared"] = next_undeclared
    coverage["spec_coverage"] = spec_cov


def collect(g, root, make_finding):
    """コードと仕様の追跡(ADR-056、SPEC-026)。(所見, 勘定) を返す。

    `## 実装の指紋` の節を持つ文書が一つでもあるときだけ効く。門は節の有無だけで
    判じ、状態を問わない(ADR-060)。「根拠を持たないコード」は挙げない — 注釈は
    任意であり、原理的に判じられない(ADR-054 の既知の限界)。
    """
    sections = _gate_sections(g)
    if not sections:
        return [], None   # 節を持つ文書が無い → 走査しない(ADR-056 の静けさ)

    expect = {doc_id: decl for doc_id, decl in sections.items()
              if _registry.is_current(g.nodes[doc_id].get("status", ""))}

    scan_root = os.path.dirname(os.path.abspath(root))
    try:
        ranges, scan_findings, coverage = _tracescan.scan_tree(
            scan_root, docs_root=root)
    except Exception:
        return [], None   # 走査で監査を落とさない

    by_id = {}
    for r in ranges:
        by_id.setdefault(r["id"], []).append(r)

    out = _fold_scan_findings(scan_findings, make_finding)
    out += _upward(by_id, g, make_finding)
    out += _downward(expect, by_id, g, make_finding)
    out += _undeclared(by_id, sections, g, make_finding)
    if coverage is not None:
        _spec_coverage(g, sections, coverage)
    return out, coverage


def apply_stagnation(root, coverage):
    """停滞の勘定(ADR-065)。直前の要約と比べ、動かない監査の連続回数を刻む。

    読むのは監査自身の前回成果物だけで、環境変数に依存しない(試験と CI で
    決定的にするため、パスは監査対象の木の親から導く)。
    """
    if coverage is None:
        return
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
        try:
            return int(cov.get("unmarked_files", 0)) + int(und)
        except (TypeError, ValueError):
            return 0

    streak = 0
    prev_cov = prev.get("trace_coverage") if isinstance(prev, dict) else None
    if isinstance(prev_cov, dict):
        cur = _open_total(coverage)
        if cur > 0 and cur == _open_total(prev_cov):
            ps = prev_cov.get("stagnation_streak")
            streak = (ps if isinstance(ps, int) and ps >= 0 else 0) + 1
    coverage["stagnation_streak"] = streak
