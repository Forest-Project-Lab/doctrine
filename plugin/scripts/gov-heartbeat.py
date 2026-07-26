#!/usr/bin/env python3
"""UserPromptSubmit の統治ハートビート(R11)。会話の鼓動ごとに統治の生存と期限を照合する。

保証限界:
- 予防: 何も予防しない。
- 検出: (1) 前回監査の要約が無い/古い(SessionEnd 監査が動いていない兆候)、
  (2) doc-review の定例の実施記録(_system/.governance-state の last_cadence_review)の
  周期超過、の二つを照合し、最も重い一件だけを助言として注入する。
  セッションに一度だけ出す(同じ警告で毎会話を埋めない)。
- 委ねる: 実際に監査・定例を回すかは Claude と人間へ。全件の検査は監査へ。

設計の要点:
- 速さ: 全木走査をしない。読むのは要約キャッシュ・状態ファイル・設定の三つの
  小ファイルだけ(UserPromptSubmit は毎会話走るため)。
- 段差: Level に依らず動く(ADR-030。死活の可視性は軽量化で削らない)。
- 決定性: --today で基準日を固定できる(テスト用)。与えなければ壁時計に退避する。
標準ライブラリのみ。決して例外を外へ出さない。終了コードは常に 0。
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _registry  # noqa: E402

DEFAULT_AUDIT_STALE_DAYS = 7
DEFAULT_CADENCE_DAYS = 30

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_STATE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[:：]\s*(\S+)\s*$")
STATE_NAME = ".governance-state"


def _parse_date(s):
    if not isinstance(s, str):
        return None
    m = _DATE_RE.match(s.strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _read_stdin_json():
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    try:
        obj = json.loads(raw) if raw and raw.strip() else {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _docs_root():
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        found = _registry.locate_docs_root(proj)
        if found is not None:
            return found
    return _registry.locate_docs_root(os.getcwd())


def _load_config(docs_root):
    if not docs_root:
        return {}
    path = os.path.join(docs_root, "_system", ".context-config.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _knob(config, key, default):
    try:
        v = int(config.get(key))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _audit_summary(docs_root):
    """前回監査の要約。inject-contract と同じ候補順・同じ root 照合。無ければ None。"""
    cands = []
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        cands.append(os.path.join(plugin_root, ".cache", "last-audit.json"))
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        cands.append(os.path.join(proj, ".claude", ".cache", "last-audit.json"))
    cands.append(os.path.join(os.getcwd(), ".claude", ".cache", "last-audit.json"))
    for path in cands:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(data, dict):
            continue
        root = data.get("root")
        if not isinstance(root, str) or not os.path.isabs(root):
            continue
        try:
            if docs_root and os.path.realpath(root) != os.path.realpath(
                    os.path.abspath(docs_root)):
                continue
        except (OSError, ValueError):
            continue
        return data
    return None


def read_state(docs_root):
    """_system/.governance-state を読む。`キー: 値` の平文。無ければ {}。"""
    out = {}
    if not docs_root:
        return out
    path = os.path.join(docs_root, "_system", STATE_NAME)
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                m = _STATE_LINE_RE.match(s)
                if m:
                    out[m.group(1)] = m.group(2)
    except (OSError, UnicodeError):
        return out
    return out


def _once_per_session(sid):
    """このセッションで既に出したか。印を残して True/False。残せなければ False(出す)。"""
    if not sid:
        return False
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
            flag = os.path.join(d, "hb-%s" % sid)
            if os.path.isfile(flag):
                return True
            with open(flag, "w", encoding="utf-8") as fh:
                fh.write("")
            return False
        except OSError:
            continue
    return False


def build_message(docs_root, today, config):
    """最も重い一件の警告文を返す。何も無ければ空文字列。純粋(入出力なしの判定は分離)。"""
    audit_stale_days = _knob(config, "audit_stale_days", DEFAULT_AUDIT_STALE_DAYS)
    cadence_days = _knob(config, "cadence_review_days", DEFAULT_CADENCE_DAYS)

    summary = _audit_summary(docs_root)
    state = read_state(docs_root)

    # 1) 監査の死活(R11)。要約なし・古い、の順に重い。
    if summary is None:
        if not state:
            return ""  # 使い始めの前(記録が何も無い)は黙る。SessionStart の案内に譲る。
        return ("【統治】前回監査の記録が見つからない。SessionEnd の監査が動いて"
                "いない可能性がある。「監査を実行して」と言えば docs-audit で確かめる(R11)。")
    audit_day = _parse_date(summary.get("today"))
    if audit_day is not None and (today - audit_day).days >= audit_stale_days:
        return ("【統治】前回監査から %d 日が経っている(最終 %s)。SessionEnd の監査が"
                "動いていない可能性がある。「監査を実行して」と言えば確かめる(R11)。"
                % ((today - audit_day).days, audit_day.isoformat()))

    # 2) doc-review 定例の周期(運用契約、§7)。
    last = _parse_date(state.get("last_cadence_review"))
    if last is None:
        return ("【統治】doc-review の定例(canonical_for 未付与・辞書外の訳語臭・"
                "意味的重複)の実施記録が無い。「定例レビューをやって」と言えば回す。"
                "終えたら _system/%s の last_cadence_review に日付を書く。" % STATE_NAME)
    if (today - last).days >= cadence_days:
        return ("【統治】doc-review の定例が前回(%s)から %d 日空いた(周期 %d 日)。"
                "「定例レビューをやって」と言えば回す。終えたら _system/%s の "
                "last_cadence_review を更新する。"
                % (last.isoformat(), (today - last).days, cadence_days, STATE_NAME))
    return ""


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        data = _read_stdin_json()
        today = None
        for i, a in enumerate(argv):
            if a == "--today" and i + 1 < len(argv):
                today = _parse_date(argv[i + 1])
            elif a.startswith("--today="):
                today = _parse_date(a.split("=", 1)[1])
        if today is None:
            today = datetime.date.today()

        docs_root = _docs_root()
        if not docs_root:
            return 0  # 統治木が無いプロジェクトでは黙る。
        config = _load_config(docs_root)
        msg = build_message(docs_root, today, config)
        if not msg:
            return 0
        sid = data.get("session_id")
        sid = "".join(c for c in sid if c.isalnum() or c in "-_")[:64] \
            if isinstance(sid, str) else ""
        if _once_per_session(sid):
            return 0
        out = {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
