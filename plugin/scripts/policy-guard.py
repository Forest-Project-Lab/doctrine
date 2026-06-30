#!/usr/bin/env python3
"""三つのガード(不変・ICD依存・削除安全)。PreToolUse と PostToolUse の両方に登録する。

保証限界:
- 予防: 書き込み/編集/削除を適用する前に三つの不変条件を点検し、違反を deny で止める。
  Guard1 不変(アーカイブ・既存ADRの改変拒否)、Guard2 ICD依存境界(R7)、Guard3 削除安全
  (現行の逆依存が残る降格/本文消し/rm・git rm・mv を拒否)。最初に拒否したガードで止める。
- 検出: Edit/MultiEdit は適用前に全文を再構成できないため、PostToolUse で書かれた
  ファイルを読み直し、Guard2/Guard3 違反なら decision:block を出す(C4)。
- 委ねる: 死リンク・逆孤児・古び等の全件監査は docs-audit に委ねる。助言だけのリンタは
  decision を出さない(C4)。ドメイン解決は _depgraph.resolve に委ねる(IDだけでは
  ドメインは決まらない、§3.4)。

頑健性(MASTER §3.6):
- 不変ガード(Guard1)と削除安全ガード(Guard3)が落ちたら fail-closed(deny「ガード異常、
  手で確認」)。Guard2(ICD依存)は docs/** の外の、フロントマターを持たない純粋な非文書
  Write のときだけ fail-open(allow)。それ以外の Guard2 例外も fail-closed。
- Hook 事象では main から例外を投げない。判定は JSON に載せ、終了コードは常に 0。

C13 の判定(重要 — 将来の改変で静かに fail-open へ倒れないよう明記する):
  構文上正しい id だが索引(グラフ)に無いだけ(dangling)→ guard は ALLOW(死リンクは
  監査の役目)。登録簿が接頭辞からして型を判定できない id(type_of が UNKNOWN)→ guard は
  DENY(fail-closed, R7)。この二つを取り違えないこと。

標準ライブラリのみ。pip も通信も使わない。決定的に動く。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _depgraph
import _frontmatter
import _registry


# ---------------------------------------------------------------------------
# Hook JSON の組み立て(MASTER §3.2 / §3.3)
# ---------------------------------------------------------------------------

def _pre_allow():
    """PreToolUse の通過(明示 allow)。"""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "",
        }
    }


def _pre_deny(reason):
    """PreToolUse の拒否(最強のレバー)。理由は日本語のガード文。"""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _post_block(reason):
    """PostToolUse の block(C4)。reason と additionalContext に同じ文を載せる。"""
    return {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": reason,
        },
    }


def _post_quiet():
    """PostToolUse の通過(空)。block を出さないときは空オブジェクト。"""
    return {}


# ---------------------------------------------------------------------------
# ルート解決(docs/ を上にたどって探す)
# ---------------------------------------------------------------------------

def _find_docs_root(start_path, cwd=None):
    """start_path から上にたどって docs/ ディレクトリを探す。見つからなければ None。

    term-check.py と同じ規約。グラフ構築(ドメイン解決・逆依存)に使う。cwd は
    start_path から見つからなかったときの控え。
    """
    candidates = []
    if start_path:
        candidates.append(os.path.dirname(os.path.abspath(start_path)))
    if cwd:
        candidates.append(os.path.abspath(cwd))
    for cur in candidates:
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            if os.path.basename(cur) == "docs":
                return cur
            cand = os.path.join(cur, "docs")
            if os.path.isdir(cand):
                return cand
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def _build_graph(docs_root):
    """docs_root からグラフを組む。root が無ければ空グラフを返す。"""
    if not docs_root or not os.path.isdir(docs_root):
        return _depgraph.build_graph(docs_root or "")
    return _depgraph.build_graph(docs_root)


# ---------------------------------------------------------------------------
# パスの判定
# ---------------------------------------------------------------------------

def _is_under_archive(file_path):
    """file_path が <domain>/archive/ の下なら True。アーカイブ木の不変判定(§3.8)。"""
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    parts = norm.split("/")
    return "archive" in parts


def _is_under_docs(file_path):
    """file_path が docs/ の木の中なら True(Guard2 の fail-open 判定に使う)。"""
    if not file_path:
        return False
    norm = file_path.replace("\\", "/")
    return "docs" in norm.split("/")


# ---------------------------------------------------------------------------
# Guard 1 — 不変(アーカイブ + 既存ADR)  [R8, §3.8]
# ---------------------------------------------------------------------------

# ADR の唯一許される lifecycle 変化(D0.8 / §3.6.2 carve-out)。
_ADR_CARVEOUT_STATUS = {
    ("proposed", "accepted"),
    ("accepted", "superseded"),
    ("accepted", "deprecated"),
}
# carve-out で触ってよいキー(status 遷移に伴うもの)。
_ADR_CARVEOUT_KEYS = frozenset({"status", "superseded_by", "updated"})


def guard_immutability(file_path, tool, tin):
    """Guard1。拒否理由(str)を返す。問題なければ None。

    1. file_path が archive/ の下 → 常に deny(Write も Edit も MultiEdit も)。
       新規 Write も拒否(アーカイブは lifecycle の移動でのみ書ける、直接著作は不可)。
    2. file_path が既存の type:ADR ファイル → deny。ただし carve-out(status を
       {proposed→accepted, accepted→superseded, accepted→deprecated} の範囲で動かす、
       および superseded_by / updated の付与)だけなら allow。
    """
    if _is_under_archive(file_path):
        return ("アーカイブ済み文書は不変です。%s は編集できません。" % file_path)

    # 既存 ADR か。ディスク上のファイルを読む(無ければ ADR 改変ではない)。
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        cur_fm, cur_body, _errs = _frontmatter.parse_file(file_path)
    except (OSError, UnicodeError):
        # 既存ファイルが読めない。fail-closed(Guard1 は安全側)。
        return ("ガード異常: 既存ファイル %s を読めません。手で確認してください。" % file_path)

    if _coerce_type(cur_fm) != "ADR":
        return None

    # ここから先は既存 ADR の改変。carve-out だけかを判定する。
    doc_id = cur_fm.get("id") or file_path
    if _adr_change_is_carveout_only(cur_fm, cur_body, tool, tin):
        return None
    return ("既存ADR %s は改変できません(status遷移とsuperseded_by付与のみ可)。" % doc_id)


def _adr_change_is_carveout_only(cur_fm, cur_body, tool, tin):
    """既存 ADR への変更が carve-out(status 遷移 + superseded_by/updated)だけか。"""
    if tool == "Write":
        new_text = tin.get("content", "")
        new_fm, new_body, _e = _frontmatter.parse(new_text)
        return _adr_delta_ok(cur_fm, cur_body, new_fm, new_body)
    # Edit / MultiEdit: ディスク内容に編集を当てた結果を作って比べる。
    new_text = _apply_edits(_render_doc(cur_fm, cur_body), tool, tin)
    if new_text is None:
        # 編集を確実に当てられない(old_string が一致しない等)→ 安全側で carve-out 否定。
        return False
    new_fm, new_body, _e = _frontmatter.parse(new_text)
    return _adr_delta_ok(cur_fm, cur_body, new_fm, new_body)


def _adr_delta_ok(cur_fm, cur_body, new_fm, new_body):
    """旧→新の差分が ADR carve-out の範囲に収まるか。"""
    # 本文が変わったら不可。
    if (cur_body or "").strip() != (new_body or "").strip():
        return False
    # carve-out 外のキーが変わったら不可。
    all_keys = set(cur_fm) | set(new_fm)
    for k in all_keys:
        if k in _ADR_CARVEOUT_KEYS:
            continue
        if cur_fm.get(k) != new_fm.get(k):
            return False
    # status 遷移は許される範囲か。
    old_s = _coerce_str(cur_fm.get("status"))
    new_s = _coerce_str(new_fm.get("status"))
    if old_s != new_s:
        if (old_s, new_s) not in _ADR_CARVEOUT_STATUS:
            return False
    return True


# ---------------------------------------------------------------------------
# Guard 2 — ICD 依存境界(R7)  [§3.6, §4.2 pseudo-spec verbatim]
# ---------------------------------------------------------------------------

def guard_icd_dependency(file_path, tool, tin, graph):
    """Guard2。拒否理由(str)を返す。問題なければ None。

    §4.2 の擬似仕様をそのまま実装する:
        proposed    = parse_frontmatter(tool_input.content)   # Write のみ
        self_domain = proposed["domain"]
        for dep in as_list(proposed.get("depends_on")):
            dep_domain = domain_of(dep)
            if dep_domain != self_domain and type_of(dep) != "ICD":
                deny(f"{dep} は {dep_domain} の内部です。{dep_domain} の ICD 宛にしてください。")

    - dep の status は無関係(C12)。構造(domain と type==ICD)だけを見る。
    - dangling(構文上正しいが索引に無い)→ allow(C13)。
    - 分類不能(type_of/resolve が UNKNOWN)→ deny fail-closed(C13)。
    Write のみ事前判定する。Edit/MultiEdit は事前に全文を作れないので、ここでは
    判定しない(PostToolUse の block に回す)。
    """
    if tool != "Write":
        return None
    content = tin.get("content", "")
    return _icd_check_content(content, graph)


def _icd_check_content(content, graph):
    """全文(content)を解析して ICD 依存違反を探す。違反理由 or None。

    fail-open は呼び出し側で「docs/外の非文書」に限定する。ここはフロントマターが
    あればそれを点検し、無ければ違反なし(None)を返す。
    """
    proposed = _frontmatter.parse_frontmatter(content)
    self_domain = _coerce_str(proposed.get("domain"))
    deps = _frontmatter.as_list(proposed.get("depends_on"))
    for dep in deps:
        reason = _icd_judge_dep(dep, self_domain, graph)
        if reason is not None:
            return reason
    return None


def _icd_judge_dep(dep, self_domain, graph):
    """一つの依存 dep を判定する。違反なら理由(str)、許容なら None。

    C13 の分岐:
      - dep が索引にある → その domain を読む。別ドメインかつ ICD でなければ deny。
      - dep が索引に無い → 登録簿が接頭辞から型を判定できるか:
          判定できる(既知の TYPE)→ dangling とみなして ALLOW(死リンクは監査)。
          判定できない(UNKNOWN)→ fail-closed DENY(R7 境界明瞭、ガードは「拒否する」)。
    """
    info = graph.resolve(dep)
    if info is not None:
        dep_domain = info.get("domain") or _depgraph.UNKNOWN
        dep_type = info.get("type") or graph.type_of(dep)
        if dep_domain != self_domain and dep_type != "ICD":
            return _icd_message(dep, dep_domain)
        return None
    # 索引に無い。登録簿の接頭辞で型を引けるか。
    reg_type = _registry.type_of(dep)
    if reg_type is None:
        # 分類不能 → fail-closed deny(C13)。
        return ("%s のドメインを解決できません。宣言するか、既知の ICD 宛にしてください。" % dep)
    # 構文上正しい既知型だが索引に無い(dangling)→ allow(死リンクは監査)。
    return None


def _icd_message(dep, dep_domain):
    """R7 の拒否文(仕様 §4.2 / spec line 310 verbatim)。一字一句この形であること。"""
    return "%s は %s の内部です。%s の ICD 宛にしてください。" % (dep, dep_domain, dep_domain)


# ---------------------------------------------------------------------------
# Guard 3 — 削除安全(降格不変条件)  [R4, §3.8]
# ---------------------------------------------------------------------------

# 降格とみなす遷移: 現行(current/accepted)→ deprecated/superseded/archived。
_DEMOTED_STATUSES = frozenset({"deprecated", "superseded", "archived"})


def guard_delete_safety_edit(file_path, tool, tin, graph):
    """Guard3(Edit/Write の本文・status 経路)。拒否理由 or None。

    現行の逆依存が残っているとき、次のいずれかを拒否する:
      1. 降格: status を 現行 → deprecated/superseded/archived に動かす Write/Edit。
      2. 本文消し: 本文を空にする Write/Edit。
    逆依存は dep-graph の reverse_current_dependents(id) で引く。
    Edit/MultiEdit で本文消し/降格が事前に確定できないときは PostToolUse の block に回す。
    """
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        cur_fm, cur_body, _e = _frontmatter.parse_file(file_path)
    except (OSError, UnicodeError):
        return ("ガード異常: 既存ファイル %s を読めません。手で確認してください。" % file_path)

    doc_id = _coerce_str(cur_fm.get("id"))
    if not doc_id:
        return None  # id の無い文書は逆依存の対象にならない。

    # 現行でない文書を降格しても不変条件には触れない(降格は現行からの遷移)。
    cur_status = _coerce_str(cur_fm.get("status")) or _registry.default_status(
        _coerce_type(cur_fm)) or ""

    # 新しい内容(全文)を作る。
    new_text = _proposed_text(cur_fm, cur_body, tool, tin)
    if new_text is None:
        return None  # 事前に確定できない → PostToolUse に回す。
    new_fm, new_body, _e2 = _frontmatter.parse(new_text)
    new_status = _coerce_str(new_fm.get("status"))

    demoting = _registry.is_current(cur_status) and new_status in _DEMOTED_STATUSES
    emptying = (cur_body or "").strip() != "" and (new_body or "").strip() == ""

    if not demoting and not emptying:
        return None

    dependents = sorted(graph.reverse_current_dependents(doc_id))
    if not dependents:
        return None  # 逆参照ゼロ → 降格してよい。

    joined = ", ".join(dependents)
    if demoting:
        return ("%s には現行の依存が残っています(%s)。後継へ張り替えてから降格してください。"
                % (doc_id, joined))
    return ("%s には現行の依存が残っています(%s)。本文を空にする前に後継へ張り替えてください。"
            % (doc_id, joined))


def _proposed_text(cur_fm, cur_body, tool, tin):
    """編集適用後の全文を作る。作れない(old_string 不一致等)なら None。"""
    if tool == "Write":
        return tin.get("content", "")
    return _apply_edits(_render_doc(cur_fm, cur_body), tool, tin)


# ---------------------------------------------------------------------------
# Guard 3 — Bash 経路(deny-only, §3.5)
# ---------------------------------------------------------------------------

# コマンドを区切るトークン(D0.6)。
_CMD_SEPARATORS = (";", "&&", "||", "|", "\n")
# 文書を取り除く動詞。
_REMOVE_VERBS = ("rm", "git rm", "mv")


def guard_delete_safety_bash(command, cwd, graph_cache):
    """Bash 経路の削除安全。拒否理由 or None。deny-only(additionalContext も block も無い)。

    command を ; && || | 改行 で分割し、各 rm/git rm/mv の対象を取り出す。一つでも
    削除安全に違反(現行の逆依存が残る現行文書)なら、コマンド全体を拒否する。
    展開できない glob は fail-closed で拒否する。
    """
    segments = _split_command(command)
    for seg in segments:
        targets, verb, had_glob_unexpandable = _extract_remove_targets(seg, cwd)
        if had_glob_unexpandable:
            return ("削除対象の glob を展開できません: %s。安全のため拒否します。"
                    % seg.strip())
        for tgt in targets:
            reason = _bash_target_violation(tgt, graph_cache)
            if reason is not None:
                return reason
    return None


def _bash_target_violation(target_path, graph_cache):
    """rm/git rm/mv の一つの対象が削除安全に違反するか。違反理由 or None。"""
    abspath = os.path.abspath(target_path)
    docs_root = _find_docs_root(abspath)
    if docs_root is None:
        return None  # docs/ の外 → ガードの関心外。
    graph = graph_cache.get(docs_root)
    if graph is None:
        try:
            graph = _build_graph(docs_root)
        except Exception:
            # fail-closed: 削除安全ガードはガード異常時に拒否する。
            return ("ガード異常: 依存グラフを組めません(%s)。手で確認してください。"
                    % docs_root)
        graph_cache[docs_root] = graph

    # 対象ファイルの id を引く。ディスクのフロントマターを読む。
    doc_id = _id_of_path(abspath, docs_root, graph)
    if doc_id is None:
        return None  # 文書として索引できない → 対象外。
    info = graph.resolve(doc_id)
    if info is None:
        return None
    if not _registry.is_current(info.get("status") or ""):
        return None  # 現行でない文書の削除は不変条件に触れない。
    dependents = sorted(graph.reverse_current_dependents(doc_id))
    if not dependents:
        return None
    joined = ", ".join(dependents)
    return ("%s には現行の依存が残っています(%s)。後継へ張り替えてから削除してください。"
            % (doc_id, joined))


def _id_of_path(abspath, docs_root, graph):
    """ファイルパスから文書 id を引く。グラフの索引(path→id)を優先、無ければ直接読む。"""
    relpath = os.path.relpath(abspath, docs_root)
    for doc_id, node in graph.nodes.items():
        if node.get("path") == relpath:
            return doc_id
    if os.path.isfile(abspath):
        try:
            fm, _b, _e = _frontmatter.parse_file(abspath)
        except (OSError, UnicodeError):
            return None
        doc_id = fm.get("id")
        if isinstance(doc_id, str) and doc_id.strip():
            return doc_id.strip()
    return None


# ---------------------------------------------------------------------------
# Bash コマンドの字句解析
# ---------------------------------------------------------------------------

def _split_command(command):
    """command を ; && || | 改行 で素朴に分割する。引用符は最小限に尊重する。"""
    if not command:
        return []
    segments = []
    buf = []
    i = 0
    n = len(command)
    in_single = False
    in_double = False
    while i < n:
        c = command[i]
        if in_single:
            if c == "'":
                in_single = False
            buf.append(c)
            i += 1
            continue
        if in_double:
            if c == '"':
                in_double = False
            buf.append(c)
            i += 1
            continue
        if c == "'":
            in_single = True
            buf.append(c)
            i += 1
            continue
        if c == '"':
            in_double = True
            buf.append(c)
            i += 1
            continue
        # 二文字区切り。
        two = command[i:i + 2]
        if two in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if c in (";", "|", "\n"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    segments.append("".join(buf))
    return [s for s in segments if s.strip() != ""]


def _extract_remove_targets(segment, cwd):
    """一区切りから rm/git rm/mv の対象パスを取り出す。

    (targets:list[str], verb:str|None, had_glob_unexpandable:bool) を返す。
    glob を含み展開できない場合は had_glob_unexpandable=True。
    """
    tokens = _tokenize(segment)
    if not tokens:
        return [], None, False

    verb = None
    arg_start = 0
    if tokens[0] == "rm":
        verb = "rm"
        arg_start = 1
    elif tokens[0] == "git" and len(tokens) >= 2 and tokens[1] == "rm":
        verb = "git rm"
        arg_start = 2
    elif tokens[0] == "mv":
        verb = "mv"
        arg_start = 1
    else:
        return [], None, False

    arg_tokens = _strip_redirections(tokens[arg_start:])
    raw_args = [t for t in arg_tokens if not t.startswith("-")]
    # mv は最後の引数が宛先。対象は src 群(末尾を除く)。
    if verb == "mv" and len(raw_args) >= 2:
        raw_args = raw_args[:-1]

    targets = []
    had_unexpandable = False
    base = os.path.abspath(cwd) if cwd else os.getcwd()
    for arg in raw_args:
        if _has_glob(arg):
            expanded = _expand_glob(arg, base)
            if expanded is None:
                had_unexpandable = True
            else:
                targets.extend(expanded)
        else:
            targets.append(_resolve_arg(arg, base))
    return targets, verb, had_unexpandable


def _tokenize(segment):
    """空白区切りの素朴なトークン化(引用符を剥がす)。"""
    tokens = []
    buf = []
    i = 0
    n = len(segment)
    in_single = False
    in_double = False
    started = False
    while i < n:
        c = segment[i]
        if in_single:
            if c == "'":
                in_single = False
            else:
                buf.append(c)
            i += 1
            continue
        if in_double:
            if c == '"':
                in_double = False
            else:
                buf.append(c)
            i += 1
            continue
        if c == "'":
            in_single = True
            started = True
            i += 1
            continue
        if c == '"':
            in_double = True
            started = True
            i += 1
            continue
        if c in (" ", "\t"):
            if started or buf:
                tokens.append("".join(buf))
                buf = []
                started = False
            i += 1
            continue
        buf.append(c)
        started = True
        i += 1
    if started or buf:
        tokens.append("".join(buf))
    return tokens


def _strip_redirections(tokens):
    """引数列からシェルのリダイレクトを取り除く(#10)。

    リダイレクト演算子(> >> < 2> &> 1> 2>> >& 等)とその被演算子は削除対象では
    ないので落とす。演算子が被演算子と結合している形(`2>/dev/null`, `>out.txt`)も、
    分離している形(`> out.txt`)も扱う。分離形では続くトークン(宛先)も落とす。
    """
    result = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        op, rest = _split_redirection(tok)
        if op is None:
            result.append(tok)
            continue
        # リダイレクト演算子。被演算子が結合していなければ次トークンが宛先。
        if rest == "":
            skip_next = True
        # いずれにせよ演算子トークン(と結合した宛先)は削除対象にしない。
    return result


# リダイレクト演算子(長いものから順に当てる)。任意の先行 fd 数字を許す。
_REDIR_OPERATORS = (">>", "&>", ">&", "2>", "1>", ">", "<<", "<")


def _split_redirection(token):
    """token がリダイレクトで始まるなら (演算子, 残り) を返す。違えば (None, token)。

    先頭の任意桁の fd 番号(例 `2` in `2>`, `10` in `10>`)を演算子の一部として吸収する。
    """
    i = 0
    n = len(token)
    while i < n and token[i].isdigit():
        i += 1
    body = token[i:]
    for op in _REDIR_OPERATORS:
        if body.startswith(op):
            # fd 数字だけ(`2` 等)でリダイレクトでないものは演算子扱いしない。
            return op, body[len(op):]
    # 先頭が数字だが演算子が続かない(ふつうの数字始まりのパス)→ リダイレクトでない。
    return None, token


def _has_glob(arg):
    return any(ch in arg for ch in ("*", "?", "["))


def _expand_glob(arg, base):
    """glob を作業木に対して展開する。展開できなければ None(fail-closed の合図)。"""
    import glob as _glob
    pattern = arg if os.path.isabs(arg) else os.path.join(base, arg)
    try:
        matches = _glob.glob(pattern)
    except Exception:
        return None
    if not matches:
        # 一致ゼロ。作業木に対象が無い → 安全側で「不在」を返す(削除しても害なし)。
        # ただし作業木が読めない等で展開不能なら None を返すべきだが、glob は例外を
        # 出さず空を返すため、ここは「該当なし=空」を返す。
        return []
    return matches


def _resolve_arg(arg, base):
    if os.path.isabs(arg):
        return arg
    return os.path.join(base, arg)


# ---------------------------------------------------------------------------
# 編集の適用 / 文書の再描画
# ---------------------------------------------------------------------------

def _render_doc(fm, body):
    """parse_file で読んだ fm/body から元の全文を近似再構成する。

    注意: これは編集を当てるためのベスト・エフォートの再構成であり、元の整形を
    完全には保たない。Guard1(ADR carve-out)と Guard3(本文消し)の判定にだけ使う。
    実運用では Write 経路で全文が来るのが正で、Edit 経路は PostToolUse の再読が要。
    """
    lines = ["---"]
    for k, v in fm.items():
        lines.append("%s: %s" % (k, _render_value(v)))
    lines.append("---")
    head = "\n".join(lines) + "\n"
    return head + (body or "")


def _render_value(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return str(v)


def _apply_edits(text, tool, tin):
    """text に Edit/MultiEdit の差し替えを当てる。当てられなければ None。

    old_string が見つからない場合は None(確実に判定できないので呼び出し側が
    PostToolUse / 安全側へ回す)。
    """
    if tool == "Edit":
        old = tin.get("old_string", "")
        new = tin.get("new_string", "")
        replace_all = bool(tin.get("replace_all", False))
        return _apply_one(text, old, new, replace_all)
    if tool == "MultiEdit":
        cur = text
        for ed in tin.get("edits", []) or []:
            old = ed.get("old_string", "")
            new = ed.get("new_string", "")
            replace_all = bool(ed.get("replace_all", False))
            cur = _apply_one(cur, old, new, replace_all)
            if cur is None:
                return None
        return cur
    return None


def _apply_one(text, old, new, replace_all):
    if old == "":
        # 空 old は新規挿入(Write 相当)で、ここでは扱わない。
        return None
    if old not in text:
        return None
    if replace_all:
        return text.replace(old, new)
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 小道具
# ---------------------------------------------------------------------------

def _coerce_str(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_type(fm):
    """フロントマターの type を引く。無ければ id 接頭辞から。どちらも無ければ ''。"""
    t = _coerce_str(fm.get("type"))
    if t:
        return t
    doc_id = fm.get("id")
    if isinstance(doc_id, str):
        reg = _registry.type_of(doc_id)
        if reg:
            return reg
    return ""


# ---------------------------------------------------------------------------
# 経路ごとの処理(PreToolUse / PostToolUse)
# ---------------------------------------------------------------------------

def _handle_pre_edit_write(tool, tin, cwd):
    """PreToolUse の Edit|Write|MultiEdit。first-deny-wins で三ガードを順に当てる。"""
    file_path = tin.get("file_path") or tin.get("path") or ""

    # Guard1 不変(fail-closed)。
    try:
        reason = guard_immutability(file_path, tool, tin)
    except Exception as exc:
        return _pre_deny("ガード異常(不変ガード): %r。手で確認してください。" % (exc,))
    if reason is not None:
        return _pre_deny(reason)

    # グラフは Guard2/Guard3 で要る。docs/ を解決して組む。
    docs_root = _find_docs_root(file_path, cwd)
    graph = None
    graph_error = None
    try:
        graph = _build_graph(docs_root)
    except Exception as exc:
        graph_error = exc

    # Guard2 ICD 依存(R7)。fail-open は docs/外の非文書 Write に限る。
    try:
        if graph is None:
            raise RuntimeError(graph_error)
        reason = guard_icd_dependency(file_path, tool, tin, graph)
    except Exception as exc:
        if _guard2_should_fail_open(file_path, tool, tin):
            reason = None  # docs/外の純粋な非文書 → fail-open allow。
        else:
            return _pre_deny("ガード異常(ICD依存ガード): %r。手で確認してください。" % (exc,))
    if reason is not None:
        return _pre_deny(reason)

    # Guard3 削除安全(fail-closed)。
    try:
        if graph is None:
            raise RuntimeError(graph_error)
        reason = guard_delete_safety_edit(file_path, tool, tin, graph)
    except Exception as exc:
        return _pre_deny("ガード異常(削除安全ガード): %r。手で確認してください。" % (exc,))
    if reason is not None:
        return _pre_deny(reason)

    return _pre_allow()


def _guard2_should_fail_open(file_path, tool, tin):
    """Guard2 を fail-open(allow)にしてよいか。

    MASTER §3.6: docs/** の外の、フロントマターを持たない純粋な非文書 Write のときだけ。
    それ以外(docs/内、あるいはフロントマターを持つ)は fail-closed。
    """
    if tool != "Write":
        return False
    if _is_under_docs(file_path):
        return False
    content = tin.get("content", "")
    # フロントマターの開始フェンスが無ければ非文書とみなす。
    head = content.lstrip()
    return not head.startswith("---")


def _handle_pre_bash(tin, cwd):
    """PreToolUse の Bash。deny-only(§3.5)。"""
    command = tin.get("command", "")
    graph_cache = {}
    try:
        reason = guard_delete_safety_bash(command, cwd, graph_cache)
    except Exception as exc:
        # 削除安全は fail-closed。
        return _pre_deny("ガード異常(Bash 削除安全): %r。手で確認してください。" % (exc,))
    if reason is not None:
        return _pre_deny(reason)
    return _pre_allow()


def _handle_post_edit(tool, tin, cwd):
    """PostToolUse の Edit|MultiEdit(C4)。書かれたファイルを読み直して再判定する。

    Guard2(ICD依存)または Guard3(削除安全)が今や違反していれば decision:block。
    Write はここでは扱わない(PreToolUse で全文を事前判定済み)。
    """
    if tool not in ("Edit", "MultiEdit"):
        return _post_quiet()
    file_path = tin.get("file_path") or tin.get("path") or ""
    if not file_path or not os.path.isfile(file_path):
        return _post_quiet()

    try:
        with open(file_path, encoding="utf-8-sig", newline="") as _fh:
            raw_post = _fh.read()
    except (OSError, UnicodeError):
        return _post_quiet()  # 読めない → 助言できない(リンタ/監査に委ねる)。
    fm, body, _e = _frontmatter.parse(raw_post)

    docs_root = _find_docs_root(file_path, cwd)
    try:
        graph = _build_graph(docs_root)
    except Exception:
        return _post_quiet()  # post の再判定が組めない → 静かに通す(監査が拾う)。

    # Guard2 を全文に対して再判定する(Write と同じ検査)。
    full_text = _render_doc(fm, body)
    reason = _icd_check_content(full_text, graph)
    if reason is not None:
        return _post_block(reason)

    # Guard3 を再判定する: status/本文が降格/空への「遷移」かつ逆依存が残るか。
    # POST 状態だけで判じると、もとから deprecated / 本文空の文書を無関係な編集で
    # 誤って block してしまう(#00/#01)。PRE 状態を編集の逆当てで復元し、
    # PreToolUse の guard_delete_safety_edit と同じ true な前後遷移だけを咎める。
    reason = _post_delete_safety(fm, body, graph, tool, tin, raw_post)
    if reason is not None:
        return _post_block(reason)

    return _post_quiet()


def _post_delete_safety(fm, body, graph, tool=None, tin=None, raw_post_text=None):
    """PostToolUse の削除安全再判定。PRE→POST の遷移で判じる(#00/#01)。

    POST 状態は引数 fm/body(読み直したファイル)。PRE 状態は POST の全文に
    Edit/MultiEdit を逆当てして復元する。逆当てできない(編集が確定できない)ときは
    安全側に倒し、降格/本文消しの遷移と「みなして」判定する(従来の POST 限定挙動)。
    遷移でなければ block しない。"""
    doc_id = _coerce_str(fm.get("id"))
    if not doc_id:
        return None

    post_status = _coerce_str(fm.get("status"))
    post_empty = (body or "").strip() == ""

    # PRE 状態の復元: POST 全文から編集を逆当てする。
    prev_status, prev_empty = _reconstruct_pre_edit_state(
        fm, body, tool, tin, raw_post_text)

    # 降格 = 現行(current/accepted)→ deprecated/superseded/archived の遷移。
    demoting = (_registry.is_current(prev_status)
                and post_status in _DEMOTED_STATUSES)
    # 本文消し = 非空 → 空 の遷移。
    emptying = (not prev_empty) and post_empty

    if not demoting and not emptying:
        return None
    dependents = sorted(graph.reverse_current_dependents(doc_id))
    if not dependents:
        return None
    joined = ", ".join(dependents)
    if demoting:
        return ("%s には現行の依存が残っています(%s)。後継へ張り替えてから降格してください。"
                % (doc_id, joined))
    return ("%s には現行の依存が残っています(%s)。本文を空にする前に後継へ張り替えてください。"
            % (doc_id, joined))


def _reconstruct_pre_edit_state(post_fm, post_body, tool, tin, raw_post_text=None):
    """POST の fm/body から PRE 編集の (status, body_empty) を復元する。

    逆当ては POST のディスク全文(raw_post_text)に対して行う。生の全文が無いときだけ
    fm/body から再描画した近似に当てる(再描画はフロントマターのバイト列が原文と
    一致しないことがあり、フロントマター内の編集で逆当てに失敗しうるため、生文優先)。
    Edit/MultiEdit を逆当て(new_string→old_string)して PRE 全文を作り、その status と
    本文空否を返す。逆当てできない/編集情報が無いときは「遷移が起きた」とみなす
    安全側の既定値(現行 status / 非空本文)を返す。
    """
    safe_default = ("current", False)  # 現行かつ非空 → あらゆる降格/空化を遷移と扱う。
    if tool not in ("Edit", "MultiEdit") or not isinstance(tin, dict):
        return safe_default
    post_text = raw_post_text if raw_post_text is not None else _render_doc(
        post_fm, post_body)
    pre_text = _invert_edits(post_text, tool, tin)
    if pre_text is None:
        return safe_default
    pre_fm, pre_body, _e = _frontmatter.parse(pre_text)
    pre_status = _coerce_str(pre_fm.get("status")) or _registry.default_status(
        _coerce_type(pre_fm)) or ""
    return pre_status, (pre_body or "").strip() == ""


def _invert_edits(text, tool, tin):
    """text(POST 全文)に Edit/MultiEdit を逆当てして PRE 全文を復元する。

    各編集の new_string→old_string を逆順に当てる。確実に逆当てできない
    (new_string が本文に無い等)なら None。
    """
    if tool == "Edit":
        old = tin.get("old_string", "")
        new = tin.get("new_string", "")
        replace_all = bool(tin.get("replace_all", False))
        return _apply_one(text, new, old, replace_all)
    if tool == "MultiEdit":
        cur = text
        for ed in reversed(tin.get("edits", []) or []):
            old = ed.get("old_string", "")
            new = ed.get("new_string", "")
            replace_all = bool(ed.get("replace_all", False))
            cur = _apply_one(cur, new, old, replace_all)
            if cur is None:
                return None
        return cur
    return None


# ---------------------------------------------------------------------------
# main — 自己ルーティング(hook_event_name × tool_name)
# ---------------------------------------------------------------------------

def main(argv=None):
    """Hook 入口。stdin の JSON を読み、事象とツールで自己ルーティングする。

    終了コードは常に 0(判定は JSON に載る、MASTER §3.6)。main から例外を投げない。
    """
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        obj = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        obj = {}

    try:
        response = _route(obj)
    except Exception as exc:
        # 最後の砦。経路判定で落ちたら、Edit/Write/MultiEdit/Bash は fail-closed deny、
        # それ以外(PostToolUse/未知)は静かに通す。
        event = obj.get("hook_event_name") if isinstance(obj, dict) else None
        if event == "PreToolUse":
            response = _pre_deny("ガード異常: %r。手で確認してください。" % (exc,))
        else:
            response = _post_quiet()

    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    return 0


def _route(obj):
    """事象とツールで処理を振り分ける。"""
    if not isinstance(obj, dict):
        return _post_quiet()
    event = obj.get("hook_event_name")
    tool = obj.get("tool_name")
    tin = obj.get("tool_input") or {}
    if not isinstance(tin, dict):
        tin = {}
    cwd = obj.get("cwd")

    if event == "PreToolUse":
        if tool == "Bash":
            return _handle_pre_bash(tin, cwd)
        if tool in ("Edit", "Write", "MultiEdit"):
            return _handle_pre_edit_write(tool, tin, cwd)
        return _pre_allow()

    if event == "PostToolUse":
        if tool in ("Edit", "MultiEdit"):
            return _handle_post_edit(tool, tin, cwd)
        return _post_quiet()

    # 未知の事象(SessionStart/End 等)はこのスクリプトの関心外。
    return _post_quiet()


if __name__ == "__main__":
    sys.exit(main())
