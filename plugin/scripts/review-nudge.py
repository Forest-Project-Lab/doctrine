#!/usr/bin/env python3
"""PostToolUse の doc-review ナッジ。型付き文書を編集したら doc-review を促す。

保証限界:
- 予防: 何も予防しない(ガードの役目)。
- 検出: 何も検出しない。判断層(doc-review)を著述・編集のたびに促すだけ。
  あわせて、会話知識の捕捉(R12)のために「このセッションで統治文書を編集した」
  「記録の文書(ADR/DECIDED/WATCH/CHANGE、またはセッションメモ)に触れた」という
  セッション別の印を残す(Stop の capture-nudge が読む)。印は検出でも拒否でもない。
- 委ねる: 文章規範・一覧外カルク・位置づけの判断は doc-review(人間とLLM)へ。
  記録するか否かの判断は capture-nudge の促しと人間へ。

doc-author 経由の著述は doc-author の手順が doc-review を回す。このナッジは、
doc-author を介さない手編集にも doc-review を促すための、もう一つの入口である。
助言だけを出し、decision は出さない(リンタと同じく実行を取り消さない)。
印の書き込みは Level の段差に依らない(R12 は生存性と同じく全 Level で効く。
ADR-030)。ナッジの出力だけが Level 3 以上(ADR-019)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402

import _frontmatter  # noqa: E402
import _registry  # noqa: E402

_NUDGE = (
    "doc-review: この文書を変更した。文章規範・一覧外カルク(逆翻訳テル)・"
    "位置づけを doc-review で見直すこと。定例3点(canonical_for 未付与・"
    "辞書外の訳語臭・意味的重複)も残っていれば見る。新しいカルクは運用正本"
    "(_system/glossary.md)のカルク表へ、新しい承認語は ADR と用語辞書へ"
    "書き戻す(§4.1)。"
)

# 記録に数える型(これらへの書き込みは「決定を記録した」とみなす。R12)。
_RECORD_TYPES = frozenset({"ADR", "DECIDED", "WATCH", "CHANGE"})
_SESSION_NOTES_NAME = ".session-notes"


def _read_stdin_json():
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _doc_path(data, argv):
    ti = data.get("tool_input") or {}
    tr = data.get("tool_response") or {}
    for cand in (ti.get("file_path"), ti.get("path"),
                 tr.get("filePath"), data.get("file_path")):
        if cand:
            return cand
    if argv:
        return argv[0]
    return None


def _typed_doc_type(path):
    """型付き統治文書なら型コードを返す。違えば None。"""
    if not path or not path.endswith(".md"):
        return None
    try:
        fm, _body, _err = _frontmatter.parse_file(path)
    except Exception:
        return None
    type_code = fm.get("type")
    if isinstance(type_code, str) and _registry.is_known_type(type_code):
        return type_code
    return None


def _docs_root_for(path):
    """path から上にたどって統治木を探す(ADR-022、登録簿に一本化)。無ければ None。"""
    return _registry.walkup_docs_root(path)


def session_flag_dir():
    """セッション別の印の置き場。plugin の cache → プロジェクトの .claude/.cache。

    決して例外を投げない。作れなければ None(印は諦める。助言層なので安全)。
    """
    cands = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(os.path.join(plugin_root, ".cache", "session-flags"))
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cands.append(os.path.join(proj, ".claude", ".cache", "session-flags"))
    cands.append(os.path.join(os.getcwd(), ".claude", ".cache", "session-flags"))
    for d in cands:
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except OSError:
            continue
    return None


def _touch_flag(flag_dir, name):
    if not flag_dir:
        return
    try:
        with open(os.path.join(flag_dir, name), "w", encoding="utf-8") as fh:
            fh.write("")
    except OSError:
        pass


def _safe_sid(data):
    sid = data.get("session_id")
    if not isinstance(sid, str) or not sid.strip():
        return None
    # ファイル名に使うので英数とハイフンだけ残す。
    return "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or None


def _mark_session(data, path, type_code):
    """会話知識の捕捉(R12)の印。統治文書の編集と、記録の文書への書き込みを残す。"""
    sid = _safe_sid(data)
    if sid is None:
        return
    flag_dir = session_flag_dir()
    if flag_dir is None:
        return
    base = os.path.basename(path or "")
    if base == _SESSION_NOTES_NAME:
        _touch_flag(flag_dir, "recorded-%s" % sid)
        return
    if type_code is None:
        return
    _touch_flag(flag_dir, "edits-%s" % sid)
    if type_code in _RECORD_TYPES:
        _touch_flag(flag_dir, "recorded-%s" % sid)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        data = _read_stdin_json()
        path = _doc_path(data, argv)
        base = os.path.basename(path or "")
        type_code = _typed_doc_type(path)
        if type_code is None and base != _SESSION_NOTES_NAME:
            return 0  # 文書でなければ静かに通す。
        # 統治木の無いプロジェクト(doctrine 未導入の土地)では、type: SPEC 等の
        # frontmatter を持つ他体系の .md を編集しても、捕捉の印も助言も出さない
        # (ADR-036: ガードの体系外無発火と同じ境界)。存在しない _system/ への
        # 書き戻し指示や、無関係なセッションの Stop 差し止めを防ぐ。
        # 木が在れば(木の外の stray 文書でも)従来どおり印と助言を出す。
        if _docs_root_for(path) is None:
            return 0
        # 捕捉の印は Level に依らず残す(R12 / ADR-030)。
        _mark_session(data, path, type_code)
        if type_code is None:
            return 0  # セッションメモへの書き込みは印だけ。ナッジは出さない。
        # 段差ゲート(ADR-019): Level 2 の縮小構成にナッジは無い。
        root = _docs_root_for(path)
        if root is not None and _registry.docs_level(root) < 3:
            return 0
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": _NUDGE,
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    except Exception:
        return 0  # ナッジは助言。失敗しても Hook を落とさない。
    return 0


if __name__ == "__main__":
    sys.exit(main())
