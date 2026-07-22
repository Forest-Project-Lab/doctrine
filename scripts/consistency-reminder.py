#!/usr/bin/env python3
"""UserPromptSubmit フック: 会話（ユーザ発話）ごとにカウンタを 1 増やし、
INTERVAL 回ごとに整合点検のリマインドを注入する。

- カウンタは .claude/.consistency-counter に置く（セッションを問わず持続。
  会話の回数を跨セッションで数え続ける）。
- INTERVAL 回に達した会話だけ、additionalContext でリマインドを返す。
- 催促するだけで、点検自体は実行しない（実行は /consistency-check または
  scripts/consistency-check.py に委ねる）。
- 何が起きても後続フックを壊さない。終了コードは常に 0。
"""
import json
import os
import sys

INTERVAL = 10


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    counter_path = os.path.join(proj, ".claude", ".consistency-counter")

    n = 0
    try:
        with open(counter_path, "r", encoding="utf-8") as fh:
            n = int((fh.read().strip() or "0"))
    except Exception:
        n = 0
    n += 1
    try:
        os.makedirs(os.path.dirname(counter_path), exist_ok=True)
        with open(counter_path, "w", encoding="utf-8") as fh:
            fh.write(str(n))
    except Exception:
        pass

    if n % INTERVAL == 0:
        msg = (
            "【整合点検のリマインド】これで %d 回目の会話です（%d 回ごと）。\n"
            "linter と audit が同じファイルへ矛盾した判定を出していないか点検する"
            "時期です。次を実行してください:\n"
            "  /consistency-check   (または python3 scripts/consistency-check.py)\n"
            "食い違いが出たら、それは「同じ入力を二つの道具が別々に裁いて矛盾する」"
            "欠陥クラス。1件ずつ意味を吟味し、本物なら SPEC 改訂 → チェック追加で"
            "固定してください。" % (n, INTERVAL)
        )
        out = {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg}}
        try:
            sys.stdout.write(json.dumps(out, ensure_ascii=False))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
