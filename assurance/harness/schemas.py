#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""保証レーンの構造化データ定義と検証（標準ライブラリのみ）。

JSON Schema の全仕様は実装しない。このレーンが使う最小部分だけを
検証する（type / properties / required / enum / const / items /
additionalProperties）。未対応のキーワードは無視せず「検証できない」
ことを誤って緑にしないため、明示的に拒否する。
"""
import hashlib
import json

_SUPPORTED_KEYWORDS = {
    "type", "properties", "required", "enum", "const", "items",
    "additionalProperties", "description", "minItems",
}

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate(schema, obj, path="$"):
    """schema に対する obj の違反を文字列のリストで返す。空なら適合。

    決して例外を投げない方針は取らない。schema 自体が壊れている・
    未対応キーワードを含む場合は ValueError を投げる（検証器の沈黙は
    偽りの緑になるため）。
    """
    errors = []
    if not isinstance(schema, dict):
        raise ValueError("schema はオブジェクトでなければならない: %s" % path)
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise ValueError("未対応の schema キーワード %s (%s)" % (sorted(unknown), path))

    if "const" in schema:
        if obj != schema["const"]:
            errors.append("%s: const 不一致" % path)
        return errors
    if "enum" in schema:
        if obj not in schema["enum"]:
            errors.append("%s: enum 外の値 %r" % (path, obj))
        return errors

    typ = schema.get("type")
    if typ is not None:
        py = _TYPES.get(typ)
        if py is None:
            raise ValueError("未対応の type %r (%s)" % (typ, path))
        if typ in ("integer", "number") and isinstance(obj, bool):
            errors.append("%s: 型不一致 (bool は %s でない)" % (path, typ))
            return errors
        if not isinstance(obj, py):
            errors.append("%s: 型不一致 (期待 %s, 実際 %s)"
                          % (path, typ, type(obj).__name__))
            return errors

    if typ == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in obj:
                errors.append("%s: 必須キー %r が無い" % (path, key))
        if schema.get("additionalProperties") is False:
            for key in obj:
                if key not in props:
                    errors.append("%s: 想定外のキー %r" % (path, key))
        for key, sub in props.items():
            if key in obj:
                errors.extend(validate(sub, obj[key], "%s.%s" % (path, key)))

    if typ == "array":
        items = schema.get("items")
        if "minItems" in schema and len(obj) < schema["minItems"]:
            errors.append("%s: 要素数 %d は minItems %d 未満"
                          % (path, len(obj), schema["minItems"]))
        if items is not None:
            for i, elem in enumerate(obj):
                errors.extend(validate(items, elem, "%s[%d]" % (path, i)))

    return errors


def sha256_of(text):
    """プロンプト・schema の指紋。証拠記録の同一性確認に使う。"""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def smoke_schema(nonce):
    """煙試験の応答 schema。nonce の往復で「実応答」を確かめる。"""
    return {
        "type": "object",
        "properties": {
            "lane_echo": {"const": nonce},
            "self_check": {"enum": ["ok"]},
        },
        "required": ["lane_echo", "self_check"],
        "additionalProperties": False,
    }


# CHALLENGE / VERIFY の判定応答。AI の一致を客観的証拠とはしない。
# verdict は「この候補を実装へ渡してよいか」の判定であって真理値ではない。
VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"enum": ["ACCEPT", "REJECT", "UNKNOWN"]},
        "reasons": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "duplicate_of": {"type": "string"},
        "missing_oracle": {"type": "boolean"},
        "normative_misreading": {"type": "boolean"},
    },
    "required": ["verdict", "reasons"],
    "additionalProperties": False,
}

# FORMALIZE の成果物。campaign 定義のフィールドをそのまま持つ。
SCENARIO_SCHEMA = {
    "type": "object",
    "properties": {
        "scenario_id": {"type": "string"},
        "normative_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "claim_id": {"type": "string"},
        "system_boundary": {"type": "string"},
        "loss": {"type": "string"},
        "hazard": {"type": "string"},
        "unsafe_control_action": {"type": "string"},
        "preconditions": {"type": "array", "items": {"type": "string"}},
        "event_sequence": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "fault": {"type": "string"},
        "injection_point": {"type": "string"},
        "expected_safe_behavior": {"type": "string"},
        "oracle": {"type": "string"},
        "falsification_signal": {"type": "string"},
        "environments": {"type": "array", "items": {"type": "string"}},
        "versions": {"type": "array", "items": {"type": "string"}},
        "severity": {"enum": ["P0", "P1", "P2", "P3"]},
        "confidence": {"enum": ["high", "medium", "low"]},
        "duplicate_of": {"type": "string"},
        "residual_risk": {"type": "string"},
        "recheck_triggers": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "scenario_id", "normative_refs", "system_boundary", "loss", "hazard",
        "unsafe_control_action", "event_sequence", "fault", "injection_point",
        "expected_safe_behavior", "oracle", "falsification_signal",
        "severity", "confidence",
    ],
    "additionalProperties": True,
}
