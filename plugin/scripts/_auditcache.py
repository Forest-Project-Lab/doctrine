#!/usr/bin/env python3
"""前回監査の要約を読む共有コア(注入と鼓動が同じ答えを得るための単一正本)。

ADR-053。以前は inject-contract.py と gov-heartbeat.py が別々に候補順と照合を
持っており、二つの欠陥を生んでいた。

- 木を消して同じ場所に作り直すと、前の世代の要約の root が一致してしまい、
  一度も監査していない木に「error 0」が引き継がれた(偽の健全信号)。
- schema の照合の段が揃っておらず、未知のスキーマの候補が先にあると、
  一方は次の候補へ進み、もう一方はそこで止まった(読み手ごとに別の答え)。

読み取りの規則(候補順・schema・root・世代)はここに一度だけ書く。呼ぶ側は
自前の照合を持たない(DECIDED-001 事実1 と同じ形)。

保証限界:
- 予防: 何も予防しない。読み取りの規則を一つにするだけである。
- 検出: 条件を満たさない候補を飛ばし、読めた要約だけを返す。何を捨てたかの
  判断(死活の警告にするか、中立の案内にするか)は呼ぶ側に委ねる。
- 委ねる: 要約の中身の真偽、監査を実際に走らせるかは呼ぶ側と人間へ。

標準ライブラリのみ。決して例外を外へ出さない。
"""
import datetime
import json
import os
import re

# doctrine:begin ADR-053
SCHEMA = "docs-audit/1"
STATE_NAME = ".governance-state"
# doctrine:end ADR-053
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# 状態ファイルの行。gov-heartbeat の読みと同じ寛容度にする(全角コロンも許す。
# ADR-042: 知らないキー・読めない行は無視し、読めた範囲で判じる)。
_STATE_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[:：]\s*(\S+)\s*$")


def candidates():
    """要約の候補パスを、読む順に返す(ADR-037)。

    プロジェクトスコープが先、旧 ${CLAUDE_PLUGIN_ROOT}/.cache は後方互換の
    フォールバックとして最後。旧配置を先に読むと、移行前の残骸が新しい要約を
    影で隠し、偽の死活警報を毎セッション出す(#69)。
    """
    out = []
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        out.append(os.path.join(proj, ".claude", ".cache", "last-audit.json"))
    out.append(os.path.join(os.getcwd(), ".claude", ".cache", "last-audit.json"))
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        out.append(os.path.join(plugin_root, ".cache", "last-audit.json"))
    return out


def _parse_date(value):
    """先頭の YYYY-MM-DD を date で返す。読めなければ None。例外は投げない。"""
    if not isinstance(value, str):
        return None
    m = _DATE_RE.match(value.strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def read_initialized(docs_root):
    """`initialized` の印を読み、(印が在るか, 日付か None) を返す。

    印の有無と日付を分けて返すのは、二つの用途で意味が違うためである。

    - 導入直後かどうかの判定(ADR-041)は**印の有無**で決める。日付が壊れて
      いても、初期化された木であることに変わりはない。ここで日付を要ると
      すると、印が壊れた木の初日が警告から始まる(誤報の側へ倒れる)。
    - 世代の照合(ADR-053)は**日付**を要る。読めなければ判じない。

    印が無い/読めないときは (False, None)。決して例外を投げない。
    """
    if not docs_root:
        return (False, None)
    path = os.path.join(docs_root, "_system", STATE_NAME)
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                m = _STATE_LINE_RE.match(line)
                if m and m.group(1) == "initialized":
                    return (True, _parse_date(m.group(2)))
    except (OSError, UnicodeError):
        return (False, None)
    return (False, None)


def initialized_date(docs_root):
    """統治木が scaffold で初期化された日。読めなければ None。

    この決定より前に作られた木は印を持たないので、世代の照合をしない側へ
    倒れる(前方寛容。ADR-042)。
    """
    return read_initialized(docs_root)[1]


def has_initialized_marker(docs_root):
    """統治木が scaffold で初期化済みか(印の有無。日付の可否は問わない)。"""
    return read_initialized(docs_root)[0]


def summary_date(summary):
    """要約が表す日。today を優先し、無ければ generated_at の先頭日付。"""
    if not isinstance(summary, dict):
        return None
    return _parse_date(summary.get("today")) or _parse_date(
        summary.get("generated_at"))


def same_root(summary_root, docs_root):
    """要約の root と読み手の統治木が同じ場所を指すか。例外は投げない。

    相対パスの root は照合できない(読み手の作業ディレクトリ次第でどの
    プロジェクトとも一致しうる)ため、不一致として捨てる。同梱の配線は常に
    絶対パスを書くので、正当な要約はここで落ちない。
    """
    if not isinstance(summary_root, str) or not summary_root.strip():
        return False
    if not os.path.isabs(summary_root):
        return False
    if not docs_root:
        return True
    try:
        return os.path.realpath(summary_root) == os.path.realpath(
            os.path.abspath(docs_root))
    except (OSError, ValueError):
        return False


def superseded_by_reinstall(summary, init_date):
    """要約が、いまの木より前の世代のものか(ADR-053 の世代の照合)。

    木を消して同じ場所に作り直すと root は一致してしまう。木の同一性は場所
    では決まらないので、初期化の日より厳密に古い要約は前の世代として捨てる。
    印が無い木、日付を読めない要約では判じない(False = 捨てない)。

    粒度は日である。同じ日に作り直した場合は日付が等しく、捨てられない
    (ADR-053 の既知の限界)。
    """
    if init_date is None:
        return False
    sdate = summary_date(summary)
    if sdate is None:
        return False
    return sdate < init_date


def load(docs_root=None):
    """前回監査の要約を返す。読めるものが無ければ None。例外は投げない。

    候補を順に見て、schema・root・世代のどれかを満たさない候補は**飛ばして
    次へ進む**(そこで止まらない)。止まると、先頭に壊れた候補があるだけで
    後ろの正しい要約に届かなくなる。
    """
    init_date = initialized_date(docs_root)
    for path in candidates():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("schema") != SCHEMA:
            continue
        if not same_root(data.get("root"), docs_root):
            continue
        if superseded_by_reinstall(data, init_date):
            continue
        return data
    return None


# ---------------------------------------------------------------------------
# フックの発火の印(ADR-062)。書き手はフック、読み手は鼓動と監査。
# 判定はここに一度だけ置く(ADR-053 と同じ原理。読み手ごとに答えを割らない)。
# ---------------------------------------------------------------------------

STAMPS_NAME = "hook-stamps"

# ガード(PreToolUse)とリンタ(PostToolUse)は同じ編集の出来事に対で発火する。
# この猶予を超えてリンタだけが新しければ、編集がガードを通っていない疑い。
GUARD_LINTER_SKEW_SECONDS = 60

_TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")


def stamps_path(proj=None):
    """印のファイルの置き場(git の追跡外。監査の要約と同じ .claude/.cache)。

    proj を与えなければ CLAUDE_PROJECT_DIR、無ければ作業ディレクトリ。監査は
    監査対象の木の親を渡す(試験と CI で決定的にするため)。
    """
    if not proj:
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(proj, ".claude", ".cache", STAMPS_NAME)


def _parse_ts(value):
    """UTC の ISO-8601(秒精度) を datetime で返す。読めなければ None。"""
    if not isinstance(value, str):
        return None
    m = _TS_RE.match(value.strip())
    if not m:
        return None
    try:
        return datetime.datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
            tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def write_stamp(key, now=None, proj=None, value=None):
    """鍵の印を上書きする。最善努力(決して例外を投げない)。

    既定は現在時刻。value を与えるとその文字列を書く(版の印など。ADR-066)。
    値は状態行の文法(空白を含まない一語)に収まるものだけ書く。フックの本務を
    妨げない。置き場が無ければ作り、書けなければ黙って諦める。知らない鍵の
    行はそのまま残す(ADR-042 の寛容と同じ形)。
    """
    try:
        if value is not None:
            stamp = str(value).strip()
            if not stamp or any(c.isspace() for c in stamp):
                return
        else:
            if now is None:
                now = datetime.datetime.now(datetime.timezone.utc)
            stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        path = stamps_path(proj)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = []
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeError):
            lines = []
        out, seen = [], False
        for line in lines:
            m = _STATE_LINE_RE.match(line)
            if m and m.group(1) == key:
                out.append("%s: %s" % (key, stamp))
                seen = True
            else:
                out.append(line)
        if not seen:
            out.append("%s: %s" % (key, stamp))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, path)
    except Exception:
        pass


def read_stamp_values(proj=None):
    """印を {鍵: 生の文字列} で返す。無ければ空。決して例外を投げない。

    read_stamps(時刻に読めた鍵だけ)と分けるのは、版の印(ADR-066)のように
    時刻でない値を持つ鍵があるためである。
    """
    out = {}
    try:
        with open(stamps_path(proj), "r", encoding="utf-8-sig") as fh:
            for line in fh:
                m = _STATE_LINE_RE.match(line)
                if m:
                    out[m.group(1)] = m.group(2)
    except (OSError, UnicodeError):
        return {}
    return out


def _read_plugin_json(dirpath):
    """<dirpath>/.claude-plugin/plugin.json を dict で返す。読めなければ None。"""
    try:
        path = os.path.join(dirpath, ".claude-plugin", "plugin.json")
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _own_package_dir():
    """自分が属する包みのディレクトリ(scripts/ の一つ上)。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def plugin_version():
    """自分が属する包みの版(plugin.json の version)。読めなければ None。

    実行中のコードの版であって、導入済みの何かの版ではない。フックはこの
    ファイルと同じ包みから起動されるので、これが「今走っているコードの版」に
    なる(ADR-066)。
    """
    data = _read_plugin_json(_own_package_dir())
    ver = data.get("version") if data else None
    if isinstance(ver, str) and ver.strip():
        return ver.strip()
    return None


def version_drift(raw_stamps, current=None):
    """版の食い違い(ADR-066)。無ければ None、あれば説明の文字列。

    セッション冒頭に注入が刻んだ版(hook_inject_version)と、今の自分の版を
    比べる。どちらかが読めなければ判じない(古い版からの更新直後は印が無い —
    前方寛容)。配線と契約はセッション開始時に固定される(DECIDED-001 事実8)
    ため、食い違いは「新しいセッションを開始する」が唯一の解になる。
    """
    if not isinstance(raw_stamps, dict):
        return None
    started = raw_stamps.get("hook_inject_version")
    if current is None:
        current = plugin_version()
    if (not isinstance(started, str) or not started.strip()
            or not isinstance(current, str) or not current.strip()):
        return None
    if started.strip() == current.strip():
        return None
    return ("プラグインの版がセッションの途中で切り替わった(開始時 %s → 今 %s)。"
            "配線と契約はセッション開始時に固定されるため、古いまま動いている。"
            "新しいセッションを開始する(ADR-066)"
            % (started.strip(), current.strip()))


def version_lag(proj=None, current=None):
    """導入済みの複製の遅れ(ADR-070)。無ければ None、あれば説明の文字列。

    実行中の包みの版と、プロジェクト自身のマーケットプレイスのマニフェスト
    (.claude-plugin/marketplace.json)が同名のプラグインに宣言する版を比べる。
    正本の版は、項目の source が指す先の plugin.json を優先し、読めなければ
    項目の version に退避する。どれかが読めなければ判じない(前方寛容)。
    マニフェストを持たない通常の導入先では None — この照合は、統治対象の
    リポジトリ自身がマーケットプレイスの正本である自己適用のときだけ成立する。
    版の大小は仮定しない。不一致だけを判じ、向きは言わない(version_drift と
    同じ規則)。
    """
    try:
        if proj is None:
            proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        own = _read_plugin_json(_own_package_dir())
        name = own.get("name") if own else None
        if current is None:
            current = plugin_version()
        if (not isinstance(name, str) or not name.strip()
                or not isinstance(current, str) or not current.strip()):
            return None
        mpath = os.path.join(proj, ".claude-plugin", "marketplace.json")
        with open(mpath, "r", encoding="utf-8-sig") as fh:
            manifest = json.load(fh)
        if not isinstance(manifest, dict):
            return None
        entries = manifest.get("plugins")
        entry = None
        if isinstance(entries, list):
            for cand in entries:
                if isinstance(cand, dict) and cand.get("name") == name.strip():
                    entry = cand
                    break
        if entry is None:
            return None
        canonical = None
        src = entry.get("source")
        if isinstance(src, str) and src.strip():
            meta = _read_plugin_json(
                os.path.normpath(os.path.join(proj, src.strip())))
            v = meta.get("version") if meta else None
            if isinstance(v, str) and v.strip():
                canonical = v.strip()
        if canonical is None:
            v = entry.get("version")
            if isinstance(v, str) and v.strip():
                canonical = v.strip()
        if canonical is None or canonical == current.strip():
            return None
        mkt = manifest.get("name")
        target = ("%s@%s" % (name.strip(), mkt.strip())
                  if isinstance(mkt, str) and mkt.strip() else name.strip())
        return ("実行中のプラグインの版(%s)が、このリポジトリが正本として宣言"
                "する版(%s)と食い違う。導入済みの複製が遅れている。"
                "「claude plugin update %s」で更新し、新しいセッションを"
                "開始する(ADR-070)" % (current.strip(), canonical, target))
    except Exception:
        return None


def read_stamps(proj=None):
    """印を {鍵: datetime} で返す。無ければ空。決して例外を投げない。"""
    out = {}
    try:
        with open(stamps_path(proj), "r", encoding="utf-8-sig") as fh:
            for line in fh:
                m = _STATE_LINE_RE.match(line)
                if not m:
                    continue
                ts = _parse_ts(m.group(2))
                if ts is not None:
                    out[m.group(1)] = ts
    except (OSError, UnicodeError):
        return {}
    return out


def liveness_gap(stamps, skew_seconds=GUARD_LINTER_SKEW_SECONDS):
    """拒否経路の欠落の疑い(ADR-062)。疑いが無ければ None、あれば説明の文字列。

    規則: リンタ(PostToolUse)の印があるのに、ガード(PreToolUse)の印が無い、
    またはリンタよりガードが skew_seconds 超古い。両者は全段階の配線で同じ
    編集の出来事に対で結ばれ、同じ包みで配られる(版が揃う)ので、この食い
    違いは古い版の名残ではなく配線の欠落を意味する。リンタの印が無ければ
    判じない(信号が無いだけで、欠落が無いことの証明ではない — 前方寛容)。
    """
    if not isinstance(stamps, dict):
        return None
    linter = stamps.get("hook_docs_linter")
    if linter is None:
        return None
    guard = stamps.get("hook_policy_guard_pre")
    if guard is None:
        return ("リンタ(PostToolUse)は発火しているのに、ガード(PreToolUse)の"
                "印が無い。拒否経路の配線が欠けている疑い。hooks の設定を"
                "確かめる(ADR-062)")
    if (linter - guard).total_seconds() > skew_seconds:
        return ("リンタの印(%s)よりガードの印(%s)が古い。編集がガードを"
                "通っていない疑い。hooks の設定を確かめる(ADR-062)"
                % (linter.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   guard.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return None


# ---------------------------------------------------------------------------
# エラージャーナル(ADR-074)。書式の正本は SPEC-021。
# ---------------------------------------------------------------------------

ERRORS_NAME = "doctrine-errors.jsonl"
_ERRORS_CAP = 20


def errors_path(proj=None):
    """エラージャーナルの置き場(git の追跡外。発火の印と同じ .claude/.cache)。"""
    if not proj:
        proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(proj, ".claude", ".cache", ERRORS_NAME)


def _error_location(exc):
    """例外の plugin 内の発生位置を「<ファイル名>:<行>」で返す。無ければ ""。

    許可制(ADR-074): 例外の自由文(str(exc))は写さない。OSError 等の例外文には
    統治対象のパスが混入するためで、ここで捨てることが構造的な安全の要である。
    位置は plugin のスクリプト配下のフレームだけから採る(基底名のみ)。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    best = ""
    try:
        tb = getattr(exc, "__traceback__", None)
        while tb is not None:
            frame_file = tb.tb_frame.f_code.co_filename
            try:
                if os.path.dirname(os.path.abspath(frame_file)) == here:
                    best = "%s:%d" % (os.path.basename(frame_file), tb.tb_lineno)
            except (OSError, ValueError):
                pass
            tb = tb.tb_next
    except Exception:
        return best
    return best


def record_error(component, exc, proj=None, now=None):
    """実行時例外の要約をジャーナルへ最善努力で追記する(ADR-074)。

    記録するのは 部品名・例外の型・plugin 内の発生位置・版・時刻 だけ
    (許可制。例外の自由文は写さない)。上限を保ち、決して例外を投げない。
    フックの本務を妨げない。書けなければ黙って諦める。
    """
    try:
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        name = type(exc).__name__ if isinstance(exc, BaseException) else "Error"
        loc = _error_location(exc) if isinstance(exc, BaseException) else ""
        entry = {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": str(component)[:40],
            "error": ("%s at %s" % (name, loc)) if loc else name,
            "version": plugin_version() or "?",
        }
        path = errors_path(proj)
        entries = read_errors(proj)
        entries.append(entry)
        entries = entries[-_ERRORS_CAP:]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_errors(proj=None):
    """ジャーナルの項目を古い順の list で返す。無ければ空。決して例外を投げない。"""
    out = []
    try:
        with open(errors_path(proj), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except (OSError, UnicodeError):
        return out
    except Exception:
        return out
    return out[-_ERRORS_CAP:]
