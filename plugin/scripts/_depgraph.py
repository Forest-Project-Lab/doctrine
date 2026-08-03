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
# doctrine:begin SPEC-006
KIND_INTRA = "intra_domain"
KIND_CROSS_ICD = "cross_domain_icd"
KIND_CROSS_VIOLATION = "cross_domain_violation"
KIND_CROSS_IMPACT = "cross_domain_impact"
KIND_DANGLING = "dangling"
# doctrine:end SPEC-006

UNKNOWN = "UNKNOWN"


class Edge(dict):
    """一つの端。{src, dst, field, kind, mirrored} を持つ素朴な dict 部分型。

    dict なので to_json/JSON 化がそのまま通る。属性風アクセスも許す。
    field は "depends_on" か "impacts"。kind は上の KIND_* のどれか。

    mirrored は「反対向きの相手が居るか」(ADR-088)。`A --depends_on--> B` に対して
    `B --impacts--> A` が在れば真、逆も同じ。**同じ事実を両端から書いたという意味で
    あって、循環という意味ではない**(循環は find_cycles が返す)。kind とは別の軸なので
    別の欄に持つ —— 一つの端が同時に「越境違反」かつ「両端書き」でありうる。
    """

    def __init__(self, src, dst, field, kind, mirrored=False):
        super().__init__(src=src, dst=dst, field=field, kind=kind,
                         mirrored=bool(mirrored))

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _is_under_system(relpath):
    """統治木の横断の棚(_system/)に在るか(ADR-091)。決して例外を投げない。"""
    if not isinstance(relpath, str):
        return False
    return relpath.replace("\\", "/").startswith("_system/")


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
            # 採用先は登録簿が一度だけ定める(先勝ち。ADR-049)。自前の整列規則を持たない。
            keep = _registry.resolve_duplicate_id(self.dup_ids[doc_id])
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

    # -- 依存の循環(R3 / R8) ----------------------------------------------

    def find_cycles(self):
        """depends_on 端の循環(自己依存と多頂点循環)を列挙する。ADR-038 / #89。

        追跡性(要求→仕様→実装→テスト→決定)の階層に循環は本来あり得ず、循環の
        存在はモデル化誤りの兆候である。循環の全構成員は「現行の依存が残る」と
        判定され続けて降格できなくなる論理的デッドロックを生む。

        返り値: list[list[str]]。各要素は一つの循環の、id を整列した list。
        自己依存 A→A は [A] の 1 要素として返す。索引に無い(dangling)端は
        たどらない(実在するノード間の循環だけを見る)。決定的(整列)。
        Tarjan の強連結成分。グラフサイズに対し線形で、サイクル安全。
        """
        index = {}
        low = {}
        on_stack = {}
        stack = []
        counter = [0]
        components = []

        def out_edges(v):
            return [w for w in self._dep_out.get(v, []) if w in self.nodes]

        def strongconnect(v):
            # 再帰でなく明示スタックで回す(深い連鎖でも RecursionError にしない)。
            work = [(v, 0)]
            while work:
                node, pi = work[-1]
                if pi == 0:
                    index[node] = low[node] = counter[0]
                    counter[0] += 1
                    stack.append(node)
                    on_stack[node] = True
                succ = out_edges(node)
                if pi < len(succ):
                    work[-1] = (node, pi + 1)
                    w = succ[pi]
                    if w not in index:
                        work.append((w, 0))
                    elif on_stack.get(w):
                        low[node] = min(low[node], index[w])
                    continue
                # node の後続を処理し終えた。
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        comp.append(w)
                        if w == node:
                            break
                    components.append(comp)
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])

        for v in sorted(self.nodes):
            if v not in index:
                strongconnect(v)

        cycles = []
        for comp in components:
            if len(comp) > 1:
                cycles.append(sorted(comp))
            elif len(comp) == 1:
                v = comp[0]
                if v in self._dep_out.get(v, []):  # 自己依存 A→A
                    cycles.append([v])
        cycles.sort()
        return cycles

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
        # 両端書きの判定に使う対の集合(ADR-088)。読み手に畳み方を発明させないため、
        # 上流が知っている事実をここで印にする。
        dep_pairs = {(s, d) for s in self.nodes for d in self._dep_out[s]}
        imp_pairs = {(s, d) for s in self.nodes for d in self._imp_out[s]}
        edges = []
        for src in sorted(self.nodes):
            src_domain = self.nodes[src]["domain"] or UNKNOWN
            for dst in self._dep_out[src]:
                edges.append(self._classify_one(
                    src, dst, "depends_on", src_domain,
                    mirrored=(dst, src) in imp_pairs))
            for dst in self._imp_out[src]:
                edges.append(self._classify_one(
                    src, dst, "impacts", src_domain,
                    mirrored=(dst, src) in dep_pairs))
        return edges

    def _classify_one(self, src, dst, field, src_domain, mirrored=False):
        if dst not in self.nodes:
            return Edge(src, dst, field, KIND_DANGLING, mirrored)
        dst_domain = self.nodes[dst]["domain"] or UNKNOWN
        if dst_domain == src_domain:
            return Edge(src, dst, field, KIND_INTRA, mirrored)
        # 別ドメイン。
        dst_type = self.type_of(dst)
        if field == "impacts":
            # impacts は ICD 境界の対象外(§3.6 は依存だけを縛る)。助言扱い。
            return Edge(src, dst, field, KIND_CROSS_IMPACT, mirrored)
        if dst_type == "ICD":
            return Edge(src, dst, field, KIND_CROSS_ICD, mirrored)
        return Edge(src, dst, field, KIND_CROSS_VIOLATION, mirrored)

    # -- 逆孤児(R3/R8) ----------------------------------------------------

    def reverse_orphans(self):
        """構造的な不在(逆孤児)を二種類返す。現行文書だけが対象。

        {"req_without_spec": [...], "spec_without_test": [...]}(ID整列)。
        - req_without_spec: 現行 REQ r で、r を depends_on に持つ現行 SPEC が一つも無い。
          ただし横断の棚(_system/)に在る要求は除く(ADR-091。_system の正本は辺で
          指されない規約であり、指させようとすると越境依存のガードが拒む)。
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
                # 横断の棚(_system/)に在る要求は、辺で指されない(ADR-091)。
                # この体系の規約では _system の正本(DECIDED・NONGOAL・WATCH)は本文で
                # 参照され、frontmatter の depends_on では指されない(実測: 一件も無い。
                # _system に ICD が無いため、越境依存のガードがそもそも拒む)。
                # 製品の粒度の要求も同じ棚に在るので、逆孤児の対象にしない。
                if not _is_under_system(node["path"]):
                    req_without_spec.append(doc_id)
            elif t == "SPEC" and doc_id not in test_targets:
                spec_without_test.append(doc_id)
        return {
            "req_without_spec": sorted(req_without_spec),
            "spec_without_test": sorted(spec_without_test),
        }

    # -- 直列化 -------------------------------------------------------------

    # 直列化のときに索引の値へ差し替える項(ADR-087 の唯一の例外)。生のフロントマターの
    # 値ではなく解決済みの端を返す。読み手にはこちらが有用である。
    _INDEXED_FIELDS = ("depends_on", "impacts")

    def to_json(self):
        """直列化できるグラフ表現。nodes + 分類済み edges + 重複/警告。決定的。

        **白名簿を持たない(ADR-087)。** 組み立てが節点へ入れた項をすべて返す。
        以前は八項の白名簿で絞っており、正本がどこにも無いまま組み立てと別々に手で
        保つ形になっていた。そして実際にずれた —— 組み立てが四項(superseded_by・
        updated・review_by・llm_context)を足した後も白名簿は八項のままで、必須項の
        題名は最初から集められてさえいなかった。項を足せば返る形にする。
        受入が組み立てと直列化の項の一致を凍らせている(それが本当の歯止めである)。
        """
        nodes = []
        for doc_id in sorted(self.nodes):
            n = dict(self.nodes[doc_id])
            n["id"] = doc_id
            n["depends_on"] = self._dep_out[doc_id]
            n["impacts"] = self._imp_out[doc_id]
            nodes.append(n)
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
            # 題名は必須項(REQUIRED_KEYS_L2)。集めていなかったので問い合わせから
            # 落ちており、読み手(doctrine-lens)が別経路を持つ原因になっていた(ADR-087)。
            "title": _frontmatter.coerce_str(fm.get("title")),
            # 出所も必須項(確定事実3)。題名と同じく集めていなかったので、宣言した
            # 道が実在するかを誰も検められなかった(ADR-097)。ADR-087 が名指した
            # 「必須項が集められてさえいない」欠陥の二件目である。
            "sources": _frontmatter.as_list(fm.get("sources")),
            "type": _frontmatter.coerce_str(fm.get("type")),
            "domain": _frontmatter.coerce_str(fm.get("domain")),
            # 責任者も必須項(確定事実3)。集めていない最後の一つだった
            # (題名 ADR-087・出所 ADR-097 に続く三件目。ADR-098)。
            "owner": _frontmatter.coerce_str(fm.get("owner")),
            "status": _frontmatter.coerce_str(fm.get("status")) or _registry.default_status(
                _frontmatter.coerce_str(fm.get("type"))) or "",
            "depends_on": _frontmatter.as_list(fm.get("depends_on")),
            "impacts": _frontmatter.as_list(fm.get("impacts")),
            "canonical_for": _frontmatter.as_list(fm.get("canonical_for")),
            "superseded_by": _frontmatter.coerce_str(fm.get("superseded_by")),
            "updated": _frontmatter.coerce_str(fm.get("updated")),
            "review_by": _frontmatter.coerce_str(fm.get("review_by")),
            "llm_context": _frontmatter.coerce_str(fm.get("llm_context")),
            # ドメインの種類(ADR-092)。省略は未分類なので空文字にする。既定は無いので
            # 型から導かない。値の当否はリンタが検め、ここでは化けずに運ぶだけにする。
            "subdomain": _frontmatter.coerce_str(fm.get("subdomain")),
            # 孤児判定の第三連言(再現可能)に使う。frontmatter は素の true/false を
            # bool に解す。欠落・非 bool は None(= 再現可能でない)として残す(加法キー)。
            "reproducible": fm.get("reproducible"),
        }
        g._add_node(node)

    g._build_indices()
    return g


