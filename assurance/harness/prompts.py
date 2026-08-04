#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""DISCOVER / CHALLENGE のプロンプトをプログラム的に組み立てる（標準ライブラリのみ）。

独立性は構造で守る:
- build_challenge_prompt は DISCOVER の構造化 JSON **だけ**を引数に取る。
  会話履歴・実装者の弁明・期待回答を渡す口を持たない。
- どちらの関数も、呼び出し側の文脈を勝手に読み込まない（引数が全て）。

この module は組み立てだけを担う。実行は sdk_lane.run_one_shot に渡す。
実モデルでの初回実行が済むまで、これらのプロンプトの有効性は未実証である
（台帳に UNASSESSED として残す）。
"""
import json

# 判定語彙は schemas.VERDICT_SCHEMA / SCENARIO_SCHEMA と対で保つ。

_DISCOVER_CHARTER = """\
あなたは Doctrine（文書統治プラグイン）の保証キャンペーンの DISCOVER 担当である。
役割: 既知のテストの言い換えではない、新しい失敗仮説を生成する。

制約:
- 読み取り専用。ファイルの変更・作成・削除・commit を提案しても実行してはならない。
- 「テストが緑=保証成立」とみなさない。正常系だけの観点を出さない。
- 各仮説は反証可能であること: 観測可能な oracle と、偽だった場合に何が見えるかを必ず書く。
- 出典（規範・仕様・コードの位置）の無い仮説は出さない。
- 思いつかなくなったことを網羅の証拠にしない。出せないなら出せないと書く。
"""

_CHALLENGE_CHARTER = """\
あなたは保証キャンペーンの CHALLENGE 担当である。DISCOVER の成果物（下の JSON）
だけを受け取り、独立に批判する。DISCOVER との会話履歴は存在しないし、要求もしない。

各候補について次を疑え:
- 規範の誤読 / システム境界の漏れ / oracle が曖昧・非観測 / 再現不能
- 実装詳細への過剰適合 / 既存試験との重複 / 重要な相互作用の欠落
- 正常系しか見ていない / AI に都合のよい停止条件
- 実 Claude と模擬ホストの混同 / 試験が実際には欠陥を検出しない可能性

判定は ACCEPT / REJECT / UNKNOWN。迷ったら ACCEPT ではなく UNKNOWN。
"""


def build_discover_prompt(seed_facts, boundary):
    """DISCOVER の一回限りセッション用プロンプト。

    seed_facts: 出発点となる事実の列（例: 直近の障害・規範の条項）。
    boundary: 対象システム境界の一文。
    """
    if not isinstance(seed_facts, (list, tuple)) or not seed_facts:
        raise ValueError("seed_facts は空でない列でなければならない")
    lines = [_DISCOVER_CHARTER,
             "対象システム境界: %s" % boundary,
             "",
             "出発点の事実（これ自体を疑ってもよい）:"]
    lines += ["- %s" % fact for fact in seed_facts]
    lines += [
        "",
        "応答は SCENARIO_SCHEMA に適合する JSON の配列だけを返す。"
        "各要素は scenario_id, normative_refs, system_boundary, loss, hazard,"
        " unsafe_control_action, event_sequence, fault, injection_point,"
        " expected_safe_behavior, oracle, falsification_signal, severity,"
        " confidence を必ず持つ。",
    ]
    return "\n".join(lines)


def build_challenge_prompt(discover_output_json):
    """CHALLENGE の一回限りセッション用プロンプト。

    引数は DISCOVER の構造化 JSON（文字列または解析済み）だけ。
    ここに会話履歴・弁明を足す口は意図して作らない。
    """
    if isinstance(discover_output_json, (dict, list)):
        payload = json.dumps(discover_output_json, ensure_ascii=False, indent=2)
    elif isinstance(discover_output_json, str) and discover_output_json.strip():
        json.loads(discover_output_json)  # 構造化されていない文字列は拒否する
        payload = discover_output_json
    else:
        raise ValueError("DISCOVER の構造化 JSON だけを受け取る")
    return "%s\n批判対象:\n%s\n\n各候補への判定を VERDICT_SCHEMA に適合する JSON で返す。" % (
        _CHALLENGE_CHARTER, payload)
