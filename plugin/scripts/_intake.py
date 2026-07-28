#!/usr/bin/env python3
"""体系外 .md の分類の記録(.md-intake)の共有コア(ADR-021 / ADR-024)。

`docs-audit`(全件を見る)と `docs-linter`(一件を見る)は、同じファイルの
分類を必ず同じに読まねばならない。両者が別実装で読むと書式の解釈がずれ、
判定が食い違う(ADR-024 が直した欠陥クラス)。それを構造的に防ぐため、
記録の読み取りと照合はこの一つのコアに集約する。

記録の書式(ADR-021/ADR-073): 一行一項目 `パス: 非文書|投影|保留|ビュー [YYYY-MM-DD]`。
パスはプロジェクト根(統治木の親)からの相対、`/` 区切り。末尾 `/` は配下全体。
照合は完全一致をプレフィクスより優先する(ADR-073)。
刻印(ビューが記す参照時点。書式の正本は ICD-005 の view-stamp-format)の
解析もここに一本化する。読み手(リンタ・監査・リリースの門)が別実装で
読むと書式の解釈がずれるためである。
標準ライブラリのみ。決して例外を投げない。
"""
import os
import re

# doctrine:begin IMPL-018
LEDGER_NAME = ".md-intake"
_LINE_RE = re.compile(
    r"^(?P<path>[^:#][^:]*?)\s*[:：]\s*(?P<kind>非文書|投影|保留|ビュー)"
    r"(?:\s+(?P<due>\d{4}-\d{2}-\d{2}))?\s*$")
# 刻印の一行(ADR-073)。HTML コメントの内外どちらも受ける。
_STAMP_RE = re.compile(r"doctrine:view\s+(?P<fields>[^>\r\n]*)")
_STAMP_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# doctrine:end IMPL-018


def load_ledger(docs_root):
    """docs_root/_system/.md-intake を読む。(entries, bad_lines) を返す。

    entries: list[(path, kind, due_or_None)]。パスはプロジェクト根からの
    相対(末尾 / は配下全体)。無ければ空。決して例外を投げない。
    """
    path = os.path.join(docs_root, "_system", LEDGER_NAME)
    entries = []
    bad = []
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeError):
        return entries, bad
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if line == "" or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m is None or (m.group("kind") == "保留" and not m.group("due")):
            bad.append((i, line))
            continue
        entries.append((m.group("path").strip().replace("\\", "/"),
                        m.group("kind"), m.group("due")))
    return entries, bad


def entry_for(relpath, entries):
    """relpath(プロジェクト根からの相対、/ 区切り)に効く記録の項目を返す。

    末尾 / の項目はプレフィクス一致、それ以外は完全一致。完全一致を
    プレフィクスより優先する(ADR-073。一括分類の配下から一件だけを
    別分類に取り出せる)。無ければ None。
    """
    for path, kind, due in entries:
        if not path.endswith("/") and relpath == path:
            return (path, kind, due)
    for path, kind, due in entries:
        if path.endswith("/") and relpath.startswith(path):
            return (path, kind, due)
    return None


def disposition_for(abspath, docs_root):
    """abspath の分類(非文書/投影/保留)を返す。記録に無ければ None。

    プロジェクト根(統治木 docs_root の親)からの相対で照合する。リンタが
    一件のファイルについて「登録済みの非文書か」を判じるための入口。
    """
    if not docs_root:
        return None
    proj = os.path.dirname(os.path.abspath(docs_root))
    if not proj:
        return None
    try:
        rel = os.path.relpath(os.path.abspath(abspath), proj).replace(os.sep, "/")
    except (ValueError, OSError):
        return None
    entries, _bad = load_ledger(docs_root)
    entry = entry_for(rel, entries)
    return entry[1] if entry else None


def parse_view_stamp(text):
    """本文から刻印(ADR-073)を探して解く。(stamp, error) を返す。

    stamp: {"src", "as_of", "date", "refs"} (無い欄は None、refs は list)。
    刻印の行が無ければ (None, None)。行はあるが必須欄(src・date)が欠ける、
    または date が YYYY-MM-DD でなければ (stamp, 理由)。最初の一行だけを見る。
    決して例外を投げない。
    """
    m = _STAMP_RE.search(text or "")
    if m is None:
        return None, None
    fields = {}
    for tok in m.group("fields").split():
        if "=" not in tok:
            continue
        key, _sep, val = tok.partition("=")
        fields[key.strip()] = val.strip()
    stamp = {
        "src": fields.get("src") or None,
        "as_of": fields.get("as-of") or None,
        "date": fields.get("date") or None,
        "refs": [r for r in (fields.get("refs") or "").split(",") if r],
    }
    if not stamp["src"] or not stamp["date"]:
        return stamp, "刻印に必須の欄(src・date)が欠けている"
    if not _STAMP_DATE_RE.match(stamp["date"]):
        return stamp, "刻印の date が YYYY-MM-DD でない: %s" % stamp["date"]
    return stamp, None
