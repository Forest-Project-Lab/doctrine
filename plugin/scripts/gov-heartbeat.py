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

import _auditcache  # noqa: E402
import _frontmatter  # noqa: E402
import _intake  # noqa: E402
import _registry  # noqa: E402

# doctrine:begin SPEC-021
DEFAULT_AUDIT_STALE_DAYS = 7
DEFAULT_CADENCE_DAYS = 30
# doctrine:end SPEC-021

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_STATE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[:：]\s*(\S+)\s*$")
STATE_NAME = _auditcache.STATE_NAME   # 正本は共有コア(ADR-053)


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
    """前回監査の要約。無ければ None。

    候補順・schema 照合・root 照合・世代の照合は、共有コア `_auditcache` が
    一度だけ定める(ADR-053)。ここは自前の照合を持たない。注入(inject-contract)
    も同じ関数を呼ぶので、「どの要約を読むか」の答えは読み手をまたいで一つに
    なる。以前は照合の段が揃っておらず、未知のスキーマの候補が先にあると、
    一方は次の候補へ進み、もう一方はそこで止まった。
    """
    return _auditcache.load(docs_root)


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


def _unclassified_strays(summary):
    """要約から未分類の体系外 .md の一覧(paths)を返す(移行キャンペーンの種。ADR-034)。

    台帳(.md-intake)に無い .md だけを数える。判定は監査が付けた所見の文言
    (「未分類」)で行う。台帳を二重に持たない(導出で回す)。"""
    out = []
    if not isinstance(summary, dict):
        return out
    for f in summary.get("findings") or []:
        if not isinstance(f, dict):
            continue
        if f.get("check") == "stray_document" and "未分類" in str(f.get("message")):
            p = str(f.get("path") or "").strip()
            if p:
                out.append(p)
    return out


def migration_line(docs_root, summary):
    """移行キャンペーンの一件(1鼓動1件)。対象が無ければ空文字列(ADR-034)。"""
    strays = _unclassified_strays(summary)
    if not strays:
        return ""
    entries, _bad = _intake.load_ledger(docs_root)
    done = len(entries)
    total = done + len(strays)
    # ファイル名は攻撃者制御になりうる(改行で偽の統治指示を捏造できる。#96)。
    # 注入境界へ届く前にサニタイズする(ADR-040)。
    nxt = _frontmatter.sanitize_inline(strays[0], 120)
    return ("【移行 %d/%d】統治木の外の .md が %d 件未分類。次の1件: %s — "
            "「これを分類して」と言えば docs-curate で進める(取り込む=doc-author で"
            "型を与える／参照=EXT アンカー／非文書=期限付きで台帳へ)。分類のたびに"
            "この数は減り、台帳(_system/.md-intake)が進捗の正本になる。"
            % (done, total, len(strays), nxt))


def build_message(docs_root, today, config):
    """最も重い一件の警告文を返す。何も無ければ空文字列。純粋(入出力なしの判定は分離)。"""
    audit_stale_days = _knob(config, "audit_stale_days", DEFAULT_AUDIT_STALE_DAYS)
    cadence_days = _knob(config, "cadence_review_days", DEFAULT_CADENCE_DAYS)

    summary = _audit_summary(docs_root)
    state = read_state(docs_root)
    level = _registry.docs_level(docs_root)

    # 1) 監査の死活(R11)。要約なし・古い、の順に重い。Level 2 に SessionEnd の監査は
    #    無い(ADR-019)ため、この検査は Level 3 以上でだけ意味を持つ(誤報を出さない)。
    if level >= 3:
        if summary is None:
            if not state:
                return ""  # 使い始めの前(記録が何も無い)は黙る。SessionStart の案内に譲る。
            if state.get("initialized"):
                # 導入直後で、初回の SessionEnd 監査がまだ走っていない状態(#74)。
                # 監査の停止ではないので警告ではなく中立の案内にする(導入初日を
                # ⚠ で始めない)。最初のセッション終了で監査が走り、以後は鮮度で促す。
                return ("【統治】導入直後です。初回の監査はこのセッションの終了時"
                        "(SessionEnd)に走ります。すぐ確かめたいなら「監査を実行して」"
                        "と言えば docs-audit で走らせられます。")
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
        if summary is None and not state:
            return ""  # 使い始めの前は促さない(騒がしい導入にしない)。
        return ("【統治】doc-review の定例(canonical_for 未付与・辞書外の訳語臭・"
                "意味的重複)の実施記録が無い。「定例レビューをやって」と言えば回す。"
                "終えたら _system/%s の last_cadence_review に日付を書く。" % STATE_NAME)
    if (today - last).days >= cadence_days:
        return ("【統治】doc-review の定例が前回(%s)から %d 日空いた(周期 %d 日)。"
                "「定例レビューをやって」と言えば回す。終えたら _system/%s の "
                "last_cadence_review を更新する。"
                % (last.isoformat(), (today - last).days, cadence_days, STATE_NAME))

    # 3) 移行キャンペーン(1鼓動1件。ADR-034)。上の義務がすべて静かなときだけ出す。
    line = migration_line(docs_root, summary)
    if line:
        return line
    # 4) 紐づけキャンペーン(ADR-065)。体系外 .md の整理が出す物を持たない体系で
    #    だけ順番が回る(位相: 文書の整理 → 紐づけの整理)。枠は増やさない。
    line = trace_campaign_line(summary)
    if line:
        return line
    # 5) Level 昇格の一度きりの案内(ADR-066)。全ての促しが静かなときだけ。
    line = level_hint_line(summary, level)
    if line:
        return line
    # 6) 悉皆モードの一度きりの案内(ADR-072)。仕様側の悉皆が済んだ体系だけ。
    return trace_mode_hint_line(summary, config)


def trace_mode_hint_line(summary, config):
    """悉皆モードの判断材料を一度だけ示す(ADR-072)。以後は印を残して黙る。

    仕様側の悉皆が済み(未宣言 0)、印なしが残り、モードが未設定のときだけ。
    入れるかは人の判断のまま(自動化しない。繰り返し促さない)。
    """
    if not isinstance(summary, dict):
        return ""
    if isinstance(config, dict) and config.get("trace_mode") == "exhaustive":
        return ""   # 既に入れている体系に案内は要らない。
    cov = summary.get("trace_coverage")
    sc = cov.get("spec_coverage") if isinstance(cov, dict) else None
    if not isinstance(sc, dict):
        return ""
    try:
        undeclared = int(sc.get("undeclared") or 0)
        unmarked = int(cov.get("unmarked_files") or 0)
    except (TypeError, ValueError):
        return ""
    if undeclared != 0 or unmarked <= 0:
        return ""
    shown = _auditcache.read_stamp_values().get("trace_mode_hint_shown")
    if shown:
        return ""
    _auditcache.write_stamp("trace_mode_hint_shown", value="shown")
    return ("【悉皆】仕様側の紐づけは出揃った(未宣言 0)が、印なしのコードが "
            "%d 件残っている。追跡を可視化や被覆の主張に使うなら、悉皆モードで"
            "残高にできる — _system/.context-config.json に「\"trace_mode\": "
            "\"exhaustive\"」と書くと、監査が残高を warn 一件で告げる"
            "(ADR-072)。入れるかは人の判断のまま。" % unmarked)


def level_hint_line(summary, level):
    """Level 昇格の判断材料を一度だけ示す(ADR-066)。以後は印を残して黙る。

    Level 2 のままで全件監査の実績(読める要約)が確認できたときだけ。昇格する
    かは人の判断のまま(自動化しない。繰り返し促さない)。
    """
    if level >= 3:
        return ""
    if not isinstance(summary, dict):
        return ""   # 実績(要約)が無ければ案内の根拠が無い。
    shown = _auditcache.read_stamp_values().get("level_hint_shown")
    if shown:
        return ""
    _auditcache.write_stamp("level_hint_shown", value="shown")
    return ("【段階】Level 2 のまま、全件監査の実績(読める要約)を確認した。"
            "常時の SessionEnd 監査と督促が要るなら Level 3 へ上げられる — "
            "_system/.docs-level に「level: 3」と書き、新しいセッションで効く"
            "(ADR-066)。上げるかは運用の判断で、この案内は一度だけ出す。")


# 文中に運ぶ id の書式(登録簿の <TYPE>-<NNN>)。要約は攻撃者制御になりうるため、
# 一致しない値は文面に載せない(ADR-040 の境界と同じ扱い。ADR-065)。
_CAMPAIGN_ID_RE = re.compile(r"^[A-Z]+-\d+$")


def trace_campaign_line(summary):
    """紐づけキャンペーン(ADR-065)。未宣言の仕様の先頭一件を自己完結文で促す。

    読むのは監査の要約だけ(全木の走査はしない。SPEC-021 の制約)。要約が
    「次の一件」(spec_coverage.next_undeclared)を運ぶ。無ければ黙る。
    """
    if not isinstance(summary, dict):
        return ""
    cov = summary.get("trace_coverage")
    if not isinstance(cov, dict):
        return ""
    sc = cov.get("spec_coverage")
    if not isinstance(sc, dict):
        return ""
    try:
        undeclared = int(sc.get("undeclared") or 0)
    except (TypeError, ValueError):
        return ""
    if undeclared <= 0:
        return ""
    nid = sc.get("next_undeclared")
    if not isinstance(nid, str) or not _CAMPAIGN_ID_RE.match(nid):
        return ""
    tail = ""
    streak = cov.get("stagnation_streak")
    if isinstance(streak, int) and streak >= 3:
        tail = "進捗が %d 回の監査で動いていない。" % streak
    return ("【紐づけ整理】%s はコードとの関係が未宣言(残り %d 件)。この一件だけ"
            "片づける: 実装があるなら範囲を印の対で囲み『実装の指紋』へ指紋を"
            "記録する(SPEC-026)。意図して結ばないなら『- コード対応なし: <理由>』"
            "を節に書く(ADR-061)。関係するコードが使い捨てなら、そのファイルに"
            "exempt を宣言する(ADR-067)。%s" % (nid, undeclared, tail))


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
        # 拒否経路の欠落の疑い(ADR-062)。判定は _auditcache に一度だけ在る。
        gap = _auditcache.liveness_gap(_auditcache.read_stamps())
        if gap:
            msg = (msg + "\n" if msg else "") + "【拒否経路の疑い】" + gap
        # 版の切替(ADR-066)。配線と契約が古いまま動いている状態を毎回検める。
        drift = _auditcache.version_drift(_auditcache.read_stamp_values())
        if drift:
            msg = (msg + "\n" if msg else "") + "【版の切替】" + drift
        # 版の遅れ(ADR-070)。導入済みの複製が正本より古いまま動き続ける状態を
        # 検める。マニフェストを持たない導入先では黙る(自己適用だけの照合)。
        lag = _auditcache.version_lag()
        if lag:
            msg = (msg + "\n" if msg else "") + "【版の遅れ】" + lag
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
