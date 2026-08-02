#!/usr/bin/env python3
"""PreCompact の印(R12)。圧縮が起きたことを機械的に残す。

**モデルへは何も言わない(ADR-077)。** 以前はここで additionalContext に退避の指示を
載せて返していたが、現行の公式仕様では additionalContext を運ぶ事象は決まっており、
PreCompact はそこに含まれない。届かない「版」があるのではなく、構造上どの版でも
届かない。つまり R12 の「圧縮前の促し」は一度も発火したことのない死んだ経路だった。

保証限界:
- 予防: 何も予防しない。圧縮自体は止めない(止めるべきでもない)。
- 検出: 圧縮が起きた事実だけを印として残す。会話本文も推論過程も写さない
  (フックは会話を持たないので、原理的に写せない)。
- 委ねる: 合図は圧縮の**後**、次の SessionStart の注入が出す(source=compact、または
  この印が新しいとき)。圧縮で失われた詳細は戻らない。できるのは「失われたかもしれない」
  と告げることだけである。

標準ライブラリのみ。決して例外を外へ出さない。終了コードは常に 0。
"""
import json
import os
import sys

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _auditcache
import _hookio
# doctrine:begin SPEC-022
# 圧縮が起きたことの印の鍵。次のセッションの注入がこれを読む(ADR-077)。
COMPACTED_KEY = "compacted"
# doctrine:end SPEC-022


def _project_has_tree():
    """このプロジェクトに統治木が在るか(ADR-036 の境界)。決して例外を投げない。

    PreCompact はファイルパスを持たないため、CLAUDE_PROJECT_DIR と作業ディレクトリ
    から統治木を解決する。統治木の無いプロジェクト(doctrine 未導入の土地)では、
    存在しない `_system/.session-notes` への退避を指示しない。
    """
    try:
        import _registry
        proj = os.environ.get("CLAUDE_PROJECT_DIR")
        return _registry.walkup_docs_root(proj or os.getcwd(), os.getcwd()) is not None
    except Exception:
        return False


def main(argv=None):
    _hookio.harden_stdout()
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        # 統治木の無いプロジェクトでは印を残さない(ADR-036 の境界)。
        if not _project_has_tree():
            return 0
        # 圧縮の印だけを原子的に残す(ADR-077)。モデルへは何も返さない —— この事象は
        # 文脈を運ばないので、返しても誰にも届かない。合図は次の SessionStart が出す。
        _auditcache.write_stamp(COMPACTED_KEY)
        _hookio.emit({}, component="precompact-dump")
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
