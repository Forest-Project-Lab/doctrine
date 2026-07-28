#!/usr/bin/env python3
"""監査の体系外 .md 系検査(ADR-069 の移送先。挙動は docs-audit に在った頃と同一)。

docs ルートの外の .md を分類の記録(.md-intake)と突き合わせる(ADR-021)。
記録の読み取り・照合は共有コア _intake に一本化(ADR-024)。呼び手(docs-audit)が
所見の工場 make_finding と日付解析 parse_date を渡す(共有コアは入口を取り込ま
ない。ADR-068 の import 境界)。

標準ライブラリのみ。決定的(整列走査)。
"""
import os

import _frontmatter
import _intake
import _registry

_WARN, _ADVISORY = "warn", "advisory"

# 記録の読み取り・照合は共有コア _intake に一本化する(ADR-024)。リンタと
# 同じコードで読むことで、同じファイルへの分類が食い違うのを構造的に防ぐ。
# doctrine:begin SPEC-011
_INTAKE_LEDGER = _intake.LEDGER_NAME
_STRAY_SKIP_DIRS = ("node_modules", "__pycache__")
_STRAY_LIST_CAP = 50
# doctrine:end SPEC-011


def _load_intake_ledger(root):
    """共有コアに委ねる。(entries, bad_lines) を返す。"""
    return _intake.load_ledger(root)


def _ledger_entry_for(relpath, entries):
    """共有コアに委ねる。relpath に効く記録の項目、無ければ None。"""
    return _intake.entry_for(relpath, entries)


def collect(root, today, make_finding, parse_date):
    """11. 体系外 .md(ADR-021, R1/R8)。

    docs ルートの親(=プロジェクト根)から .md を走査し、次だけを挙げる。
    ①登録簿の型を持つ .md → warn(置き場所の誤り)
    ②分類の記録に無い .md → advisory(未分類。external-md-intake へ)
    ③期限を過ぎた「保留」 → warn(再浮上)
    ④実在しないパスを指す記録の項目 → advisory(掃除の合図)
    dot ディレクトリ・node_modules・__pycache__ と、監査対象の docs ルート
    自身は走査しない。決定的(整列走査)。一覧は上限で正直に切り詰める。
    """
    out = []
    docs_root = os.path.abspath(root)
    proj = os.path.dirname(docs_root)
    if not proj or proj == docs_root or not os.path.isdir(proj):
        return out
    entries, bad_lines = _load_intake_ledger(root)
    for lineno, line in bad_lines:
        out.append(make_finding(
            "stray_document", _ADVISORY, "", "_system/" + _INTAKE_LEDGER,
            "分類の記録の %d 行目が読めない(『パス: 非文書|投影|保留 日付』の形): %s"
            % (lineno, line[:80])))

    strays = []
    for dirpath, dirnames, filenames in os.walk(proj):
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d not in _STRAY_SKIP_DIRS
            and os.path.abspath(os.path.join(dirpath, d)) != docs_root)
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            abspath = os.path.join(dirpath, name)
            rel = os.path.relpath(abspath, proj).replace(os.sep, "/")
            strays.append((rel, abspath))
    strays.sort()

    seen_rel = set()
    listed = 0
    for rel, abspath in strays:
        seen_rel.add(rel)
        if rel in _registry.ROOT_POINTER_FILES:
            # 根の案内(CLAUDE.md/AGENTS.md)は仕様がプロジェクト根に置くと
            # 定める投影(§3.7/§5)。未分類として挙げない。
            continue
        try:
            fm, _body, _errs = _frontmatter.parse_file(abspath)
        except (OSError, UnicodeError):
            continue
        type_code = fm.get("type")
        typed = isinstance(type_code, str) and _registry.is_known_type(type_code)
        entry = _ledger_entry_for(rel, entries)
        if typed:
            out.append(make_finding(
                "stray_document", _WARN, _coerce_id(fm), rel,
                "登録簿の型 %s を持つ文書が docs/ の外に在る。doc-author で "
                "docs/<domain>/ の置き場所へ移すか、型を外す" % type_code))
            continue
        if entry is None:
            if listed < _STRAY_LIST_CAP:
                out.append(make_finding(
                    "stray_document", _ADVISORY, "", rel,
                    "統治木の外の .md が未分類。docs-curate(external-md-intake)"
                    "で三分類し %s/_system/%s へ記録する"
                    % (os.path.basename(docs_root), _INTAKE_LEDGER)))
                listed += 1
            continue
        _epath, kind, due = entry
        if kind == "保留" and due is not None and parse_date(due) is not None \
                and parse_date(due) < today:
            out.append(make_finding(
                "stray_document", _WARN, "", rel,
                "保留の期限(%s)を過ぎた。取り込むか、非文書と決めて記録を更新する"
                % due))
    if listed >= _STRAY_LIST_CAP:
        over = sum(1 for rel, _a in strays
                   if _ledger_entry_for(rel, entries) is None) - listed
        if over > 0:
            out.append(make_finding(
                "stray_document", _ADVISORY, "", "_system/" + _INTAKE_LEDGER,
                "未分類の一覧を %d 件で切り詰めた(残り %d 件。黙って隠さない)"
                % (_STRAY_LIST_CAP, over)))

    for path, kind, _due in entries:
        if path.endswith("/"):
            if not os.path.isdir(os.path.join(proj, path.rstrip("/"))):
                out.append(make_finding(
                    "stray_document", _ADVISORY, "",
                    "_system/" + _INTAKE_LEDGER,
                    "分類の記録が実在しない場所 %s を指している(記録を掃除する)"
                    % path))
        elif path not in seen_rel and not os.path.isfile(os.path.join(proj, path)):
            out.append(make_finding(
                "stray_document", _ADVISORY, "", "_system/" + _INTAKE_LEDGER,
                "分類の記録が実在しないファイル %s を指している(記録を掃除する)"
                % path))
    return out


def _coerce_id(fm):
    v = fm.get("id")
    return v if isinstance(v, str) else ""
