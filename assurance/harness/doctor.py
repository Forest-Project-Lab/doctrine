#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""保証レーンの前提診断（標準ライブラリのみ・どの python3 でも動く）。

レーンが使えないとき PASS ではなく UNASSESSED へ倒す（終了コード 3）。
資格情報は存在の有無だけを見る。内容は読まない・書かない。

終了コード: 0=PASS / 3=UNASSESSED / 1=内部エラー。
"""
import argparse
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
VENV_PYTHON = os.path.join(LANE_DIR, ".venv", "bin", "python")

REQUIRED = ("python", "venv_sdk", "auth_signal")


def _run(cmd, timeout=30):
    """subprocess の薄い包み。(returncode, stdout, stderr) を返し例外を投げない。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "not found: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 126, "", str(exc)


def assess(env, home, venv_python=VENV_PYTHON, run=_run,
           version_info=sys.version_info):
    """前提を検める。時計は読まない（記録時刻は main が押す）。

    返り値: {"status": "PASS"|"UNASSESSED", "checks": [...]}
    checks の status は ok / missing / info の三値。
    """
    checks = []

    ok = version_info >= (3, 10)
    checks.append({
        "name": "python",
        "status": "ok" if ok else "missing",
        "detail": "%d.%d.%d (SDK は 3.10 以上を要求)" % version_info[:3],
    })

    if not os.path.isfile(venv_python):
        checks.append({
            "name": "venv_sdk", "status": "missing",
            "detail": "venv が無い: %s（README の venv 構築を実行）" % venv_python,
        })
    else:
        code, out, err = run([
            venv_python, "-c",
            "import importlib.metadata as m;"
            "import claude_agent_sdk;"
            "print(m.version('claude-agent-sdk'))",
        ])
        if code == 0 and out:
            checks.append({"name": "venv_sdk", "status": "ok",
                           "detail": "claude-agent-sdk %s" % out})
        else:
            checks.append({"name": "venv_sdk", "status": "missing",
                           "detail": "SDK import 失敗: %s" % (err or out or code)})

    signals = []
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        signals.append("CLAUDE_CODE_OAUTH_TOKEN")
    if env.get("ANTHROPIC_API_KEY"):
        signals.append("ANTHROPIC_API_KEY")
    cred = os.path.join(home or "", ".claude", ".credentials.json")
    if home and os.path.isfile(cred):
        signals.append(".claude/.credentials.json")
    checks.append({
        "name": "auth_signal",
        "status": "ok" if signals else "missing",
        "detail": ("存在を確認: %s" % ", ".join(signals)) if signals
        else "認証の手掛かりが無い（token も鍵も資格情報ファイルも不在）",
    })

    code, out, err = run(["claude", "--version"], timeout=20)
    checks.append({
        "name": "claude_cli", "status": "info",
        "detail": out if code == 0 else
        "PATH に無い（SDK は自前のバイナリを同梱するため必須ではない）",
    })

    code, out, _err = run(["git", "-C", REPO_DIR, "rev-parse", "HEAD"], timeout=20)
    checks.append({"name": "git_sha", "status": "info",
                   "detail": out if code == 0 else "取得できない"})

    required_ok = all(
        c["status"] == "ok" for c in checks if c["name"] in REQUIRED)
    return {"status": "PASS" if required_ok else "UNASSESSED", "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="JSON だけを書く")
    args = parser.parse_args(argv)

    report = assess(env=os.environ, home=os.path.expanduser("~"))
    import datetime
    report["generated_at"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for c in report["checks"]:
            print("[%s] %s: %s" % (c["status"], c["name"], c["detail"]))
        print("status:", report["status"])
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
