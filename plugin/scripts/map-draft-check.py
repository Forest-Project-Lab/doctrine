#!/usr/bin/env python3
"""意味モデル下書きの出所検証(SPEC-029 / ADR-136)。system-map-draft 技能の機械の門。

対象は lens 側の検証用スキーマ system-map/gold-model/0.1 に従う JSON。起草した
下書きが確定(confirmed)へ昇格する前に、機械で確かめられることだけを確かめる:
出所(provenance)が実在するか、下書きが自分を確定と名乗っていないか、依存グラフの
辺を Flow に写していないか。

検査(所見の code):
- D1_NOT_PROPOSED: review_status を持つ実体は proposed に限る(下書きは自分を
  確定しない)。
- D2_SOURCE_UNRESOLVED: リポジトリ接頭付きパスの出所が --repo の作業木に実在
  するか。@rev 付きは git の履歴でも確かめる。locator の行番号・引用も、できる
  範囲で照合する。検証の道が無いもの(URL・会話など)は所見にせず「機械検証不能」
  の一覧に載せる。検証できないものを検証済みとは言わない。
- D3_BAD_DATE: checked_at / observed_at が実在する YYYY-MM-DD で、--today より
  未来でないこと(--today 無指定なら形だけ検める)。
- D4_ANCHOR_UNMATCHED: target_kind=code_range かつ authority=doctrine のアンカー
  の target が、追跡索引(trace-index/1)の返すいずれかの範囲の path を含むこと。
  source_revision の commit が --repo の履歴に実在すること。
- D5_FLOW_FROM_DEP_EDGE: Flow の出所が dep-graph / depends_on / impacts を名指し
  していれば所見(依存辺の Flow 化の早期信号)。
- D6_UNKNOWN_WITHOUT_NEGATIVE: verification_status=unknown の Contract は
  verdict=silent かつ checked_at 付きの負の出所を最低 1 件持つ。
- D7_SHAPE: 最上位の必須キーと語彙(列挙)の形。

M 層(lens 側 INVARIANTS.md)との分担: ここで早期に検めるのは M-07 の一部(D1)・
M-08(D5)・M-11(D6)だけである。M-02/03/04/05/06/09/12/15/16 は lens 側 validator
の受け持ちであり、この門は validator の置き換えではない。この門に固有の務めは
D2 —— 出所の実在(捏造出所ゼロの門)である。

保証限界:
- 予防: 何も予防しない。検収のときに人が叩く門であり、フックではない。
- 検出: 上記 D1〜D7。出所の意味の正しさ(引用が主旨を正しく写しているか)は検出
  できない。URL の中身は取得しない(ネットワークを使わない)。
- 委ねる: 意味の確認と確定への昇格は所有者に、モデル全体の不変条件は lens 側
  validator に委ねる。

終了コード: 0 所見なし / 1 所見あり / 2 使い方の誤り / 3 対象(モデル・リポジトリ
の根・--trace-json の実体)が無い。ICD-002 の 0/2/3 の規約に、所見あり=1
(docs-linter --batch と同じ)を加えた形。

標準ライブラリのみ。決定的(壁時計を読まない。日付の上限は --today で受け取る)。
"""
import json
import os
import re
import subprocess
import sys

# 作業木にバイトコードを残さない(ADR-075)。marketplace の source がディレクトリ
# のとき、ここに書いた物はそのまま利用者へ複製される。
sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _frontmatter          # noqa: E402  日付の解釈の正本(ADR-099・ADR-101)

# doctrine:begin SPEC-029
SCHEMA = "map-draft-check/1"
MODEL_SCHEMA = "system-map/gold-model/0.1"
USAGE = ("map-draft-check.py --model PATH --repo PATH [--docs-root PATH] "
         "[--repo-prefix NAME] [--today YYYY-MM-DD] [--trace-json PATH] "
         "[--json]")

# 語彙の正本は lens 側 gold-model の schema.json(0.1)。ここはその写しである(D7)。
ENUM_REVIEW_STATUS = ("proposed", "confirmed")
ENUM_VERDICT = ("present", "silent")
ENUM_TARGET_KIND = ("document", "code_range", "test", "external_doc",
                    "artifact")
ENUM_AUTHORITY = ("doctrine", "gold_model")
ENUM_VERIFICATION_STATUS = ("unknown", "claimed", "planned", "verified",
                            "failed", "stale", "not_applicable")

TOP_KEYS = ("schema", "target", "system", "elements", "flows", "contracts",
            "scenarios", "anchors")
ENTITY_LISTS = ("elements", "flows", "contracts", "scenarios", "anchors")

SOURCE_RE = re.compile(r"^([\w.-]+):\s*(.+?)(?:@([0-9a-f]{7,40}))?$")
PATHISH_RE = re.compile(r"^[\w./\-]+$")
LOC_LINE_RE = re.compile(r"L(\d+)|(\d+)行")
LOC_QUOTE_RE = re.compile(r"「([^」]+)」|『([^』]+)』")
DEP_EDGE_RE = re.compile(r"dep-graph|depends_on|impacts")
BLOB_URL_RE = re.compile(r"/blob/([0-9a-f]{7,40})/([^#?]+)")


class _Git(object):
    """--repo の git への読み取り専用の最小の問い。使えなければ黙って退く。"""

    def __init__(self, repo):
        self.repo = repo
        self._state = None      # True=使える / False=使えない / None=未確認
        self._shallow = False

    def _run(self, args):
        try:
            return subprocess.run(
                ["git", "-C", self.repo] + args,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None

    def available(self):
        if self._state is None:
            r = self._run(["rev-parse", "--is-inside-work-tree"])
            self._state = bool(r and r.returncode == 0
                               and r.stdout.strip() == b"true")
            if self._state:
                s = self._run(["rev-parse", "--is-shallow-repository"])
                self._shallow = bool(s and s.stdout.strip() == b"true")
        return self._state

    def shallow(self):
        self.available()
        return self._shallow

    def has_commit(self, rev):
        """rev(tag でも SHA でも)が commit として履歴に在るか。"""
        r = self._run(["cat-file", "-e", "%s^{commit}" % rev])
        return bool(r and r.returncode == 0)

    def has_object(self, rev, path):
        """rev の時点に path が在るか(git cat-file -e rev:path)。"""
        r = self._run(["cat-file", "-e", "%s:%s" % (rev, path)])
        return bool(r and r.returncode == 0)


def _f(findings, code, where, message):
    findings.append({"code": code, "where": where, "message": message})


def _u(unver, where, source, reason):
    unver.append({"where": where, "source": source, "reason": reason})


def _named(model, label):
    """一覧の実体を (位置ラベル, dict) で返す。dict でない要素は飛ばす。"""
    seq = model.get(label)
    if not isinstance(seq, list):
        return
    for i, item in enumerate(seq):
        if not isinstance(item, dict):
            continue
        name = item.get("id") if isinstance(item.get("id"), str) else ""
        yield "%s[%s]" % (label, name or i), item


def _entities(model):
    """review_status を担いうる実体(system と五つの一覧)を全て返す。"""
    system = model.get("system")
    if isinstance(system, dict):
        yield "system", system
    for label in ENTITY_LISTS:
        for where, item in _named(model, label):
            yield where, item


def _sources_of(where, entity):
    """実体の provenance の各 Source を (位置ラベル, dict) で返す。"""
    prov = entity.get("provenance")
    if not isinstance(prov, list):
        return
    for j, src in enumerate(prov):
        if isinstance(src, dict):
            yield "%s.provenance[%d]" % (where, j), src


def _iter_sources(model):
    for where, entity in _entities(model):
        for sw, src in _sources_of(where, entity):
            yield sw, src


# ---- D1 / D7: 形と自己確定 -------------------------------------------------

def check_d1(model, findings):
    """D1: 下書きは自分を確定しない。review_status は proposed に限る。"""
    for where, entity in _entities(model):
        if "review_status" not in entity:
            continue
        value = entity.get("review_status")
        if value != "proposed":
            _f(findings, "D1_NOT_PROPOSED", where,
               "review_status が %r。下書きの実体は proposed に限る"
               "(M-07 の早期検査)" % (value,))


def check_d7(model, findings):
    """D7: 最上位の形と語彙。語彙の正本は lens 側 gold-model の schema.json。"""
    for key in TOP_KEYS:
        if key not in model:
            _f(findings, "D7_SHAPE", "(top)", "必須キー %s が無い" % key)
    if "schema" in model and model.get("schema") != MODEL_SCHEMA:
        _f(findings, "D7_SHAPE", "(top)",
           "schema が %r(%s に限る)" % (model.get("schema"), MODEL_SCHEMA))
    for label in ENTITY_LISTS:
        if label in model and not isinstance(model.get(label), list):
            _f(findings, "D7_SHAPE", label, "一覧(配列)でない")
    for where, item in _named(model, "elements"):
        for key in ("id", "name", "kind"):
            if key not in item:
                _f(findings, "D7_SHAPE", where, "必須キー %s が無い" % key)
    for where, item in _named(model, "flows"):
        # 項の名は schema.json の宣言どおり from / to(source/destination ではない)
        for key in ("id", "from", "to"):
            if key not in item:
                _f(findings, "D7_SHAPE", where, "必須キー %s が無い" % key)
    _check_enums(model, findings)


def _check_enums(model, findings):
    """語彙(列挙)の当否。キーが在るときだけ検める。"""
    for where, entity in _entities(model):
        _enum(findings, where, "review_status", entity, ENUM_REVIEW_STATUS)
    for where, item in _named(model, "anchors"):
        _enum(findings, where, "target_kind", item, ENUM_TARGET_KIND)
        _enum(findings, where, "authority", item, ENUM_AUTHORITY)
    for where, item in _named(model, "contracts"):
        _enum(findings, where, "verification_status", item,
              ENUM_VERIFICATION_STATUS)
    for sw, src in _iter_sources(model):
        _enum(findings, sw, "verdict", src, ENUM_VERDICT)


def _enum(findings, where, key, entity, allowed):
    if key not in entity:
        return
    value = entity.get(key)
    if value not in allowed:
        _f(findings, "D7_SHAPE", where,
           "%s が %r(許す値: %s)" % (key, value, ", ".join(allowed)))


# ---- D2: 出所の実在(この門に固有の務め) ------------------------------------

def check_d2(model, opts, git, findings, unver):
    """D2: 出所の実在。検証の道が無いものは所見にせず一覧へ回す。"""
    n = 0
    for sw, src in _iter_sources(model):
        n += 1
        _check_one_source(sw, src, opts, git, findings, unver)
    return n


def _check_one_source(sw, src, opts, git, findings, unver):
    source = src.get("source")
    if not isinstance(source, str) or not source.strip():
        _f(findings, "D2_SOURCE_UNRESOLVED", sw, "source が空か文字列でない")
        return
    source = source.strip()
    if source.startswith("http://") or source.startswith("https://"):
        _check_url_source(sw, source, git, findings, unver)
        return
    m = SOURCE_RE.match(source)
    path = m.group(2).strip() if m else ""
    if not m or not PATHISH_RE.match(path):
        _u(unver, sw, source,
           "URL でもリポジトリ接頭付きパスでもない。機械検証の道が無い")
        return
    prefix, rev = m.group(1), m.group(3)
    if opts["repo_prefix"] and prefix != opts["repo_prefix"]:
        _u(unver, sw, source,
           "接頭 %s は --repo-prefix(%s)と異なり --repo の対象外"
           % (prefix, opts["repo_prefix"]))
        return
    abspath = os.path.join(opts["repo"], path)
    if not os.path.isfile(abspath):
        _f(findings, "D2_SOURCE_UNRESOLVED", sw,
           "出所のファイルが --repo の作業木に無い: %s" % path)
        return
    _check_locator(sw, src, abspath, findings)
    if rev:
        _check_rev(sw, source, path, rev, git, findings, unver)


def _check_locator(sw, src, abspath, findings):
    """locator のできる範囲の照合。行番号は行数以内、引用は本文に実在。"""
    locator = src.get("locator")
    if not isinstance(locator, str) or not locator:
        return
    try:
        with open(abspath, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return
    total = len(text.splitlines())
    for m in LOC_LINE_RE.finditer(locator):
        line = int(m.group(1) or m.group(2))
        if line < 1 or line > total:
            _f(findings, "D2_SOURCE_UNRESOLVED", sw,
               "locator の行 %d がファイルの行数(%d)を超える" % (line, total))
    if src.get("verdict") == "silent":
        return  # 負の出所の引用は「無いこと」の要約でありうる。実在を求めない
    for m in LOC_QUOTE_RE.finditer(locator):
        quote = m.group(1) or m.group(2)
        if quote and quote not in text:
            _f(findings, "D2_SOURCE_UNRESOLVED", sw,
               "locator の引用「%s」が本文に見つからない" % quote)


def _check_rev(sw, source, path, rev, git, findings, unver):
    """@rev の照合。git が無い・rev が履歴に無いときは検証不能(所見にしない)。"""
    if not git.available():
        _u(unver, sw, source, "git が使えず @%s を検証できない" % rev)
        return
    if not git.has_commit(rev):
        _u(unver, sw, source,
           ("浅い複製のため" if git.shallow() else "")
           + "履歴に %s が無く、検証できない" % rev)
        return
    if not git.has_object(rev, path):
        _f(findings, "D2_SOURCE_UNRESOLVED", sw,
           "%s の時点に %s が無い(git cat-file -e)" % (rev, path))


def _check_url_source(sw, source, git, findings, unver):
    """URL は取得しない。blob URL でローカル履歴が知る SHA だけ局所で検める。"""
    m = BLOB_URL_RE.search(source)
    if m and git.available() and git.has_commit(m.group(1)):
        if not git.has_object(m.group(1), m.group(2)):
            _f(findings, "D2_SOURCE_UNRESOLVED", sw,
               "blob URL の %s の時点に %s が無い"
               % (m.group(1)[:12], m.group(2)))
        return
    _u(unver, sw, source, "URL は取得しない。機械検証不能として列挙する")


# ---- D3: 日付 ---------------------------------------------------------------

def _iter_dates(model):
    for sw, src in _iter_sources(model):
        if "checked_at" in src:
            yield sw, "checked_at", src.get("checked_at")
    for where, item in _named(model, "anchors"):
        if "observed_at" in item:
            yield where, "observed_at", item.get("observed_at")
    for where, item in _named(model, "contracts"):
        ev = item.get("evidence")
        if not isinstance(ev, list):
            continue
        for k, e in enumerate(ev):
            if isinstance(e, dict) and "observed_at" in e:
                yield ("%s.evidence[%d]" % (where, k), "observed_at",
                       e.get("observed_at"))


def check_d3(model, today, findings):
    """D3: 日付の形(YYYY-MM-DD)と、--today を超えない(未来の確認日を許さない)。"""
    for where, key, value in _iter_dates(model):
        d = _frontmatter.parse_date(value)
        if d is None:
            _f(findings, "D3_BAD_DATE", where,
               "%s が %r(実在する YYYY-MM-DD に限る)" % (key, value))
        elif today is not None and d > today:
            _f(findings, "D3_BAD_DATE", where,
               "%s が %s で --today(%s)より未来" % (key, value, today))


# ---- D4: アンカーと追跡範囲 -------------------------------------------------

def _trace_ranges(opts):
    """追跡範囲を得る。--trace-json 優先、無ければ同じディレクトリの
    trace-index.py を子プロセスで実行する(入口は入口を取り込まない)。
    得られなければ (None, 理由) を返す。"""
    if opts["trace_json"]:
        try:
            with open(opts["trace_json"], "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            return None, "--trace-json が読めない(%r)" % (exc,)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        cmd = [sys.executable, os.path.join(here, "trace-index.py"),
               "--root", opts["repo"], "--format", "json"]
        if opts["docs_root"]:
            cmd += ["--docs-root", opts["docs_root"]]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, "trace-index を実行できない(%r)" % (exc,)
        if proc.returncode != 0:
            return None, "trace-index が %d で終わった" % proc.returncode
        try:
            payload = json.loads(proc.stdout.decode("utf-8"))
        except (ValueError, UnicodeError):
            return None, "trace-index の返す JSON が読めない"
    if payload.get("schema") != "trace-index/1":
        return None, "schema が trace-index/1 でない"
    ranges = payload.get("ranges")
    return (ranges if isinstance(ranges, list) else []), None


def check_d4(model, opts, git, findings, unver):
    """D4: doctrine 権威の code_range アンカーは追跡範囲と一致し、
    source_revision の commit が履歴に実在する。"""
    anchors = [(w, a) for w, a in _named(model, "anchors")
               if a.get("target_kind") == "code_range"
               and a.get("authority") == "doctrine"]
    if not anchors:
        return
    ranges, why = _trace_ranges(opts)
    paths = []
    if ranges is not None:
        paths = sorted({r.get("path") for r in ranges
                       if isinstance(r, dict) and r.get("path")})
    for where, anchor in anchors:
        target = anchor.get("target")
        target = target if isinstance(target, str) else ""
        if ranges is None:
            _u(unver, where, target, "追跡範囲が得られない: %s" % why)
        elif not any(p in target for p in paths):
            _f(findings, "D4_ANCHOR_UNMATCHED", where,
               "target が trace-index の返すどの範囲の path も含まない: %r"
               % target)
        rev = anchor.get("source_revision")
        if isinstance(rev, str) and rev:
            _check_anchor_rev(where, rev, git, findings, unver)


def _check_anchor_rev(where, rev, git, findings, unver):
    """source_revision(commit の実在)。git cat-file -e で問う。"""
    if not git.available():
        _u(unver, where, rev, "git が使えず source_revision を検証できない")
        return
    if git.has_commit(rev):
        return
    if git.shallow():
        _u(unver, where, rev, "浅い複製のため履歴に無く、検証できない")
        return
    _f(findings, "D4_ANCHOR_UNMATCHED", where,
       "source_revision %s が --repo の履歴に無い(git cat-file -e)" % rev)


# ---- D5 / D6 ----------------------------------------------------------------

def check_d5(model, findings):
    """D5: 依存グラフの辺を Flow の出所にしない(M-08 の早期信号)。"""
    for where, flow in _named(model, "flows"):
        for sw, src in _sources_of(where, flow):
            for key in ("source", "locator"):
                value = src.get(key)
                if isinstance(value, str) and DEP_EDGE_RE.search(value):
                    _f(findings, "D5_FLOW_FROM_DEP_EDGE", sw,
                       "%s が依存辺を名指ししている(%r)。文書辺の自動 Flow 化"
                       "は禁止(M-08)" % (key, value))


def check_d6(model, findings):
    """D6: unknown の Contract は負の出所(silent + checked_at)を最低 1 件持つ。"""
    for where, contract in _named(model, "contracts"):
        if contract.get("verification_status") != "unknown":
            continue
        ok = any(src.get("verdict") == "silent" and src.get("checked_at")
                 for _sw, src in _sources_of(where, contract))
        if not ok:
            _f(findings, "D6_UNKNOWN_WITHOUT_NEGATIVE", where,
               "verification_status=unknown だが verdict=silent かつ "
               "checked_at 付きの負の出所が無い(M-11 の早期検査)")


# ---- 報告と入口 -------------------------------------------------------------

def _totals(findings, unver, n_sources):
    by_code = {}
    for f in findings:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
    return {"findings": len(findings), "unverifiable": len(unver),
            "sources": n_sources, "by_code": by_code}


def _render_text(model_path, findings, unver, totals):
    out = ["# map-draft-check",
           "model: %s" % os.path.basename(model_path),
           "所見: %d 件 / 機械検証不能: %d 件 / 出所: %d 件"
           % (totals["findings"], totals["unverifiable"], totals["sources"])]
    for f in findings:
        out.append("  [%s] %s  %s" % (f["code"], f["where"], f["message"]))
    if not findings:
        out.append("  (所見は無い)")
    if unver:
        out.append("機械検証不能(検証済みとは言わない):")
        for u in unver:
            out.append("  - %s  %s  (%s)"
                       % (u["where"], u["source"], u["reason"]))
    return "\n".join(out)


def _parse_args(argv):
    """最小の引数解析。誤りがあれば (None, 理由) を返す。"""
    opts = {"model": None, "repo": None, "docs_root": None,
            "repo_prefix": None, "today": None, "trace_json": None,
            "json": False}
    flags = {"--model": "model", "--repo": "repo", "--docs-root": "docs_root",
             "--repo-prefix": "repo_prefix", "--today": "today",
             "--trace-json": "trace_json"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            opts["json"] = True
            i += 1
        elif a in flags and i + 1 < len(argv):
            opts[flags[a]] = argv[i + 1]
            i += 2
        else:
            return None, "不明な引数か値の欠落: %s" % a
    if not opts["model"] or not opts["repo"]:
        return None, "--model と --repo は必須"
    if opts["today"] is not None:
        today = _frontmatter.parse_date(opts["today"])
        if today is None:
            return None, "--today は実在する YYYY-MM-DD"
        opts["today"] = today
    return opts, None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    opts, err = _parse_args(argv)
    if opts is None:
        sys.stderr.write("usage error: %s\n%s\n" % (err, USAGE))
        return 2
    if not os.path.isfile(opts["model"]):
        sys.stderr.write("モデルが無い: %s\n" % opts["model"])
        return 3
    if not os.path.isdir(opts["repo"]):
        sys.stderr.write("リポジトリの根が無い: %s\n" % opts["repo"])
        return 3
    if opts["trace_json"] and not os.path.isfile(opts["trace_json"]):
        sys.stderr.write("--trace-json が無い: %s\n" % opts["trace_json"])
        return 3
    if not opts["docs_root"]:
        cand = os.path.join(opts["repo"], "doctrine_docs")
        if os.path.isdir(cand):
            opts["docs_root"] = cand
    findings, unver = [], []
    try:
        with open(opts["model"], "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeError) as exc:
        sys.stderr.write("モデルが読めない: %r\n" % (exc,))
        return 3
    model = None
    try:
        model = json.loads(text)
    except ValueError as exc:
        _f(findings, "D7_SHAPE", "(top)", "JSON として読めない(%s)" % exc)
    if model is not None and not isinstance(model, dict):
        _f(findings, "D7_SHAPE", "(top)", "最上位が JSON オブジェクトでない")
        model = None
    n_sources = 0
    if model is not None:
        git = _Git(opts["repo"])
        check_d7(model, findings)
        check_d1(model, findings)
        n_sources = check_d2(model, opts, git, findings, unver)
        check_d3(model, opts["today"], findings)
        check_d4(model, opts, git, findings, unver)
        check_d5(model, findings)
        check_d6(model, findings)
    totals = _totals(findings, unver, n_sources)
    if opts["json"]:
        payload = {"schema": SCHEMA, "model": os.path.basename(opts["model"]),
                   "findings": findings, "unverifiable": unver,
                   "totals": totals}
        sys.stdout.write(json.dumps(payload, ensure_ascii=False,
                                    sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(
            _render_text(opts["model"], findings, unver, totals) + "\n")
    return 1 if findings else 0
# doctrine:end SPEC-029


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 例外は握りつぶさず、告げて非零で終える
        sys.stderr.write("map-draft-check: internal error: %r\n" % (exc,))
        sys.exit(3)
