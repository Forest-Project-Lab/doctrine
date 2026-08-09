#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""実 SDK の煙試験（venv の python で動かす）。

oracle: 隔離した一回限りのセッションが、こちらの与えた nonce（一回限りの
乱数値）をそのまま構造化応答で返すこと。nonce の往復により、記録が
実応答であって定型文・キャッシュ・模擬でないことを確かめる。

- 子セッションの cwd は「リポジトリの外の空の一時ディレクトリ」に置き、
  setting_sources=[] と併せて、本セッションの設定・Hook から隔離する。
- 証拠は assurance/ledger/smoke-latest.json（コミット対象）と
  assurance/ledger/runs/（コミットしない）へ書く。

終了コード: 0=PASS / 2=FAIL / 3=UNASSESSED / 4=UNKNOWN / 1=内部エラー。
"""
import argparse
import datetime
import json
import os
import secrets
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import ledger_io, schemas, sdk_lane  # noqa: E402

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)
LEDGER_DIR = os.path.join(LANE_DIR, "ledger")

_EXIT = {"PASS": 0, "FAIL": 2, "UNASSESSED": 3, "UNKNOWN": 4}


def _git(args):
    try:
        proc = subprocess.run(["git", "-C", REPO_DIR] + args,
                              capture_output=True, text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except OSError:
        return None


def _env_note():
    """環境の手掛かり。名前だけを記録し、値は決して書かない。"""
    names = sorted(k for k in os.environ
                   if k.startswith(("CLAUDE", "ANTHROPIC")))
    home = os.path.expanduser("~")
    return {
        "env_keys_present": names,
        "credentials_file_present": os.path.isfile(
            os.path.join(home, ".claude", ".credentials.json")),
    }


def build_prompt(nonce):
    return (
        "これは配管の煙試験である。推論も前置きも不要。"
        "次の JSON オブジェクトだけを返すこと: "
        '{"lane_echo": "%s", "self_check": "ok"}' % nonce
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=sdk_lane.DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--no-ledger", action="store_true",
                        help="台帳へ書かない（故障注入の実験用）")
    args = parser.parse_args(argv)

    nonce = secrets.token_hex(8)
    schema = schemas.smoke_schema(nonce)
    prompt = build_prompt(nonce)
    isolated_cwd = tempfile.mkdtemp(prefix="assurance-smoke-")

    record = sdk_lane.run_one_shot(
        prompt,
        schema=schema,
        model=args.model,
        cwd=isolated_cwd,
        allowed_tools=(),
        max_turns=1,
        timeout_s=args.timeout,
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    record.update({
        "doctrine:exempt": "保証レーンの証拠台帳。仕様との対応なし(ADR-114)",
        "kind": "smoke",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "isolated_cwd": isolated_cwd,
        "environment": _env_note(),
        "nonce_len": len(nonce),
    })

    if not args.no_ledger:
        os.makedirs(os.path.join(LEDGER_DIR, "runs"), exist_ok=True)
        latest = os.path.join(LEDGER_DIR, "smoke-latest.json")
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        for path in (latest,
                     os.path.join(LEDGER_DIR, "runs", "smoke-%s.json" % stamp)):
            ledger_io.write_json(path, record, sort_keys=True)

    print(json.dumps(
        {k: record.get(k) for k in
         ("status", "oracle", "errors", "sdk_version", "duration_ms",
          "result_meta", "git_sha")},
        ensure_ascii=False, indent=2))
    return _EXIT.get(record["status"], 1)


if __name__ == "__main__":
    sys.exit(main())
