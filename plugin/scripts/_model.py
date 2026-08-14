#!/usr/bin/env python3
"""意味モデル(MODEL 型)の本文の解析と語彙の正本(ADR-163)。

保証限界:
- 予防: 器(lens 側 `system-map/gold-model/0.1`)が要する構造の規則を、ここに一度だけ
  定義する。リンタ(docs-linter)と描き手(render-projection)と門(map-draft-check)は、
  この部品を呼び、規則を二重定義しない(DECIDED-001 事実1)。
- 検出: 本文の塊が JSON として読めるか、実体ごとの必須欄が在るか、限られた語の値が
  語彙の中に在るか、id が文書の中で一意か、文書の中の参照が実在するか、
  文書の `status` と値の `review_status` が揃っているか(ADR-163 決定6)。
- 委ねる: **意味の正しさは検めない**。その要素が本当に在るか、その流れが実際に起きるかは
  見ない。出所の実在は map-draft-check が、確定の判断は人が持つ。M 層の不変条件
  (証跡の最小形・負の出所など)は lens 側 validator が持つ。

**兄弟文書を読まない。** 検めるのは渡された一文書の本文だけである(NONGOAL-001 第5項)。

標準ライブラリだけを使う。決定的に動く(壁時計も乱数も読まない)。
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _registry

# doctrine:begin SPEC-031
# 器の版。描き手が持つ定数とする(ADR-163 決定9)。版の進め方は #294 の B1 が持つ。
MODEL_SCHEMA = "system-map/gold-model/0.1"

# 描く先の最上位の欄(map-draft-check の TOP_KEYS と同じ形)。
TOP_KEYS = ("schema", "target", "system", "elements", "flows", "contracts",
            "scenarios", "anchors")
ENTITY_LISTS = ("elements", "flows", "contracts", "scenarios", "anchors")

# 必須節と、描く先の欄の対応。**節名は登録簿から機械的に導く** —— 字面を写すと
# 登録簿を直したときに本文の値だけが拾われなくなる(WATCH-001 第2項が同じ形の
# 手写しを戻り禁止にしている。DECIDED-001 事実1)。登録簿の並びは器の最上位の欄と
# 一対一である(ADR-163 決定2。_registry.py の註釈がそう宣言している)。
_MODEL_SECTIONS = _registry.required_sections("MODEL")
_SECTION_ORDER = ("system",) + ENTITY_LISTS
SECTION_FOR_LIST = dict(zip(_SECTION_ORDER[1:], _MODEL_SECTIONS[1:]))
SYSTEM_SECTION = _MODEL_SECTIONS[0] if _MODEL_SECTIONS else "系の概要"

# 散文を書く欄。用語の門(禁止同義語・カルク・未定義語)は、この欄の値にだけ掛ける
# (id・種別・パス・日付のような機械の値には掛けない)。
PROSE_FIELDS = ("purpose", "boundary", "guarantee", "response_measure",
                "label", "payload_or_action", "condition", "name",
                "responsibilities", "assumptions", "na_reason",
                "self_loop_reason")

# 引退した位置づけ(ADR-027 の退避・後継による置換・廃止)。確定の同値はここへ
# 掛けない —— 確定を経た模型を引退させる道を塞がないためである(ADR-164)。
RETIRED_STATUSES = ("deprecated", "superseded", "archived")

# 語彙の正本(lens 側 gold-model の schema.json 0.1 を写したもの)。
ENUM_REVIEW_STATUS = ("proposed", "confirmed")
ENUM_VERDICT = ("present", "silent")
ENUM_TARGET_KIND = ("document", "code_range", "test", "external_doc",
                    "artifact")
ENUM_AUTHORITY = ("doctrine", "gold_model")
ENUM_VERIFICATION_STATUS = ("unknown", "claimed", "planned", "verified",
                            "failed", "stale", "not_applicable")
ENUM_ELEMENT_KIND = ("person", "organization", "system", "subsystem",
                     "component", "operation", "external_system", "device")
ENUM_FLOW_KIND = ("data", "command", "event", "physical", "human_action")
ENUM_SCENARIO_KIND = ("normal", "exception")

# 実体ごとの必須欄。手引き(skills/system-map-draft/references/model-shape.md)が
# 「必須」と書いた欄をそのまま採る。
REQUIRED_FIELDS = {
    "system": ("target", "purpose", "boundary", "provenance", "review_status"),
    "elements": ("id", "name", "kind", "purpose", "responsibilities", "owner",
                 "provenance", "review_status"),
    "flows": ("id", "from", "to", "label", "kind", "payload_or_action",
              "condition", "provenance", "review_status"),
    "contracts": ("id", "subject", "assumptions", "guarantee",
                  "response_measure", "verification_status", "owner",
                  "provenance", "review_status"),
    "scenarios": ("id", "kind", "steps", "provenance", "review_status"),
    "anchors": ("id", "target_kind", "target", "source_revision",
                "observed_at", "authority"),
}

# 出所(Source)の必須欄。
PROVENANCE_FIELDS = ("source", "locator", "checked_at", "verdict")

_H2_RE = re.compile(r"^##\s+(.*?)\s*$")
_H3_RE = re.compile(r"^###\s+(.*?)\s*$")
_FENCE_OPEN_RE = re.compile(r"^\s*```json\s*$")
_FENCE_ANY_RE = re.compile(r"^\s*```")


class Finding(object):
    """一件の所見。severity は 'ERROR' か 'WARN'(リンタの段に合わせる)。"""

    __slots__ = ("code", "severity", "where", "message", "line")

    def __init__(self, code, severity, where, message, line=0):
        self.code = code
        self.severity = severity
        self.where = where
        self.message = message
        self.line = line

    def __repr__(self):                                   # pragma: no cover
        return "Finding(%s, %s, %s)" % (self.code, self.where, self.message)


def _f(out, code, where, message, line=0, severity="ERROR"):
    out.append(Finding(code, severity, where, message, line))


def _scan(body):
    """本文を一度だけ走り、(塊の列, 見出しの列) を返す。

    塊は (節名, 見出し, 塊の文字列, 行番号)。見出しは (節名, 見出し, 行番号, 塊を持つか)。
    **塊を持たない見出しも返す** —— 見出しが在るのに値が無い実体は、正本には見えて
    投影には居ない、という黙った食い違いになるからである。
    """
    blocks = []
    headings = []
    section = None
    cur = None                 # いま開いている見出しの、headings の中の位置
    i = 0
    lines = body.splitlines()
    n = len(lines)
    while i < n:
        line = lines[i]
        m2 = _H2_RE.match(line)
        if m2:
            section = m2.group(1)
            cur = None
            i += 1
            continue
        m3 = _H3_RE.match(line)
        if m3:
            headings.append([section, m3.group(1), i + 1, False])
            cur = len(headings) - 1
            i += 1
            continue
        if _FENCE_OPEN_RE.match(line):
            start = i + 1
            j = start
            while j < n and not _FENCE_ANY_RE.match(lines[j]):
                j += 1
            heading = headings[cur][1] if cur is not None else None
            blocks.append((section, heading, "\n".join(lines[start:j]), start))
            if cur is not None:
                headings[cur][3] = True
            i = j + 1
            continue
        i += 1
    return blocks, headings


def parse_blocks(body):
    """本文から (節名, 見出し, 塊の文字列, 行番号) の列を、出現順で返す。

    節は `## 見出し`、実体は `### 見出し`、値は直後の ```json の囲みである。
    節名の照合は部分一致とする(リンタの必須節検査と同じ規律。言い換えは許さないが、
    「## 要素の一覧（案）」のような添え書きは通す)。
    """
    return _scan(body)[0]


def _list_for_section(section):
    """節名から、描く先の欄の名を返す。対応が無ければ None。"""
    if not section:
        return None
    if SYSTEM_SECTION in section:
        return "system"
    for key, name in SECTION_FOR_LIST.items():
        if name in section:
            return key
    return None


def parse_model(body):
    """本文を (model, findings) に解く。model は描く先の形に組んだ写像。

    JSON として読めない塊は所見にし、その塊だけを落とす(他の塊の点検は続ける)。
    """
    findings = []
    model = {"system": None, "elements": [], "flows": [], "contracts": [],
             "scenarios": [], "anchors": []}
    blocks, headings = _scan(body)
    for section, heading, line, has_block in headings:
        if _list_for_section(section) is None or has_block:
            continue
        _f(findings, "MODEL_HEADING_WITHOUT_BLOCK", heading,
           "見出しが在るのに ```json の塊が無い。値が投影へ出ない"
           "(囲みは ```json と綴る)", line)
    for section, heading, raw, line in blocks:
        target = _list_for_section(section)
        if target is None:
            # 必須節の外に置かれた塊は、値として拾わない(散文の例示を値にしない)。
            continue
        try:
            value = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            _f(findings, "MODEL_BAD_JSON", heading or section,
               "JSON として読めない(%s)。塊の中身を直す" % exc, line)
            continue
        if not isinstance(value, dict):
            _f(findings, "MODEL_BAD_JSON", heading or section,
               "塊が写像(オブジェクト)でない", line)
            continue
        if target == "system":
            if model["system"] is not None:
                _f(findings, "MODEL_DUPLICATE_SYSTEM", section,
                   "「%s」の塊が二つ以上ある。系は一つだけ書く" % SYSTEM_SECTION,
                   line)
                continue
            model["system"] = value
            model["_system_line"] = line
            continue
        value["_line"] = line
        value["_heading"] = heading or ""
        model[target].append(value)
    return model, findings


def _strip_internal(value):
    """解析の覚え書き(先頭が _ の鍵)を落とした複製を返す。"""
    return {k: v for k, v in value.items() if not k.startswith("_")}


def _check_enum(findings, where, key, entity, allowed, line):
    if key not in entity:
        return
    if entity.get(key) not in allowed:
        _f(findings, "MODEL_BAD_ENUM", where,
           "%s が %r(許す値: %s)" % (key, entity.get(key), ", ".join(allowed)),
           line)


def _check_provenance(findings, where, entity, line):
    prov = entity.get("provenance")
    if prov is None:
        return                      # 必須欄の検査が null を欠落として咎める
    if not isinstance(prov, list) or not prov:
        _f(findings, "MODEL_BAD_PROVENANCE", where,
           "provenance は一件以上の配列である(読んだ場所を書く)", line)
        return
    for idx, src in enumerate(prov):
        sw = "%s.provenance[%d]" % (where, idx)
        if not isinstance(src, dict):
            _f(findings, "MODEL_BAD_PROVENANCE", sw, "出所が写像でない", line)
            continue
        for key in PROVENANCE_FIELDS:
            if key not in src:
                _f(findings, "MODEL_MISSING_FIELD", sw,
                   "出所の必須欄 %s が無い" % key, line)
        _check_enum(findings, sw, "verdict", src, ENUM_VERDICT, line)


def check_structure(model, findings):
    """形と語彙と文書の中の参照を検める。model は parse_model の返り値。"""
    system = model.get("system")
    if system is None:
        _f(findings, "MODEL_MISSING_SYSTEM", SYSTEM_SECTION,
           "「%s」の節に JSON の塊が無い。系は一つ書く" % SYSTEM_SECTION)
    else:
        line = model.get("_system_line", 0)
        for key in REQUIRED_FIELDS["system"]:
            if system.get(key) is None:
                _f(findings, "MODEL_MISSING_FIELD", "system",
                   "必須欄 %s が無い(値が null も欠落と数える)" % key, line)
        _check_enum(findings, "system", "review_status", system,
                    ENUM_REVIEW_STATUS, line)
        _check_provenance(findings, "system", system, line)

    seen = {}
    for label in ENTITY_LISTS:
        for item in model.get(label, []):
            line = item.get("_line", 0)
            ident = item.get("id")
            # id が無いときは見出しで指す(『elements[?]』では直す先が分からない)。
            if isinstance(ident, str) and ident:
                where = "%s[%s]" % (label, ident)
            elif item.get("_heading"):
                where = "%s[見出し『%s』]" % (label, item["_heading"])
            else:
                where = "%s[?]" % label
            for key in REQUIRED_FIELDS[label]:
                if item.get(key) is None:
                    _f(findings, "MODEL_MISSING_FIELD", where,
                       "必須欄 %s が無い(値が null も欠落と数える)" % key, line)
            if "id" in item and not (isinstance(ident, str) and ident.strip()):
                _f(findings, "MODEL_BAD_ID", where,
                   "id が空でない文字列でない(%r)。id は文書の中で一意の文字列とする"
                   % (ident,), line)
            if isinstance(ident, str) and ident:
                if ident in seen:
                    _f(findings, "MODEL_DUPLICATE_ID", where,
                       "id %s が二度使われている(先は %s)" % (ident, seen[ident]),
                       line)
                else:
                    seen[ident] = where
                heading = item.get("_heading") or ""
                if heading and ident not in heading:
                    _f(findings, "MODEL_HEADING_ID_MISMATCH", where,
                       "見出し『%s』に id %s が無い。見出しと塊を揃える"
                       % (heading, ident), line)
            if label != "anchors":
                _check_enum(findings, where, "review_status", item,
                            ENUM_REVIEW_STATUS, line)
                _check_provenance(findings, where, item, line)
        # 語彙(実体ごと)
    for item in model.get("elements", []):
        _check_enum(findings, "elements[%s]" % item.get("id"), "kind", item,
                    ENUM_ELEMENT_KIND, item.get("_line", 0))
    for item in model.get("flows", []):
        _check_enum(findings, "flows[%s]" % item.get("id"), "kind", item,
                    ENUM_FLOW_KIND, item.get("_line", 0))
    for item in model.get("scenarios", []):
        _check_enum(findings, "scenarios[%s]" % item.get("id"), "kind", item,
                    ENUM_SCENARIO_KIND, item.get("_line", 0))
    for item in model.get("contracts", []):
        _check_enum(findings, "contracts[%s]" % item.get("id"),
                    "verification_status", item, ENUM_VERIFICATION_STATUS,
                    item.get("_line", 0))
    for item in model.get("anchors", []):
        where = "anchors[%s]" % item.get("id")
        _check_enum(findings, where, "target_kind", item, ENUM_TARGET_KIND,
                    item.get("_line", 0))
        _check_enum(findings, where, "authority", item, ENUM_AUTHORITY,
                    item.get("_line", 0))
    _check_references(model, findings)


def _ids(model, label):
    """label の実体の id の集合。空でない文字列だけを採る。"""
    return {i.get("id") for i in model.get(label, [])
            if isinstance(i.get("id"), str) and i.get("id").strip()}


def _check_references(model, findings):
    """文書の中の参照が実在するか(幽霊要素の禁止。M-12 と同じ趣旨)。"""
    elements = _ids(model, "elements")
    flows = _ids(model, "flows")
    anchors = _ids(model, "anchors")
    scenarios = _ids(model, "scenarios")

    def _need(where, value, pool, what, line):
        if value is None:
            return
        if not isinstance(value, str) or value not in pool:
            _f(findings, "MODEL_DANGLING_REF", where,
               "%s が指す %r が文書の中に無い" % (what, value), line)

    for item in model.get("elements", []):
        where = "elements[%s]" % item.get("id")
        line = item.get("_line", 0)
        _need(where, item.get("parent"), elements, "parent", line)
        realized = item.get("realized_by")
        if realized is None:
            pass
        elif not isinstance(realized, list):
            # 配列でない値を反復すると、文字を一つずつ辿るか例外が漏れる。
            # 所見にして止める(SPEC-031「例外を投げない」)。
            _f(findings, "MODEL_BAD_REALIZED_BY", where,
               "realized_by が配列でない(%r)。アンカーの id の配列とする"
               % (realized,), line)
        else:
            for anchor in realized:
                _need(where, anchor, anchors, "realized_by", line)
    for item in model.get("flows", []):
        where = "flows[%s]" % item.get("id")
        line = item.get("_line", 0)
        _need(where, item.get("from"), elements, "from", line)
        _need(where, item.get("to"), elements, "to", line)
        if (item.get("from") is not None
                and item.get("from") == item.get("to")
                and not item.get("self_loop_reason")):
            _f(findings, "MODEL_SELF_LOOP_WITHOUT_REASON", where,
               "自己ループには self_loop_reason を書く", line)
    for item in model.get("scenarios", []):
        where = "scenarios[%s]" % item.get("id")
        line = item.get("_line", 0)
        if item.get("kind") == "exception":
            _need(where, item.get("exception_of"), scenarios, "exception_of",
                  line)
        steps = item.get("steps")
        if steps is not None and not isinstance(steps, list):
            _f(findings, "MODEL_BAD_STEPS", where, "steps が配列でない", line)
            continue
        for idx, step in enumerate(steps or []):
            sw = "%s.steps[%d]" % (where, idx)
            if not isinstance(step, dict):
                _f(findings, "MODEL_BAD_STEPS", sw, "段が写像でない", line)
                continue
            _need(sw, step.get("actor"), elements, "actor", line)
            _need(sw, step.get("receiver"), elements, "receiver", line)
            _need(sw, step.get("flow"), flows, "flow", line)


def check_confirmation(model, status, findings):
    """文書の `status` と値の `review_status` の同値を検める(ADR-163 決定6)。

    `current` は「全ての値が confirmed」と同値である。片方だけが進んだ状態を
    咎める —— **確定の一押しは人の仕事であり、機械は食い違いだけを言う。**
    """
    values = []
    if model.get("system") is not None:
        values.append(("system", model["system"], model.get("_system_line", 0)))
    for label in ENTITY_LISTS:
        if label == "anchors":
            continue                      # アンカーは値を担わない(指し先の記述)
        for item in model.get(label, []):
            values.append(("%s[%s]" % (label, item.get("id")), item,
                           item.get("_line", 0)))
    if not values:
        return
    if status in RETIRED_STATUSES:
        # 引退した模型(廃止・置換・退避)の値は confirmed のまま凍らせてよい。
        # ここを咎めると、確定を経た模型を引退させる道が塞がる(ADR-164)。
        return
    unconfirmed = [(w, line) for (w, v, line) in values
                   if v.get("review_status") != "confirmed"]
    if _registry.is_current(status):
        for where, line in unconfirmed:
            _f(findings, "MODEL_UNCONFIRMED_IN_CURRENT", where,
               "status が current だが review_status が confirmed でない"
               "(確定の一押しと値の状態を揃える。ADR-163 決定6)", line)
    elif not unconfirmed:
        # **機械へ「確定せよ」とは言わない。** 確定の一押しは人の仕事であり、
        # 機械が取れる行いは値を戻すことだけである(ADR-163 決定6・ADR-164)。
        _f(findings, "MODEL_CONFIRMED_NOT_CURRENT", "(文書)",
           "全ての値が confirmed である。確定の一押し(status)は人が行う —— "
           "機械は status を動かさない。値を proposed へ戻すか、人の確定を待つ",
           model.get("_system_line", 0), severity="WARN")


def check_document(body, status):
    """本文と `status` を検め、所見の列を返す。リンタの口はこれ一つ。"""
    model, findings = parse_model(body)
    check_structure(model, findings)
    check_confirmation(model, status, findings)
    return findings


def prose_values(model):
    """塊の中の散文の値を (where, 行, 文字列) の列で返す(用語の門に掛けるため)。

    掛けるのは PROSE_FIELDS の欄だけである —— id・種別・パス・日付のような機械の値に
    用語の門を掛けると、誤った咎めが出る。文字列の配列は要素ごとに返す。
    """
    out = []

    def _take(where, entity, line):
        for key in PROSE_FIELDS:
            value = entity.get(key)
            if isinstance(value, str):
                out.append((where, line, value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.append((where, line, item))

    system = model.get("system")
    if isinstance(system, dict):
        _take("system", system, model.get("_system_line", 0))
    for label in ENTITY_LISTS:
        for item in model.get(label, []):
            _take("%s[%s]" % (label, item.get("id")), item,
                  item.get("_line", 0))
    return out


def build_json(model):
    """解析した写像から、描く先の形の写像を組む(一方通行の投影。ADR-161 決定3)。

    並びは文書の中の出現順とする。解析の覚え書き(先頭が _ の鍵)は落とす。
    """
    system = dict(model.get("system") or {})
    target = system.pop("target", None)
    out = {
        "schema": MODEL_SCHEMA,
        "target": target,
        "system": _strip_internal(system),
    }
    for label in ENTITY_LISTS:
        out[label] = [_strip_internal(i) for i in model.get(label, [])]
    return out


def render_json(model):
    """描く先の JSON の文字列(決定的。末尾に改行を一つ置く)。"""
    return json.dumps(build_json(model), ensure_ascii=False, indent=2,
                      sort_keys=True) + "\n"
# doctrine:end SPEC-031
