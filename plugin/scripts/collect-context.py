#!/usr/bin/env python3
"""タスク別の最小コンテキストを集める道具(llm-context-pack, R5)。

保証限界:
- 予防: never 群(RESEARCH/ARCHIVE と明示 never)を被覆計算より前に必ず除外する。
  never 文書は要求を「覆う」場合でもパックに入らない(R5「never群が渡らない」)。
- 検出: 要求の被覆を満たす最少集合を貪欲法で選び、覆えなかった要求を uncovered
  として表に出す。各事実に出所(由来文書)を付け、語彙が近い文書の取り違えを防ぐ。
- 委ねる: 境界違反(ドメイン越え依存が ICD でない)の拒否はガード/監査に委ね、
  ここでは印を付けるだけ。最適なトークン上限の値は運用と受入テストに委ねる(§7)。

CLI:
  collect-context.py --task TASKSPEC [--docs-root R] [--domain D]
                     [--require REQ_ID ...] [--format json|md] [--max-tokens N]
TASKSPEC は自由記述のタスク文、またはタスクを書いたファイルへのパス。
被覆対象の要求は --require で明示するのが権威。--require が無いときは TASKSPEC
の語を REQ の title に当てて候補を引く(最善努力。被覆の保証ではない)。

終了コード: 0 が常態(覆えない要求があっても 0。それは報告すべき状態であって
スクリプトの失敗ではない)。2 は使い方の誤り(CLI 引数の不備)。

標準ライブラリだけを使う。pip も通信も使わない。出力は決定的(整列済み)。
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _frontmatter
import _registry


# --- トークン推定(inject-contract と同じ保守的な見積もり, MASTER §5.4) -------

def estimate_tokens(text, chars_per_token=4.0):
    """文字数ベースの保守的な推定。決定的。日本語では過大に見積もる側に倒れる。"""
    if not text:
        return 0
    return int(math.ceil(len(text) / float(chars_per_token)))


# --- 設定(二つの上限は別キー, C10) ----------------------------------------

def _config_path(docs_root):
    return os.path.join(docs_root, "_system", ".context-config.json")


def load_task_pack_cap(docs_root, override):
    """task_pack_token_cap を解決する。injection_token_cap とは別キー(C10)。

    解決順: --max-tokens(override) → <docs-root>/_system/.context-config.json の
    task_pack_token_cap → None(上限なし)。injection_token_cap は読まない。
    """
    if override is not None:
        return override
    path = _config_path(docs_root)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict):
        return None
    cap = cfg.get("task_pack_token_cap")
    if isinstance(cap, bool):
        return None
    if isinstance(cap, int):
        return cap
    if isinstance(cap, float):
        return int(cap)
    return None


# --- 引数解析 ---------------------------------------------------------------

def _parse_args(argv):
    """argv を (opts, error) に解く。error があれば usage 終了に回す。"""
    opts = {
        "task": None,
        "docs_root": None,
        "domain": None,
        "require": [],
        "format": "json",
        "max_tokens": None,
    }
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--task":
            if i + 1 >= n:
                return None, "--task にはタスク記述が必要"
            opts["task"] = argv[i + 1]
            i += 2
            continue
        if a == "--docs-root":
            if i + 1 >= n:
                return None, "--docs-root にはパスが必要"
            opts["docs_root"] = argv[i + 1]
            i += 2
            continue
        if a == "--domain":
            if i + 1 >= n:
                return None, "--domain には名前が必要"
            opts["domain"] = argv[i + 1]
            i += 2
            continue
        if a == "--require":
            # 一つ以上の REQ_ID。次の '--' 始まりまで取り込む(REPEATED でも可)。
            if i + 1 >= n or argv[i + 1].startswith("--"):
                return None, "--require には REQ_ID が必要"
            i += 1
            while i < n and not argv[i].startswith("--"):
                opts["require"].append(argv[i])
                i += 1
            continue
        if a == "--format":
            if i + 1 >= n:
                return None, "--format には json か md が必要"
            val = argv[i + 1]
            if val not in ("json", "md"):
                return None, "--format は json か md"
            opts["format"] = val
            i += 2
            continue
        if a == "--max-tokens":
            if i + 1 >= n:
                return None, "--max-tokens には整数が必要"
            try:
                opts["max_tokens"] = int(argv[i + 1])
            except ValueError:
                return None, "--max-tokens は整数"
            i += 2
            continue
        return None, "不明な引数: %s" % a

    if opts["task"] is None:
        return None, "--task は必須"
    return opts, None


def _usage(msg):
    sys.stdout.write("usage error: %s\n" % msg)
    sys.stdout.write(
        "collect-context.py --task TASKSPEC [--docs-root R] [--domain D] "
        "[--require REQ_ID ...] [--format json|md] [--max-tokens N]\n"
    )
    return 2


# --- docs ルートの解決 ------------------------------------------------------

def resolve_docs_root(explicit):
    """docs ルートを解く。--docs-root → $CLAUDE_PROJECT_DIR/docs → ./docs。"""
    if explicit:
        return explicit
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cand = os.path.join(proj, "docs")
        if os.path.isdir(cand):
            return cand
    return "docs"


def read_task_text(taskspec):
    """TASKSPEC を読む。ファイルなら中身、そうでなければ文字列そのもの。"""
    try:
        if taskspec and os.path.isfile(taskspec):
            with open(taskspec, "r", encoding="utf-8-sig", newline="") as fh:
                return fh.read()
    except OSError:
        pass
    return taskspec or ""


# --- 文書の事実抽出(出所付き) ---------------------------------------------

def _facts_for(doc_id, title, body):
    """文書本文から事実行を切り出す。出所は呼び出し側が付ける。

    DECIDED/ICD/箇条書き型は行ごとの事実、散文(SPEC 等)は見出し節を単位にする。
    本文が無い、または読めないときは title 一行を唯一の事実にする(出所は保つ)。
    """
    facts = []
    if body:
        for raw in body.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if stripped == "":
                continue
            # 箇条書き(-, *)と見出し(#)を事実の単位にする。散文の通常行も拾う。
            if stripped.startswith(("- ", "* ")):
                facts.append(stripped[2:].strip())
            elif stripped.startswith("#"):
                facts.append(stripped.lstrip("#").strip())
            else:
                facts.append(stripped)
    if not facts:
        facts.append(title or doc_id)
    # 決定的: 出現順を保つが、空は落とす。
    return [f for f in facts if f]


# --- 被覆の計算(最少集合, §3.9) -------------------------------------------

def _covers(node_id, req_universe, graph, dep_index):
    """node_id が覆う要求集合を req_universe の中で返す。

    覆うとは: node_id 自身が REQ(== req)、または node_id の depends_on 閉包が
    その REQ に至る。閉包は depends_on 端のみ(決定的, サイクル安全)。

    返り値: (covered:set, by_trace:bool)。by_trace は「自分自身でなく追跡で
    覆う」ものが一つでもあれば True。実体(SPEC等)を裸の REQ より優先するための印。
    """
    covered = set()
    by_trace = False
    if node_id in req_universe:
        covered.add(node_id)        # 自分自身(REQ)を覆う — 実体ではない
    reach = _dep_closure(node_id, dep_index)
    for r in req_universe:
        if r in reach:
            covered.add(r)
            by_trace = True         # 追跡で覆う = 実体を運ぶ
    return covered, by_trace


def _dep_closure(start, dep_index):
    """depends_on 端の前向き閉包(自分自身は含めない)。サイクル安全。"""
    seen = set()
    stack = list(dep_index.get(start, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(dep_index.get(cur, []))
    seen.discard(start)
    return seen


def greedy_cover(eligible_ids, req_universe, graph, dep_index, token_of):
    """貪欲な最少集合被覆(決定的) + 逆向きの剪定(reverse-prune)。

    返り値: (selected_ids:list, covers_map:dict, uncovered:set)。
    各反復で「未被覆の要求を最も多く覆う」文書を選ぶ。同点はトークンの少ない方、
    さらに同点は id の辞書順。選んだ後、後から見て他で覆える文書を落とす剪定で
    貪欲解を最少へ寄せる。覆えない要求は uncovered として残す(隠さない)。
    """
    covers_map = {}
    substantive = {}      # nid -> True if it covers by tracing (carries 実体)
    for nid in eligible_ids:
        c, by_trace = _covers(nid, req_universe, graph, dep_index)
        if c:
            covers_map[nid] = c
            substantive[nid] = by_trace

    remaining = set(req_universe)
    selected = []
    selected_set = set()
    # 決定的な走査順(id 昇順)。同点での最終 tie-break が「id 辞書順で先」になる
    # よう、昇順に見て狭義の改善のときだけ best を入れ替える(等しいなら先勝ち)。
    order = sorted(covers_map)
    while remaining:
        best = None
        best_key = None
        for nid in order:
            if nid in selected_set:
                continue
            gain = len(covers_map[nid] & remaining)
            if gain == 0:
                continue
            # 選好キー(大きいほど良い): まず被覆数、次に実体を持つ文書(SPEC等を
            # 裸の REQ より優先。REQ は需要の宣言で、実体は追跡先が運ぶ)、
            # 次にトークンの少ない方。id 辞書順の先勝ちは昇順走査+狭義比較で得る。
            key = (gain, 1 if substantive.get(nid) else 0, -token_of(nid))
            if best is None or key > best_key:
                best = nid
                best_key = key
        if best is None:
            break       # 残りは覆えない
        selected.append(best)
        selected_set.add(best)
        remaining -= covers_map[best]

    # 逆向き剪定: 最後に選んだものから順に、その文書が覆う要求が他の選択で
    # すべて覆えるなら落とす(冗長な文書を最少へ寄せる)。決定的。
    pruned = list(selected)
    for nid in reversed(selected):
        others = [o for o in pruned if o != nid]
        others_cover = set()
        for o in others:
            others_cover |= covers_map.get(o, set())
        need = covers_map[nid] & set(req_universe)
        if need <= others_cover:
            pruned = others
    # 元の選択順を保つ(剪定後)。
    final = [nid for nid in selected if nid in set(pruned)]
    return final, covers_map, set(remaining)


# --- 依存閉包の同梱(ICD 等。never は決して引かない) ------------------------

def dependency_closure(selected_ids, graph, dep_index, excluded_never, already):
    """選んだ文書の depends_on 閉包(推移的)を同梱候補にする。never は決して引かない。

    返り値: (closure_ids:list, boundary_flags:dict)。closure_ids は selected と
    `already`(既に primary で覆われた要求 id)に無い被依存の id(整列)。「閉包」の名に
    忠実に、一段だけでなく depends_on を多段でたどる(SPEC→ICD-A→ICD-B なら ICD-B も
    引く, finding #17)。各段で never 群(excluded_never)は決して引かず、たどりもしない
    (R5 の硬い保証は閉包の途中でも崩れない)。境界違反(ドメイン越え依存が ICD でない)は
    印を付けるが拒否はしない(ガード/監査の職分)。サイクル安全(訪問済みは再訪しない)。
    """
    closure = set()
    boundary = {}
    skip = set(selected_ids) | set(already)
    # 既に閉包に入れた/起点の id は再展開しない(サイクル安全・決定的)。
    visited = set(selected_ids)
    # 起点(selected)から多段にたどる。スタックには (src_id, dep_id) を積む。
    stack = []
    for nid in selected_ids:
        for dep in dep_index.get(nid, []):
            stack.append((nid, dep))
    while stack:
        src_id, dep = stack.pop()
        if dep in excluded_never:
            continue              # never は決して引かない・たどらない(R5)
        dep_node = graph.nodes.get(dep)
        if dep_node is None:
            continue              # 索引に無い(dangling)→ 同梱しない・たどらない
        # 境界違反の検出(ドメイン越え依存が ICD でない)。出所の domain で判定。
        src = graph.nodes.get(src_id)
        src_domain = src["domain"] if src else None
        if src_domain and dep_node["domain"] and dep_node["domain"] != src_domain:
            if dep_node["type"] != "ICD":
                boundary[dep] = "境界違反"
        if dep not in skip:
            closure.add(dep)
        # 次の段へ。dep を起点に depends_on をたどる(訪問済みは展開しない)。
        if dep not in visited:
            visited.add(dep)
            for nxt in dep_index.get(dep, []):
                stack.append((dep, nxt))
    return sorted(closure), boundary


# --- パックの組み立て -------------------------------------------------------

def build_pack(docs_root, required, domain, task_text):
    """被覆計算を回し、パックの構造(dict)を返す。出力整形は呼び出し側。"""
    graph = _depgraph.build_graph(docs_root)

    # 本文と title を読む索引(出所付き事実のため)。_depgraph のノードは title を
    # 持たないので、ここで frontmatter から拾う。
    bodies = {}
    titles = {}
    for nid, node in graph.nodes.items():
        path = os.path.join(docs_root, node["path"])
        try:
            fm, body, _errs = _frontmatter.parse_file(path)
        except (OSError, UnicodeDecodeError):
            fm, body = {}, ""
        bodies[nid] = body
        t = fm.get("title")
        titles[nid] = t if isinstance(t, str) else ""

    # --- R5: never 群を被覆計算より前に必ず除外する ---
    excluded_never = set()
    for nid, node in graph.nodes.items():
        meta = {"type": node["type"], "llm_context": node["llm_context"] or None}
        if _registry.effective_llm_context(meta) == "never":
            excluded_never.add(nid)

    # depends_on 索引(never も閉包の禁を判定するため keys は全 id)。
    dep_index = {nid: graph._dep_out.get(nid, []) for nid in graph.nodes}

    # 被覆の宇宙 U。--require が権威。無ければ task の語で REQ title を当てる。
    if required:
        req_universe = set(required)
    else:
        req_universe = _derive_reqs(graph, task_text, domain, excluded_never)

    # --require の中に索引に無い REQ があれば即 uncovered。
    missing_reqs = {r for r in req_universe if r not in graph.nodes}

    # 適格な task 文書(候補)。never は既に除外。非現行と他ドメインは外す。
    eligible = []
    for nid, node in graph.nodes.items():
        if nid in excluded_never:
            continue
        eff = _registry.effective_llm_context(
            {"type": node["type"], "llm_context": node["llm_context"] or None})
        # always 群は SessionStart 契約に既にあるので二重には出さない。
        if eff != "task" and node["type"] != "REQ":
            # REQ 自身は task 群。それ以外で task でないものは候補にしない。
            continue
        if not _registry.is_current(node["status"]):
            continue
        if domain and node["domain"] and node["domain"] != domain:
            continue
        eligible.append(nid)

    # REQ が宇宙にあり索引にあるなら、その REQ 自身も適格(自分を覆う)。
    for r in req_universe:
        if r in graph.nodes and r not in eligible:
            node = graph.nodes[r]
            if r not in excluded_never and _registry.is_current(node["status"]):
                if not (domain and node["domain"] and node["domain"] != domain):
                    eligible.append(r)
    eligible = sorted(set(eligible))

    def token_of(nid):
        return estimate_tokens(titles.get(nid, "") + bodies.get(nid, ""))

    selected, covers_map, uncovered = greedy_cover(
        eligible, req_universe, graph, dep_index, token_of)

    # 覆えない要求 = 貪欲で残った分 + そもそも索引に無い要求。
    uncovered = set(uncovered) | missing_reqs

    # never 群でのみ言及される要求を見分けて理由を添える。要求が uncovered で、
    # かつ「never 文書なら覆えた(自分自身が never、または never 文書の追跡が
    # その要求に至る)」とき never-only と判定する。R5 の「除外を表に出す」。
    never_reach = set()
    for nid in excluded_never:
        if nid in req_universe:
            never_reach.add(nid)        # 要求自体が never 文書
        for r in _dep_closure(nid, dep_index):
            if r in req_universe:
                never_reach.add(r)      # never 文書の追跡がその要求に至る
    never_only = {r for r in uncovered if r in never_reach}

    # 依存閉包(ICD 等)を同梱。never は決して引かない。選択済みの文書と、既に
    # primary で覆われている要求 id は二重に出さない(同梱は不足を補うため)。
    already = set(selected) | (set(req_universe) - uncovered)
    closure_ids, boundary = dependency_closure(
        selected, graph, dep_index, excluded_never, already)

    # 出力レコードを組み立てる。
    primary_records = [_record(graph, bodies, titles, nid, covers_map, "primary",
                               boundary) for nid in selected]
    dependency_records = [_record(graph, bodies, titles, nid, covers_map,
                                  "dependency", boundary) for nid in closure_ids]

    return {
        "graph": graph,
        "bodies": bodies,
        "required": sorted(req_universe),
        "selected": selected,
        "closure": closure_ids,
        "primary_records": primary_records,
        "dependency_records": dependency_records,
        "uncovered": sorted(uncovered),
        "never_only": sorted(never_only),
        "boundary": boundary,
        "excluded_never": sorted(excluded_never),
    }


def _record(graph, bodies, titles, nid, covers_map, role, boundary):
    """一文書の出力レコード(出所付き事実)を作る。"""
    node = graph.nodes[nid]
    title = titles.get(nid, "")
    facts = _facts_for(nid, title, bodies.get(nid, ""))
    rec = {
        "id": nid,
        "title": title,
        "domain": node["domain"],
        "type": node["type"],
        "path": node["path"],
        "status": node["status"],
        "covers": sorted(covers_map.get(nid, set())),
        "role": role,
        "facts": [
            {"text": f, "source_id": nid, "source_path": node["path"]}
            for f in facts
        ],
    }
    if nid in boundary:
        rec["boundary"] = boundary[nid]
    return rec


def _derive_reqs(graph, task_text, domain, excluded_never):
    """--require が無いとき、task の語を REQ の title に当てて候補を引く。

    最善努力(語の重なりで当てる)。被覆の保証ではない。決定的(整列)。
    """
    words = set(w for w in _tokenize(task_text) if len(w) >= 2)
    reqs = set()
    for nid, node in graph.nodes.items():
        if node["type"] != "REQ":
            continue
        if nid in excluded_never:
            continue
        if not _registry.is_current(node["status"]):
            continue
        if domain and node["domain"] and node["domain"] != domain:
            continue
        title = (node.get("title") or "").lower()
        title_words = set(_tokenize(title))
        if words & title_words:
            reqs.add(nid)
    return reqs


def _tokenize(text):
    """素朴な語分割(空白/記号区切り、小文字化)。決定的。"""
    if not text:
        return []
    out = []
    buf = []
    for ch in text.lower():
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


# --- 整形(json / md) -------------------------------------------------------

def _enforce_cap(records, cap):
    """task_pack_token_cap を守る。要求を唯一覆う文書は決して落とさない。

    返り値: (kept_records, trimmed:bool)。被覆の限界余剰が小さい(他で覆える)
    文書から落とす。覆える要求がゼロになる落とし方はしない。
    """
    if cap is None or cap <= 0:
        return records, False
    # まず一意被覆(他に同じ要求を覆う文書が無い)を必須として守る。
    all_covered = {}
    for rec in records:
        for r in rec["covers"]:
            all_covered.setdefault(r, []).append(rec["id"])
    unique_keepers = set()
    for r, holders in all_covered.items():
        if len(holders) == 1:
            unique_keepers.add(holders[0])

    def rec_tokens(rec):
        text = rec["title"] + "".join(f["text"] for f in rec["facts"])
        return estimate_tokens(text)

    kept = list(records)
    trimmed = False
    # 限界被覆の小さい(=他で覆える, dependency 役を優先的に)文書から落とす。
    droppable = [
        rec for rec in kept
        if rec["id"] not in unique_keepers
    ]
    # 落とす順: dependency を先に、次に被覆数の少ない順、id 辞書順(決定的)。
    droppable.sort(key=lambda r: (r["role"] != "dependency",
                                  len(r["covers"]), r["id"]))
    idx = 0
    while idx < len(droppable):
        total = sum(rec_tokens(r) for r in kept)
        if total <= cap:
            break
        victim = droppable[idx]
        kept = [r for r in kept if r["id"] != victim["id"]]
        trimmed = True
        idx += 1
    return kept, trimmed


def render_json(pack, cap):
    primary = pack["primary_records"]
    dependency = pack["dependency_records"]
    kept, trimmed = _enforce_cap(primary + dependency, cap)
    kept_ids = {r["id"] for r in kept}
    out = {
        "schema": "context-pack/1",
        "required": pack["required"],
        "docs": [r for r in (primary + dependency) if r["id"] in kept_ids],
        "uncovered": pack["uncovered"],
        "uncovered_reasons": _uncovered_reasons(pack),
        "boundary_violations": sorted(pack["boundary"].keys()),
        "trimmed": trimmed,
    }
    return json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _uncovered_reasons(pack):
    reasons = {}
    never_only = set(pack["never_only"])
    for r in pack["uncovered"]:
        if r in never_only:
            reasons[r] = "never 群でのみ言及 → パック対象外"
        else:
            reasons[r] = "被覆する現行文書が無い"
    return reasons


def render_md(pack, cap):
    primary = pack["primary_records"]
    dependency = pack["dependency_records"]
    kept, trimmed = _enforce_cap(primary + dependency, cap)
    kept_ids = {r["id"] for r in kept}

    lines = []
    lines.append("# タスク・コンテキスト・パック")
    lines.append("")
    if pack["required"]:
        lines.append("被覆対象の要求: " + ", ".join(pack["required"]))
    else:
        lines.append("要求未指定: 被覆対象なし")
    lines.append("")

    for rec in primary:
        if rec["id"] not in kept_ids:
            continue
        _render_doc_md(lines, rec)

    dep_kept = [r for r in dependency if r["id"] in kept_ids]
    if dep_kept:
        lines.append("## 依存により同梱")
        lines.append("")
        for rec in dep_kept:
            _render_doc_md(lines, rec)

    if pack["uncovered"]:
        lines.append("## 覆えなかった要求")
        lines.append("")
        reasons = _uncovered_reasons(pack)
        for r in pack["uncovered"]:
            lines.append("- %s (%s)" % (r, reasons[r]))
        lines.append("")

    if trimmed:
        lines.append("注記: task_pack_token_cap を超えたため、限界被覆の小さい"
                     "文書を切り詰めた。")
        lines.append("")

    return "\n".join(lines) + "\n"


def _render_doc_md(lines, rec):
    head = "## %s — %s" % (rec["id"], rec["title"])
    if rec["covers"]:
        head += "  (covers: %s)" % ", ".join(rec["covers"])
    if "boundary" in rec:
        head += "  (%s)" % rec["boundary"]
    lines.append(head)
    lines.append("")
    for f in rec["facts"]:
        lines.append("- %s  〔出所: %s · %s〕"
                     % (f["text"], f["source_id"], f["source_path"]))
    lines.append("")


# --- main -------------------------------------------------------------------

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    docs_root = resolve_docs_root(opts["docs_root"])
    if not os.path.isdir(docs_root):
        # ルート不在でも壊さない: 空だが妥当な結果を返す(覆える文書ゼロ)。
        empty = {
            "schema": "context-pack/1",
            "required": sorted(opts["require"]),
            "docs": [],
            "uncovered": sorted(opts["require"]),
            "uncovered_reasons": {r: "docs ルートが無い"
                                  for r in sorted(opts["require"])},
            "boundary_violations": [],
            "trimmed": False,
        }
        if opts["format"] == "md":
            sys.stdout.write("# タスク・コンテキスト・パック\n\n"
                             "docs ルートが見つからない: %s\n" % docs_root)
        else:
            sys.stdout.write(json.dumps(empty, ensure_ascii=False,
                                        sort_keys=True, indent=2) + "\n")
        return 0

    cap = load_task_pack_cap(docs_root, opts["max_tokens"])
    task_text = read_task_text(opts["task"])

    pack = build_pack(docs_root, opts["require"], opts["domain"], task_text)

    if opts["format"] == "md":
        sys.stdout.write(render_md(pack, cap))
    else:
        sys.stdout.write(render_json(pack, cap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
