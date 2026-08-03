#!/usr/bin/env python3
"""三つのガード(不変・ICD依存・削除安全)。PreToolUse と PostToolUse の両方に登録する。

保証限界:
- 予防: 書き込み/編集/削除を適用する前に三つの不変条件を点検し、違反を deny で止める。
  Guard1 不変(アーカイブ・既存ADRの改変拒否)、Guard2 ICD依存境界(R7)、Guard3 削除安全
  (現行の逆依存が残る降格/本文消し/rm・git rm・mv を拒否)。最初に拒否したガードで止める。
- 検出: PostToolUse で書かれたファイルを読み直し、Guard2/Guard3 違反なら
  decision:block を出す(C4)。ADR-076 以降これは主たる門ではなく突き合わせであり、
  外部の競合や tool 実装差を拾う。Guard2 の主たる拒否は PreToolUse に立つ
  (Edit/MultiEdit も変更後の全文を組み立てて事前に判ずる)。
- 委ねる: 死リンク・逆孤児・古び等の全件監査は docs-audit に委ねる。助言だけのリンタは
  decision を出さない(C4)。ドメイン解決は _depgraph.resolve に委ねる(IDだけでは
  ドメインは決まらない、§3.4)。

頑健性(MASTER §3.6):
- 不変ガード(Guard1)と削除安全ガード(Guard3)が落ちたら fail-closed(deny「ガード異常、
  手で確認」)。Guard2(ICD依存)は docs/** の外の、フロントマターを持たない純粋な非文書
  Write のときだけ fail-open(allow)。それ以外の Guard2 例外も fail-closed。
  編集後の全文を組み立てられないときも、対象が統治文書なら deny する(ADR-076)。
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

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _hookio
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
    """start_path から上にたどって統治木を探す。見つからなければ None。

    解決は登録簿の walkup_docs_root に一本化(ADR-022): doctrine_docs 優先、
    docs は _system を持つ場合だけ統治木と認める。素の docs/ は他所の土地で
    あり、グラフ構築(ドメイン解決・逆依存)にも不変ガードにも使わない。
    """
    return _registry.walkup_docs_root(start_path, cwd)


def _build_graph(docs_root):
    """docs_root からグラフを組む。root が無ければ空グラフを返す。"""
    if not docs_root or not os.path.isdir(docs_root):
        return _depgraph.build_graph(docs_root or "")
    return _depgraph.build_graph(docs_root)


# ---------------------------------------------------------------------------
# パスの判定
# ---------------------------------------------------------------------------

def _is_under_archive(file_path):
    """file_path が統治木の中の <domain>/archive/ の下なら True(§3.8)。

    ADR-022: 不変ガードは統治木(doctrine_docs、または _system を持つ docs)の
    中の archive/ にだけ効く。木の外の archive という名前のディレクトリは
    他所の土地であり、拒否しない。
    """
    if not file_path:
        return False
    root = _registry.walkup_docs_root(file_path)
    if root is None:
        return False
    norm, rootn = _contained_pair(file_path, root)
    if not norm.startswith(rootn + "/"):
        return False
    return "archive" in norm[len(rootn) + 1:].split("/")


def _contained_pair(file_path, root):
    """包含判定に使う (対象, 木) の正規化パス。両方ともリンクを解決する(ADR-075)。

    abspath だけではリンクを追わないため、archive/ を指すディレクトリリンクを
    経由すると「木の外」と読まれて不変ガードが外れた。同じファイルの
    _pre_target_is_guard_inert と _handle_post_edit は realpath を使っており、
    包含の基準がガードの中で食い違っていた。厳しい側(realpath)へ揃える。
    """
    return (os.path.realpath(file_path).replace("\\", "/"),
            os.path.realpath(root).replace("\\", "/"))


def _is_under_docs(file_path):
    """file_path が統治木の中なら True(Guard2 の fail-open 判定に使う)。

    ADR-022: 木の発見は walkup_docs_root に一本化し、さらに「その木の中に
    在る」ことを包含で確かめる(木がプロジェクトに在るだけでは足りない)。
    素の docs/ は統治木でない。
    """
    if not file_path:
        return False
    root = _registry.walkup_docs_root(file_path)
    if root is None:
        return False
    norm, rootn = _contained_pair(file_path, root)
    return norm.startswith(rootn + "/")


def _project_has_tree(file_path, cwd=None):
    """このファイルのプロジェクトに統治木が在るか(ADR-036 の境界)。

    統治木が一つも解決できないプロジェクト(素の Obsidian/Jekyll 等、
    doctrine を導入していない土地)では、ドメイン/ICD の規範も削除安全の
    不変条件も意味を持たない。二・三ガードはその外では発火しない
    (リンタの体系外無発火 ADR-024 と同じ境界を、ガードにも一貫適用する)。
    木が在れば、木の外の stray 文書に対しても従来どおり点検する。
    決して例外を投げない(解決不能は「木なし」に倒す=安全側で沈黙)。
    """
    try:
        return _registry.walkup_docs_root(file_path, cwd) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Guard 1 — 不変(アーカイブ + 既存ADR)  [R8, §3.8]
# ---------------------------------------------------------------------------

# ADR の唯一許される lifecycle 変化(D0.8 / §3.6.2 carve-out)。
# doctrine:begin SPEC-003
_ADR_CARVEOUT_STATUS = {
    ("proposed", "accepted"),
    ("accepted", "superseded"),
    ("accepted", "deprecated"),
}
# carve-out で触ってよいキー(status 遷移に伴うもの)。
_ADR_CARVEOUT_KEYS = frozenset({"status", "superseded_by", "updated"})
# doctrine:end SPEC-003


def guard_immutability(file_path, tool, tin, cwd=None):
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

    # フロントマターを読む経路は、プロジェクトに統治木が在るときだけ判ずる
    # (ADR-103。ADR-036 の境界を三つのガードで揃える)。実測: 木がどこにも無い土地の
    # `type: ADR` なメモが編集できなかった —— ADR-036 が名指しした害そのものである。
    # 置き場所の判定(archive/ の下)は木を辿るので元から無発火であり、上で済んでいる。
    # 木が在れば、木の外の逸れた文書も従来どおり点検する。
    if not _project_has_tree(file_path, cwd):
        return None
    try:
        cur_fm, cur_body, cur_errs = _frontmatter.parse_file(file_path)
    except (OSError, UnicodeError):
        # 既存ファイルが読めない。fail-closed(Guard1 は安全側)。
        return ("ガード異常: 既存ファイル %s を読めません。手で確認してください。" % file_path)

    # 型と位置づけを読めないなら、不変を判じられない。**沈黙して開かない**
    # (確定事実12。ADR-102)。実測: `type: [ADR]` で受理済み ADR の本文が書き換えられ、
    # `status: [archived]` で倉庫の外のアーカイブが編集できた。正規化を揃えるだけでは
    # 直らない —— 空文字も「ADR ではない」なので、読めないことを読めないと扱う。
    # 境界は上で判じてある(木の無い土地では既に戻っている)。不在は対象にしない
    # (「無い」と「読めない」を分ける。不在は必須キーの検査の領分)。
    for key in ("type", "status"):
        if key not in cur_fm:
            continue
        raw = cur_fm.get(key)
        if raw is None or isinstance(raw, str):
            continue
        return ("%s を文字列として読めないため、不変を判じられません"
                "(%s: %r)。値を素のスカラで書いてください。"
                % ("型" if key == "type" else "位置づけ(status)", key, raw))

    cur_type = _coerce_type(cur_fm)
    if cur_type != "ADR":
        # ADR-027: status『archived』の文書は、置き場所に依らず不変。
        # (パス判定だけでは、倉庫の外に居る archived 文書が編集自由になる。)
        eff_status = _frontmatter.coerce_str(cur_fm.get("status")).strip() \
            or _registry.default_status(cur_type) or ""
        if eff_status == "archived":
            return ("アーカイブ済み(status: archived)の文書は不変です。%s は編集できません。"
                    % (cur_fm.get("id") or file_path))
        return None

    # ここから先は既存 ADR の改変。
    doc_id = cur_fm.get("id") or file_path

    # 不変は accepted から始まる(ADR-095)。ディスク上の実効 status が proposed の ADR は
    # まだ決定ではなく下書きなので、本文を直せる。語彙は最初から proposed を許していた
    # のに、ガードが存在した瞬間から凍らせていたため、木に proposed の ADR は一件も
    # 生まれなかった(実測)。逆向き(accepted → proposed)は carve-out の外なので、
    # 受理済みを下書きへ落として書き換える道は開かない。
    if (_frontmatter.coerce_str(cur_fm.get("status")).strip()
            or _registry.default_status("ADR") or "") == "proposed":
        return None

    if _adr_change_is_carveout_only(cur_fm, cur_body, tool, tin, file_path,
                                    cur_errs):
        return None
    return ("既存ADR %s は改変できません(status遷移とsuperseded_by付与のみ可)。" % doc_id)


def _adr_change_is_carveout_only(cur_fm, cur_body, tool, tin, file_path=None,
                                 cur_errs=None):
    """既存 ADR への変更が carve-out の範囲だけか。

    carve-out は二つ。(1) status 遷移 + superseded_by/updated の付与。
    (2) フロントマターの構文修復(ADR-075)。ADR は不変だが、構文が壊れた
    フロントマターは値を黙って落とす。不変を理由に修復まで拒むと、壊れた ADR が
    永久に直せず CI が赤のまま閉じる。修復だけを、本文不変と「誤りが消えること」で
    機械的に見分けて許す。
    """
    new_text = _proposed_text(cur_fm, cur_body, tool, tin, file_path)
    if new_text is None:
        # 編集を確実に当てられない(old_string が一致しない等)→ 安全側で carve-out 否定。
        return False
    new_fm, new_body, new_errs = _frontmatter.parse(new_text)
    if _adr_delta_ok(cur_fm, cur_body, new_fm, new_body):
        return True
    return _is_syntax_repair(cur_fm, cur_body, cur_errs,
                             new_fm, new_body, new_errs)


def _is_syntax_repair(cur_fm, cur_body, cur_errs, new_fm, new_body, new_errs):
    """壊れたフロントマターの修復だけか(ADR-075)。

    四つを全て満たすときだけ真。(1) 編集前に構文の誤りがある。(2) 編集後は無い。
    (3) 本文が変わらない。(4) 誤りに関わらなかった鍵の値が変わらない。
    誤りに関わった鍵だけが動くので、修復に見せかけて決定を書き換えることはできない。
    """
    if not cur_errs or new_errs:
        return False
    if (cur_body or "").strip() != (new_body or "").strip():
        return False
    broken = {e.get("key") for e in cur_errs if isinstance(e, dict) and e.get("key")}
    if not broken:
        return False          # 鍵を特定できない誤り(閉じ '---' 欠落等)は許さない。
    for k in set(cur_fm) | set(new_fm):
        if k in broken or k in _ADR_CARVEOUT_KEYS:
            continue
        if cur_fm.get(k) != new_fm.get(k):
            return False
    return True


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
    old_s = _frontmatter.coerce_str(cur_fm.get("status"))
    new_s = _frontmatter.coerce_str(new_fm.get("status"))
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

    Write・Edit・MultiEdit のいずれも事前判定する(ADR-076)。以前は Write だけを見て、
    Edit/MultiEdit は「事前に全文を作れない」として PostToolUse の block へ回していた。
    その前提は同じファイルの `_proposed_text` が反証しており(Guard1 と Guard3 は
    どちらも事前判定でそれを使っている)、作れないのではなく作っていなかっただけである。
    PostToolUse の block は書き込みを巻き戻さないので、回した分だけ作業木は不正な状態で
    残っていた。
    """
    if tool == "Write":
        return _icd_check_content(tin.get("content", ""), graph)
    if not file_path or not os.path.isfile(file_path):
        return None  # 新規作成は Write の経路。編集の対象が無ければ判ずるものが無い。
    try:
        cur_fm, cur_body, _e = _frontmatter.parse_file(file_path)
    except (OSError, UnicodeError):
        return ("ガード異常: 既存ファイル %s を読めません。手で確認してください。" % file_path)
    new_text = _proposed_text(cur_fm, cur_body, tool, tin, file_path)
    if new_text is None:
        # 全文を作れない。統治文書ならガードが判定を持たない状態なので拒む(ADR-076)。
        # ADR-075 が直したのは、まさに「判定を持たないまま allow へ倒れる」欠陥である。
        # 体系外の非文書は Guard2 の対象でないので、従来どおり通す。
        if _frontmatter.coerce_str(cur_fm.get("id")) or _is_under_docs(file_path):
            return ("編集後の全文を組み立てられないため、ICD 依存を検められません"
                    "(old_string 不一致の疑い)。編集を見直してください。")
        return None
    return _icd_check_content(new_text, graph)


def _icd_check_content(content, graph):
    """全文(content)を解析して ICD 依存違反を探す。違反理由 or None。

    fail-open は呼び出し側で「docs/外の非文書」に限定する。ここはフロントマターが
    あればそれを点検し、無ければ違反なし(None)を返す。
    """
    proposed = _frontmatter.parse_frontmatter(content)
    self_domain = _frontmatter.coerce_str(proposed.get("domain"))
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

    doc_id = _frontmatter.coerce_str(cur_fm.get("id"))
    if not doc_id:
        return None  # id の無い文書は逆依存の対象にならない。

    # 現行でない文書を降格しても不変条件には触れない(降格は現行からの遷移)。
    cur_status = _frontmatter.coerce_str(cur_fm.get("status")) or _registry.default_status(
        _coerce_type(cur_fm)) or ""

    # 新しい内容(全文)を作る。
    new_text = _proposed_text(cur_fm, cur_body, tool, tin, file_path)
    if new_text is None:
        return None  # 事前に確定できない → PostToolUse に回す。
    new_fm, new_body, _e2 = _frontmatter.parse(new_text)
    new_status = _frontmatter.coerce_str(new_fm.get("status"))

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


def _proposed_text(cur_fm, cur_body, tool, tin, file_path=None):
    """編集適用後の全文を作る。作れない(old_string 不一致等)なら None。

    編集はディスクの生の全文へ当てる(ADR-075)。以前は _render_doc の正規化した
    再構成へ当てていたため、生ファイルの整形(`status:  current` のような余分な
    空白・引用符・コメント行)を old_string が含むと一致せず None になり、判定を
    持たないまま allow へ倒れた。実測: 空白1つなら deny、2つなら allow。
    生が読めないときだけ再構成へ退く。
    """
    if tool == "Write":
        return tin.get("content", "")
    base = None
    if file_path:
        try:
            base = _frontmatter.read_text(file_path)
        except (OSError, UnicodeError):
            base = None
    if base is None:
        base = _render_doc(cur_fm, cur_body)
    return _apply_edits(base, tool, tin)


# ---------------------------------------------------------------------------
# Guard 3 — Bash 経路(deny-only, §3.5)
# ---------------------------------------------------------------------------


def _apply_cd(segment, base):
    """区切りが `cd DIR` なら基準を移す。(新しい base, 解決できたか) を返す。

    `cd sub && rm x` の x は sub/x を指す。全区切りで基準を固定していたため、
    実在しないパスに解決されて削除安全が丸ごと外れていた(ADR-075)。
    宛先が変数・コマンド置換・`-` のときは静的に決められないので偽を返す。
    """
    tokens = _tokenize(segment)
    if not tokens or tokens[0] not in ("cd", "pushd"):
        return base, True
    args = [t for t in _strip_redirections(tokens[1:]) if not t.startswith("-")]
    if not args:
        return base, True                 # 引数なしの cd は HOME。対象を持たない。
    dst = args[0]
    if dst == "-" or _looks_dynamic(dst):
        return base, False
    return os.path.normpath(_resolve_arg(dst, base)), True


def _looks_dynamic(token):
    """展開しないと決まらない文字を含むか($VAR・`cmd`・$(cmd)・~・glob)。"""
    return any(ch in token for ch in ("$", "`", "~", "*", "?"))


# git の大域オプションのうち、値を次のトークンに取るもの。
_GIT_OPTS_WITH_VALUE = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                        "--exec-path", "--config-env")


def _skip_git_global_opts(tokens, base):
    """`git` の大域オプションを読み飛ばす。(部分コマンドの添字, 新 base) を返す。

    -C DIR は以降の相対パスの基準を移す。`git -C dir rm PATH` を動詞なしと読むと
    削除安全が丸ごと外れる(ADR-075)。解決できない -C は base に None を返し、
    呼び手が安全側(拒否)へ倒せるようにする。
    """
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in _GIT_OPTS_WITH_VALUE:
            if i + 1 >= len(tokens):
                return None, base
            val = tokens[i + 1]
            if tok == "-C":
                if _looks_dynamic(val):
                    return None, None
                base = os.path.normpath(_resolve_arg(val, base))
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return i, base
    return None, base


def _has_delete_verb(segment):
    """この区切りが rm / git rm / mv / git mv を含むか(先頭の動詞だけを見る)。"""
    tokens = _tokenize(segment)
    if not tokens:
        return False
    if tokens[0] in ("rm", "mv"):
        return True
    if tokens[0] != "git":
        return False
    sub_i, _base = _skip_git_global_opts(tokens, "")
    return sub_i is not None and tokens[sub_i] in ("rm", "mv")


def guard_delete_safety_bash(command, cwd, graph_cache):
    """Bash 経路の削除安全。拒否理由 or None。deny-only(additionalContext も block も無い)。

    command を ; && || | 改行 で分割し、各 rm/git rm/mv の対象を取り出す。一つでも
    削除安全に違反(現行の逆依存が残る現行文書)なら、コマンド全体を拒否する。
    展開できない glob は fail-closed で拒否する。
    """
    segments = _split_command(command)
    # 削除の動詞を一つも含まないコマンドには、このガードは何も言わない。
    # `cd "$D" && ls` のような無害な経路まで「cd を解決できない」で拒むのは
    # 過剰であり、統治と無関係な作業を止める(ADR-075)。
    if not any(_has_delete_verb(seg) for seg in segments):
        return None
    base = os.path.abspath(cwd) if cwd else os.getcwd()
    for seg in segments:
        base, resolvable = _apply_cd(seg, base)
        if not resolvable:
            # cd の宛先を静的に決められない(変数・コマンド置換)。以降の相対パスの
            # 意味が決まらないので、安全側で拒否する(展開不能な glob と同じ扱い)。
            return ("削除安全: `cd` の宛先を静的に解決できないため、この経路の "
                    "削除対象を確かめられません。絶対パスで書き直してください。")
        targets, verb, had_glob_unexpandable = _extract_remove_targets(seg, base)
        if had_glob_unexpandable:
            return ("削除対象の glob を展開できません: %s。安全のため拒否します。"
                    % seg.strip())
        # ディレクトリ対象(rm -rf <domain> / git rm -r / mv <dir> 等)は、配下の
        # 統治文書(.md)を列挙して一つずつ検査する(#71)。単一ファイル指定より
        # ドメインごと消す方が高頻度の破壊経路であり、素通りさせない。
        for tgt in _expand_dir_targets(targets):
            reason = _bash_target_violation(tgt, graph_cache)
            if reason is not None:
                return reason
    return None


def _expand_dir_targets(targets):
    """対象のうちディレクトリを、配下の .md ファイルへ展開する(#71)。

    ファイルはそのまま返す。ディレクトリは、その中の全 .md を再帰列挙して返す
    (統治文書かどうかは _bash_target_violation が木の解決で判じる)。存在しない
    対象・.md 以外のファイルはそのまま通す(後段が対象外と判じる)。決定的(整列)。
    """
    out = []
    for t in targets:
        ap = os.path.abspath(t)
        if os.path.isdir(ap):
            for dirpath, dirnames, filenames in os.walk(ap):
                dirnames.sort()
                for fn in sorted(filenames):
                    if fn.endswith(".md"):
                        out.append(os.path.join(dirpath, fn))
        else:
            out.append(t)
    return out


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
    # 対象自身の status は問わない(ADR-075)。降格は「現行からの遷移」なので現行性が
    # 条件になるが、削除は状態に依らず現行の依存先を死リンクにする。DECIDED-001 事実5
    # も「削除・降格してよいのは現行の逆依存がゼロのときだけ」と status を条件にしない。
    # 同じ文書の「本文を空にする Write」は既に status を問わず拒否しており、
    # 完全に消す rm だけが通るのは判定の非対称だった。
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


def _verb_of(tokens, base):
    """先頭のトークン列から (動詞, 引数の開始位置, 基準, 解決不能か) を返す。

    `git` は大域オプションを部分コマンドの前に取る。`git -C DIR rm PATH` を
    動詞なしと読むと削除安全が丸ごと外れる(ADR-075)。-C は基準も動かす。
    """
    if tokens[0] == "rm":
        return "rm", 1, base, False
    if tokens[0] == "mv":
        return "mv", 1, base, False
    if tokens[0] != "git":
        return None, 0, base, False
    sub_i, git_base = _skip_git_global_opts(tokens, base)
    if git_base is None:
        return None, 0, base, True
    if sub_i is None or sub_i >= len(tokens):
        return None, 0, git_base, False
    if tokens[sub_i] == "rm":
        return "git rm", sub_i + 1, git_base, False
    if tokens[sub_i] == "mv":
        # git mv も mv と同じ移動/上書きの意味論で扱う(SPEC-003)。
        return "mv", sub_i + 1, git_base, False
    return None, 0, git_base, False


def _extract_remove_targets(segment, cwd):
    """一区切りから rm/git rm/mv の対象パスを取り出す。

    (targets:list[str], verb:str|None, had_glob_unexpandable:bool) を返す。
    glob を含み展開できない場合は had_glob_unexpandable=True。
    """
    tokens = _tokenize(segment)
    if not tokens:
        return [], None, False

    # cwd は呼び手が cd を織り込んだ基準ディレクトリである(ADR-075)。
    base = os.path.abspath(cwd) if cwd else os.getcwd()
    verb, arg_start, base, unresolvable = _verb_of(tokens, base)
    if unresolvable:
        return [], None, True            # -C の宛先を解決できない → 安全側。
    if verb is None:
        return [], None, False

    arg_tokens = _strip_redirections(tokens[arg_start:])

    # mv の -t/--target-directory は引数順を逆にする(-t DIR SRC…)。DIR が宛先で
    # 位置引数はすべて src。これを取り違えると宛先の上書き検査が誤対象になる(#71)。
    forced_dst = None  # -t/--target-directory で明示された宛先
    raw_args = []
    j = 0
    while j < len(arg_tokens):
        tok = arg_tokens[j]
        if tok in ("-t", "--target-directory"):
            if j + 1 < len(arg_tokens):
                forced_dst = arg_tokens[j + 1]
                j += 2
                continue
            j += 1
            continue
        if tok.startswith("--target-directory="):
            forced_dst = tok.split("=", 1)[1]
            j += 1
            continue
        if tok.startswith("-"):
            j += 1
            continue  # その他の旗(-T/-f 等)は飛ばす。
        raw_args.append(tok)
        j += 1

    # mv は最後の引数が宛先。対象は src 群(末尾を除く)。ただし上書きは宛先
    # 内容の破壊なので、rm と同等に宛先側も対象へ含める:
    # - 宛先が既存ファイル → その宛先。
    # - 宛先が glob → 展開して同様(展開不能は安全側の拒否へ倒す)。
    # - 宛先が既存ディレクトリ → 中の同名(= src の basename)既存ファイル。
    # 新しい名前への改名だけが破壊でないので含めない。
    extra_targets = []
    had_unexpandable = False
    # 宛先(dst)と src 群を決める。-t DIR SRC… なら DIR が宛先で位置引数は全て src。
    # そうでなければ末尾が宛先。宛先の上書きは破壊なので extra_targets に含める。
    dst = None
    srcs = []
    if verb == "mv" and forced_dst is not None and raw_args:
        dst = forced_dst
        srcs = raw_args
        raw_args = srcs
    elif verb == "mv" and len(raw_args) >= 2:
        dst = raw_args[-1]
        srcs = raw_args[:-1]
        raw_args = srcs
    if verb == "mv" and dst is not None:
        if _has_glob(dst):
            dst_paths = _expand_glob(dst, base)
            if dst_paths is None:
                had_unexpandable = True
                dst_paths = []
        else:
            dst_paths = [_resolve_arg(dst, base)]
        for d in dst_paths:
            if os.path.isfile(d):
                extra_targets.append(d)
            elif os.path.isdir(d):
                for src in srcs:
                    if _has_glob(src):
                        src_paths = _expand_glob(src, base) or []
                    else:
                        src_paths = [_resolve_arg(src, base)]
                    for s in src_paths:
                        cand = os.path.join(d, os.path.basename(s))
                        if os.path.isfile(cand):
                            extra_targets.append(cand)

    targets = []
    for arg in raw_args:
        if _has_glob(arg):
            expanded = _expand_glob(arg, base)
            if expanded is None:
                had_unexpandable = True
            else:
                targets.extend(expanded)
        else:
            targets.append(_resolve_arg(arg, base))
    targets.extend(extra_targets)
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



def _coerce_type(fm):
    """フロントマターの type を引く。無ければ id 接頭辞から。どちらも無ければ ''。"""
    t = _frontmatter.coerce_str(fm.get("type"))
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
        reason = guard_immutability(file_path, tool, tin, cwd)
    except Exception as exc:
        return _pre_deny("ガード異常(不変ガード): %r。手で確認してください。" % (exc,))
    if reason is not None:
        return _pre_deny(reason)

    # 統治木の無いプロジェクト(doctrine 未導入の土地)では、二・三ガードは
    # 発火しない(ADR-036: リンタの体系外無発火 ADR-024 と同じ境界)。
    # depends_on 風のキーを持つ他体系(Obsidian 等)の Write/Edit を誤って
    # deny/block しない。木が在れば従来どおり(stray 文書も点検する)。
    if not _project_has_tree(file_path, cwd):
        return _pre_allow()

    # docs/ の木の外の、二・三ガードが発火しえない対象は、グラフ構築(全 .md
    # 走査)を省いて通す(G1: レイテンシ早期通過)。判定は変わらない。
    if _pre_target_is_guard_inert(file_path, tool, tin):
        return _pre_allow()

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


def _pre_target_is_guard_inert(file_path, tool, tin):
    """docs/ の木の外にあり、二・三ガードのどちらも発火しえない対象か。

    グラフ構築(全 .md 走査)の前に置く早期通過(early-out)の判定。判定を一切
    変えない最適化である。inert 判定は「解決後(realpath)の対象」に対して行う:
    シンボリック/ハードリンク越しに docs/ 内の統治文書へ届く編集を取りこぼさない
    ため。MECE:
      - Write: content にフロントマターの開始フェンス '---' が無ければ Guard2 は
        fail-open(§3.6)、Guard3 は id を持たず発火しない。
      - Edit/MultiEdit: Guard3 は対象をディスクから読み id で判じるので、on-disk に
        id があれば発火しうる。Guard2 は ADR-076 以降 Edit も事前判定するので、
        on-disk にフロントマターがあるか、編集が `depends_on` に触れるなら発火しうる。
        どちらも起きない非文書のときだけ inert とみなす。
    Guard1 は本判定より前に当て済み(early-out は allow へしか倒れない)。
    """
    if _is_under_docs(file_path) or _is_under_docs(os.path.realpath(file_path)):
        return False
    if tool == "Write":
        head = tin.get("content", "").lstrip()
        return not head.startswith("---")
    # Edit/MultiEdit: 編集が depends_on を持ち込むなら Guard2 が発火しうる(ADR-076)。
    # 全文の組み立ては高いので、ここは編集文字列の字面だけを見る安い検査に留める。
    if _edit_mentions_depends_on(tin):
        return False
    if os.path.isfile(file_path):
        try:
            fm, _b, _e = _frontmatter.parse_file(file_path)
        except (OSError, UnicodeError):
            return False  # 読めない対象は早期通過させず Guard3 に委ねる。
        if _frontmatter.coerce_str(fm.get("id")) or fm:
            return False  # id は Guard3、フロントマター有りは Guard2 が発火しうる。
    return True


def _edit_mentions_depends_on(tin):
    """編集の文字列が `depends_on` に触れるか(早期通過の安い検査)。"""
    for edit in [tin] + _frontmatter.as_list(tin.get("edits")):
        if not isinstance(edit, dict):
            continue
        for key in ("old_string", "new_string"):
            if "depends_on" in _frontmatter.coerce_str(edit.get(key)):
                return True
    return False


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

    # 統治木の無いプロジェクトでは起動後ガードも発火しない(ADR-036 の境界)。
    # PreToolUse と同じく、木が一つも解決できなければ静かに通す。
    _lvl_root = _find_docs_root(file_path, cwd)
    if _lvl_root is None:
        return _post_quiet()

    # 段差ゲート(ADR-019): Level 2 は起動後ガード(block)を持たない縮小構成。
    # .docs-level を読んで自主的に静かに通す。PreToolUse の予防は残る。
    if _registry.docs_level(_lvl_root) < 3:
        return _post_quiet()

    try:
        with open(file_path, encoding="utf-8-sig", newline="") as _fh:
            raw_post = _fh.read()
    except (OSError, UnicodeError):
        return _post_quiet()  # 読めない → 助言できない(リンタ/監査に委ねる)。
    fm, body, _e = _frontmatter.parse(raw_post)

    # docs/ の木の外で、フロントマターの開始フェンス '---' を持たない純粋な非文書
    # → Guard2(ICD依存, _icd_check_content)は depends_on を読めず、Guard3 は id を
    # 持たない。どちらも発火しえないので、グラフ構築を省いて静かに通す(G1: 早期通過)。
    # 判定は id ではなくフェンスで行う: id 無しでも domain+depends_on を持つ文書型の
    # 編集は Guard2-POST が発火しうるため(CORRECTNESS 指摘)。
    if (not _is_under_docs(file_path)
            and not _is_under_docs(os.path.realpath(file_path))
            and not raw_post.lstrip().startswith("---")):
        return _post_quiet()

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
    doc_id = _frontmatter.coerce_str(fm.get("id"))
    if not doc_id:
        return None

    post_status = _frontmatter.coerce_str(fm.get("status"))
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
    pre_status = _frontmatter.coerce_str(pre_fm.get("status")) or _registry.default_status(
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

    終了コードは通常 0(判定は JSON に載る)。例外は一つだけ: 判定を stdout へ
    書けなかったときの PreToolUse で、exit 2(stderr が拒否理由になる仕様)へ倒す。
    書けない拒否を exit 0 で返すと編集がそのまま通る(fail-open。ADR-075)。
    main から例外を投げない。
    """
    _hookio.harden_stdout()
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        obj = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        obj = {}

    # 発火の印(ADR-062)。予防の面(PreToolUse)が生きている証跡を残す。
    # 最善努力であり、失敗しても本務(判定)を妨げない。
    try:
        if isinstance(obj, dict) and obj.get("hook_event_name") == "PreToolUse":
            import _auditcache
            _auditcache.write_stamp("hook_policy_guard_pre")
    except Exception:
        pass

    try:
        response = _route(obj)
    except Exception as exc:
        # 最後の砦。経路判定で落ちたら、Edit/Write/MultiEdit/Bash は fail-closed deny、
        # それ以外(PostToolUse/未知)は静かに通す。
        try:
            import _auditcache
            _auditcache.record_error("policy-guard", exc)
        except Exception:
            pass
        event = obj.get("hook_event_name") if isinstance(obj, dict) else None
        if event == "PreToolUse":
            response = _pre_deny("ガード異常: %r。手で確認してください。" % (exc,))
        else:
            response = _post_quiet()

    # 書けなければ PreToolUse は exit 2 で倒す(拒否を握り潰さない。ADR-075)。
    blocking = (obj.get("hook_event_name") == "PreToolUse"
                if isinstance(obj, dict) else False)
    return _hookio.emit_or_block(response, blocking, component="policy-guard")


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
