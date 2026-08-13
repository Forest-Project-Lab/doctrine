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
import subprocess
import sys

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _audit_stray
import _config
import _audit_trace
import _auditcache
import _frontmatter
import _registry
import _revinfo
import _termcheck


SCHEMA = _auditcache.SCHEMA   # 要約 schema の正本は共有コア(ADR-053)

# この版の監査が走らせる検査の名前の一覧(#95。検証器の実行証跡)。要約に
# checks_run として載せ、読み手(注入・生存性)が期待する検査集合を知れるようにする。
# 検査を足す・消すときは本一覧を同じ変更で更新する(TEST が凍結する)。ある検査が
# 黙って消えても、この一覧と要約の差で見えるようにする(沈黙する検証器の禁止。R11)。
# doctrine:begin SPEC-011
AUDIT_CHECKS = (
    "dead_link", "dep_cycle", "review_by_overrun", "stale_draft",
    "source_missing", "template_placeholder", "bad_date",
    "stale_proposed", "orphan",
    "reverse_orphan_req_no_spec", "reverse_orphan_spec_no_test",
    "canonical_conflict", "near_duplicate", "icd_dependency_violation",
    "projection_drift", "unregistered_document", "shadowed_document",
    "stray_document", "view_stale", "stale_current", "source_drift",
    "archive_integrity",
    "adr_not_landed", "glossary_seed_drift", "ext_anchor_broken",
    "ext_sole_guard_missing", "ext_sole_guard_loose", "memory_shadow",
    "trace_mark_error", "trace_broken_ref", "trace_deprecated_ref",
    "trace_stale", "trace_missing_impl", "trace_marker_suspect",
    "trace_scan_truncated", "trace_unexpected_impl", "trace_undeclared_impl",
    "trace_exempt_conflict", "trace_unmarked_backlog", "guard_liveness_gap",
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
# 境界は \b を使わない(ADR-075)。\w は Unicode 既定で仮名・漢字を含むため、
# 「SPEC-901の」「はSPEC-902を」のように地の文が直接隣接する参照を \b が
# 成立させず、取りこぼしていた。この一本が dead_link・adr_not_landed・
# projection_drift・memory_shadow の唯一の入口なので、四つが同時に漏れる。
_ID_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z_-])([A-Z]+-\d+)(?![0-9A-Za-z_-])")
# 単語シングル化(語彙的酷似)。英数字連なり + 連続する非ASCII。
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\x00-\x7f]+")


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
        "summary_in_project": False,
        "fail_on": "never",     # 既定は SessionEnd 想定(非ブロッキング)
        "config": None,
        "today": None,
        "respect_docs_level": False,
        "detach": False,        # SessionEnd 用。負債を置いて子へ渡し即座に返る。
        "clear_due": None,      # 切り離された子だけが付ける。完走したら印を消す。
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
            # 空の値は「与えられていない」ではない。配線の ${CLAUDE_PROJECT_DIR}
            # が展開されなかった姿である。素通りさせると、告げられていない木を
            # 作業ディレクトリから歩いて見つけて監査してしまう —— 境界が沈黙して
            # 開く(DECIDED-001 第12項)。使用法の誤りとして 2 へ倒す(INC-032)。
            if not argv[i + 1].strip():
                return None, ("--root-from が空。配線の ${CLAUDE_PROJECT_DIR} が"
                              "展開されていない疑い(境界は沈黙して開かない)")
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
            if not argv[i + 1].strip():
                return None, "--summary-out が空"
            opts["summary_out"] = argv[i + 1]
            i += 2
            continue
        if a == "--summary-in-project":
            # 要約の置き場を --root-from の値から導く。配線が
            # "${CLAUDE_PROJECT_DIR}/.claude/.cache/..." と書くと、変数が
            # 展開されないとき "/.claude/..." (ファイルシステムの根)になる。
            # 生の変数がシェルでパスになる場所を無くす(INC-032)。
            opts["summary_in_project"] = True
            i += 1
            continue
        if a == "--detach":
            # SessionEnd の口は 1 秒台でしか待ってもらえない(INC-039 の実測)。
            # 全件監査は 8〜9.5 秒かかるので、この口では負債の印だけを置き、
            # 監査そのものは切り離した子に渡して即座に返る。
            opts["detach"] = True
            i += 1
            continue
        if a == "--clear-due":
            # 切り離された子が自分に付ける。完走したときだけ負債の印を消す。
            # 利用者が手で付けることは想定しないが、付いても害は無い。
            if i + 1 >= n:
                return None, "--clear-due には識別子が必要"
            if not argv[i + 1].strip():
                return None, "--clear-due が空"
            opts["clear_due"] = argv[i + 1]
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


def _coerce_knobs(data, defaults):
    """設定の値を既定と同じ型へ揃える。揃わない値は落とす(ADR-075)。

    数値キーを文字列で書いた設定が素通りして比較の途中で例外になり、全件監査が
    落ちていた。CI の門は「所見ゼロ」と読んで緑で通る。ここで型を検め、
    不正値は既定のまま(= その項目は無かったことに)する。決して例外を投げない。
    """
    out = {}
    for key, value in data.items():
        want = defaults.get(key)
        if key not in defaults:
            continue
        if key in ("today", "trace_mode"):
            if isinstance(value, str) and value.strip():
                out[key] = value
            continue
        if key == "trace_exempt":
            if isinstance(value, dict):
                out[key] = value
            continue
        if isinstance(value, bool):
            continue                       # bool は数値として受けない
        if isinstance(want, float):
            if isinstance(value, (int, float)):
                out[key] = float(value)
            continue
        if isinstance(want, int):
            if isinstance(value, int):
                out[key] = value
            elif isinstance(value, float) and value == int(value):
                out[key] = int(value)
            continue
        out[key] = value
    return out


def _resolve_knobs(path):
    """設定から調整値の dict を解く。読み取りは共有コアが正本(ADR-104)。

    ここは「値の意味」を持つ —— 型を検めて写し、不正値は既定のまま残す。
    名前を _load_config から改めた(読むのは正本であり、ここは解く側である)。
    """
    knobs = {
        "draft_stale_days": DEFAULT_DRAFT_STALE_DAYS,
        "orphan_stale_days": DEFAULT_ORPHAN_STALE_DAYS,
        "jaccard": DEFAULT_JACCARD,
        "top_findings_cap": DEFAULT_TOP_FINDINGS,
        "near_dup_cap": DEFAULT_NEAR_DUP_CAP,
        "near_dup_max_docs": DEFAULT_NEAR_DUP_MAX_DOCS,
        "today": None,
        "trace_mode": None,        # 悉皆モード(ADR-072)。"exhaustive" だけが効く
        "trace_exempt": {},        # 設定側の統治外宣言 {パス: 理由}(ADR-072)
    }
    # 読み取りは共有コアが正本(ADR-104)。以前ここだけ utf-8 で開いており、BOM 付きの
    # 設定で監査だけが既定へ落ちていた(trace_mode を見失い、残高の警告が黙って消えた)。
    data = _config.load(config_path=path)
    if not data:
        return knobs
    # 型を検めてから写す(ADR-075)。数値キーを文字列で書くと、以前は素通りして
    # 比較の途中で例外になり、全件監査が落ちた。CI の門は所見ゼロ扱いで通る。
    # 同じ設定を読む collect-context・gov-heartbeat・inject-contract は検めている。
    if isinstance(data, dict):
        data = _coerce_knobs(data, knobs)
        for k in knobs:
            if k in data:
                knobs[k] = data[k]
    return knobs


# ---------------------------------------------------------------------------
# 日付ユーティリティ(決定的; 壁時計に依存しない経路を優先)
# ---------------------------------------------------------------------------



class _TodayError(ValueError):
    """--today / config.today に値はあるが解せない(使用法エラー → 終了コード 2)。"""


def _resolve_today(opts, knobs):
    """today を解決する。--today > config.today > 壁時計(最後の手段)。

    値が供給されているのに解せないときは _TodayError を投げる(制御不能な壁時計参照に
    黙って退避しない、docstring の保証)。値が一切供給されないときだけ壁時計に退避する。
    """
    raw = opts.get("today") or knobs.get("today")
    if raw:
        d = _frontmatter.parse_date(raw)
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


def _projection_listed_ids(g, node):
    """投影の「列挙された id 集合」— 各行の最初の id だけを数える(ADR-113)。

    列挙とは行を与えられることであり、他の行の題名に名が出ることではない。
    後継 ADR の題名「(◯◯を置換)」が Overview の題名セルに写り、現行でない文書が
    「載っている」と誤って咎められた実測がある。一覧形式でも表形式でも行の主は
    行頭側の id なので、行の後方の id は写り込みとして読み飛ばす。参照検出の
    共用器(_body_id_refs)は変えない —— あちらは自由文の id も参照として数える。
    """
    body = node.get("_body")
    if body is None:
        body = _read_body(os.path.join(g.root, node["path"]))
    refs = set()
    for line in body.splitlines():
        for m in _ID_TOKEN_RE.finditer(line):
            tok = m.group(1)
            if _registry.type_of(tok) is not None:
                refs.add(tok)
                break
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
        d = _frontmatter.parse_date(rb)
        if d is None:
            # 形式の誤りは超過ではない。bad_date が名で咎める(ADR-100)。
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


def _check_stale_proposed(g, today, stale_days):
    """4. proposed 放置(ADR-095)。status==proposed かつ updated が閾値より古い。

    proposed は現行でないので、孤児・逆孤児・adr_not_landed のどの検査からも見えない。
    **不変を accepted から始めた以上、下書きのまま置かれたものを誰かが見る必要がある。**
    咎めるのは放置だけで、proposed であること自体は咎めない(下書きは正当な状態である)。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if node["status"] != "proposed":
            continue
        if _is_stale(node["updated"], today, stale_days):
            out.append(_finding(
                "stale_proposed", SEV_WARN, doc_id, node["path"],
                "proposed のまま %d 日以上更新が無い(updated %s)。受理するか捨てる"
                % (stale_days, node["updated"] or "?")))
    return out


def _is_stale(updated, today, stale_days):
    """updated が today より stale_days 日以上前なら True。

    **日付が読めないときは偽を返す**(ADR-100)。以前は真(古び扱い)にしており、
    壊れた日付が「陳腐化の疑い」として誤った名前で報されていた。一つの欠陥は
    一つの名前で出す —— 安全側は bad_date(error)が保つ。
    """
    d = _frontmatter.parse_date(updated)
    if d is None:
        return False
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
        # 陳腐化: updated が古い（放置されている）。
        #
        # review_by の超過はここでは見ない（ADR-149）。超過には専用の検査
        # review_by_overrun（warn）が既に在り、孤児が error で数えると同じ事実を
        # 二重に数えることになる。二つは意味が違う —— review_by は「予定した
        # 見直しの日が来た」という暦の出来事であり、孤児は「誰にも引かれないまま
        # 放置されている」という状態である。暦の出来事を変更の門から error で
        # 出すと、誰も何も変えていない日に main が赤くなる（2026-11-10 に
        # 起きる形を実測。INC-034）。門は変更の可否を判ずる装置であって、
        # 暦の管理装置ではない。
        if not _is_stale(node["updated"], today, stale_days):
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
        d = _frontmatter.parse_date(node["updated"])
        if d is None:
            continue  # 読めない日付で古びを判じない(ADR-100)。bad_date が咎める。
        if (today - d).days >= cycle:
            out.append(_finding(
                "stale_current", SEV_WARN, doc_id, node["path"],
                "型 %s の既定点検周期 %d 日を超えた(updated %s)。内容を確かめて "
                "updated を更新するか、review_by を付ける(ADR-025)"
                % (node["type"], cycle, node["updated"] or "?")))
    return out


# 出所の道の形(ADR-097)。拡張子を持つ相対の道だけを対象にする。URL・文書 id・
# issue の番号・自由文は対象にしない(それぞれ別の検査か、機械で判じられない)。
_SOURCE_PATH_RE = re.compile(r"^[\w./-]+\.[A-Za-z0-9]{1,6}$")


def _check_bad_date(g):
    """16. 壊れた日付(ADR-100)。節点の updated・review_by が解せなければ error。

    日付の解釈は共有コアが正本(ADR-099)。ここは「解せなかったときに何と言うか」
    だけを受け持つ。**形式の誤りを「超過」や「陳腐化」の名で報せない** ——
    名が事実を語らないと、読み手が直す先を間違える。

    節点は created を運ばないので、created はファイル単位のリンタだけが見る
    (必須キーではない。確定事実3)。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        for key in ("updated", "review_by"):
            raw = node.get(key)
            if not raw:
                continue          # 不在は必須キー/期限の検査の領分。
            if _frontmatter.parse_date(raw) is not None:
                continue
            out.append(_finding(
                "bad_date", SEV_ERROR, doc_id, node["path"],
                "%s が日付として解せない(『%s』)。YYYY-MM-DD の実在する日付を書く"
                % (key, raw)))
    return out


def _check_template_placeholder(g):
    """15. 雛形の指示文の残り(ADR-098)。フロントマターの値が指示文のままなら error。

    判定は共有コア `_frontmatter.placeholder_fields` に一度だけ在り、ファイル単位の
    リンタも同じコアを呼ぶ(答えが割れない。ADR-053 と同じ原理)。本文は見ない
    —— 正当な山括弧(`<svg>`・置き場所の記法・id の書式)が出るからである。

    対象は現行でない文書も含む。埋め忘れは状態に依らず欠陥だからである。
    """
    out = []
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        meta = {}
        for key in ("id", "title", "domain", "owner", "updated", "review_by",
                    "superseded_by", "sources", "depends_on", "impacts",
                    "canonical_for"):
            if key in node:
                meta[key] = node[key]
        for key, value in _frontmatter.placeholder_fields(meta):
            out.append(_finding(
                "template_placeholder", SEV_ERROR, doc_id, node["path"],
                "%s が雛形の指示文のままである(『%s』)。値を書く" % (key, value)))
    return out


def _check_source_missing(g, root):
    """14. 宣言した出所の実在(ADR-097)。`sources` の道が在ることを検める。

    対象は現行の文書。**ADR と投影は除く** —— 受理済み ADR は不変なので `sources` の
    道を直せず、咎めても直す道が無い(非目標 第12項が「旧 id を指し続ける参照は監査が
    事後に指す」と立場を決めている)。`source_drift` と孤児の検査も同じ理由で除いている。

    検めるのは「在ること」だけである。その中身が主張を支えているかは見ないし、
    認識の等級(読んだ／推論した)も見ない。
    """
    out = []
    proj = os.path.dirname(os.path.abspath(root))
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        if not _registry.is_current(node["status"]):
            continue
        t = node["type"]
        if t == "ADR" or _registry.is_projection(t):
            continue
        for src in _frontmatter.as_list(node.get("sources")):
            if not isinstance(src, str):
                continue
            src = src.strip()
            if not src or src.startswith(("http://", "https://")):
                continue
            if not _SOURCE_PATH_RE.match(src):
                continue
            if os.path.exists(os.path.join(proj, src.replace("/", os.sep))):
                continue
            out.append(_finding(
                "source_missing", SEV_WARN, doc_id, node["path"],
                "sources が指す道 %s が実在しない(動いたか消えた)。"
                "指し先を確かめて sources を直す" % src))
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
        own = _frontmatter.parse_date(node["updated"])
        if own is None:
            continue  # updated 壊れは必須キー/陳腐化側の話。
        for dep in sorted(node["depends_on"]):
            target = g.nodes.get(dep)
            if target is None:
                continue  # dead link 検査が見る。
            td = _frontmatter.parse_date(target["updated"])
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
        if not _registry.is_archived_path(parts[:-1]):
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
            # 機械が何も見ていないアンカー。review_by が唯一の見張りである(ADR-086)。
            # 常時見張られている exists/hash のアンカーと同じ寛容さを与えない。
            out.extend(_check_ext_sole_guard(doc_id, node))
            continue
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


# 唯一の見張りである期限の上限(ADR-086)。見立てであって測って出した値ではない ——
# 実測では反証が更新から約5〜7日で届いており、30日でも定例が先に捉えたことにはならない。
# 縮めるのは窓であって、先に捉えることは保証しない。
EXT_SOLE_GUARD_MAX_DAYS = 30


def _check_ext_sole_guard(doc_id, node):
    """`検査: review_by のみ` のアンカーの期限を判ずる(ADR-086)。

    二段に分ける。見張りの不在は事実なので error、上限の超過は見立てなので warn。
    """
    out = []
    rb = _frontmatter.parse_date(node.get("review_by"))
    if rb is None:
        out.append(_finding(
            "ext_sole_guard_missing", SEV_ERROR, doc_id, node["path"],
            "機械が何も見ていないアンカー(検査: review_by のみ)に review_by が無い。"
            "唯一の見張りが不在で、この境界は沈黙して開いている(ADR-086)"))
        return out
    up = _frontmatter.parse_date(node.get("updated"))
    if up is None:
        return out  # updated が読めないなら間隔を判じられない(schema 検査の領分)。
    span = (rb - up).days
    if span > EXT_SOLE_GUARD_MAX_DAYS:
        out.append(_finding(
            "ext_sole_guard_loose", SEV_WARN, doc_id, node["path"],
            "機械が何も見ていないアンカー(検査: review_by のみ)の点検の間隔が %d 日ある。"
            "唯一の見張りなので %d 日以内にする(ADR-086。exists/hash で常時見張られる"
            "アンカーには課さない)" % (span, EXT_SOLE_GUARD_MAX_DAYS)))
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
        listed = _projection_listed_ids(g, overview_node)
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
        listed = {i for i in _projection_listed_ids(g, icd_index_node)
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


_CTX_BEGIN = _registry.CTXMAP_BEGIN
_CTX_END = _registry.CTXMAP_END
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
    findings += _check_stale_proposed(g, today, knobs["draft_stale_days"])
    findings += _check_source_missing(g, root)
    findings += _check_template_placeholder(g)
    findings += _check_bad_date(g)
    findings += _check_orphan(g, today, knobs["orphan_stale_days"])
    findings += _check_reverse_orphan(g)
    findings += _check_canonical_conflict(g)
    findings += _check_near_duplicate(g, knobs["jaccard"], knobs["near_dup_cap"], knobs["near_dup_max_docs"])
    findings += _check_icd_violation(g)
    findings += _check_projection_drift(g)
    findings += _check_unregistered(g)
    findings += _audit_stray.collect(root, today, _finding, _frontmatter.parse_date,
                                 graph=g)
    findings += _check_stale_current(g, today)
    findings += _check_source_drift(g)
    findings += _check_archive_integrity(g)
    findings += _check_adr_not_landed(g)
    findings += _check_glossary_seed(root)
    findings += _check_ext_anchors(g, root)
    findings += _check_memory_shadow(g, root)
    findings += _check_guard_liveness(root)
    trace_findings, trace_coverage = _audit_trace.collect(
        g, root, _finding,
        trace_mode=knobs.get("trace_mode"),
        trace_exempt=knobs.get("trace_exempt"))
    findings += trace_findings

    # 停滞の勘定(ADR-065)は追跡系モジュールに在る(ADR-069 の移送)。
    _audit_trace.apply_stagnation(root, trace_coverage)

    findings.sort(key=lambda f: (f["check"], f["doc_id"], f["message"]))
    return findings, trace_coverage




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

    _src_rev = _revinfo.revision_of(os.path.abspath(root))

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
        # 測った木の版と作り手(ADR-155/ADR-156)。意味は graph の宣言と同じ。
        "source_revision": _src_rev["source_revision"],
        "source_dirty": _src_rev["source_dirty"],
        "generator": _revinfo.generator_info("docs-audit.py"),
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

def _detach_and_queue(argv, opts):
    """負債の印を置き、監査そのものを切り離した子へ渡して即座に返る。

    SessionEnd の口の予算は、このホストの実測で 1 秒超〜2 秒未満だった。全件監査
    (274 文書で 8〜9.5 秒)は常にこれを超えて打ち切られ、要約は 5 日・8 セッション
    にわたって一度も更新されなかった(INC-039)。口では負債だけを置く。

    子が完走すれば印は消える。子が落ちても・切り離しが効かない環境でも、印は
    残る —— 次のセッションの契約注入がそれを読んで「監査が済んでいない」と告げる。
    どちらに転んでも、走らなかったことが黙って消えないのが要点である。

    ここで例外を投げない。SessionEnd の口を壊すことは、監査が遅れることより悪い。
    """
    proj = _auditcache.project_dir(opts["root_from"])
    # セッション識別子はホストによって鍵の名が違う。stdin の JSON は読まない
    # (対話 CLI では待ちで止まる。main の注記と同じ理由)。どれも無ければ時刻を
    # 使う —— 識別子が取れないことを負債を置かない理由にはしない。
    token = ""
    for key in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        token = os.environ.get(key) or ""
        if token:
            break
    token = token or datetime.datetime.now(datetime.timezone.utc).strftime(
        "queued-%Y%m%dT%H%M%SZ")
    try:
        _auditcache.write_due(token, proj=proj)
    except Exception:                                    # noqa: BLE001
        pass
    child = [sys.executable, os.path.abspath(__file__)]
    child += [a for a in argv if a != "--detach"]
    child += ["--clear-due", token]
    try:
        subprocess.Popen(                                # noqa: S603
            child, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, cwd=proj)
    except (OSError, ValueError):
        # 切り離せない環境では監査は走らないが、負債の印は残っている。
        # 沈黙して開かない(DECIDED-001 第12項): 何が起きたかを一行で告げる。
        sys.stdout.write("監査を切り離せなかった。負債の印だけ残す: %s\n" % token)
    return 0


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
            "[--summary-out PATH | --summary-in-project] "
            "[--fail-on error|never] [--config PATH] "
            "[--today YYYY-MM-DD] [--respect-docs-level] "
            "[--detach] [--clear-due TOKEN]\n")
        return 2

    if opts["detach"]:
        return _detach_and_queue(list(argv), opts)

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
        root = (_registry.walkup_docs_root(os.getcwd())
                or _registry.DOCS_DIR_NAMES[0])
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

    # 設定は監査対象の木のものを既定で読む(ADR-072)。明示の --config が優先。
    # 無ければ既定値のまま(前方寛容)。道の組み立ては共有コアが正本(ADR-104)。
    config_path = opts["config"] or _config.path_for(root)
    knobs = _resolve_knobs(config_path)
    # today の解決は監査本体の前に行う。供給された today が解せないのは使用法エラー
    # (壁時計に黙って退避しない、§日付ユーティリティの保証)→ 終了コード 2。
    try:
        today = _resolve_today(opts, knobs)
    except _TodayError as exc:
        sys.stdout.write("usage error: %s\n" % exc)
        sys.stdout.write(
            "docs-audit.py [--root PATH | --root-from PROJ] [--json] "
            "[--summary-out PATH | --summary-in-project] "
            "[--fail-on error|never] [--config PATH] "
            "[--today YYYY-MM-DD] [--respect-docs-level]\n")
        return 2

    try:
        findings, trace_coverage = run_audit(root, today, knobs)
        summary = build_summary(root, findings, today, knobs,
                                trace_coverage=trace_coverage)
    except Exception as exc:  # 監査自身のクラッシュ。Hook 連鎖を壊さない。
        sys.stderr.write("docs-audit: internal error: %r\n" % (exc,))
        _auditcache.record_error(
            "docs-audit", exc, proj=os.path.dirname(os.path.abspath(root)))
        # SessionEnd は teardown を壊さないために 0。CI(fail-on error)でも
        # 監査が壊れたこと自体は所見ではないので、ここでは 0 を返さず安全側に倒す。
        return 0

    # 要約の永続化(--summary-out)。原子的に書き、失敗しても 0 を保つ(§5.5)。
    write_ok = True
    summary_out = opts["summary_out"]
    if opts["summary_in_project"] and not summary_out:
        # 置き場は解決済みのプロジェクト根から導く(INC-032)。生の変数が
        # シェルでパスになる場所を作らない。WATCH-001 第9項の置き場に限る。
        base = opts["root_from"] or os.path.dirname(os.path.abspath(root))
        summary_out = os.path.join(base, ".claude", ".cache", "last-audit.json")
    if summary_out:
        proj = opts["root_from"] or os.path.dirname(os.path.abspath(root))
        try:
            _atomic_write(summary_out,
                          json.dumps(summary, ensure_ascii=False,
                                     sort_keys=True, indent=2) + "\n")
        except OSError as exc:
            write_ok = False
            sys.stderr.write("docs-audit: summary write failed: %r\n" % (exc,))
            # 書けなかったことを沈黙させない(ADR-121)。統治の唯一の全体像を
            # 書けなかった実行が 0 を返すと、書けたときと外から区別がつかない
            # —— 送ったコントロールアクションが守られたと仮定しない(STPA)。
            # 所見の重さとは分ける: これは前提の欠如であって所見ではないので、
            # 兄弟の門の規約に合わせて 3（場所が実在しない・前提の欠如）を返す。
        # 走ったこと自体の印(ADR-119)。要約が書けたかと分けて残すので、鮮度の
        # 警告が『走らなかった』と『走ったが書けなかった』を区別できる。印の
        # 書き込みは最善努力で、失敗しても監査の本務を妨げない(ADR-062)。
        _auditcache.write_stamp("hook_session_end_audit", proj=proj)
        _auditcache.write_stamp("hook_session_end_write", proj=proj,
                                value="ok" if write_ok else "failed")

    # 負債の解消。**要約を書けたときだけ**消す(INC-039)。走っただけで消すと、
    # 書けなかった実行が負債を帳消しにしてしまい、次のセッションは古い要約を
    # 「済んだもの」として受け取る —— 直そうとしている形そのものに戻る。
    if opts["clear_due"] and write_ok and summary_out:
        _auditcache.clear_due(
            opts["clear_due"],
            proj=opts["root_from"] or os.path.dirname(os.path.abspath(root)))

    # 標準出力。
    if opts["json"]:
        sys.stdout.write(json.dumps(summary, ensure_ascii=False,
                                    sort_keys=True) + "\n")
    else:
        sys.stdout.write(_render_human(summary))

    # ゲート判定。
    if opts["fail_on"] == "error" and summary["totals"][SEV_ERROR] > 0:
        return 1
    if summary_out and not write_ok:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
