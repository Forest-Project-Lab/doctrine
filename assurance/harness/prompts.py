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

# 指紋の取り方は一箇所に持つ（schemas は標準ライブラリだけに依存するので循環しない）。
from harness.schemas import sha256_of  # noqa: F401  (rubric_fingerprint が使う)

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


def build_discover_prompt(seed_facts, boundary, principle_index=()):
    """DISCOVER の一回限りセッション用プロンプト。

    seed_facts: 出発点となる事実の列（例: 直近の障害・規範の条項）。
    boundary: 対象システム境界の一文。
    principle_index: (鍵, 題, 一文) の列。出典として引ける鍵をここで示す。
        空でも組めるが、そのときは出典の機械照合ができない。
    """
    if not isinstance(seed_facts, (list, tuple)) or not seed_facts:
        raise ValueError("seed_facts は空でない列でなければならない")
    lines = [_DISCOVER_CHARTER,
             "対象システム境界: %s" % boundary,
             "",
             "出発点の事実（これ自体を疑ってもよい）:"]
    lines += ["- %s" % fact for fact in seed_facts]
    if principle_index:
        lines += ["", "引ける規範の鍵（鍵 ｜ 題 ｜ 一文）:"]
        lines += ["- %s ｜ %s ｜ %s" % (k, t, st)
                  for k, t, st in principle_index]
    lines += [
        "",
        "応答は SCENARIOS_SCHEMA に適合する JSON だけを返す（`scenarios` の配列）。"
        "各要素は scenario_id, normative_refs, system_boundary, loss, hazard,"
        " unsafe_control_action, event_sequence, fault, injection_point,"
        " expected_safe_behavior, oracle, falsification_signal, severity,"
        " confidence を必ず持つ。scenario_id は `SCN-` で始まる一意の識別子にする。"
        "normative_refs には、下に示した規範の鍵をそのまま書く。一覧に無い鍵は"
        "機械照合で外される（憶測の出典を書かない）。",
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

    判定の単位は**主張**（統制欠陥一件）である。規範（JERG L219・L479-481・L2491）が
    「検証とは客観的証拠の提示であり、証拠を伴わない主張は検証とみなさない」と定める
    以上、解決する出典を一つでも保つ主張は証拠を提示している。実在しない出典が
    混じっていたことは記録の欠陥であって、証拠の不在ではない。

    そこで網羅の割当（ADR-118）と同じ流儀に揃える —— 解決しない出典は外して残し、
    主張そのものは保つ。ただし外した事実は `citation_defect` として主張に刻み、
    その主張だけでは事象を閉じられない（`cast_analysis.settled` が求めるのは
    刻みの無い欠陥である）。捨てれば見逃しの理由を追えなくなる（CAST L3929）。

    返り値: (accepted_flaws, rejected_flaws)
    - accepted … 統制要素が実在し、解決する出典を一つ以上保つ主張。
    - rejected … 統制要素が実在しない、または解決する出典が一つも無い主張。
    """
    accepted, rejected = [], []
    elements = set(known_element_ids)
    keys = set(known_principle_keys)
    for flaw in analysis.get("control_flaws", []):
        refs = list(flaw.get("normative_refs") or [])
        resolved = [r for r in refs if r in keys]
        unknown_refs = [r for r in refs if r not in keys]
        problems = []
        if flaw.get("control_element_id") not in elements:
            problems.append("統制構造に無い要素 %r" % flaw.get("control_element_id"))
        if not resolved:
            problems.append("解決する規範鍵が一つも無い %s" % unknown_refs[:3])
        if problems:
            rejected.append({"flaw": flaw, "problems": problems})
            continue
        flaw = dict(flaw)
        flaw["normative_refs"] = resolved
        if unknown_refs:
            flaw["unresolved_refs"] = unknown_refs
            flaw["citation_defect"] = True
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
- 実装・試験・証拠あり … 原則が求めることが実装され、**機械が守っており**、証拠を指せる。
  ここでの「試験」は unittest に限らない —— 監査の検査・リンタの検査コード・Hook の
  イベント・スクリプトも、機械が守っている証拠である（床が実際に求めるのはこれで、
  決定や仕様だけでは足りない）。
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
  試験ファイルの場所（`plugin/tests/test_audit.py`）。解決しないポインタは
  機械照合で外され、その割当は UNKNOWN へ落ちる。
  **試験は名ではなくファイルで指す。**索引は試験ファイルと件数を渡すが、
  個々の試験の名は渡していない（1317 件を載せると入力が三倍近くになる）。
  渡していない名を書かせる形を案内しない —— 書けば当て推量になり、
  当て推量は機械照合で外れる（INC-038）。
- 索引に無いものを在ることにしない。索引は現状のすべてではないが、あなたが
  参照してよい唯一の現状である。読んでいないものを根拠にしない。
- 原則の言い回しが体系の語と違うだけの場合と、実際に機構が無い場合を区別する。
- 迷ったら「実装・試験・証拠あり」ではなく UNKNOWN。**緑へ倒さない。**
- recheck_trigger には「この割当を見直すべき出来事」を一文で書く。

境界の判定規則（ここで迷いが集中する。ADR-133）:
- **決定や仕様だけを証拠にして「実装・試験・証拠あり」を採らない。**決定は
  「そう決めた」ことの記録であって、決めたことが現に効いている証拠ではない。
  ADR や SPEC の id しか挙げられないなら「対応計画あり」とし、gap に
  「決めたが、それを働かせる機構が索引に無い」と書く。
- **事後に検出する機構を、事前に阻止することを求める原則の証拠にしない。**
  検出は阻止ではない。原則が「〜させない」「〜の前に〜を済ませる」を求めていて、
  挙げられる機構が「後から欠落を挙げる」ものしか無いなら「対応計画あり」とし、
  gap にその差（検出は在るが阻止は無い）を書く。
- 挙げた機構が原則の求めることの**一部**しか果たさないなら「対応計画あり」と
  し、gap に残りを書く。全部を果たすときだけ「実装・試験・証拠あり」を採る。
- 話題が同じだけの機構を証拠にしない。原則が求める働きと、機構が実際に果たす
  働きが同じかを見る。
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
        elif (a.get("disposition") == "実装・試験・証拠あり"
                and not _has_enforcing_pointer(resolved, resolve)):
            a["original_disposition"] = a["disposition"]
            a["disposition"] = "対応計画あり"
            a["reason"] = ("[証拠が決定・仕様だけなので 対応計画あり へ落とした] "
                           + str(a.get("reason") or ""))
            downgraded.append(a)
        else:
            accepted.append(a)
    return accepted, downgraded, rejected


# 「機構を指さない」ポインタの種別。決定と仕様は『そう決めた』ことの記録で
# あって、決めたことが現に効いている証拠ではない（ADR-133）。
_NON_ENFORCING_POINTER_KINDS = frozenset({"document"})


def _has_enforcing_pointer(pointers, resolve):
    """解決した証拠のうち、機構を指すものが一つでも在るか（ADR-133 の床）。

    **これは規準の全部ではなく、機械で決まるところだけの床である。**挙げられた
    機構が原則の求めることを実際に果たしているかは意味の判断であり、機械では
    閉じない（NONGOAL-001 第1項）。ここで落とせるのは「決定しか挙げられて
    いない」という、読まなくても判る形だけである。残りの幅は規準の文（憲章）と
    抜取りの独立再判定（ADR-132）が受け持つ。

    .md のファイル場所も文書の側に数える —— 置き場所で呼ばれただけの文書を
    機構と読ませない。
    """
    for p in pointers:
        kind = resolve(p)
        if kind in _NON_ENFORCING_POINTER_KINDS:
            continue
        if kind == "file" and str(p).strip().endswith(".md"):
            continue
        return True
    return False


def rubric_fingerprint():
    """採点規準の指紋。本文から導くので、本文を変えれば必ず動く。

    手で書いた版番号は本文とずれる（導入複製が版番号を据え置いたまま中身だけ
    古びた INC-019 と同じ形）。だから版は宣言せず、内容から取る。
    """
    return sha256_of(_MAP_COVERAGE_CHARTER)


def verify_scenarios(scenarios, known_principle_keys):
    """創出された scenario の出典を照合する（創出の反幻覚 oracle）。

    ADR-121 と同じ主張単位の規則にする —— 解決する出典を一つでも保つ scenario は
    残し、外した鍵を刻む。解決する出典がゼロの scenario だけを却下する。

    返り値: (accepted, rejected)
    """
    keys = set(known_principle_keys)
    accepted, rejected = [], []
    for scn in scenarios:
        refs = list(scn.get("normative_refs") or [])
        resolved = [r for r in refs if r in keys]
        unknown = [r for r in refs if r not in keys]
        if not resolved:
            rejected.append({"scenario": scn,
                             "problems": ["解決する規範鍵が一つも無い %s"
                                          % unknown[:3]]})
            continue
        scn = dict(scn)
        scn["normative_refs"] = resolved
        if unknown:
            scn["unresolved_refs"] = unknown
            scn["citation_defect"] = True
        accepted.append(scn)
    return accepted, rejected


def verify_verdicts(verdicts, requested_ids):
    """CHALLENGE の判定を、依頼した候補の id と突き合わせる。

    返り値: (matched, unrequested, missing)
    - matched      … 依頼した候補への判定。
    - unrequested  … 依頼していない id への判定（受け取らない）。
    - missing      … 判定が返ってこなかった候補の id（沈黙を ACCEPT と読まない）。
    """
    wanted = list(requested_ids)
    seen = set()
    matched, unrequested = [], []
    for v in verdicts:
        sid = v.get("scenario_id")
        if sid in wanted:
            seen.add(sid)
            matched.append(v)
        else:
            unrequested.append(v)
    missing = [sid for sid in wanted if sid not in seen]
    return matched, unrequested, missing


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
    return ("%s\n批判対象:\n%s\n\n"
            "CHALLENGE_SCHEMA に適合する JSON だけを返す（`verdicts` の配列）。"
            "**候補の一つひとつに一つの判定を返す。** 各判定は scenario_id を"
            "そのまま写し、verdict と reasons を必ず持つ。判定を返さなかった候補は"
            "沈黙として扱われ、ACCEPT とは読まれない。" % (
                _CHALLENGE_CHARTER, payload))


_CANDIDATE_FORMULATION_CHARTER = """\
あなたは保証キャンペーンの DISCOVER 担当である。事故分析が残した新規仮説の候補
（下の JSON）だけを受け取り、独立批判に掛けられる scenario へ定式化する。
分析セッションとの会話履歴は存在しないし、要求もしない。

制約:
- 定式化するのは渡された候補だけ。**渡されていない仮説を発明しない。**
  各 scenario の source_candidate に、元の候補の鍵（`INC-…#番号`）をそのまま
  書く。鍵の無い scenario・一覧に無い鍵を書いた scenario は機械照合で外される。
- 候補は仮説であり、判定済みの scenario ではない。定式化は受理ではない ——
  この後の独立批判（CHALLENGE）が別セッションで判定する。
- 各 scenario は反証可能であること: 観測可能な oracle と、偽だった場合に何が
  見えるか（falsification_signal）を必ず書く。
- 下の既存 scenario id の一覧と実質同一の候補は、scenario の duplicate_of に
  その id を書く。言い換えの増殖は独立批判を薄める。duplicate_of を書いた
  scenario は批判へは渡されず、出自だけが記帳される。
- normative_refs には、下に示した規範の鍵をそのまま書く。一覧に無い鍵は
  機械照合で外される（憶測の出典を書かない）。
- 観測可能な oracle に書き直せない候補は、無理に scenario にしない。出さな
  かった候補は台帳の側が dropped として理由つきで記帳する。思いつかないこと・
  書けないことを隠さない。
"""


def build_candidate_formulation_prompt(candidates, principle_index, boundary,
                                       existing_scenarios):
    """候補定式化の一回限りセッション用プロンプト（ADR-140）。

    candidates: orchestrator.cast_scenario_candidates の形の列
        （incident_id・index・hypothesis・oracle・falsification_signal・
        severity）。これが定式化の唯一の対象。
    principle_index: (鍵, 題, 一文) の列。出典として引ける鍵。
    boundary: 対象システム境界の一文。
    existing_scenarios: 既存の scenario id の列（重複の照合先）。

    引数は四つの構造化された入力だけ。会話履歴・弁明・期待する結論を渡す口は
    意図して作らない（CHALLENGE と同じ独立性の規律。ADR-115）。
    """
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError("candidates は空でない列でなければならない")
    payload = []
    for cand in candidates:
        if (not isinstance(cand, dict) or not cand.get("incident_id")
                or cand.get("index") is None):
            raise ValueError(
                "候補は incident_id と index を持つ構造化された記録で"
                "なければならない")
        payload.append({
            "source_candidate": "%s#%s" % (cand["incident_id"], cand["index"]),
            "hypothesis": cand.get("hypothesis") or "",
            "oracle": cand.get("oracle") or "",
            "falsification_signal": cand.get("falsification_signal") or "",
            "severity": cand.get("severity") or "",
        })
    if not str(boundary or "").strip():
        raise ValueError("システム境界が空のまま定式化へ渡さない")
    if not principle_index:
        raise ValueError("規範の鍵が空のまま定式化へ渡さない（UNASSESSED へ倒す）")
    if not isinstance(existing_scenarios, (list, tuple)):
        raise ValueError("existing_scenarios は scenario id の列でなければならない")
    lines = [_CANDIDATE_FORMULATION_CHARTER,
             "対象システム境界: %s" % boundary,
             "",
             "--- 定式化の対象（事故分析の新規仮説候補。これが唯一の入力）---",
             json.dumps(payload, ensure_ascii=False, indent=2),
             "--- 対象ここまで ---",
             "",
             "既存の scenario id（実質同一なら duplicate_of に書く）:"]
    lines += ["- %s" % sid for sid in existing_scenarios] or ["- (無し)"]
    lines += ["", "引ける規範の鍵（鍵 ｜ 題 ｜ 一文）:"]
    lines += ["- %s ｜ %s ｜ %s" % (k, t, st)
              for k, t, st in principle_index]
    lines += [
        "",
        "応答は SCENARIOS_SCHEMA に適合する JSON だけを返す（`scenarios` の配列）。"
        "各要素は scenario_id, normative_refs, system_boundary, loss, hazard,"
        " unsafe_control_action, event_sequence, fault, injection_point,"
        " expected_safe_behavior, oracle, falsification_signal, severity,"
        " confidence を必ず持ち、source_candidate に元の候補の鍵をそのまま書く。"
        "scenario_id は `SCN-` で始まる一意の識別子にする。",
    ]
    return "\n".join(lines)


_FORMALIZE_CHARTER = """\
あなたは保証キャンペーンの FORMALIZE 担当（jerg レーン＝検証計画と客観的証拠の
観点）である。批判を生き残った失敗仮説（下の JSON）だけを受け取り、一件ごとに
検証計画を審査する。DISCOVER・CHALLENGE との会話履歴は存在しないし、要求もしない。

規律:
- 検証は客観的証拠の提示に基づく。AI の同意・もっともらしさは証拠ではない。
- oracle は**実装の前に**観測可能であること。未来の実装が生む観測に依存する計画は
  承認しない（先に赤を再現できない計画は、修正の効果を測れない）。
- 反証条件の無い計画を承認しない。before_fix_fails_when（修正前に何が FAIL するか）
  と after_fix_passes_when（修正後に何が PASS するか）は、どちらも具体の観測で書く。
- oracle が観測不能な scenario は REJECT し、reasons に何が観測できないかを書く。
- red_reproduction_design の procedure は、別セッションが手順だけで再現できる粒度で
  書く。injection_point は実在する場所を指し、isolation には破壊的操作をどこへ
  隔離するか（一時ディレクトリ・使い捨て fixture・worktree）を必ず書く。
- evidence_spec には、赤の証拠をどの成果物（artifact）に残し、何を必ず記録するか
  （must_record）を書く。記録の無い再現は証拠にならない。
- normative_refs には、下に示す規範の鍵を**そのまま**書く。一覧に無い鍵は機械照合で
  外される（憶測の出典を書かない）。
- 迷ったら APPROVE ではなく UNKNOWN。**承認へ倒さない。**
"""


def build_formalize_prompt(scenarios_json, principle_index):
    """FORMALIZE の一回限りセッション用プロンプト。

    scenarios_json: 批判を生き残った scenario の構造化 JSON（列または文字列）だけ。
    principle_index: [(dedupe_key, title, statement), ...]（jerg カタログ）。

    実装者の会話・弁明・期待する結論を渡す口は意図して作らない
    （CHALLENGE と同じ独立性の規律。ADR-115）。
    """
    if isinstance(scenarios_json, (dict, list)):
        if not scenarios_json:
            raise ValueError("空の scenario 列は審査に渡さない")
        payload = json.dumps(scenarios_json, ensure_ascii=False, indent=2)
    elif isinstance(scenarios_json, str) and scenarios_json.strip():
        json.loads(scenarios_json)  # 構造化されていない文字列は拒否する
        payload = scenarios_json
    else:
        raise ValueError("生き残った scenario の構造化 JSON だけを受け取る")
    if not principle_index:
        raise ValueError("jerg カタログが空のまま審査へ渡さない（UNASSESSED へ倒す）")
    refs = "\n".join("- %s ｜ %s ｜ %s" % (key, title, statement)
                     for key, title, statement in principle_index)
    return (
        "%s\n--- 審査対象（批判を生き残った scenario。これが唯一の入力）---\n%s\n"
        "--- 引ける規範の鍵（dedupe_key ｜ 題 ｜ 一文）---\n%s\n"
        "--- 一覧ここまで ---\n\n"
        "FORMALIZE_PLAN_SCHEMA に適合する JSON だけを返す（`plans` の配列）。"
        "**scenario の一つひとつに一つの計画を返す。** 各計画は scenario_id を"
        "そのまま写し、verdict・reasons・red_reproduction_design・"
        "acceptance_criteria・evidence_spec・normative_refs を必ず持つ。"
        "計画を返さなかった scenario は沈黙として扱われ、APPROVE とは読まれない。"
        % (_FORMALIZE_CHARTER, payload, refs))


def verify_formalize_plans(plans, known_principle_keys, requested_ids):
    """FORMALIZE の計画を、依頼した scenario と規範の鍵に突き合わせる。

    出典は ADR-121 の主張単位の規則 —— 解決する鍵を一つでも保つ計画は残し、
    解決しない鍵は外して `citation_defect` を刻む。解決する鍵がゼロの計画は
    受け取らない（その scenario は沈黙側に残る）。

    返り値: (matched, unrequested, missing)
    - matched      … 依頼した scenario への、出典照合を通った計画。
    - unrequested  … 依頼していない id への計画（受け取らない）。
    - missing      … 計画が返ってこなかった scenario の id（沈黙を APPROVE と
                     読まない。出典ゼロで却下された計画の id もここに残る）。
    """
    keys = set(known_principle_keys)
    wanted = list(requested_ids)
    seen = set()
    matched, unrequested = [], []
    for plan in plans:
        sid = plan.get("scenario_id")
        if sid not in wanted:
            unrequested.append(plan)
            continue
        refs = list(plan.get("normative_refs") or [])
        resolved = [r for r in refs if r in keys]
        unknown = [r for r in refs if r not in keys]
        if not resolved:
            # 解決する出典がゼロの計画は台帳へ入れない。scenario は沈黙のまま
            # 残り、unformalized_survivors が挙げ続ける（ADR-121・ADR-138）。
            continue
        plan = dict(plan)
        plan["normative_refs"] = resolved
        if unknown:
            plan["unresolved_refs"] = unknown
            plan["citation_defect"] = True
        seen.add(sid)
        matched.append(plan)
    missing = [sid for sid in wanted if sid not in seen]
    return matched, unrequested, missing


def oracle_observable(plan):
    """PLAN_APPROVED の guard（orchestrator の TRANSITIONS と同名）。

    verdict が APPROVE で、再現手順（procedure の全段）・injection_point・
    isolation・両方の受入条件・evidence_spec のすべてが空白でないこと。
    空文字での形式的な充足は通さない（leading_indicators_defined と同じ流儀）。
    REJECT・UNKNOWN の計画は、欄が埋まっていても承認とは読まない。
    """
    if plan.get("verdict") != "APPROVE":
        return False
    design = plan.get("red_reproduction_design") or {}
    procedure = design.get("procedure") or []
    if not procedure:
        return False
    for step in procedure:
        if not str(step or "").strip():
            return False
    for key in ("injection_point", "isolation"):
        if not str(design.get(key) or "").strip():
            return False
    criteria = plan.get("acceptance_criteria") or {}
    for key in ("before_fix_fails_when", "after_fix_passes_when"):
        if not str(criteria.get(key) or "").strip():
            return False
    spec = plan.get("evidence_spec") or {}
    if not str(spec.get("artifact") or "").strip():
        return False
    must = spec.get("must_record") or []
    if not must:
        return False
    for item in must:
        if not str(item or "").strip():
            return False
    return True


_VERIFY_CHARTER = """\
あなたは保証キャンペーンの VERIFY 担当（jerg レーン＝検証計画と客観的証拠の
観点）である。修正の主張（下の JSON）だけを受け取り、独立に検証する。
実装者との会話履歴は存在しないし、要求もしない。

規律:
- AI の一致は客観的証拠ではない。あなたの判定も含めて、証拠は与えられた観測
  （赤の記録・diff・修正後の観測）だけである。観測に無いことを補完しない。
- **緑のスイートは、修正が赤の原因へ効いた証明ではない。**修正前に FAIL した
  当の観測（red_evidence）が、この diff によって PASS へ変わったかを見る。
  別の理由で緑になった可能性（試験の削除・条件の緩和・偶然）を疑う。
- **oracle を変える修正を疑う。**diff が判定基準・試験・閾値の側を書き換えて
  いるなら、それは修正ではなく基準の緩和でありうる。checks の green_is_green を
  FAIL か UNKNOWN にし、reasons に書く。
- **一主題でない diff を疑う。**複数の無関係な変更が混ざった diff は、どの変更が
  効いたかを判別できない。single_change を FAIL にする。
- 判定は PASS / FAIL / UNKNOWN。迷ったら PASS ではなく UNKNOWN。
"""


def build_verify_prompt(verify_input_json):
    """VERIFY の一回限りセッション用プロンプト。

    引数は構造化された一つの対象 {target_id, claim, red_evidence, diff,
    post_fix_observation} だけ（dict または JSON 文字列）。
    会話履歴・弁明を足す口は意図して作らない（CHALLENGE と同じ独立性）。
    """
    if isinstance(verify_input_json, dict):
        if not verify_input_json.get("target_id"):
            raise ValueError("target_id を持つ構造化された対象だけを受け取る")
        payload = json.dumps(verify_input_json, ensure_ascii=False, indent=2)
    elif isinstance(verify_input_json, str) and verify_input_json.strip():
        parsed = json.loads(verify_input_json)  # 構造化されていない文字列は拒否
        if not isinstance(parsed, dict) or not parsed.get("target_id"):
            raise ValueError("target_id を持つ構造化された対象だけを受け取る")
        payload = verify_input_json
    else:
        raise ValueError("検証対象の構造化 JSON だけを受け取る")
    return (
        "%s\n--- 検証対象（これが唯一の入力。会話履歴は存在しない）---\n%s\n"
        "--- 対象ここまで ---\n\n"
        "VERIFY_RECORD_SCHEMA に適合する JSON だけを返す。target_id をそのまま"
        "写し、verdict・reasons・checks（red_was_red / green_is_green / "
        "single_change の三値）を必ず持つ。判定できない check は UNKNOWN と書く"
        "（沈黙や省略は PASS とは読まれない）。" % (_VERIFY_CHARTER, payload))


_ASSUMPTION_CHARTER = """\
あなたは保証キャンペーンの想定検証の担当（jerg レーン＝検証計画と客観的証拠の
観点）である。想定の登記（下の JSON）だけを受け取り、観測に照らして想定が
成り立つかを独立に判じる。実装者との会話履歴は存在しないし、要求もしない。

規律:
- 証拠は与えられた観測（observations・observation_history）だけである。観測に
  無いことを補完しない。観測が古い・欠けているなら、それ自体を reasons に書く。
- AI の一致は客観的証拠ではない。あなたの判定は「観測が想定をどう裏付けるか
  （または反するか）」の読みであり、観測の代わりにはならない。
- 判定は PASS（観測が想定を支える）/ FAIL（観測が想定に反する）/
  UNKNOWN（観測からは判じられない）。迷ったら PASS ではなく UNKNOWN。
"""


def build_assumption_verification_prompt(assumption_json):
    """想定検証の一回限りセッション用プロンプト（ADR-126・ADR-144）。

    引数は構造化された一つの登記 {asm_id, assumption, leading_indicators,
    observations, observation_history} だけ。会話・弁明の口は作らない。
    """
    if isinstance(assumption_json, dict):
        if not assumption_json.get("asm_id"):
            raise ValueError("asm_id を持つ構造化された登記だけを受け取る")
        payload = json.dumps(assumption_json, ensure_ascii=False, indent=2)
    elif isinstance(assumption_json, str) and assumption_json.strip():
        parsed = json.loads(assumption_json)
        if not isinstance(parsed, dict) or not parsed.get("asm_id"):
            raise ValueError("asm_id を持つ構造化された登記だけを受け取る")
        payload = assumption_json
    else:
        raise ValueError("想定の構造化 JSON だけを受け取る")
    return (
        "%s\n--- 想定の登記（これが唯一の入力。会話履歴は存在しない）---\n%s\n"
        "--- 登記ここまで ---\n\n"
        "ASSUMPTION_VERDICT_SCHEMA に適合する JSON だけを返す。asm_id をそのまま"
        "写し、holds（PASS/FAIL/UNKNOWN）と reasons を必ず持つ。"
        % (_ASSUMPTION_CHARTER, payload))
