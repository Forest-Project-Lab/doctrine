#!/usr/bin/env python3
# doctrine:begin SPEC-015
"""docs-system-init の足場づくり。_system の最小配置とルートの案内だけを置く(非破壊)。

保証限界:
- 予防: 既存ファイルを一切壊さない。対象が既にあれば飛ばす。上書き・併合・切り詰めを
  しない(§4.1, §6 メタ「既存を壊さない」)。空の足場(ドメインのフォルダや各層、
  watchlist・context-map・icd-index・hooks・skills)を先に作らない(§3.7「空の足場を
  先に作らない」, R8)。
- 検出: 何も検出しない。配置の有無だけを報告する。
- 委ねる: ドメインのフォルダと各層の生成は doc-author に、投影の描画は
  render-projection に、ガード/リンタの実体は hooks.json と各スクリプトに委ねる。
  用語の強制は term-check/リンタに委ねる(ここは辞書を「置く」だけで強制しない)。

CLI:
  scaffold.py [--level {2,3,4}] [--root PATH] [--dry-run] [--fallback]
作る対象(これだけ。存在すれば飛ばす。原子的・冪等)。統治木は既定で
doctrine_docs/(ADR-022。既に docs/_system が在るなら docs/ を使い続ける):
  <統治木>/_system/glossary.md      GLOSSARY(§1 の承認語表+カルク表を種にする)
  <統治木>/_system/decided-facts.md DECIDED(review_by を created+90日で埋める)
  <統治木>/_system/non-goals.md     NONGOAL
  <統治木>/_system/overview.md      OVERVIEW(投影。種蒔き後に render-projection で導出)
  AGENTS.md / CLAUDE.md             ルートの案内(投影の入口。手で保守しない)
  <統治木>/_system/.docs-level      単一行 'level: N'(C9。能動 Level を公開)
overview はこの実行で新規に置いた場合だけ、種蒔きの直後に render-projection.py を
呼んで正本から導出した表で置き直す(投影の描画は render-projection に委ねる、の実行)。
これで初期化直後のコーパスが自分の監査(projection_drift)を素通しで通る。既存の
overview には決して触れない(非破壊)。導出に失敗しても足場は成立しているので 0 で
終わり、手動での render-projection 実行を促す一行を出す。
終了コード: 0 成功(全飛ばしも成功)。2 引数/入出力の誤り。

標準ライブラリのみ。pip も通信も使わない。決定的(実行日は --today で上書き可)。
"""
# doctrine:end SPEC-015
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _registry

# Templates ship alongside scripts/ under plugin/templates/. Resolve relative to
# this file so the script works from any cwd and under ${CLAUDE_PLUGIN_ROOT}.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_SCRIPTS_DIR)
TEMPLATES_DIR = os.path.join(_PLUGIN_ROOT, "templates")

# Default review_by horizon for the seeded DECIDED fact (documented placeholder
# for the owner to adjust; MASTER §5.8 / slice A.5). 90 days from created.
REVIEW_BY_HORIZON_DAYS = 90


# ---------------------------------------------------------------------------
# Date helpers — deterministic, overridable via --today for tests.
# ---------------------------------------------------------------------------
def _today_iso(today_opt):
    """Return ISO-8601 'YYYY-MM-DD' for the run date.

    Uses --today when supplied (deterministic tests); else datetime.date.today.
    """
    if today_opt:
        return today_opt
    import datetime
    return datetime.date.today().isoformat()


def _add_days_iso(iso_date, days):
    """Return iso_date + `days` as 'YYYY-MM-DD'. Falls back to the input on a
    malformed date (never raises; the seed stays usable)."""
    import datetime
    try:
        y, m, d = (int(x) for x in iso_date.split("-"))
        base = datetime.date(y, m, d)
        return (base + datetime.timedelta(days=days)).isoformat()
    except (ValueError, TypeError):
        return iso_date


# ---------------------------------------------------------------------------
# Template loading + placeholder fill.
# ---------------------------------------------------------------------------
def _read_template(name):
    """Read a template file from plugin/templates/. Raises OSError on I/O."""
    path = os.path.join(TEMPLATES_DIR, name)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _fill_common(text, created):
    """Fill run-date placeholders common to the seeded _system docs.

    Replaces the template's '<YYYY-MM-DD>' for created/updated with the run
    date. Other angle-bracket placeholders (owner, topic ids, subjects) are
    LEFT for the human owner to complete — scaffold seeds structure, not
    content (§3.7). Only the dated fields are concretized so the linter's
    required-key / date checks pass on a fresh tree.
    """
    return text.replace("<YYYY-MM-DD>", created)


def _glossary_seed(created):
    """Seed docs/_system/glossary.md from the GLOSSARY template (§1 tables).

    The template already carries a concrete id (GLOSSARY-001), the 承認語 table,
    the カルク table and the 一語訳 line — term-check reads this as the
    operational dictionary (no 二重定義). Only the dates are filled here.
    """
    return _fill_common(_read_template("glossary.md.tmpl"), created)


def _decided_seed(created):
    """Seed docs/_system/decided-facts.md from the DECIDED template.

    Concretizes id -> DECIDED-001 and fills review_by = created + 90 days so the
    linter's DECIDED-requires-review_by check passes on a fresh tree. The body's
    instructional angle-bracket placeholders stay for the owner.
    """
    text = _read_template("decided.md.tmpl")
    text = text.replace("DECIDED-<連番>", "DECIDED-001")
    text = _fill_common(text, created)
    review_by = _add_days_iso(created, REVIEW_BY_HORIZON_DAYS)
    # The template emits 'review_by: <YYYY-MM-DD>' but _fill_common already
    # turned every '<YYYY-MM-DD>' into `created`; re-point the frontmatter
    # review_by line (and the body echo) to created+90d.
    text = text.replace("review_by: %s" % created,
                        "review_by: %s" % review_by)
    return text


def _nongoal_seed(created):
    """Seed docs/_system/non-goals.md from the NONGOAL template."""
    text = _read_template("nongoal.md.tmpl")
    text = text.replace("NONGOAL-<連番>", "NONGOAL-001")
    return _fill_common(text, created)


def _overview_seed(created):
    """Seed docs/_system/overview.md from the OVERVIEW projection stub.

    Carries the 「描画される。手で編集しない。」 header; render-projection.py later
    overwrites the table region from the model. scaffold only lays the stub.
    """
    text = _read_template("overview.md.tmpl")
    text = text.replace("OVERVIEW-<連番>", "OVERVIEW-001")
    return _fill_common(text, created)


def _agents_pointer(created, tree=_registry.DOCS_DIR_NAMES[0]):
    """Root AGENTS.md — a minimal projection pointer (§5). Collects no knowledge."""
    return _root_pointer("AGENTS.md", tree)


def _claude_pointer(created, tree=_registry.DOCS_DIR_NAMES[0]):
    """Root CLAUDE.md — a minimal projection pointer (§5). Collects no knowledge."""
    return _root_pointer("CLAUDE.md", tree)


def _root_pointer(name, tree):
    """Render a root entry pointer (CLAUDE.md / AGENTS.md).

    These are 投影: the minimal entry, hand-maintained を避ける。They only point
    at the _system canonical docs; they hold no facts (§5).
    """
    return (
        "<!-- これは投影。最小の案内。手で保守しない。 -->\n"
        "# %s\n\n"
        "これは投影であり、最小の案内である。知識を集めない。入口だけを示す。\n\n"
        "- 用語辞書の正本: `%s/_system/glossary.md`\n"
        "- 現行文書の一覧(投影): `%s/_system/overview.md`\n"
        "- 確定した事実: `%s/_system/decided-facts.md`\n"
        "- やらないこと: `%s/_system/non-goals.md`\n"
    ) % (name, tree, tree, tree, tree)


def _docs_level_marker(level):
    """Render docs/_system/.docs-level (C9): a single line 'level: N'."""
    return "level: %d\n" % level


def _governance_state_seed(created):
    """Seed _system/.governance-state (#74)。定例レビューの実施記録を初期化する。

    種蒔きが無いと、導入直後から heartbeat が「doc-review 定例の実施記録が無い」を
    毎セッション促す(導入初日が催促から始まる)。作成日を last_cadence_review に
    置き、新品の木では定例を「済み」として扱う(空の木に見直す事実は無い)。以後は
    定例の周期でだけ促す。手で書くファイル(SPEC-021/ADR-034)。
    """
    return ("# 統治の運用状態(手で書く。定例を終えたら日付を更新する。SPEC-021/ADR-034)\n"
            "initialized: %s\n"
            "last_cadence_review: %s\n" % (created, created))


# ---------------------------------------------------------------------------
# Plan: the EXACT set of paths scaffold may write (relative to root).
# ---------------------------------------------------------------------------
def _choose_tree(root, fallback):
    """統治木のディレクトリ名を選ぶ(ADR-022。判定は登録簿に一本化)。

    既定は DOCS_DIR_NAMES[0](doctrine_docs)。ただし既に docs が統治木の印
    (_system)を持つなら docs を使い続ける(統治木を二つにしない)。印を
    持たない素の docs/ は他所の土地なので選ばない。
    """
    prefix = ".claude/" if fallback else ""
    legacy = os.path.join(root, prefix + "docs")
    if _registry.is_doctrine_tree(legacy, "docs"):
        return "docs"
    return _registry.DOCS_DIR_NAMES[0]


def _build_plan(level, created, fallback, tree=_registry.DOCS_DIR_NAMES[0]):
    """Return an ordered list of (relpath, content) for the minimal layout.

    With --fallback the _system docs + pointers move under '.claude/' (§5 /
    MASTER §9 plugin-not-installed mode). Without it they live at the repo root.
    The set is EXACTLY: 4 _system docs + .docs-level marker +
    .governance-state seed + 2 root pointers. NOTHING else (no domain folders,
    no watchlist/context-map/icd-index, no hooks, no skills — §3.7, A.2).
    `tree` is the governed root dir name (ADR-022: doctrine_docs, or docs for a
    pre-existing legacy tree).
    """
    prefix = ".claude/" if fallback else ""
    sysdir = prefix + tree + "/_system/"
    return [
        (sysdir + "glossary.md", _glossary_seed(created)),
        (sysdir + "decided-facts.md", _decided_seed(created)),
        (sysdir + "non-goals.md", _nongoal_seed(created)),
        (sysdir + "overview.md", _overview_seed(created)),
        (sysdir + ".docs-level", _docs_level_marker(level)),
        (sysdir + ".governance-state", _governance_state_seed(created)),
        (prefix + "AGENTS.md", _agents_pointer(created, tree)),
        (prefix + "CLAUDE.md", _claude_pointer(created, tree)),
    ]


# ---------------------------------------------------------------------------
# Atomic, non-destructive write.
# ---------------------------------------------------------------------------
def _atomic_write_new(abspath, content):
    """Write content to abspath atomically, ONLY if it does not already exist.

    Returns 'created' on write, 'skip' if the file pre-existed. Uses a temp file
    in the same directory + os.replace so an interrupted run never leaves a
    half-written seed. A pre-existing file is NEVER touched (既存を壊さない).
    The exists-check is best-effort; os.replace would still overwrite, so we
    re-check just before replacing to keep the non-destruction guarantee.
    """
    if os.path.exists(abspath):
        return "skip"
    parent = os.path.dirname(abspath) or "."
    os.makedirs(parent, exist_ok=True)
    # Final guard against a race: if it appeared meanwhile, do not clobber.
    if os.path.exists(abspath):
        return "skip"
    fd, tmp = _mkstemp_in(parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        # os.replace is atomic, but it WOULD overwrite. Re-check existence and
        # only replace when still absent, else discard the temp.
        if os.path.exists(abspath):
            os.remove(tmp)
            return "skip"
        os.replace(tmp, abspath)
        return "created"
    except BaseException:
        # Clean up the temp on any failure; never leave partial state.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def _mkstemp_in(directory):
    """Create a temp file in `directory`; return (fd, path). Stdlib tempfile."""
    import tempfile
    return tempfile.mkstemp(prefix=".scaffold-", suffix=".tmp", dir=directory)


# ---------------------------------------------------------------------------
# Argument parsing.
# ---------------------------------------------------------------------------
def _parse_args(argv):
    """Parse [--level N] [--root P] [--dry-run] [--fallback] [--today D].

    Returns (opts, error_message). --today is an undocumented test hook for a
    deterministic run date (mirrors docs-audit's overridable 'today').
    """
    opts = {
        "level": 2,
        "root": os.getcwd(),
        "dry_run": False,
        "fallback": False,
        "today": None,
    }
    i = 0
    n = len(argv)
    while i < n:
        a = argv[i]
        if a == "--level" or a.startswith("--level="):
            if "=" in a:
                val = a.split("=", 1)[1]
                i += 1
            else:
                if i + 1 >= n:
                    return None, "--level には 2|3|4 が必要"
                val = argv[i + 1]
                i += 2
            if val not in ("2", "3", "4"):
                return None, "--level は 2, 3, 4 のいずれか"
            opts["level"] = int(val)
            continue
        if a == "--root" or a.startswith("--root="):
            if "=" in a:
                opts["root"] = a.split("=", 1)[1]
                i += 1
            else:
                if i + 1 >= n:
                    return None, "--root にはパスが必要"
                opts["root"] = argv[i + 1]
                i += 2
            continue
        if a == "--today" or a.startswith("--today="):
            if "=" in a:
                opts["today"] = a.split("=", 1)[1]
                i += 1
            else:
                if i + 1 >= n:
                    return None, "--today には日付が必要"
                opts["today"] = argv[i + 1]
                i += 2
            continue
        if a == "--dry-run":
            opts["dry_run"] = True
            i += 1
            continue
        if a == "--fallback":
            opts["fallback"] = True
            i += 1
            continue
        return None, "不明な引数: %s" % a
    return opts, None


def _usage(msg):
    sys.stdout.write("usage error: %s\n" % msg)
    sys.stdout.write(
        "scaffold.py [--level {2,3,4}] [--root PATH] [--dry-run] [--fallback]\n"
    )
    return 2


# ---------------------------------------------------------------------------
# Overview derivation (delegated to render-projection; §3.9 投影は描画する).
# ---------------------------------------------------------------------------
def _derive_overview(root, fallback):
    """Re-render the just-seeded overview.md from the seeded canonical docs.

    Called ONLY when THIS run created overview.md, so overwriting it keeps the
    non-destruction guarantee (we replace our own stub, never a pre-existing
    file). Delegates to render-projection.py (the projection owner) in a
    subprocess; a failure leaves the stub in place and does not fail the
    scaffold (the layout itself succeeded).
    """
    import subprocess
    prefix = ".claude/" if fallback else ""
    tree = _choose_tree(root, fallback)
    docs_root = os.path.join(root, prefix + tree)
    out_path = os.path.join(docs_root, "_system", "overview.md")
    renderer = os.path.join(_SCRIPTS_DIR, "render-projection.py")
    try:
        proc = subprocess.run(
            [sys.executable, renderer, "overview",
             "--docs-root", docs_root, "--out", out_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=60, text=True)
        rc = proc.returncode
    except (OSError, subprocess.SubprocessError):
        rc = -1
    if rc != 0:
        sys.stdout.write(
            "scaffold: overview の導出に失敗(雛形のまま)。"
            "render-projection.py overview を手で実行すること。\n")
    else:
        sys.stdout.write("RENDER       %s\n"
                         % (prefix + tree + "/_system/overview.md"))


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
_GITIGNORE_LINES = (".claude/.cache/",)


def _reconcile_level(level_path, requested):
    """既存の .docs-level を要求 Level に合わせる(#90)。戻り値は報告文 or ""。

    印が無ければ何もしない(plan の作成が扱う)。読めて同じなら何もしない。異なれば
    要求 Level へ書き換え、UPGRADE/DOWNGRADE を報告する。--level は利用者の能動的な
    選択なので、既存印の更新は意図どおり(非破壊の対象外)。決して例外を投げない。
    """
    try:
        if not os.path.isfile(level_path):
            return ""
        with open(level_path, "r", encoding="utf-8-sig") as fh:
            cur = fh.read()
        m = re.search(r"level:\s*([2-4])", cur)
        cur_level = int(m.group(1)) if m else None
        if cur_level == requested:
            return ""
        tmp_dir = os.path.dirname(level_path) or "."
        fd, tmp = _mkstemp_in(tmp_dir)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(_docs_level_marker(requested))
        os.replace(tmp, level_path)
        verb = "UPGRADE" if (cur_level is None or requested > cur_level) else "DOWNGRADE"
        return ("%s Level %s → %d(.docs-level を更新)。Level 3 以上では初回の "
                "SessionEnd 監査から全件検査が効く。" % (verb, cur_level, requested))
    except OSError:
        return ""


def _ensure_gitignore(root):
    """root/.gitignore に監査キャッシュの行を非破壊で足す(#74)。戻り値は報告文 or ""。

    既に在れば何もしない。無ければ作る/追記する。SessionEnd 監査が
    .claude/.cache/last-audit.json を無断生成するため、追跡から外して未追跡ファイルの
    常駐を避ける。決して既存行を消さない。例外を投げない。
    """
    try:
        path = os.path.join(root, ".gitignore")
        existing = ""
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as fh:
                existing = fh.read()
        have = set(ln.strip() for ln in existing.splitlines())
        missing = [ln for ln in _GITIGNORE_LINES if ln not in have]
        if not missing:
            return ""
        add = ""
        if existing and not existing.endswith("\n"):
            add += "\n"
        if existing:
            add += "\n# doctrine: 監査キャッシュ(実行時状態。コミットしない)\n"
        else:
            add = "# doctrine: 監査キャッシュ(実行時状態。コミットしない)\n"
        add += "\n".join(missing) + "\n"
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write(add)
        return "GITIGNORE   .gitignore に %s を追記(監査キャッシュを追跡から除外)" % ", ".join(missing)
    except OSError:
        return ""


def main(argv=None):
    """Lay down the minimal _system layout non-destructively. Exit 0 on all-skip."""
    if argv is None:
        argv = sys.argv[1:]

    opts, err = _parse_args(list(argv))
    if err is not None:
        return _usage(err)

    try:
        created = _today_iso(opts["today"])
        tree = _choose_tree(opts["root"], opts["fallback"])
        plan = _build_plan(opts["level"], created, opts["fallback"], tree)
        root = opts["root"]

        if os.path.basename(os.path.normpath(root)) in ("docs", "doctrine_docs"):
            # --root は統治木ではなくプロジェクトの根を取る。統治木自体を渡すと
            # 入れ子の木が生まれる(初見の利用者が最も踏みやすい取り違え)。
            sys.stdout.write(
                "注意: --root にはプロジェクトの根を渡す(統治木のディレクトリ"
                "自体を渡すと入れ子の木が生まれる)。\n")

        if opts["dry_run"]:
            # Print the plan; write NOTHING (no dirs, no files). Exit 0.
            sys.stdout.write("dry-run: 次を配置する(既存は飛ばす)。書き込みはしない。\n")
            for relpath, _content in plan:
                abspath = os.path.join(root, relpath)
                state = "SKIP (exists)" if os.path.exists(abspath) else "CREATE"
                sys.stdout.write("  %-14s %s\n" % (state, relpath))
            # 後段(Level 昇格・.gitignore)の意図も dry-run で正直に見せる。
            level_rel = (".claude/" if opts["fallback"] else "") + tree + "/_system/.docs-level"
            lp = os.path.join(root, level_rel)
            if os.path.isfile(lp):
                try:
                    with open(lp, "r", encoding="utf-8-sig") as fh:
                        m = re.search(r"level:\s*([2-4])", fh.read())
                    if m and int(m.group(1)) != opts["level"]:
                        sys.stdout.write("  %-14s %s (level %s→%d)\n"
                                         % ("UPDATE", level_rel, m.group(1), opts["level"]))
                except OSError:
                    pass
            gi = os.path.join(root, ".gitignore")
            gi_have = set()
            if os.path.isfile(gi):
                try:
                    with open(gi, "r", encoding="utf-8-sig") as fh:
                        gi_have = set(ln.strip() for ln in fh.read().splitlines())
                except OSError:
                    pass
            if any(ln not in gi_have for ln in _GITIGNORE_LINES):
                sys.stdout.write("  %-14s .gitignore (監査キャッシュを追記)\n" % "APPEND")
            return 0

        created_n = 0
        skipped_n = 0
        overview_created = False
        for relpath, content in plan:
            abspath = os.path.join(root, relpath)
            result = _atomic_write_new(abspath, content)
            if result == "created":
                created_n += 1
                if relpath.endswith("overview.md"):
                    overview_created = True
                sys.stdout.write("CREATE       %s\n" % relpath)
            else:
                skipped_n += 1
                sys.stdout.write("SKIP (exists) %s\n" % relpath)
        if overview_created:
            _derive_overview(root, opts["fallback"])

        # #90 Level 昇格/降格: .docs-level は利用者が --level で能動的に選ぶ制御印で
        # あり、非破壊の対象(内容の種)とは別物。既存の印が --level と食い違うなら、
        # 明示の意図として更新する(SKIP だと「--level 3 と言ったのに変わらない」問題)。
        level_rel = (".claude/" if opts["fallback"] else "") + tree + "/_system/.docs-level"
        upgrade_msg = _reconcile_level(os.path.join(root, level_rel), opts["level"])
        if upgrade_msg:
            sys.stdout.write(upgrade_msg + "\n")

        # #74 .gitignore: 監査キャッシュ(実行時状態)を追跡から外す。非破壊の追記。
        gi_msg = _ensure_gitignore(root)
        if gi_msg:
            sys.stdout.write(gi_msg + "\n")

        sys.stdout.write("作成 %d, 飛ばし %d。\n" % (created_n, skipped_n))
        return 0
    except OSError as exc:
        # I/O failure (permissions, read-only fs). Report; exit 2. Never leaves
        # partial seed files (atomic write cleans its temp).
        sys.stdout.write("scaffold: 入出力エラー: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
