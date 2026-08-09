#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""doctrine の統制構造（CAST の分析対象。標準ライブラリのみ）。

CAST は「誰が・何を・どの手掛かりを見て制御していたか」を先に置き、そこから
統制の欠陥を導く。分析のたびに構造を口頭で組み直すと、要素の抜けが記録に
残らないまま結論だけが変わる。そこで構造はここに一度だけ書き、cast レーンへは
この列だけを渡す（会話・弁明は渡さない。ADR-115 の独立性）。

各要素は実在するファイルを指す。指す先が消えたら決定論試験が落ちる
（構造が古びたことを、分析の質ではなくファイルの実在で検出する）。

kind の読み:
- controller     … 制御を掛ける側（人・自動の門）
- actuator       … 制御を実際に及ぼす経路
- sensor         … 状態を測って上位へ返す経路（先行指標が載る場所）
- process        … 制御される対象そのもの
"""
import os

LANE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(LANE_DIR)

# 要素の正本。id は分析の参照鍵であり、改名は分析の履歴を切るので避ける。
ELEMENTS = (
    {
        "id": "OWNER",
        "name": "所有者（人）",
        "kind": "controller",
        "implemented_by": None,
        "control_actions": [
            "互換性を壊す変更・配布境界の変更・復旧不能な削除の可否を決める",
            "評価 model の最低線を決める（ADR-116）",
            "push / PR / merge を許す範囲を決める",
        ],
        "feedback": ["進捗報告（規定形式）", "PR の diff", "台帳 assurance/ledger/"],
        "known_gaps": ["報告が実施ではなく意図を書いていても、人からは見分けにくい"],
    },
    {
        "id": "CI_RELEASE_CHECK",
        "name": "CI（本体試験・監査・release-check）",
        "kind": "controller",
        "implemented_by": ".github/workflows",
        "control_actions": ["merge 前に赤で止める"],
        "feedback": ["ジョブの成否", "docs-audit の JSON"],
        "known_gaps": [
            "CI が見るのはリポジトリ正本であり、利用者環境へ導入された複製の版は見ない",
        ],
    },
    {
        "id": "SESSION_START_CONTRACT",
        "name": "SessionStart の契約注入",
        "kind": "actuator",
        "implemented_by": "plugin/scripts/inject-contract.py",
        "control_actions": ["セッション冒頭に確定・非目標・退行監視の要点を注入する"],
        "feedback": ["注入の有無そのものが統治の生存の指標（R11）"],
        "known_gaps": [
            "注入は主セッションだけに効き、サブエージェントには届かない（NONGOAL-001）",
        ],
    },
    {
        "id": "HEARTBEAT",
        "name": "UserPromptSubmit の鼓動（古び・版遅れの警告）",
        "kind": "sensor",
        "implemented_by": "plugin/scripts/gov-heartbeat.py",
        "control_actions": ["監査の古び・版の遅れをターンごとに警告する"],
        "feedback": [".claude/.cache/last-audit.json", "導入複製の版"],
        "known_gaps": [
            "検出器自身が導入複製の側で動くため、版が遅れると検出器も遅れる"
            "（古びの検出器が古びる共通原因故障。INC-005）",
        ],
    },
    {
        "id": "PRE_TOOL_GUARD",
        "name": "PreToolUse のガード（拒否の門）",
        "kind": "controller",
        "implemented_by": "plugin/scripts/policy-guard.py",
        "control_actions": ["違反する編集・削除を終了コード2で拒む"],
        "feedback": ["拒否の応答（呼び出し側のモデルへ返る）"],
        "known_gaps": [
            "ガードが実際に拒否できることは体系側から検出しない（NONGOAL-001）",
            "Hook が起動しない経路で書かれた文書は止められない",
        ],
    },
    {
        "id": "POST_TOOL_LINTER",
        "name": "PostToolUse のリンタと助言",
        "kind": "sensor",
        "implemented_by": "plugin/scripts/docs-linter.py",
        "control_actions": ["編集された一つの文書だけを点検し、助言を返す"],
        "feedback": ["additionalContext（助言）"],
        "known_gaps": ["decision を出さない設計であり、拒否はガード頼み（WATCH-001）"],
    },
    {
        "id": "SESSION_END_AUDIT",
        "name": "SessionEnd の全件監査",
        "kind": "sensor",
        "implemented_by": "plugin/scripts/docs-audit.py",
        "control_actions": ["統治木を全件走査し、要約を .claude/.cache へ書く"],
        # 宣言と実装の突合（INC-001 推奨#2 の着地）: この feedback の宣言を
        # 実際に stat する経路は observe_assumptions.py が持つ —— ASM-001 の
        # 観測が last-audit.json の generated_at と mtime を読み、ASM-002 の
        # 観測が checks_run 集合を現行 AUDIT_CHECKS と照合する。複製側の
        # 自己申告に依存しない外形観測がこれである（ADR-144）。
        "feedback": [".claude/.cache/last-audit.json（次セッションの注入と鼓動が読む）"],
        "known_gaps": [
            "SessionEnd が発火しない終了（強制終了・環境の落ち）では走らず、"
            "走らなかったこと自体は次セッションの古び警告でしか判らない（INC-001）",
        ],
    },
    {
        "id": "CAPTURE_NUDGE",
        "name": "Stop / PreCompact の決定捕捉",
        "kind": "sensor",
        "implemented_by": "plugin/scripts/capture-nudge.py",
        "control_actions": ["セッション終端と圧縮後に、決定の取りこぼしを促す"],
        "feedback": ["退避したメモ"],
        "known_gaps": ["圧縮の前に促すことは原理的にできない（ADR-077・NONGOAL-001）"],
    },
    {
        "id": "PLUGIN_DISTRIBUTION",
        "name": "配布と導入複製の更新経路",
        "kind": "actuator",
        "implemented_by": ".claude-plugin/marketplace.json",
        "control_actions": ["marketplace 経由で利用者環境へ複製を配る・更新する"],
        "feedback": ["claude plugin update の応答"],
        "known_gaps": [
            "更新は利用者の操作に依存し、複製が何世代遅れているかを"
            "リポジトリ側からは観測できない（INC-005）",
        ],
    },
    {
        "id": "ASSURANCE_LANE",
        "name": "保証レーン（本ハーネス）",
        "kind": "controller",
        "implemented_by": "assurance/harness/orchestrator.py",
        "control_actions": [
            "次の行動を決定論で導く", "事象を台帳へ積み、分析が済むまで閉じない",
            # 進捗の停止を観測する責任は、ここに一意に置く（INC-006 推奨#5。
            # 2026-08-09 の所有者委任裁定）。「next_actions は空にならない」と
            # いう不変条件を持つのはこの要素だけである。監査と鼓動には持たせない
            # —— 重複させると双方が他方を前提にして減衰する。
            "進捗の停止を観測する（next_actions が空にならないことを保つ）",
            # 台帳そのものの健全性に対する責任も、ここに一意に置く
            # （INC-027 推奨#8）。書き手は原子化で「書き切れなかった」側を守るが、
            # 「読めない台帳が在る」ことを声に出すのは validate の仕事である。
            "台帳の健全性を保つ（読めない台帳を名指し、破損を空へ写像させない）",
        ],
        "feedback": ["assurance/ledger/", "決定論試験の成否"],
        "known_gaps": [
            "評価者は同系 model であり、共通原因故障は残余リスクとして残る",
            # ASM-006。原子化（ledger_io.write_json）が守るのは「書き切れなかった」
            # 側だけで、二つの走らせ手が両方書き切って片方の追記が整形式のまま
            # 消える形（INC-008）は守らない。単一の書き手を想定している。
            "台帳への同時書き込みは想定していない（ASM-006。INC-008 が実例）",
        ],
    },
    {
        "id": "GOVERNANCE_TREE",
        "name": "統治木（doctrine_docs 配下の文書）",
        "kind": "process",
        "implemented_by": "doctrine_docs/_system/decided-facts.md",
        "control_actions": [],
        "feedback": ["docs-audit の findings", "dep-graph の逆依存"],
        "known_gaps": ["ガードを通さずに書かれた文書は統治の外に出る"],
    },
)

ELEMENT_IDS = tuple(e["id"] for e in ELEMENTS)


def missing_implementations():
    """implemented_by が指す先が実在しない要素の id。構造の古びの oracle。"""
    missing = []
    for e in ELEMENTS:
        rel = e["implemented_by"]
        if rel is None:
            continue
        if not os.path.exists(os.path.join(REPO_DIR, rel)):
            missing.append(e["id"])
    return missing


def as_prompt_text():
    """cast レーンへ渡す統制構造の平文。判断は入れず、事実と既知の穴だけ。"""
    lines = []
    for e in ELEMENTS:
        lines.append("### %s（%s / %s）" % (e["id"], e["name"], e["kind"]))
        if e["implemented_by"]:
            lines.append("- 実体: %s" % e["implemented_by"])
        for a in e["control_actions"]:
            lines.append("- 制御: %s" % a)
        for f in e["feedback"]:
            lines.append("- 手掛かり: %s" % f)
        for g in e["known_gaps"]:
            lines.append("- 既知の穴: %s" % g)
        lines.append("")
    return "\n".join(lines)
