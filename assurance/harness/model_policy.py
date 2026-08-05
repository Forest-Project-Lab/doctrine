#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""役割ごとの model / effort の方針（標準ライブラリのみ）。

所有者指示(2026-08-04): 規範の評価・批判・分析は最低でも opus の effort high。
haiku を使ってよいのは、意味を要さない配管確認と、「弱い model でも意味が
保たれるか」を意図して測る劣化プローブだけ。

評価役の model を黙って弱いものへ落とさない。落ちるくらいなら UNASSESSED。
（sdk_lane は fallback_model を渡さない設計であり、この方針と整合する。）
"""

# 役割 → 実行条件。評価の最低線は 'high'（引き上げは可・引き下げは所有者判断）。
ROLES = {
    # 意味を要さない配管確認(煙試験の nonce 往復など)
    "plumbing": {"model": "claude-haiku-4-5", "effort": None},
    # 規範の抽出・観点創出・独立批判・検証計画・事故分析(最低線: opus high)
    "evaluation": {"model": "claude-opus-5", "effort": "high"},
    # 意図した弱 model プローブ(evaluation と同じ入力で意味の保持を比べる)
    "degradation-probe": {"model": "claude-haiku-4-5", "effort": None},
}

_EVALUATION_MIN = ("claude-opus-5", "high")
_EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")


def options_for(role):
    """役割の実行条件を返す。未知の役割は例外（黙って既定へ倒さない）。"""
    if role not in ROLES:
        raise ValueError("未知の役割 %r（許すのは %s）" % (role, sorted(ROLES)))
    return dict(ROLES[role])


def assert_evaluation_floor(model, effort):
    """評価役の最低線を検める。破っていれば例外。

    劣化プローブは 'degradation-probe' 役を名指しで使う。評価役の条件を
    この関数を通さずに組んだ呼び出しは、決定論試験が拒否する。
    """
    if model != _EVALUATION_MIN[0]:
        raise ValueError(
            "評価役の model は %s 固定（%r は不可。弱い model の比較は "
            "degradation-probe 役を明示して使う）" % (_EVALUATION_MIN[0], model))
    if effort not in _EFFORT_ORDER or (
            _EFFORT_ORDER.index(effort) < _EFFORT_ORDER.index(_EVALUATION_MIN[1])):
        raise ValueError(
            "評価役の effort は %s 以上（%r は不可）" % (_EVALUATION_MIN[1], effort))
    return True
