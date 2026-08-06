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

# 規範抽出（冊子 → 検証原則カタログ）の応答。source_quote は原文の連続断片で
# なければならず、抽出器がチャンク本文との照合で検める（出典なき候補は却下）。
PRINCIPLE_CATEGORIES = [
    "検証計画", "独立性", "証拠と記録", "試験設計", "レビューと監査",
    "構成管理と変更管理", "不適合と是正", "供給者と再利用", "安全性と危険要因",
    "運用と保守", "組織と力量", "文書化", "その他",
]

PRINCIPLES_SCHEMA = {
    "type": "object",
    "properties": {
        "principles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "statement": {"type": "string"},
                    "source_quote": {"type": "string"},
                    "source_lines": {"type": "string"},
                    "category": {"enum": PRINCIPLE_CATEGORIES},
                    "applicability": {"type": "string"},
                    "suggested_oracle": {"type": "string"},
                    "dedupe_key": {"type": "string"},
                },
                "required": ["title", "statement", "source_quote",
                             "source_lines", "category", "applicability",
                             "suggested_oracle", "dedupe_key"],
                "additionalProperties": False,
            },
        },
        "chunk_note": {"type": "string"},
    },
    "required": ["principles"],
    "additionalProperties": False,
}

# CAST_ANALYSIS の成果物。事象そのものではなく「統制のどこが欠けていたか」を書く。
# 統制欠陥は統制構造の要素 id を必ず指し、規範の出典（CAST カタログの dedupe_key）を
# 必ず持つ。どちらも機械照合できるので、出典なき断定は却下できる。
CONTROL_FLAW_TYPES = [
    "制御動作が無い", "制御動作が遅い", "制御動作が誤っている",
    "手掛かりが無い", "手掛かりが誤っている", "手掛かりが遅い",
    "統制の対象範囲が想定と食い違う", "統制どうしの調整の欠如",
    "統制自身の劣化を検出できない",
]

CAST_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "incident_id": {"type": "string"},
        "loss": {"type": "string"},
        "hazard": {"type": "string"},
        "control_flaws": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "control_element_id": {"type": "string"},
                    "flaw_type": {"enum": CONTROL_FLAW_TYPES},
                    "description": {"type": "string"},
                    "why_it_seemed_adequate": {"type": "string"},
                    "normative_refs": {
                        "type": "array", "items": {"type": "string"}, "minItems": 1},
                    "evidence_ref": {"type": "string"},
                },
                "required": ["control_element_id", "flaw_type", "description",
                             "why_it_seemed_adequate", "normative_refs"],
                "additionalProperties": False,
            },
        },
        "why_existing_assurance_missed": {"type": "string"},
        "systemic_factors": {"type": "array", "items": {"type": "string"}},
        "leading_indicators": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string"},
                    "observable": {"type": "string"},
                    "where": {"type": "string"},
                    "threshold": {"type": "string"},
                    "version_independent": {"type": "boolean"},
                    "why_version_independent": {"type": "string"},
                },
                "required": ["indicator", "observable", "where", "threshold",
                             "version_independent"],
                "additionalProperties": False,
            },
        },
        "new_scenario_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis": {"type": "string"},
                    "oracle": {"type": "string"},
                    "falsification_signal": {"type": "string"},
                    "severity": {"enum": ["P0", "P1", "P2", "P3"]},
                },
                "required": ["hypothesis", "oracle", "falsification_signal",
                             "severity"],
                "additionalProperties": False,
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "kind": {"enum": ["機構の変更", "監視の追加", "文書化",
                                      "所有者判断", "調査の継続"]},
                    "owner_decision_required": {"type": "boolean"},
                },
                "required": ["action", "kind", "owner_decision_required"],
                "additionalProperties": False,
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"enum": ["high", "medium", "low"]},
    },
    "required": ["incident_id", "loss", "hazard", "control_flaws",
                 "why_existing_assurance_missed", "leading_indicators",
                 "unknowns", "confidence"],
    "additionalProperties": False,
}

# 規範網羅の分類（campaign「規範網羅」の五値）。
COVERAGE_DISPOSITIONS = [
    "実装・試験・証拠あり", "対応計画あり", "非該当で理由あり",
    "UNKNOWN", "UNASSESSED",
]

# MAP_COVERAGE の成果物。原則ごとに五値のどれかへ割り当てる。
# 「実装・試験・証拠あり」は証拠ポインタが索引で解決したときだけ通る
# （通らなければ prompts.verify_coverage_assignments が UNKNOWN へ落とす）。
COVERAGE_ASSIGNMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "assignments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "disposition": {"enum": COVERAGE_DISPOSITIONS},
                    "reason": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "gap": {"type": "string"},
                    "recheck_trigger": {"type": "string"},
                    "confidence": {"enum": ["high", "medium", "low"]},
                },
                "required": ["key", "disposition", "reason",
                             "recheck_trigger", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assignments"],
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


# DISCOVER の成果物。scenario の器（構造化応答は object を要るので配列を包む）。
SCENARIOS_SCHEMA = {
    "type": "object",
    "properties": {
        "scenarios": {"type": "array", "minItems": 1, "items": SCENARIO_SCHEMA},
        "note": {"type": "string"},
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}

# CHALLENGE の成果物。候補ごとに一つの判定を返す（どれに対する判定かを必ず名乗る）。
CHALLENGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "scenario_id": {"type": "string"},
                    "verdict": {"enum": ["ACCEPT", "REJECT", "UNKNOWN"]},
                    "reasons": {"type": "array", "items": {"type": "string"},
                                "minItems": 1},
                    "duplicate_of": {"type": "string"},
                    "missing_oracle": {"type": "boolean"},
                    "normative_misreading": {"type": "boolean"},
                },
                "required": ["scenario_id", "verdict", "reasons"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

