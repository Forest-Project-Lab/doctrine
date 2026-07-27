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

SCHEMA = "docs-audit/1"
STATE_NAME = ".governance-state"
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
