#!/usr/bin/env python3
"""依存グラフのエンジン(core)。全文書の frontmatter から有向グラフを組み立てる。

保証限界:
- 予防: ここでは何も予防しない。グラフを組み立てて問い合わせに答えるだけの純粋なエンジン。
- 検出: 影響集合・逆依存・端の分類(intra/cross-domain/dangling)・逆孤児という構造を検出する。
  違反かどうかの判定や報告の体裁は持たない。それは監査・ガードに委ねる。
- 委ねる: 端の分類は事実(intra_domain / cross_domain_icd / cross_domain_violation /
  cross_domain_impact / dangling)を返すだけで、拒否や警告はガード・監査に委ねる。

設計の要点(slice 05 A.2):
- 依存(depends_on)と影響(impacts)は別の端として持つ。混ぜない。
  - 依存端 A --depends_on--> B: A は B を前提とする。逆依存(誰が X に依存するか)と
    §3.8 降格不変条件(逆参照ゼロ)と R7 のICD境界はこの端で判定する。
  - 影響端 A --impacts--> B: A を変えると B に波及する。前向き影響集合(R4)はこの端で出す。
- ドメインは frontmatter の domain から引く。IDだけではドメインは決まらない(§3.4)。
  resolve(id) がこのドメイン解決を担い、ガード・リンタ・監査の事実上の domain_of になる。

標準ライブラリだけを使う。pip も通信も使わない。出力は決定的(整列済み)。
"""
from __future__ import annotations

import os

import _frontmatter
import _registry


# 端の種類(MASTER §5.2 / slice 05 A.2)。cross_domain_violation は depends_on 端だけに付く。
KIND_INTRA = "intra_domain"
KIND_CROSS_ICD = "cross_domain_icd"
KIND_CROSS_VIOLATION = "cross_domain_violation"
KIND_CROSS_IMPACT = "cross_domain_impact"
KIND_DANGLING = "dangling"

UNKNOWN = "UNKNOWN"


class Edge(dict):
    """一つの端。{src, dst, field, kind} を持つ素朴な dict 部分型。

    dict なので to_json/JSON 化がそのまま通る。属性風アクセスも許す。
    field は "depends_on" か "impacts"。kind は上の KIND_* のどれか。
    """

    def __init__(self, src, dst, field, kind):
        super().__init__(src=src, dst=dst, field=field, kind=kind)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class Graph(object):
    """docs ルート配下の全 .md から組み立てた依存グラフ。

    ノード = 文書。キーは frontmatter の id(= ファイル名の語幹, §3.7)。
    端 = depends_on / impacts。すべての走査はサイクル安全(訪問済み集合)。
    出力は決定的: ID・端は整列して返す。
    """

    def __init__(self, root):
        self.root = root
        self.nodes = {}          # id -> node dict
        self.dup_ids = {}        # id -> [path, path, ...] (重複 id)
        self.parse_warnings = [] # frontmatter の無いファイルなど
        # 隣接表(構築時に確定)。
        self._dep_out = {}       # id -> sorted list of depends_on target ids
        self._imp_out = {}       # id -> sorted list of impacts target ids
        self._dep_in = {}        # id -> sorted list of ids whose depends_on includes id

    # -- 構築 ---------------------------------------------------------------

    def _add_node(self, node):
        doc_id = node["id"]
        if doc_id in self.nodes:
            # 重複 id(別ファイルが同じ id)。両方残すが曖昧として記録(slice 05 A.3.2)。
            self.dup_ids.setdefault(doc_id, [self.nodes[doc_id]["path"]])
            self.dup_ids[doc_id].append(node["path"])
            # 後勝ち(決定的: パスで整列して最後を採用)。
            keep = sorted(self.dup_ids[doc_id])[-1]
            if node["path"] == keep:
                self.nodes[doc_id] = node
            return
        self.nodes[doc_id] = node

    def _build_indices(self):
        for doc_id, node in self.nodes.items():
            self._dep_out[doc_id] = sorted(set(node["depends_on"]))
            self._imp_out[doc_id] = sorted(set(node["impacts"]))
        # 逆依存表。
        rev = {}
        for doc_id in self.nodes:
            for dst in self._dep_out[doc_id]:
                rev.setdefault(dst, set()).add(doc_id)
        for dst, srcs in rev.items():
            self._dep_in[dst] = sorted(srcs)

    # -- 解決(domain_of / type_of / status_of) ---------------------------

    def resolve(self, doc_id):
        """ID をコーパスの索引で解決する。{path, domain, type, status} か None。

        これがガード・リンタ・監査の事実上の domain_of / type_of / status_of。
        domain は frontmatter の domain から、type は frontmatter の type
        (無ければ id 接頭辞から)、status は frontmatter の status から引く。
        グラフに無い id は None(呼び出し側が dangling / 未解決として扱う)。
        """
        node = self.nodes.get(doc_id)
        if node is None:
            return None
        return {
            "path": node["path"],
            "domain": node["domain"],
            "type": node["type"],
            "status": node["status"],
        }

    def domain_of(self, doc_id):
        """ドメイン名、または索引に無ければ UNKNOWN。便宜関数。"""
        node = self.nodes.get(doc_id)
        if node is None:
            return UNKNOWN
        return node["domain"] or UNKNOWN

    def type_of(self, doc_id):
        """型コード、または索引に無ければ UNKNOWN。便宜関数。

        索引にある文書は frontmatter の type を優先する。索引に無い id は
        登録簿(接頭辞)で型を引き、それも未知なら UNKNOWN。
        """
        node = self.nodes.get(doc_id)
        if node is not None and node["type"]:
            return node["type"]
        reg = _registry.type_of(doc_id)
        return reg if reg else UNKNOWN

    def status_of(self, doc_id):
        node = self.nodes.get(doc_id)
        if node is None:
            return UNKNOWN
        return node["status"] or UNKNOWN

    # -- 前向き影響集合(R4) -----------------------------------------------

    def forward_impacts(self, doc_id):
        """impacts 端の推移閉包(自分自身は含めない)。サイクル安全。R4。"""
        return self._closure(doc_id, self._imp_out)

    def _closure(self, start, out_index):
        seen = set()
        stack = list(out_index.get(start, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(out_index.get(cur, []))
        seen.discard(start)
        return seen

    # -- 逆依存(R3 / 降格不変条件) ---------------------------------------

    def reverse_dependents(self, doc_id, current_only=False, transitive=False):
        """depends_on で doc_id を指す全ノード。

        current_only=True: 現行(current/accepted)のノードだけに絞る。
        transitive=True: 上流の閉包まで(誰の依存をたどっても doc_id に至るか)。
        既定は直接の依存だけ。削除安全ガードはこれを current_only=True で呼ぶ。
        """
        if transitive:
            result = self._reverse_closure(doc_id)
        else:
            result = set(self._dep_in.get(doc_id, []))
        if current_only:
            result = {n for n in result if self._is_current(n)}
        return result

    def reverse_current_dependents(self, doc_id):
        """= reverse_dependents(doc_id, current_only=True)(C7 / slice 03 名)。"""
        return self.reverse_dependents(doc_id, current_only=True)

    def _reverse_closure(self, start):
        seen = set()
        stack = list(self._dep_in.get(start, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(self._dep_in.get(cur, []))
        seen.discard(start)
        return seen

    def _is_current(self, doc_id):
        node = self.nodes.get(doc_id)
        if node is None:
            return False
        return _registry.is_current(node["status"])

    # -- 端の分類(R7) -----------------------------------------------------

    def classify_edges(self):
        """全端を分類して返す。list[Edge{src, dst, field, kind}]。決定的(整列)。

        kind:
          intra_domain          同一ドメイン(§3.6 で許される)
          cross_domain_icd      別ドメインかつ dst が ICD(許される)
          cross_domain_violation 別ドメインかつ dst が ICD でない依存端(R7違反)
          cross_domain_impact   別ドメインの影響端(助言。R7 違反ではない)
          dangling              dst が索引に無い

        cross_domain_violation は depends_on 端だけに付く(MASTER §5.2 / A.2)。
        cross-domain な impacts は cross_domain_impact(助言)に分類する。
        """
        edges = []
        for src in sorted(self.nodes):
            src_domain = self.nodes[src]["domain"] or UNKNOWN
            for dst in self._dep_out[src]:
                edges.append(self._classify_one(src, dst, "depends_on", src_domain))
            for dst in self._imp_out[src]:
                edges.append(self._classify_one(src, dst, "impacts", src_domain))
        return edges

    def _classify_one(self, src, dst, field, src_domain):
        if dst not in self.nodes:
            return Edge(src, dst, field, KIND_DANGLING)
        dst_domain = self.nodes[dst]["domain"] or UNKNOWN
        if dst_domain == src_domain:
            return Edge(src, dst, field, KIND_INTRA)
        # 別ドメイン。
        dst_type = self.type_of(dst)
        if field == "impacts":
            # impacts は ICD 境界の対象外(§3.6 は依存だけを縛る)。助言扱い。
            return Edge(src, dst, field, KIND_CROSS_IMPACT)
        if dst_type == "ICD":
            return Edge(src, dst, field, KIND_CROSS_ICD)
        return Edge(src, dst, field, KIND_CROSS_VIOLATION)

    # -- 逆孤児(R3/R8) ----------------------------------------------------

    def reverse_orphans(self):
        """構造的な不在(逆孤児)を二種類返す。現行文書だけが対象。

        {"req_without_spec": [...], "spec_without_test": [...]}(ID整列)。
        - req_without_spec: 現行 REQ r で、r を depends_on に持つ現行 SPEC が一つも無い。
        - spec_without_test: 現行 SPEC s で、s を depends_on に持つ現行 TEST が一つも無い。
        たどるリンクは depends_on のみ(決定的, slice 05 A.5)。
        """
        # 現行 SPEC / TEST が depends_on で指す先を集める。
        spec_targets = set()
        test_targets = set()
        for doc_id, node in self.nodes.items():
            if not self._is_current(doc_id):
                continue
            t = node["type"]
            if t == "SPEC":
                spec_targets.update(self._dep_out[doc_id])
            elif t == "TEST":
                test_targets.update(self._dep_out[doc_id])

        req_without_spec = []
        spec_without_test = []
        for doc_id, node in self.nodes.items():
            if not self._is_current(doc_id):
                continue
            t = node["type"]
            if t == "REQ" and doc_id not in spec_targets:
                req_without_spec.append(doc_id)
            elif t == "SPEC" and doc_id not in test_targets:
                spec_without_test.append(doc_id)
        return {
            "req_without_spec": sorted(req_without_spec),
            "spec_without_test": sorted(spec_without_test),
        }

    # -- 直列化 -------------------------------------------------------------

    def to_json(self):
        """直列化できるグラフ表現。nodes + 分類済み edges + 重複/警告。決定的。"""
        nodes = []
        for doc_id in sorted(self.nodes):
            n = self.nodes[doc_id]
            nodes.append({
                "id": doc_id,
                "type": n["type"],
                "domain": n["domain"],
                "status": n["status"],
                "path": n["path"],
                "depends_on": self._dep_out[doc_id],
                "impacts": self._imp_out[doc_id],
                "canonical_for": n["canonical_for"],
            })
        return {
            "root": self.root,
            "nodes": nodes,
            "edges": [dict(e) for e in self.classify_edges()],
            "duplicate_ids": {k: sorted(v) for k, v in sorted(self.dup_ids.items())},
            "parse_warnings": sorted(self.parse_warnings),
        }


# ---------------------------------------------------------------------------
# 構築
# ---------------------------------------------------------------------------

def build_graph(root):
    """docs ルート配下の全 .md を走査してグラフを組み立てる。

    frontmatter の無いファイルはノードにしない(parse_warning に記録)。
    list 型フィールドは _frontmatter.as_list を通して読む(MASTER §1 束縛規則)。
    決定的: ファイルは整列順に走査する。
    """
    g = Graph(root)
    if not os.path.isdir(root):
        return g

    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".md"):
                paths.append(os.path.join(dirpath, name))
    paths.sort()

    for path in paths:
        relpath = os.path.relpath(path, root)
        try:
            fm, _body, _errs = _frontmatter.parse_file(path)
        except (OSError, UnicodeDecodeError):
            g.parse_warnings.append(relpath)
            continue
        doc_id = fm.get("id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            # frontmatter が無い、または id を持たない → 参照できないのでノードにしない。
            g.parse_warnings.append(relpath)
            continue
        doc_id = doc_id.strip()
        node = {
            "id": doc_id,
            "path": relpath,
            "type": _coerce_str(fm.get("type")),
            "domain": _coerce_str(fm.get("domain")),
            "status": _coerce_str(fm.get("status")) or _registry.default_status(
                _coerce_str(fm.get("type"))) or "",
            "depends_on": _frontmatter.as_list(fm.get("depends_on")),
            "impacts": _frontmatter.as_list(fm.get("impacts")),
            "canonical_for": _frontmatter.as_list(fm.get("canonical_for")),
            "superseded_by": _coerce_str(fm.get("superseded_by")),
            "updated": _coerce_str(fm.get("updated")),
            "review_by": _coerce_str(fm.get("review_by")),
            "llm_context": _coerce_str(fm.get("llm_context")),
            # 孤児判定の第三連言(再現可能)に使う。frontmatter は素の true/false を
            # bool に解す。欠落・非 bool は None(= 再現可能でない)として残す(加法キー)。
            "reproducible": fm.get("reproducible"),
        }
        g._add_node(node)

    g._build_indices()
    return g


def _coerce_str(value):
    """frontmatter のスカラ値を str に正規化する。None/bool/欠落は '' になる。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    return str(value)
