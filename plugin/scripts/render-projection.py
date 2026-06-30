#!/usr/bin/env python3
"""投影(Overview・ICD一覧・Context Map骨組み)を正本から決定論で描画する(§3.9, §5.6)。

保証限界:
- 予防: 投影を手で書き溜める作業をなくす。正本(各文書のフロントマターと§3の登録簿)から
  描画し直すだけにして、投影と現行集合のずれが入り込むのを防ぐ(§3.9 [R1][R8])。
- 検出: --check は描画結果とディスク上の投影を突き合わせ、ずれ(投影ドリフト)を非ゼロ終了で
  知らせる。docs-audit の投影ドリフト検出はこの描画結果を基準にする。
- 委ねる: 意味を含む投影(Context Map の結合の要点)の本文は docs-curate に委ねる。本スクリプトは
  骨組み(ノードと端)だけを決定論で描き、その外側の散文は保つ。違反の合否判定は監査・ガードに委ねる。

決定論の核:
- 壁時計を読まない。投影の updated は各源の updated の最大値にする。源が変わらなければ
  再描画しても updated は動かず、--check は揺れない(§3.9 [R1])。
- すべての並びは明示キーで整列する。ファイルシステムの列挙順に依存しない。
- 二度描画すればバイト単位で一致する(冪等)。

このスクリプトは標準ライブラリだけを使う。pip も通信も使わない。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _frontmatter
import _registry

# 投影の冒頭に必ず置く一行(§3.9 / 付録B / テンプレート規則)。
HEADER_LINE = "描画される。手で編集しない。"

# Context Map 骨組みの差し替え区間を囲む印(slice 06 §3.5)。この印の外側の散文は
# 再描画でも保つ。docs-curate は印の内側を手で触らない。
CTXMAP_BEGIN = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
CTXMAP_END = "<!-- END PROJECTION:context-map-skeleton -->"

# 投影の置き場所(§3.7 / C8)。ファイル名は固定。
OVERVIEW_REL = "_system/overview.md"
ICD_INDEX_REL = "_system/icd-index.md"
CTXMAP_REL = "_system/context-map.md"

MODES = ("overview", "icd-index", "context-map-skeleton", "all")


# ---------------------------------------------------------------------------
# 引数解析
# ---------------------------------------------------------------------------
def _parse_args(argv):
    """argv を (opts, error_message) に解く。error は usage 終了(2)に回す。"""
    opts = {"mode": None, "docs_root": "docs", "out": None, "check": False}
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--docs-root":
            if i + 1 >= n:
                return None, "--docs-root にはパスが必要"
            opts["docs_root"] = argv[i + 1]
            i += 2
            continue
        if a == "--out":
            if i + 1 >= n:
                return None, "--out にはパスが必要(- で標準出力)"
            opts["out"] = argv[i + 1]
            i += 2
            continue
        if a == "--check":
            opts["check"] = True
            i += 1
            continue
        if a.startswith("--"):
            return None, "不明な引数: %s" % a
        if opts["mode"] is not None:
            return None, "モードは一つだけ指定する"
        if a not in MODES:
            return None, "不明なモード: %s" % a
        opts["mode"] = a
        i += 1

    if opts["mode"] is None:
        return None, "モードを一つ指定する(overview|icd-index|context-map-skeleton|all)"
    if opts["check"] and opts["out"] is not None:
        return None, "--check と --out は同時に使えない"
    if opts["out"] is not None and opts["mode"] == "all":
        return None, "--out は単一モードでだけ使える(all は不可)"
    return opts, None


def _usage(msg):
    sys.stdout.write("usage error: %s\n" % msg)
    sys.stdout.write(
        "render-projection.py (overview|icd-index|context-map-skeleton|all) "
        "[--docs-root R] [--out PATH|-] [--check]\n"
    )
    return 2


# ---------------------------------------------------------------------------
# 源の収集(決定論)
# ---------------------------------------------------------------------------
class _Doc(object):
    """一文書の投影に要る素。フロントマターから読む(本文は読まない, §3.2)。"""

    __slots__ = ("id", "title", "type", "domain", "status", "updated",
                 "canonical_for", "relpath")

    def __init__(self, doc_id, title, type_code, domain, status, updated,
                 canonical_for, relpath):
        self.id = doc_id
        self.title = title
        self.type = type_code
        self.domain = domain
        self.status = status
        self.updated = updated
        self.canonical_for = canonical_for
        self.relpath = relpath


def _collect_docs(docs_root):
    """docs_root 配下の全 .md をフロントマターから読み、_Doc の list を返す。

    id を持たない/フロントマターの無いファイルは投影に出せないので飛ばす。
    決定論: 相対パスで整列して走査する。同じ id が複数あればパス先勝ちで一つだけ採り、
    残りは stderr に警告する(slice 06 §3.7)。本文は一切読まない(フロントマターのみ)。
    """
    docs = []
    seen_ids = {}
    if not os.path.isdir(docs_root):
        return docs

    paths = []
    for dirpath, dirnames, filenames in os.walk(docs_root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".md"):
                paths.append(os.path.join(dirpath, name))
    paths.sort()

    for path in paths:
        relpath = os.path.relpath(path, docs_root).replace(os.sep, "/")
        try:
            fm, _body, _errs = _frontmatter.parse_file(path)
        except (OSError, UnicodeDecodeError):
            sys.stderr.write("読めない文書を飛ばす: %s\n" % relpath)
            continue
        doc_id = fm.get("id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            continue
        doc_id = doc_id.strip()
        if doc_id in seen_ids:
            # 重複 id。先勝ち(パス整列順で先)。決定論のため後続は無視して警告。
            sys.stderr.write("id の重複を飛ばす: %s (%s, 既出 %s)\n"
                             % (doc_id, relpath, seen_ids[doc_id]))
            continue
        seen_ids[doc_id] = relpath
        docs.append(_Doc(
            doc_id=doc_id,
            title=_coerce_str(fm.get("title")),
            type_code=_coerce_str(fm.get("type")),
            domain=_coerce_str(fm.get("domain")),
            status=_coerce_str(fm.get("status")) or _registry.default_status(
                _coerce_str(fm.get("type"))) or "",
            updated=_coerce_str(fm.get("updated")),
            canonical_for=_frontmatter.as_list(fm.get("canonical_for")),
            relpath=relpath,
        ))
    return docs


def _coerce_str(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _max_updated(docs):
    """源 updated の最大値(辞書順)。壁時計は読まない(§3.9 [R1])。

    YYYY-MM-DD の updated は辞書順比較が日付順と一致する。一つも無ければ
    決定論の安定値として空文字でなく固定の "—" を使う(空集合でも揺れない)。
    """
    vals = [d.updated for d in docs if d.updated]
    if not vals:
        return "—"
    return max(vals)


def _type_order_key(type_code):
    """§3.2 登録簿の行順を整列キーにする。未知型は末尾(大きな添字+コード)。"""
    if type_code in _registry.TYPES:
        return (0, _registry.TYPES.index(type_code))
    return (1, 0)


def _domain_order_key(domain):
    """ドメイン整列キー。_system を必ず先頭に、残りは辞書順。"""
    if domain == "_system":
        return (0, "")
    return (1, domain or "")


def _is_projection_doc(doc):
    """この文書は投影そのものか。Overview に載せない対象。

    型が投影型(OVERVIEW・CTXMAP, §1.5/C8)か、ファイル名が固定の投影名
    (overview.md・icd-index.md・context-map.md)なら投影とみなす。型が未設定でも
    ファイル名で拾えるようにしておく(描画した投影を取りこぼさないため)。
    """
    if _registry.is_projection(doc.type):
        return True
    base = doc.relpath.rsplit("/", 1)[-1]
    return base in _registry.PROJECTION_FILES


# ---------------------------------------------------------------------------
# 描画: 共通の冒頭(フロントマター + 投影の一行)
# ---------------------------------------------------------------------------
def _render_head(doc_id, title, updated):
    """投影文書の冒頭(type:OVERVIEW の最小フロントマター + 投影の一行 + 見出し前まで)。

    C8: ICD一覧も Overview も type:OVERVIEW、id:OVERVIEW-<n>。固定キー順で安定描画。
    """
    lines = [
        "---",
        "id: %s" % doc_id,
        "title: %s" % title,
        "type: OVERVIEW",
        "domain: _system",
        "status: current",
        "owner: render-projection",
        "updated: %s" % updated,
        "llm_context: always",
        "sources: []",
        "---",
        "",
        HEADER_LINE,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Overview 投影(§3.3)
# ---------------------------------------------------------------------------
def render_overview(docs):
    """現行文書の一覧と一行説明を描画する。決定論(整列)。

    含める文書: status が現行(current/accepted)のものだけ(§3.9「現行文書の一覧」)。
    deprecated/superseded/archived/draft/proposed は除く。
    投影そのもの(OVERVIEW・CTXMAP、および固定名の投影ファイル)は除く。投影は描画された
    ビューであって正本ではないため、自分自身を一覧へ載せない。これにより all 描画後に
    --check しても自己参照のずれが出ず、冪等が保たれる。
    並び: ドメイン昇順(_system 先頭)→ §3.2 登録簿の型順 → id 昇順。
    一行説明の源は title(本文ではない, §3.2 OVERVIEW は仕様本文を入れない)。
    """
    current = [d for d in docs
               if _registry.is_current(d.status) and not _is_projection_doc(d)]
    updated = _max_updated(current)
    out = [_render_head("OVERVIEW-001", "現行文書の一覧", updated)]
    out.append("# Overview")
    out.append("")
    out.append("| id | type | domain | title |")
    out.append("|---|---|---|---|")

    current.sort(key=lambda d: (_domain_order_key(d.domain),
                                _type_order_key(d.type), d.id))
    for d in current:
        out.append("| %s | %s | %s | %s |"
                   % (d.id, d.type, d.domain, _cell(d.title)))
    if not current:
        out.append("")
        out.append("現行文書なし。")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# ICD一覧 投影(§3.4)
# ---------------------------------------------------------------------------
def render_icd_index(docs):
    """全ドメインの ICD 文書から索引を描画する。決定論(整列)。

    対象: type が ICD の全文書(status は問わない。索引は全 ICD を映す)。
    並び: ドメイン昇順 → id 昇順。canonical_for はフロントマターから(本文は入れない)。
    frontmatter は type:OVERVIEW、id:OVERVIEW-<n>(C8。INDEX 型は作らない)。
    """
    icds = [d for d in docs if d.type == "ICD"]
    updated = _max_updated(icds)
    out = [_render_head("OVERVIEW-002", "ICD一覧", updated)]
    out.append("# ICD一覧")
    out.append("")
    out.append("| domain | ICD id | title | canonical_for | updated |")
    out.append("|---|---|---|---|---|")

    icds.sort(key=lambda d: (_domain_order_key(d.domain), d.id))
    for d in icds:
        cf = ", ".join(d.canonical_for) if d.canonical_for else ""
        out.append("| %s | %s | %s | %s | %s |"
                   % (d.domain, d.id, _cell(d.title), _cell(cf), d.updated))
    if not icds:
        out.append("")
        out.append("現行 ICD なし。")
    return "\n".join(out) + "\n"


def _cell(text):
    """表セルに安全に入れる。改行とパイプを潰す(表が崩れないように)。"""
    if not text:
        return ""
    return text.replace("\n", " ").replace("|", "\\|").strip()


# ---------------------------------------------------------------------------
# Context Map 骨組み(構造だけ。意味の散文は印の外側で保つ, §3.5)
# ---------------------------------------------------------------------------
def render_ctxmap_skeleton(docs_root):
    """ドメインとICDの全体図(骨組み)を依存グラフから描画する。決定論。

    ノード: 各ドメイン + その ICD(複数あれば列挙、無ければ「ICD 未公開」)。
    端: ドメイン越えの depends_on のうち ICD を指すもの(§3.6 の正しい境界端)。
    違法な端(ドメイン越え依存で ICD でない先)も描くが (境界違反) と印す
    (拒否は監査・ガードの仕事。投影は可視化するだけ, slice 06 §3.5/§3.7)。
    返すのは印で囲む差し替え区間の中身だけ(印の外側は呼び出し側が保つ)。
    """
    g = _depgraph.build_graph(docs_root)

    # ドメイン → そのドメインの ICD id 群。
    domain_icds = {}
    domains = set()
    for doc_id in sorted(g.nodes):
        node = g.nodes[doc_id]
        dom = node["domain"] or _depgraph.UNKNOWN
        domains.add(dom)
        if node["type"] == "ICD":
            domain_icds.setdefault(dom, []).append(doc_id)
    for dom in domain_icds:
        domain_icds[dom].sort()

    lines = []
    lines.append("## ドメインとICD")
    lines.append("")
    if not domains:
        lines.append("ドメインなし。")
    else:
        for dom in sorted(domains, key=_domain_order_key):
            icds = domain_icds.get(dom, [])
            if icds:
                lines.append("- %s: %s" % (dom, ", ".join(icds)))
            else:
                lines.append("- %s: (ICD 未公開)" % dom)

    # ドメイン越えの depends_on 端だけを採る(§3.6)。kind で ICD/違反を見分ける。
    edges = []
    for e in g.classify_edges():
        if e["field"] != "depends_on":
            continue
        if e["kind"] == _depgraph.KIND_CROSS_ICD:
            edges.append((e["src"], e["dst"], False))
        elif e["kind"] == _depgraph.KIND_CROSS_VIOLATION:
            edges.append((e["src"], e["dst"], True))
    edges.sort(key=lambda t: (t[0], t[1]))

    lines.append("")
    lines.append("## ドメイン越えの依存(ICD境界)")
    lines.append("")
    if not edges:
        lines.append("ドメイン越えの依存なし。")
    else:
        for src, dst, violation in edges:
            mark = " (境界違反)" if violation else ""
            lines.append("- %s --depends_on--> %s%s" % (src, dst, mark))

    return "\n".join(lines) + "\n"


def _splice_ctxmap(existing, skeleton_body, updated):
    """既存の context-map.md の印の内側を skeleton_body で差し替える。

    印の外側の散文(結合の要点)は保つ(slice 06 §3.5)。印が無い既存ファイルや
    新規ファイルには、最小のフロントマター + 投影の一行 + 散文の置き場 + 印付き区間を
    組み立てる。冪等: 同じ源・同じ外側なら再描画でバイト一致する。
    """
    block = "%s\n%s%s\n" % (CTXMAP_BEGIN, skeleton_body, CTXMAP_END)

    if existing and CTXMAP_BEGIN in existing and CTXMAP_END in existing:
        b = existing.index(CTXMAP_BEGIN)
        e = existing.index(CTXMAP_END) + len(CTXMAP_END)
        # 印の直後に元から改行があれば取り込む(冪等のため一つだけ残す)。
        tail = existing[e:]
        if tail.startswith("\n"):
            tail = tail[1:]
        return existing[:b] + block + tail

    if existing:
        # 印が無い既存ファイル。散文は壊さず、末尾に印付き区間を足す。
        sep = "" if existing.endswith("\n") else "\n"
        return existing + sep + "\n" + block

    # 新規ファイル。最小の足場を組む。updated はここでは固定文言にする
    # (Context Map の updated は源グラフではなく構造の版に紐づくため、骨組み描画では
    #  壁時計を読まず固定にして冪等を保つ)。
    head = "\n".join([
        "---",
        "id: CTXMAP-001",
        "title: 全体図",
        "type: CTXMAP",
        "domain: _system",
        "status: current",
        "owner: render-projection",
        "updated: %s" % updated,
        "llm_context: task",
        "sources: []",
        "---",
        "",
        HEADER_LINE,
        "",
        "# Context Map",
        "",
        "結合の要点はこの印の外側に書く。印の内側は描画される。",
        "",
        "",
    ])
    return head + block


# ---------------------------------------------------------------------------
# 出力 / --check
# ---------------------------------------------------------------------------
def _read_existing(path):
    """既存ファイルを読む。無ければ None。読めなければ None(描画で新規扱い)。"""
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _atomic_write(path, content):
    """親ディレクトリを作り、一時ファイル経由で原子的に書く。"""
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    os.replace(tmp, path)


def _render_one(mode, docs_root, docs):
    """単一モードの最終文字列を返す。context-map は既存の外側散文を取り込む。

    overview / icd-index は完結した投影文字列。context-map-skeleton は既存ファイルの
    印の外側を保った最終文字列(ディスクの内容に依存して合成する)。
    """
    if mode == "overview":
        return render_overview(docs)
    if mode == "icd-index":
        return render_icd_index(docs)
    if mode == "context-map-skeleton":
        skeleton = render_ctxmap_skeleton(docs_root)
        existing = _read_existing(os.path.join(docs_root, CTXMAP_REL))
        return _splice_ctxmap(existing, skeleton, _max_updated(docs))
    raise ValueError("未対応モード: %s" % mode)


def _canonical_path(mode, docs_root):
    rel = {
        "overview": OVERVIEW_REL,
        "icd-index": ICD_INDEX_REL,
        "context-map-skeleton": CTXMAP_REL,
    }[mode]
    return os.path.join(docs_root, rel)


def _do_check(mode, docs_root, docs):
    """--check: 描画結果とディスクを突き合わせる。一致 0、ずれ(または未生成)で非ゼロ。

    context-map は印の内側(骨組み)だけを比べる(印の外側の散文はドリフトではない)。
    """
    path = _canonical_path(mode, docs_root)
    existing = _read_existing(path)
    rendered = _render_one(mode, docs_root, docs)

    if existing is None:
        sys.stdout.write("投影未生成: %s\n" % path)
        return 1

    if mode == "context-map-skeleton":
        want = _extract_skeleton(rendered)
        have = _extract_skeleton(existing)
        if want == have:
            return 0
        sys.stdout.write("投影ドリフト(骨組み): %s\n" % path)
        _emit_diff(have, want)
        return 1

    if existing == rendered:
        return 0
    sys.stdout.write("投影ドリフト: %s\n" % path)
    _emit_diff(existing, rendered)
    return 1


def _extract_skeleton(text):
    """印で囲まれた骨組み区間の中身を取り出す。印が無ければ None(=ドリフト扱い)。"""
    if text is None or CTXMAP_BEGIN not in text or CTXMAP_END not in text:
        return None
    b = text.index(CTXMAP_BEGIN) + len(CTXMAP_BEGIN)
    e = text.index(CTXMAP_END)
    return text[b:e]


def _emit_diff(have, want):
    """ディスク(have)と描画(want)の行差分を出す。決定論。"""
    import difflib
    have_lines = (have or "").splitlines(keepends=True)
    want_lines = (want or "").splitlines(keepends=True)
    diff = difflib.unified_diff(have_lines, want_lines,
                                fromfile="on-disk", tofile="rendered")
    for line in diff:
        sys.stdout.write(line if line.endswith("\n") else line + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    docs_root = opts["docs_root"]
    if not os.path.isdir(docs_root):
        sys.stdout.write("docs-root not found: %s\n" % docs_root)
        return 3

    docs = _collect_docs(docs_root)

    if opts["mode"] == "all":
        # 三つを正本パスへ描画する(--out/--check は all 不可: _parse_args で弾く)。
        if opts["check"]:
            rc = 0
            for m in ("overview", "icd-index", "context-map-skeleton"):
                rc = _do_check(m, docs_root, docs) or rc
            return rc
        for m in ("overview", "icd-index", "context-map-skeleton"):
            content = _render_one(m, docs_root, docs)
            _atomic_write(_canonical_path(m, docs_root), content)
        return 0

    mode = opts["mode"]

    if opts["check"]:
        return _do_check(mode, docs_root, docs)

    content = _render_one(mode, docs_root, docs)

    if opts["out"] == "-":
        sys.stdout.write(content)
        return 0
    if opts["out"] is not None:
        _atomic_write(opts["out"], content)
        return 0
    _atomic_write(_canonical_path(mode, docs_root), content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
