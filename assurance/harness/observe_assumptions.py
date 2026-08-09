#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""想定の観測器（決定論・SDK なし。ADR-144・ADR-126）。

登記簿 assurance/ledger/assumptions.json の各想定について、機械で測れる
先行指標を再測定し、`observation_history` へ**追記だけ**を行う。既存の欄
（leading_indicators の中の観測・verified_by）は決して書き換えない。

- 観測の日付は --today で必ず渡す（実時計を読まない。ADR-094 と同じ規律）。
- --dry-run は観測を印字するだけで登記簿へ書かない。
- `verified_by` はこの道具では**埋めない**。検証者の欄は、キャンペーンが別に
  走らせる独立の評価セッションの実施で埋める（書き込み口は set_verified_by。
  機械の観測は観測であって検証ではない —— 観測器自身の誤りは観測器では
  検められない）。

観測の対象（登記簿の四件と一対一）:
- ASM-001: last-audit.json の generated_at と mtime・hook-stamps の
  SessionEnd の印・要約より新しいセッションの印の連続数（閾値 N=2。
  INC-001 推奨#8）。
- ASM-002: 要約の checks_run 集合と現行 AUDIT_CHECKS の照合（import できる
  ときだけ。監査は走らせない）。
- ASM-003: 導入複製の gitCommitSha とリポジトリ HEAD・両者の版番号の照合。
- ASM-004: sdk_lane の認証判定が文言の部分一致に寄りかかったままかの静的点検。
"""
import argparse
import datetime
import glob
import importlib.util
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import ledger_io, sdk_lane  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
ASSUMPTIONS_PATH = os.path.join(LANE_DIR, "ledger", "assumptions.json")

OBSERVED_BY = "observe_assumptions.py (決定論)"

# 「要約より新しいセッションの印」が何個連続したら先行指標が立つか。
# INC-001 推奨#8 の N をここで決める（N=2。一つなら現行セッションで説明が
# つく —— ASM-001 の abnormal_when の文面そのまま）。観測の文にも必ず N を
# 書き出す（基準の無い観測は観測ではない）。
CONSECUTIVE_SESSIONS_THRESHOLD = 2

ASM_001 = "ASM-001-sessionend-always-fires"
ASM_002 = "ASM-002-audit-cache-has-a-single-writer"
ASM_003 = "ASM-003-version-string-identifies-the-copy"
ASM_004 = "ASM-004-sdk-error-surface-separates-fault-families"


def _project_dir():
    return os.environ.get("CLAUDE_PROJECT_DIR") or REPO_DIR


def _utc_iso(epoch_seconds):
    return datetime.datetime.fromtimestamp(
        epoch_seconds, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_hook_stamps(cache_dir):
    """hook-stamps の key: value を dict で返す。読めなければ空。"""
    out = {}
    path = os.path.join(cache_dir, "hook-stamps")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                out[key.strip()] = value.strip()
    except OSError:
        pass
    return out


def sessions_newer_than_audit(flags_dir, generated_at):
    """要約の generated_at より新しいセッションの印（edits-*）の名の列。

    印の時点はファイルの mtime（UTC）。generated_at が読めない形なら全部を
    「判らない」として空を返す（数え間違いより数えないほうが安全側）。
    """
    if not (isinstance(generated_at, str) and len(generated_at) >= 10):
        return []
    out = []
    try:
        names = sorted(os.listdir(flags_dir))
    except OSError:
        return []
    for name in names:
        if not name.startswith("edits-"):
            continue
        try:
            mtime = _utc_iso(os.stat(os.path.join(flags_dir, name)).st_mtime)
        except OSError:
            continue
        if mtime > generated_at.replace(" ", "T", 1):
            out.append(name)
    return out


def observe_asm_001(today, project_dir=None):
    """SessionEnd は必ず発火する、の観測（INC-001 推奨#2・#8）。

    control_structure が feedback と宣言する last-audit.json を、正本の側が
    実際に stat する経路がこれである（宣言と実装の乖離の解消。INC-001 推奨#2）。
    """
    cache = os.path.join(project_dir or _project_dir(), ".claude", ".cache")
    audit_path = os.path.join(cache, "last-audit.json")
    observed = []
    try:
        mtime = _utc_iso(os.stat(audit_path).st_mtime)
        with open(audit_path, encoding="utf-8") as f:
            generated_at = json.load(f).get("generated_at")
    except (OSError, ValueError) as exc:
        observed.append("last-audit.json が読めない（%s: %s）" % (audit_path, exc))
        return {"id": ASM_001, "date": today, "state": "UNKNOWN",
                "observed": observed}
    observed.append("last-audit.json: generated_at %s・mtime %s"
                    % (generated_at, mtime))

    stamps = _read_hook_stamps(cache)
    end_stamps = sorted(k for k in stamps if k.startswith("hook_session_end_"))
    if end_stamps:
        observed.append("hook-stamps の SessionEnd の印: %s"
                        % "・".join("%s=%s" % (k, stamps[k]) for k in end_stamps))
    else:
        observed.append("hook-stamps に hook_session_end_* の印は無い"
                        "（不在は不実行の証明ではない。ADR-119 の前方寛容）")

    newer = sessions_newer_than_audit(
        os.path.join(cache, "session-flags"), generated_at)
    n = CONSECUTIVE_SESSIONS_THRESHOLD
    observed.append(
        "要約より新しいセッションの印 %d 件（%s）。閾値 N=%d —— 連続 %d "
        "セッションにわたって監査の記録が無ければ先行指標が立つ（INC-001 "
        "推奨#8。一つなら現行セッションで説明がつく）"
        % (len(newer), "・".join(newer) or "無し", n, n))
    state = "FAIL" if len(newer) >= n else "PASS"
    return {"id": ASM_001, "date": today, "state": state, "observed": observed}


def _load_audit_checks(audit_script=None):
    """現行 docs-audit.py の AUDIT_CHECKS を、監査を走らせずに読む。

    import は最善努力とする —— 読めない環境では None（観測は UNKNOWN へ倒す。
    緑へも赤へも倒さない）。
    """
    path = audit_script or os.path.join(
        REPO_DIR, "plugin", "scripts", "docs-audit.py")
    if not os.path.isfile(path):
        return None
    scripts_dir = os.path.dirname(path)
    added = scripts_dir not in sys.path
    if added:
        sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "_observe_docs_audit", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        checks = getattr(module, "AUDIT_CHECKS", None)
        return set(checks) if checks else None
    except Exception:
        return None
    finally:
        if added:
            sys.path.remove(scripts_dir)


def observe_asm_002(today, project_dir=None, audit_script=None):
    """last-audit.json は監査以外が書かない、の観測（checks_run の集合照合）。

    弱い指標である —— 監査の書き手を成りすます者は集合も写せる（ASM-002 の
    観測の但し書きそのまま）。強い区別は信頼根を要し、体系は持たない
    （NONGOAL-001 第18項）。
    """
    audit_path = os.path.join(project_dir or _project_dir(),
                              ".claude", ".cache", "last-audit.json")
    observed = []
    try:
        with open(audit_path, encoding="utf-8") as f:
            recorded = json.load(f).get("checks_run")
    except (OSError, ValueError) as exc:
        observed.append("last-audit.json が読めない（%s）" % exc)
        return {"id": ASM_002, "date": today, "state": "UNKNOWN",
                "observed": observed}
    if not isinstance(recorded, list):
        observed.append("要約に checks_run が無い（旧世代の要約の疑い）")
        return {"id": ASM_002, "date": today, "state": "FAIL",
                "observed": observed}
    expected = _load_audit_checks(audit_script)
    if expected is None:
        observed.append("現行 AUDIT_CHECKS を import できない（最善努力の外。"
                        "監査は走らせない）")
        return {"id": ASM_002, "date": today, "state": "UNKNOWN",
                "observed": observed}
    got = set(recorded)
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    if not missing and not extra:
        observed.append("checks_run %d 件は現行 AUDIT_CHECKS %d 件と集合として"
                        "完全一致（差集合は両方向とも空）" % (len(got), len(expected)))
        state = "PASS"
    else:
        observed.append("checks_run が現行 AUDIT_CHECKS と食い違う"
                        "（要約に無い: %s ／ 要約だけに在る: %s）"
                        % (missing[:5] or "無し", extra[:5] or "無し"))
        state = "FAIL"
    return {"id": ASM_002, "date": today, "state": state, "observed": observed}


def _installed_plugin_rows(home):
    """installed_plugins.json から doctrine の導入複製の行を集める。"""
    rows = []
    pattern_root = os.path.join(home, ".claude", "plugins")
    candidates = [os.path.join(pattern_root, "installed_plugins.json")]
    candidates += sorted(glob.glob(
        os.path.join(pattern_root, "**", "installed_plugins.json"),
        recursive=True))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        plugins = data.get("plugins")
        if not isinstance(plugins, dict):
            continue
        for key, entries in plugins.items():
            if "doctrine" not in str(key):
                continue
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict):
                    rows.append(entry)
        if rows:
            return rows
    return rows


def _git_head(repo_dir):
    try:
        proc = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def observe_asm_003(today, home=None, repo_dir=None):
    """導入複製の同一性は版番号で判定できる、の観測（INC-019）。"""
    home = home or os.path.expanduser("~")
    repo = repo_dir or REPO_DIR
    observed = []
    rows = _installed_plugin_rows(home)
    if not rows:
        observed.append("installed_plugins.json が読めないか doctrine の行が無い"
                        "（%s/.claude/plugins）" % home)
        return {"id": ASM_003, "date": today, "state": "UNKNOWN",
                "observed": observed}
    copy = rows[0]
    copy_sha = copy.get("gitCommitSha")
    copy_version = copy.get("version")
    head = _git_head(repo)
    try:
        with open(os.path.join(repo, "plugin", ".claude-plugin",
                               "plugin.json"), encoding="utf-8") as f:
            repo_version = json.load(f).get("version")
    except (OSError, ValueError):
        repo_version = None
    observed.append("導入複製: gitCommitSha %s・version %s ／ リポジトリ: "
                    "HEAD %s・version %s"
                    % (copy_sha, copy_version, head, repo_version))
    if not copy_sha or not head:
        return {"id": ASM_003, "date": today, "state": "UNKNOWN",
                "observed": observed}
    if copy_sha == head:
        observed.append("複製とリポジトリは同一の commit を指す")
        return {"id": ASM_003, "date": today, "state": "PASS",
                "observed": observed}
    if copy_version and repo_version and copy_version == repo_version:
        observed.append("版番号が等しいまま commit が違う —— 版番号は複製の"
                        "同一性を判定していない（ASM-003 の abnormal_when "
                        "そのもの）")
        return {"id": ASM_003, "date": today, "state": "FAIL",
                "observed": observed}
    observed.append("commit は違うが版番号も違う（版が複製を区別できて"
                    "いるかは、この観測だけでは判じない）")
    return {"id": ASM_003, "date": today, "state": "UNKNOWN",
            "observed": observed}


def observe_asm_004(today):
    """SDK の例外表面は故障族を区別できる、の静的観測（INC-003）。

    見るのは sdk_lane の分岐の**種類**だけ —— 認証の判定が文言の部分一致
    （_AUTH_MARKERS）に寄りかかったままなら、想定は破れたまま（FAIL）。
    実行時の挙動は測らない（それは故障注入 mutations-*.json の仕事）。
    """
    observed = []
    if not callable(getattr(sdk_lane, "classify_error", None)):
        observed.append("sdk_lane.classify_error が見当たらない（構造が変わった。"
                        "観測器の側を見直すこと）")
        return {"id": ASM_004, "date": today, "state": "UNKNOWN",
                "observed": observed}
    markers = getattr(sdk_lane, "_AUTH_MARKERS", None)
    if isinstance(markers, tuple) and markers:
        observed.append("認証の判定は文言の部分一致のまま（_AUTH_MARKERS %d 語）。"
                        "それ以外の族は UNKNOWN へ落ちる —— 型に基づく分岐は"
                        "認証の族へ届いていない" % len(markers))
        state = "FAIL"
    else:
        observed.append("_AUTH_MARKERS が見当たらない（分岐の形が変わった。"
                        "族の区別が立ったかは実行時の故障注入で確かめること）")
        state = "UNKNOWN"
    return {"id": ASM_004, "date": today, "state": state, "observed": observed}


def observe_all(today, project_dir=None, home=None):
    """四件の想定の観測を、登記簿の並びと同じ順で返す。"""
    return [
        observe_asm_001(today, project_dir=project_dir),
        observe_asm_002(today, project_dir=project_dir),
        observe_asm_003(today, home=home),
        observe_asm_004(today),
    ]


def apply_observations(doc, observations, observed_by=OBSERVED_BY):
    """観測を登記簿の dict へ**追記だけ**で写す。

    各行の observation_history 末尾へ {date, state, observed, observed_by} を
    足す。既存のどの欄（leading_indicators・verified_by・observations）にも
    触れない。返り値は (追記した想定 id の列, 行が見つからなかった id の列)。
    """
    rows = {r.get("id"): r for r in doc.get("assumptions", [])
            if isinstance(r, dict)}
    applied, unmatched = [], []
    for obs in observations:
        row = rows.get(obs["id"])
        if row is None:
            unmatched.append(obs["id"])
            continue
        row.setdefault("observation_history", []).append({
            "date": obs["date"],
            "state": obs["state"],
            "observed": list(obs["observed"]),
            "observed_by": observed_by,
        })
        applied.append(obs["id"])
    return applied, unmatched


def set_verified_by(ledger, asm_id, text):
    """verified_by を埋める書き込み口（独立の評価セッションの実施が使う）。

    text は検証の主体と方式（誰が・何を・どう検めたか）を名指しする文で
    なければならない。空文は受け付けない —— 空の検証者は null と同義で、
    null は既に語彙にある（ADR-126）。ledger は読み込んだ登記簿の dict で、
    書き戻しは呼ぶ側が行う。
    """
    if not (text or "").strip():
        raise ValueError(
            "verified_by は検証の主体と方式を名指しする文であること"
            "（検証者が居ないなら null のまま置く）")
    for row in ledger.get("assumptions", []):
        if isinstance(row, dict) and row.get("id") == asm_id:
            row["verified_by"] = text
            return row
    raise KeyError("想定 %s が登記簿に無い" % asm_id)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="verified_by はこの道具では埋めない。検証者の欄は、キャンペーンが"
               "別に走らせる独立の評価セッションの実施で埋める"
               "（書き込み口は set_verified_by）。")
    parser.add_argument("--today", required=True,
                        help="観測の日付（必須。実時計を読まない）")
    parser.add_argument("--dry-run", action="store_true",
                        help="観測を印字するだけで登記簿へ書かない")
    parser.add_argument("--ledger", default=ASSUMPTIONS_PATH,
                        help="登記簿のパス（既定: assurance/ledger/assumptions.json）")
    args = parser.parse_args(argv)

    observations = observe_all(args.today)
    if args.dry_run:
        print(json.dumps({"dry_run": True, "observations": observations},
                         ensure_ascii=False, indent=2))
        return 0

    with open(args.ledger, encoding="utf-8") as f:
        doc = json.load(f)
    applied, unmatched = apply_observations(doc, observations)
    ledger_io.write_json(args.ledger, doc)
    print(json.dumps({
        "written": os.path.relpath(args.ledger, REPO_DIR),
        "applied": applied,
        "unmatched": unmatched,
        "states": {o["id"]: o["state"] for o in observations},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
