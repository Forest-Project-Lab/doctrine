#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""一回限り・隔離・読み取り専用の SDK 評価セッション（venv の python で動かす）。

方針（campaign / assurance/README.md）:
- `setting_sources=[]` を必ず明示する。省略時は user/project/local を読む
  （external-specs.md 第4項）。評価者に実装者の設定・Hook・会話を継がせない。
- 前提が欠けるときは UNASSESSED、走って oracle を満たさないときは FAIL、
  観測できないときは UNKNOWN。沈黙して緑にしない。
- 資格情報の内容・SDK の思考過程は記録しない。

この module 自体の import は SDK 不要（純粋関数は決定論試験の対象）。
SDK は run_one_shot の中で初めて import する。
"""
import asyncio
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import schemas  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5"

# 認証・接続の欠如を示す語。ProcessError の本文でしか区別できない場合の縮退。
_AUTH_MARKERS = ("authentication", "unauthorized", "login", "api key",
                 "credentials", "billing", "oauth")


def classify_error(exc_name, text):
    """例外を状態語彙へ写す。判らないときは UNKNOWN（緑へ倒さない）。"""
    lowered = (text or "").lower()
    if exc_name in ("CLINotFoundError", "CLIConnectionError"):
        return "UNASSESSED"
    if any(m in lowered for m in _AUTH_MARKERS):
        return "UNASSESSED"
    if exc_name in ("ProcessError", "CLIJSONDecodeError", "TimeoutError"):
        return "UNKNOWN"
    return "UNKNOWN"


def _supported_option_names():
    from claude_agent_sdk import ClaudeAgentOptions
    import dataclasses
    return {f.name for f in dataclasses.fields(ClaudeAgentOptions)}


def _summarize_usage(value, depth=0):
    """usage/cost の要約。深い入れ子・巨大値は落とす（台帳の肥大防止）。"""
    if depth > 2:
        return None
    if isinstance(value, dict):
        return {k: _summarize_usage(v, depth + 1)
                for k, v in list(value.items())[:20]}
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(type(value).__name__)


def run_one_shot(prompt, *, schema=None, model=DEFAULT_MODEL, cwd=None,
                 allowed_tools=(), max_turns=1, timeout_s=240,
                 system_prompt=None, env=None, execution_kind="real-sdk"):
    """一回限りの query() を実行し、証拠となる記録 dict を返す。

    記録は必ず status を持つ: PASS / FAIL / UNKNOWN / UNASSESSED。
    schema を渡すと構造化応答（output_format=json_schema）を要求し、
    受け取った structured_output をレーン側でも独立に再検証する
    （SDK 側の検証と同じ誤りを複製しないための二重化）。
    """
    started = time.time()
    record = {
        "execution_kind": execution_kind,
        "status": "UNKNOWN",
        "oracle": None,
        "errors": [],
        "prompt_sha256": schemas.sha256_of(prompt),
        "schema_sha256": schemas.sha256_of(schema) if schema else None,
        "options": {
            "model": model,
            "max_turns": max_turns,
            "allowed_tools": list(allowed_tools),
            "setting_sources": [],
            "cwd": str(cwd) if cwd else None,
            "timeout_s": timeout_s,
        },
        "sdk_version": None,
        "init": None,
        "result_meta": None,
        "structured_output": None,
        "result_text_head": None,
    }

    try:
        import importlib.metadata
        from claude_agent_sdk import ClaudeAgentOptions, query
        record["sdk_version"] = importlib.metadata.version("claude-agent-sdk")
    except Exception as exc:  # SDK 不在 = 前提欠如
        record["status"] = "UNASSESSED"
        record["errors"].append("sdk-import: %s" % exc)
        return record

    desired = {
        "setting_sources": [],
        "allowed_tools": list(allowed_tools),
        "max_turns": max_turns,
        "model": model,
        "cwd": str(cwd) if cwd else None,
        "system_prompt": system_prompt,
        "env": dict(env or {}),
    }
    if schema is not None:
        desired["output_format"] = {"type": "json_schema", "schema": schema}

    supported = _supported_option_names()
    unsupported = sorted(k for k in desired if k not in supported)
    if unsupported:
        # 外部仕様の前提が破れた。黙って落とさず未評価として可視化する。
        record["status"] = "UNASSESSED"
        record["errors"].append(
            "sdk-option-mismatch: %s は ClaudeAgentOptions に無い"
            "（external-specs.md の再確認 trigger）" % unsupported)
        return record

    options = ClaudeAgentOptions(
        **{k: v for k, v in desired.items() if v is not None or k == "cwd"})

    messages = []

    async def _consume():
        async for message in query(prompt=prompt, options=options):
            name = type(message).__name__
            if name == "SystemMessage":
                subtype = getattr(message, "subtype", None)
                if subtype == "init" and record["init"] is None:
                    data = getattr(message, "data", None) or {}
                    record["init"] = {
                        "model": data.get("model"),
                        "claude_code_version": data.get(
                            "claude_code_version") or data.get("version"),
                        "session_id": data.get("session_id"),
                        "tools_count": len(data.get("tools") or []),
                    }
            elif name == "ResultMessage":
                messages.append(message)

    try:
        asyncio.run(asyncio.wait_for(_consume(), timeout=timeout_s))
    except Exception as exc:
        name = type(exc).__name__
        if isinstance(exc, asyncio.TimeoutError):
            name = "TimeoutError"
        record["errors"].append("%s: %s" % (name, str(exc)[:500]))
        record["status"] = classify_error(name, str(exc))
        record["duration_ms"] = int((time.time() - started) * 1000)
        return record

    record["duration_ms"] = int((time.time() - started) * 1000)

    if not messages:
        record["status"] = "UNKNOWN"
        record["errors"].append("ResultMessage が来なかった")
        return record

    result = messages[-1]
    record["result_meta"] = {
        "subtype": getattr(result, "subtype", None),
        "num_turns": getattr(result, "num_turns", None),
        "duration_api_ms": getattr(result, "duration_api_ms", None),
        "total_cost_usd": getattr(result, "total_cost_usd", None),
        "session_id": getattr(result, "session_id", None),
        "is_error": getattr(result, "is_error", None),
        "usage": _summarize_usage(getattr(result, "usage", None)),
    }
    text = getattr(result, "result", None)
    if isinstance(text, str):
        record["result_text_head"] = text[:2000]
    record["structured_output"] = getattr(result, "structured_output", None)

    if getattr(result, "is_error", False):
        record["status"] = classify_error(
            "ResultError", str(record["result_text_head"]))
        record["errors"].append("result subtype=%s" % record["result_meta"]["subtype"])
        return record

    if schema is not None:
        out = record["structured_output"]
        if out is None:
            record["status"] = "FAIL"
            record["oracle"] = "structured_output が無い"
            return record
        violations = schemas.validate(schema, out)
        if violations:
            record["status"] = "FAIL"
            record["oracle"] = "レーン側再検証で違反: %s" % violations[:5]
            return record
        record["status"] = "PASS"
        record["oracle"] = "structured_output がレーン側再検証にも適合"
        return record

    record["status"] = "PASS" if record["result_text_head"] else "UNKNOWN"
    record["oracle"] = "自由文応答あり（schema なし実行）"
    return record
