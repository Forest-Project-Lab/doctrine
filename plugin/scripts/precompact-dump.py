#!/usr/bin/env python3
"""PreCompact の退避指示(R12)。圧縮で会話が要約される前に、未記録の決定をディスクへ。

保証限界:
- 予防: 何も予防しない。圧縮自体は止めない(止めるべきでもない)。
- 検出: 何も検出しない。圧縮の直前という「記憶が消える最後の機会」に、
  未記録の決定・根拠・用語をセッションメモ(_system/.session-notes)へ書き出す
  よう指示を注入するだけ。実際に書くかは Claude と人間に委ねる。
- 委ねる: 選別(メモ→ADR/DECIDED への正式化)は次セッションの SessionStart 注入が
  義務として出す(inject-contract の未選別メモ節)。書式の正しさは選別時に正す。

additionalContext が PreCompact で届かない版の Claude Code でも、何も壊さない
(出力は無害な JSON。読まれなければ静かに終わるだけ)。標準ライブラリのみ。
決して例外を外へ出さない。終了コードは常に 0。
"""
import json
import os
import sys

_INSTRUCTION = (
    "【統治・圧縮前の退避】この会話はまもなく圧縮され、詳細は失われる。"
    "未記録の決定・撤回・新しい用語・重要な根拠がこの会話にあるなら、圧縮の前に"
    "統治木の `_system/.session-notes` へ一行ずつ追記すること"
    "(形式: `- <一文の事実> (出所: 会話, YYYY-MM-DD)`)。次のセッション開始時に、"
    "このメモを ADR・DECIDED へ選別する義務が自動で出る(R12)。"
    "記録すべきものが無ければ何もしなくてよい。"
)


def main(argv=None):
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreCompact",
                "additionalContext": _INSTRUCTION,
            }
        }
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
