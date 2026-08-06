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


_EXTRACT_CHARTER = """\
あなたは規範文書から検証原則を抽出する担当である。対象は下のチャンク
（行番号 L… 付き）だけ。他の章・他の版・自分の一般知識から補完しない。

規律:
- 原則は一文一義の statement に言い換える。曖昧語（適切に・十分に）はそのまま写さず、
  何が要求されているかを具体に書く。
- source_quote には、チャンク本文に**連続して実在する原文断片**（20〜80字程度）を
  そのまま書く。存在しない引用は機械照合で却下される。
- source_lines は "L開始-L終了" の形で、引用が実在する行を指す。
- 目次・免責・扉・図表番号だけの箇所からは抽出しない。
- 同じ原則の言い換え増殖を避ける。dedupe_key は原則の本質を表す短い正規化句にする。
- applicability は「文書統治プラグイン doctrine（Hook・リンタ・監査・スキル・CI で
  Markdown 統治木を統治する）へどう効くか」の仮説を一文で。
- suggested_oracle は「守られていないとき何が観測できるか」を一文で。
- このチャンクに原則が無ければ principles は空配列でよい（無理に作らない）。
"""


def build_extract_principles_prompt(book_title, chunk, numbered_text):
    """規範抽出の一回限りセッション用プロンプト。

    chunk: books.chunk_lines の要素（絶対行番号を持つ）。
    numbered_text: books.numbered(chunk) の行番号付き本文。
    """
    if not numbered_text.strip():
        raise ValueError("空のチャンクは抽出に渡さない")
    return (
        "%s\n対象冊子: %s\n対象範囲: L%d-L%d\n\n"
        "--- チャンク本文（行番号付き）---\n%s\n--- 本文ここまで ---\n\n"
        "PRINCIPLES_SCHEMA に適合する JSON だけを返す。"
        % (_EXTRACT_CHARTER, book_title,
           chunk["start_line"], chunk["end_line"], numbered_text))


def verify_principles(chunk_text, principles):
    """引用の実在をチャンク本文と照合する（抽出の反幻覚 oracle）。

    返り値: (accepted, rejected)。空白差は正規化して照合する。
    照合できない source_quote を持つ原則は却下へ落とす。
    """
    def norm(s):
        return "".join((s or "").split())

    hay = norm(chunk_text)
    accepted, rejected = [], []
    for p in principles:
        needle = norm(p.get("source_quote", ""))
        if len(needle) >= 10 and needle in hay:
            accepted.append(p)
        else:
            rejected.append(p)
    return accepted, rejected


_CAST_CHARTER = """\
あなたは保証キャンペーンの CAST_ANALYSIS 担当である。事故分析の規範（CAST）に
沿って、事象そのものではなく**統制構造のどこが欠けていたか**を分析する。

規律:
- 個人・エージェントの不注意を原因にしない。「なぜその時点では妥当に見えたか」を
  必ず書く。責任追及ではなく統制の再設計が目的である。
- 統制欠陥は、下の統制構造に実在する要素 id を必ず指す。無い要素は作らない。
- normative_refs には、下の CAST 検証原則の dedupe_key を**そのまま**書く。
  一覧に無い鍵は機械照合で却下される。憶測の出典を書かない。
- 修正済みの事象でも「なぜ既存の保証が見逃したか」を書く。修正は分析の代わりに
  ならない。
- leading_indicators（先行指標）は、事象が再発する**前**に観測できるものだけを書く。
  事後に判る事実は指標ではない。どこで観測するか（where）と、何をもって異常と
  するか（threshold）を具体に書く。
- 指標が導入複製の版に依存するなら version_independent を false にする。
  版が遅れると検出器も遅れる故障（古びの検出器が古びる）を隠さない。
- 判らないことは unknowns に書く。埋めるために推測で断定しない。
- **事象が名指しする機構が、下の統制構造のどこにも見当たらないなら、まずその旨を
  unknowns の先頭へ書く。** 事象の記録は与えられた入力であって、実在の証明では
  ない。実在を確かめないまま統制欠陥を断定しない。見当たらない機構について
  分析を組み立てるときは、confidence を low にする。
  （この一項は故障注入 A2 で入った —— 実在しない機構についての捏造事象に対し、
  評価器は統制欠陥を8件生成し、実在を疑う unknowns を一つも出さなかった。
  出典の照合は「引用が実在するか」しか見ず、「対象が実在するか」を見ない。）
"""


def build_cast_analysis_prompt(incident, control_structure_text, principle_index):
    """CAST_ANALYSIS の一回限りセッション用プロンプト。

    incident: incidents.json の一件（構造化された記録だけ）。
    control_structure_text: control_structure.as_prompt_text() の平文。
    principle_index: [(dedupe_key, title, statement), ...] の列（CAST カタログ）。

    実装者の会話・弁明・期待する結論を渡す口は意図して作らない
    （CHALLENGE と同じ独立性の規律。ADR-115）。
    """
    if not isinstance(incident, dict) or not incident.get("id"):
        raise ValueError("incident は id を持つ構造化された記録でなければならない")
    if not control_structure_text.strip():
        raise ValueError("統制構造が空のまま分析へ渡さない")
    if not principle_index:
        raise ValueError("CAST カタログが空のまま分析へ渡さない（UNASSESSED へ倒す）")

    refs = "\n".join(
        "- %s ｜ %s ｜ %s" % (key, title, statement)
        for key, title, statement in principle_index)
    return (
        "%s\n"
        "--- 事象の記録（これが唯一の入力。会話履歴は存在しない）---\n%s\n"
        "--- 統制構造（実在する要素だけ。id をそのまま使う）---\n%s\n"
        "--- CAST 検証原則（dedupe_key ｜ 題 ｜ 一文）---\n%s\n"
        "--- 一覧ここまで ---\n\n"
        "CAST_ANALYSIS_SCHEMA に適合する JSON だけを返す。"
        % (_CAST_CHARTER,
           json.dumps(incident, ensure_ascii=False, indent=2),
           control_structure_text, refs))


def verify_cast_analysis(analysis, known_element_ids, known_principle_keys):
    """統制欠陥の参照先の実在を照合する（分析の反幻覚 oracle）。

    返り値: (accepted_flaws, rejected_flaws)。rejected は理由を添えて返す。
    実在しない統制要素・カタログに無い規範鍵を指す欠陥は実装へ渡さない。
    """
    accepted, rejected = [], []
    elements = set(known_element_ids)
    keys = set(known_principle_keys)
    for flaw in analysis.get("control_flaws", []):
        problems = []
        if flaw.get("control_element_id") not in elements:
            problems.append("統制構造に無い要素 %r" % flaw.get("control_element_id"))
        unknown_refs = [r for r in flaw.get("normative_refs", []) if r not in keys]
        if unknown_refs:
            problems.append("カタログに無い規範鍵 %s" % unknown_refs[:3])
        if problems:
            rejected.append({"flaw": flaw, "problems": problems})
        else:
            accepted.append(flaw)
    return accepted, rejected


def leading_indicators_defined(analysis):
    """CAST_DONE の guard（orchestrator の TRANSITIONS と同名）。

    先行指標が一つ以上あり、どれも「どこで観測するか」と「何を異常とするか」を
    埋めていること。空文字での形式的な充足は通さない。
    """
    indicators = analysis.get("leading_indicators") or []
    if not indicators:
        return False
    for ind in indicators:
        for key in ("indicator", "observable", "where", "threshold"):
            if not str(ind.get(key) or "").strip():
                return False
    return True


_MAP_COVERAGE_CHARTER = """\
あなたは保証キャンペーンの MAP_COVERAGE 担当（jerg レーン＝検証計画と客観的証拠の
観点）である。検証原則の一つひとつを、下に示す doctrine の**現状の索引**と
突き合わせ、五値のどれかへ割り当てる。

五値の意味:
- 実装・試験・証拠あり … 原則が求めることが実装され、試験があり、証拠を指せる。
- 対応計画あり       … 実装は無いが、対応する決定や仕様が現に在る（gap に何が
                        足りないかを書く）。
- 非該当で理由あり   … この体系には当たらない（reason に、なぜ当たらないかを書く。
                        「対象外の領域だから」で終わらせず、境界の根拠を示す）。
- UNKNOWN            … 索引からは判定できない。判らないことを判らないと書く。
- UNASSESSED         … 前提が欠けて評価できない。

規律:
- **証拠ポインタの無い「実装・試験・証拠あり」を書かない。** evidence には索引に
  実在するものだけを書く: 文書 id（`SPEC-011`）・ファイルの場所
  （`plugin/scripts/docs-audit.py`）・監査の検査名（`adr_not_landed`）・
  リンタの検査コード（`MISSING_KEY`）・Hook のイベント名（`SessionEnd`）・
  `plugin/tests/test_x.py::test_名` の形。解決しないポインタは機械照合で外され、
  その割当は UNKNOWN へ落ちる。
- 索引に無いものを在ることにしない。索引は現状のすべてではないが、あなたが
  参照してよい唯一の現状である。読んでいないものを根拠にしない。
- 原則の言い回しが体系の語と違うだけの場合と、実際に機構が無い場合を区別する。
- 迷ったら「実装・試験・証拠あり」ではなく UNKNOWN。**緑へ倒さない。**
- recheck_trigger には「この割当を見直すべき出来事」を一文で書く。
"""


def build_map_coverage_prompt(principles, system_index_text):
    """MAP_COVERAGE の一回限りセッション用プロンプト。

    principles: [{key, title, statement, category, applicability,
                  suggested_oracle}, ...]（割当の対象だけ）。
    system_index_text: system_index.as_prompt_text() の平文。

    ここでも、実装者の会話・弁明・期待する結論を渡す口は作らない。
    """
    if not principles:
        raise ValueError("割当の対象が空のまま評価へ渡さない")
    if not system_index_text.strip():
        raise ValueError("現状の索引が空のまま評価へ渡さない（UNASSESSED へ倒す）")
    items = []
    for p in principles:
        items.append(
            "- key: %s\n  題: %s\n  原則: %s\n  分類: %s\n"
            "  当てはめ仮説: %s\n  想定 oracle: %s"
            % (p.get("key"), p.get("title"), p.get("statement"),
               p.get("category"), p.get("applicability"),
               p.get("suggested_oracle")))
    return (
        "%s\n--- doctrine の現状の索引 ---\n%s\n--- 索引ここまで ---\n\n"
        "--- 割当の対象（%d 件。すべてに一つずつ答える）---\n%s\n"
        "--- 対象ここまで ---\n\n"
        "COVERAGE_ASSIGNMENT_SCHEMA に適合する JSON だけを返す。"
        "assignments は対象と同じ %d 件で、key はそのまま写す。"
        % (_MAP_COVERAGE_CHARTER, system_index_text,
           len(principles), "\n".join(items), len(principles)))


def verify_coverage_assignments(assignments, resolve, requested_keys):
    """割当の証拠ポインタを索引と照合する（網羅の反幻覚 oracle）。

    resolve: ポインタ文字列 → 種別 or None（system_index.resolve_pointer の部分適用）。
    requested_keys: 依頼した key の集合。知らない key の割当は受け取らない。

    返り値: (accepted, downgraded, rejected)
    - accepted   … そのまま台帳へ入れてよい割当。
    - downgraded … 「実装・試験・証拠あり」だが解決する証拠が無く UNKNOWN へ落とした割当。
    - rejected   … 依頼していない key（台帳へ入れない）。
    """
    known = set(requested_keys)
    accepted, downgraded, rejected = [], [], []
    for a in assignments:
        if a.get("key") not in known:
            rejected.append({"assignment": a, "problem": "依頼していない key"})
            continue
        pointers = list(a.get("evidence") or [])
        resolved = [p for p in pointers if resolve(p)]
        unresolved = [p for p in pointers if not resolve(p)]
        a = dict(a)
        a["evidence"] = resolved
        if unresolved:
            a["unresolved_evidence"] = unresolved
        if a.get("disposition") == "実装・試験・証拠あり" and not resolved:
            a["original_disposition"] = a["disposition"]
            a["disposition"] = "UNKNOWN"
            a["reason"] = ("[証拠ポインタが索引で解決しないため UNKNOWN へ落とした] "
                           + str(a.get("reason") or ""))
            downgraded.append(a)
        else:
            accepted.append(a)
    return accepted, downgraded, rejected


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
