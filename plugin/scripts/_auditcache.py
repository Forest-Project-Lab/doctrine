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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter          # noqa: E402  日付の解釈の正本(ADR-099)

# doctrine:begin ADR-053
SCHEMA = "docs-audit/1"
STATE_NAME = ".governance-state"
# doctrine:end ADR-053
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
                    return (True, _frontmatter.parse_date(m.group(2)))
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
    return _frontmatter.parse_date(summary.get("today")) or _frontmatter.parse_date(
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

def project_dir(proj=None):
    """実行時の状態を書いてよいプロジェクト根。信じられなければ作業ディレクトリ。

    信じるのは**絶対パスで実在するディレクトリ**だけとする。相対の値は
    作業ディレクトリ次第で別の場所を指し、ガードとリンタの印が二つのファイルへ
    割れる —— すると鮮度の判定が「拒否経路の配線が欠けている」という偽の警報を
    出す。実測では、相対の値でリポジトリの作業木の中へ `sub/.claude/.cache/` が
    生成された（INC-032）。置き場は `${CLAUDE_PROJECT_DIR}/.claude/.cache` に
    限る（WATCH-001 第9項）。

    信じられない値は「与えられていない」と同じ既定（作業ディレクトリ）へ倒す。
    黙って広げない —— 与えられた値から勝手に場所を作らない、という意味である。
    """
    for candidate in (proj, os.environ.get("CLAUDE_PROJECT_DIR")):
        if not candidate or not isinstance(candidate, str):
            continue
        if not os.path.isabs(candidate):
            continue
        if not os.path.isdir(candidate):
            continue
        return candidate
    return os.getcwd()


def session_token():
    """ホストが与えるセッション識別子。取れなければ None（INC-001 推奨#0）。

    鍵の名はホストによって違うので、候補を順に見る。**取れないときに時刻で
    埋めない** —— 要約へ載せる値は「どのセッションが書いたか」の記録であって、
    埋めれば別のセッションと見分けが付かなくなる。負債の印（`write_due`）の
    ように必ず一意の token が要る場面では、呼ぶ側が自前の代替を足す。

    判定はここに一度だけ置く（`project_dir` と同じ原理。読み手ごとに答えを
    割らない。DECIDED-001 事実1）。
    """
    for key in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        value = os.environ.get(key) or ""
        if value:
            return value
    return None


DUE_NAME = "audit-due"

# 監査の負債の印。SessionEnd の口は 1 秒台で返さないとホストに打ち切られるが
# (INC-039 の実測: 遅延 1 秒は完了 3/3、2 秒は打ち切り 3/3)、全件監査の所要は
# 8〜9.5 秒である。そこで口では負債だけを置き、監査そのものは切り離した子が
# 走る。子が完走すれば印は消え、消えなければ次のセッションが負債を見る。
# 「走らなかったこと」が、要約の古さではなくファイルの実在として残るのが要点。


def due_dir(proj=None):
    """監査の負債の印の置き場。印と同じ .claude/.cache の下。"""
    return os.path.join(project_dir(proj), ".claude", ".cache", DUE_NAME)


def write_due(token, proj=None, now=None):
    """負債の印を置く。最善努力(決して例外を投げない)。返り値はパスか None。

    token はセッションの識別子。無ければ呼び出し側が時刻から作る。ファイル名に
    使うので、英数とハイフン以外は落とす(ファイル名による注入を作らない)。
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(token or ""))[:64]
    if not safe:
        return None
    try:
        d = due_dir(proj)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, safe + ".json")
        stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        # 一時名に pid を混ぜる(ADR-075)。write_stamp と同じ形。
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"token": safe, "queued_at": stamp},
                                ensure_ascii=False))
        os.replace(tmp, path)
        return path
    except OSError:
        return None


def clear_due(token, proj=None):
    """負債の印を消す。監査が完走したときだけ呼ぶ。真偽を返す。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(token or ""))[:64]
    if not safe:
        return False
    try:
        os.remove(os.path.join(due_dir(proj), safe + ".json"))
        return True
    except OSError:
        return False


def read_due(proj=None):
    """未消化の負債を [(token, queued_at)] で返す。古い順。読めない印は飛ばす。

    黙って空にしない —— 読めなかった印は queued_at を None として残し、
    「在るが読めない」を「無い」と取り違えないようにする。
    """
    out = []
    try:
        names = sorted(os.listdir(due_dir(proj)))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        token = name[:-5]
        queued = None
        try:
            with open(os.path.join(due_dir(proj), name), encoding="utf-8") as fh:
                queued = (json.load(fh) or {}).get("queued_at")
        except (OSError, ValueError):
            queued = None
        out.append((token, queued if isinstance(queued, str) else None))
    out.sort(key=lambda pair: (pair[1] or "", pair[0]))
    return out


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
    return os.path.join(project_dir(proj), ".claude", ".cache", STAMPS_NAME)


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
        # 一時名に pid を混ぜる(ADR-075)。固定名だと二つのフックが同時に
        # 書いたとき互いの一時ファイルを上書きし、片方の鍵が消える
        # (実測 60 回に 1 回)。docs-audit の要約書き出しは既に pid 付き。
        tmp = "%s.%d.tmp" % (path, os.getpid())
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
    前方寛容)。本プラグインの配線は plugin 層なのでセッション中は保持される
    (DECIDED-001 事実8。settings 由来の hooks は live reload されるが、こちらは
    別の層である。ADR-080)。契約の注入もセッション冒頭の一度きりなので、
    食い違いは「新しいセッションを開始する」が解になる。
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
            "本プラグインの配線と契約はセッション中は保持されるため、古いまま動いている。"
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
            proj = project_dir()
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


def audit_write_gap(stamps, summary, write_ok=None):
    """監査は走ったのに要約が更新されていない疑い(ADR-119)。無ければ None。

    規則: 監査の発火の印があり、かつ (a) 書き込みの印が失敗を告げている、
    または (b) 印が要約の日付より新しいとき、「走ったが書けていない」。
    **印が無ければ何も言わない** —— 不在は不実行の証明ではなく、段階や利用者の
    設定で SessionEnd の監査を持たない構成があるため(ADR-062 と同じ前方寛容)。

    この判定が要るのは、鮮度の警告だけでは『走らなかった』と『走ったが書けな
    かった』を区別できないからである(事象 INC-001 で 8 日ぶん区別できなかった)。
    """
    if not isinstance(stamps, dict):
        return None
    ran = stamps.get("hook_session_end_audit")
    if ran is None:
        return None
    if not isinstance(summary, dict):
        return None            # 要約が一度も無い状態は鮮度側の警告が扱う。
    if write_ok is False:
        return ("監査は走っているが、要約を書けていない(書き込みの印が失敗を"
                "告げている)。置き場(.claude/.cache)の権限と場所を確かめる"
                "(ADR-119)")
    audit_day = _frontmatter.parse_date(summary.get("today"))
    if audit_day is None:
        return None
    if ran.date() > audit_day:
        return ("監査は走っている(印 %s)のに、要約は %s のままである。"
                "要約の書き込みが失敗している疑い。置き場(.claude/.cache)の"
                "権限と場所を確かめる(ADR-119)"
                % (ran.strftime("%Y-%m-%dT%H:%M:%SZ"), audit_day.isoformat()))
    return None


def version_lag_advice(lag_message):
    """版の食い違いの告げ方に、転記の求め方を添える(ADR-122)。

    規範は運用側から供給側へのフィードバックを求める。送らない体系では、
    渡すかどうかを利用者が決められる形——転記——にしか橋を架けられない。
    そこで、食い違いを告げるときだけ求め方を添える（毎回は言わない）。
    """
    return ("%s。供給側へ伝えるなら『現地状態を出して』と言えば、貼り付けられる形で"
            "出す（版と生存の印だけ。統治対象の内容は入らない。**送信はしない**）"
            % lag_message.rstrip("。"))


def field_state_report(proj=None):
    """現地で何が動いているかを、貼り付けられる平文で返す(ADR-122)。

    規範(CAST)は運用側から供給側へのフィードバックを求めるが、本体系は通信しない
    (確定事実7)。そこで**送らずに転記できる形**で示す。この関数は文字列を返す
    だけで、どこへも送らない。

    載せるのは版と生存の印だけとする。統治対象の内容(文書の場所・本文・所見の
    中身)は載せない —— エラージャーナル(ADR-074)と同じ線引きである。読めない
    ものは「不明」と書き、推測で埋めない。決して例外を投げない。
    """
    if proj is None:
        proj = project_dir()

    def _or_unknown(value):
        return value if isinstance(value, str) and value.strip() else "不明"

    try:
        values = read_stamp_values(proj) or {}
    except Exception:
        values = {}
    try:
        running = plugin_version()
    except Exception:
        running = None
    try:
        lag = version_lag(proj)
    except Exception:
        lag = None

    lines = [
        "doctrine 現地状態(転記用。この出力は送信されない)",
        "- 実行中の版: %s" % _or_unknown(running),
        "- セッション冒頭に刻まれた版: %s"
        % _or_unknown(values.get("hook_inject_version")),
        "- 正本との食い違い: %s" % ("あり" if lag else "なし・判定不能"),
        "- 監査の走った印: %s"
        % _or_unknown(values.get("hook_session_end_audit")),
        "- 監査の要約を書けたか: %s"
        % _or_unknown(values.get("hook_session_end_write")),
        "- リンタの発火の印: %s" % _or_unknown(values.get("hook_docs_linter")),
        "- ガードの発火の印: %s"
        % _or_unknown(values.get("hook_policy_guard_pre")),
        "（統治対象の内容は含めない。渡すかどうかは利用者が決める）",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# エラージャーナル(ADR-074)。書式の正本は SPEC-021。
# ---------------------------------------------------------------------------

ERRORS_NAME = "doctrine-errors.jsonl"
_ERRORS_CAP = 20


def errors_path(proj=None):
    """エラージャーナルの置き場(git の追跡外。発火の印と同じ .claude/.cache)。"""
    if not proj:
        proj = project_dir()
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
