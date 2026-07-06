#!/usr/bin/env python3
"""PostToolUse の doc-review ナッジ。型付き文書を編集したら doc-review を促す。

保証限界:
- 予防: 何も予防しない(ガードの役目)。
- 検出: 何も検出しない。判断層(doc-review)を著述・編集のたびに促すだけ。
- 委ねる: 文章規範・一覧外カルク・位置づけの判断は doc-review(人間とLLM)へ。

doc-author 経由の著述は doc-author の手順が doc-review を回す。このナッジは、
doc-author を介さない手編集にも doc-review を促すための、もう一つの入口である。
助言だけを出し、decision は出さない(リンタと同じく実行を取り消さない)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402

import _frontmatter  # noqa: E402
import _registry  # noqa: E402

_NUDGE = (
    "doc-review: この文書を変更した。文章規範・一覧外カルク(逆翻訳テル)・"
    "位置づけを doc-review で見直すこと。新しいカルクは用語辞書のカルク表へ、"
    "新しい承認語は ADR と用語辞書へ書き戻す(§4.1)。"
)


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


def _is_typed_doc(path):
    """型付き統治文書か。フロントマターに既知の型があれば真。"""
    if not path or not path.endswith(".md"):
        return False
    try:
        fm, _body, _err = _frontmatter.parse_file(path)
    except Exception:
        return False
    type_code = fm.get("type")
    return isinstance(type_code, str) and _registry.is_known_type(type_code)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        data = _read_stdin_json()
        path = _doc_path(data, argv)
        if not _is_typed_doc(path):
            return 0  # 文書でなければ静かに通す。
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
