#!/usr/bin/env python3
"""Stop の捕捉ナッジ(R12)。統治文書を編集したセッションの終端で、決定の記録を一度だけ問う。

保証限界:
- 予防: 何も予防しない。記録の質も保証しない。
- 検出: 「このセッションで統治文書を編集したのに、記録の文書(ADR/DECIDED/WATCH/
  CHANGE)にもセッションメモにも触れていない」という不作為だけを検出し、停止を
  一度だけ差し止めて問う(decision: block)。応答の中身(記録する/決定なしと明言する)
  は判断層に委ねる。
- 委ねる: 記録すべき決定があったかの判断は Claude と人間へ。会話に決定が
  「無かった」ことの検証は構造ではできない(§7)。

印(edits-<sid> / recorded-<sid>)は review-nudge.py が PostToolUse で残す。
本スクリプトは Stop で一度だけ読む。無限ループは stop_hook_active と
nudged-<sid> の二重の歯止めで防ぐ。Level の段差に依らず動く(ADR-030)。
標準ライブラリのみ。決して例外を外へ出さない。終了コードは常に 0。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_FLAG_STALE_SECONDS = 7 * 24 * 3600   # 印の掃除(7日より古い印は消す)

_REASON = (
    "【統治・記録の確認】このセッションで統治文書を編集したが、決定の記録"
    "(ADR・DECIDED・WATCH・CHANGE)にもセッションメモにも触れていない。"
    "終える前に一つだけ答えること: このセッションで方針の決定・撤回・新しい"
    "用語の定義はあったか。あったなら doc-author で ADR(設計判断)か DECIDED"
    "(横断の確定事実)へ今記録する。無かったなら『このセッションに記録すべき"
    "決定は無い』と明言してから終える。この確認はセッションに一度だけ出る(R12)。"
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


def _safe_sid(data):
    sid = data.get("session_id")
    if not isinstance(sid, str) or not sid.strip():
        return None
    return "".join(c for c in sid if c.isalnum() or c in "-_")[:64] or None


def _flag_dir():
    """review-nudge.py と同じ置き場の解決(書けなくてもよいので読み側は緩く)。"""
    cands = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(os.path.join(plugin_root, ".cache", "session-flags"))
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cands.append(os.path.join(proj, ".claude", ".cache", "session-flags"))
    cands.append(os.path.join(os.getcwd(), ".claude", ".cache", "session-flags"))
    for d in cands:
        if os.path.isdir(d):
            return d
    return None


def _sweep_stale(flag_dir):
    """7日より古い印を消す(たまり続けないための掃除。失敗は無視)。"""
    try:
        now = time.time()
        for name in os.listdir(flag_dir):
            p = os.path.join(flag_dir, name)
            try:
                if now - os.path.getmtime(p) > _FLAG_STALE_SECONDS:
                    os.remove(p)
            except OSError:
                continue
    except OSError:
        pass


def main(argv=None):
    try:
        data = _read_stdin_json()
        # 歯止め1: 既にこの Stop ナッジ経由で続行しているなら、二度は止めない。
        if data.get("stop_hook_active"):
            return 0
        sid = _safe_sid(data)
        if sid is None:
            return 0
        d = _flag_dir()
        if d is None:
            return 0
        _sweep_stale(d)
        edits = os.path.isfile(os.path.join(d, "edits-%s" % sid))
        recorded = os.path.isfile(os.path.join(d, "recorded-%s" % sid))
        nudged_path = os.path.join(d, "nudged-%s" % sid)
        nudged = os.path.isfile(nudged_path)
        if not edits or recorded or nudged:
            return 0
        # 歯止め2: セッションに一度だけ。先に印を書いてから問う。
        try:
            with open(nudged_path, "w", encoding="utf-8") as fh:
                fh.write("")
        except OSError:
            return 0  # 印を残せないなら、ループの恐れを避けて問わない。
        sys.stdout.write(json.dumps(
            {"decision": "block", "reason": _REASON}, ensure_ascii=False))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
