#!/usr/bin/env python3
"""フック境界の入出力(importable core)。ADR-075。

Hook は統治の唯一の実行点である。ここで書き出しに失敗すると、拒否の JSON が
ハーネスへ届かない。Claude Code の約束は「exit 0 + JSON でだけ判定が読まれ、
それ以外の非ゼロ終了は非ブロッキングの誤り」なので、書き出しの失敗はそのまま
fail-open(拒否が消えて編集が通る)になる。実際に PYTHONIOENCODING が非 UTF-8 の
環境で、日本語の拒否理由が UnicodeEncodeError を起こし exit 1 で消えた。

保証限界:
- 予防: 標準出力を UTF-8 へ張り替え、書けなければ ASCII へ退避する。PreToolUse は
  最後に exit 2(stderr が拒否理由になる仕様)へ倒して拒否を守る。
- 検出: 書き出しの失敗そのものはエラージャーナル(_auditcache)へ落ちる。
- 委ねる: ハーネスが exit 2 を尊重するかは実行環境の仕様であり、ここでは測れない。

標準ライブラリのみ。決して例外を外へ出さない。
"""
import json
import sys

# 作業木にバイトコードを残さない(ADR-075)。フックは一回きりの短命な
# プロセスで、__pycache__ の利得はほぼ無い。一方、marketplace の source が
# ディレクトリのとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

# ハーネスが JSON を読むのは exit 0 のときだけ。exit 2 は「阻止する誤り」で
# stderr が理由になる(PreToolUse・UserPromptSubmit・Stop・PreCompact で有効)。
# doctrine:begin SPEC-019
EXIT_OK = 0
EXIT_BLOCK = 2


def harden_stdout():
    """三つの標準ストリームを UTF-8 へ張り替える。失敗しても黙って進む(最善努力)。

    PYTHONIOENCODING や locale が非 UTF-8 でも、日本語の理由を書け、日本語を含む
    payload を読めるようにする。入力側も要る: payload の tool_input には編集後の
    本文がそのまま載るため、非 ASCII の locale では stdin の読み取りが失敗し、
    payload が空 dict に化けてガードが判定を持たないまま allow へ倒れる。
    errors は入力を "replace"(読めない字は捨てても判定は続ける)、出力を
    "backslashreplace"(理由の字は落とさない)にする。
    """
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


def _dumps(obj):
    """JSON 文字列。ensure_ascii=False を先に試し、駄目なら ASCII へ退避。"""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps(obj, ensure_ascii=True, default=str)


def emit(obj, component=None):
    """応答を標準出力へ書く。書けたら True。

    符号化で失敗したら ASCII へ退避して書き直す。それでも書けなければ False を
    返し、呼び手が fail-closed の判断へ回れるようにする(黙って諦めない)。
    """
    for text in (_dumps(obj), json.dumps(obj, ensure_ascii=True, default=str)):
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
            return True
        except Exception:
            continue
    if component:
        _record(component, "stdout write failed")
    return False


def emit_or_block(obj, blocking, component=None, reason="doctrine guard: "
                  "cannot write decision to stdout; blocking to stay safe"):
    """応答を書く。書けず、かつ阻止できる事象なら exit 2 で倒す。終了コードを返す。

    blocking が真なのは PreToolUse のように exit 2 が阻止になる事象だけである。
    理由は ASCII だけで書く(符号化が壊れている前提の経路なので日本語は使わない)。
    """
    if emit(obj, component=component):
        return EXIT_OK
    if not blocking:
        return EXIT_OK          # 阻止できない事象で非ゼロを返しても雑音になるだけ。
    try:
        sys.stderr.write(reason + "\n")
    except Exception:
        pass
    return EXIT_BLOCK


def _record(component, message):
    try:
        import _auditcache
        _auditcache.record_error(component, message)
    except Exception:
        pass


def read_payload(limit=8 * 1024 * 1024):
    """stdin の JSON を dict で返す。読めなければ空 dict。決して例外を投げない。"""
    try:
        raw = sys.stdin.read(limit)
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}
# doctrine:end SPEC-019
