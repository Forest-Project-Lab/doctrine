#!/usr/bin/env python3
# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""per-turn 性能の受入基準(ADR-047 の予告の実装)。

ADR-047: 「1 編集あたりのフック合計を 1 秒以内(1500 文書規模)とし、これを
受入基準へ足す方向とする(数値の確定は受入テストで詰める)」。本試験がその
確定である — 合成統治木 1,500 文書で、1 編集の対(ガード PreToolUse +
リンタ PostToolUse)の実時間を測り、1 秒の門で凍結する。

閾値の根拠: リンタとガードは編集された一ファイルだけを読む設計(NONGOAL
第5項)なので、木の規模にほぼ依存しない。実測はこの環境で対あたり約 0.1〜
0.3 秒であり、1 秒は共有の CI 実行環境の揺らぎを含めても破らない余裕を
持つ。これを超えたら、per-turn の経路に全件走査が紛れ込んだ疑いである。

合成文書は `depends_on` を持つ(ADR-075)。持たない木で測っていた間、この門は
守るべき経路を一度も通っていなかった: リンタの ICD 依存検査は `depends_on` が
空なら即座に降り、全件走査へ入らない。実際にはその先で依存グラフを丸ごと
組んでおり、O(N) の走査が per-turn の経路に居座ったまま門は緑だった。
規模を変えた二点で測り、費用が木の規模に比例して伸びないことも併せて凍結する。
"""
import json
import os
import shutil
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util  # noqa: E402

DOCS = 1500
BUDGET_SECONDS = 1.0   # ADR-047 の目安を受入の数値として確定する。


def _fm(i):
    # depends_on を必ず持たせる(ADR-075)。ICD 依存検査の経路を通すために要る。
    return ("---\nid: SPEC-%03d\ntitle: 合成 %d\ntype: SPEC\ndomain: perf\n"
            "status: current\nowner: t\nupdated: 2026-06-01\nsources: []\n"
            "depends_on: [SPEC-000]\n---\n\n"
            "# 合成 %d\n\n## 入出力\nx\n\n## 制約\nx\n\n## エラー時挙動\nx\n\n"
            "## 受入基準\nx\n" % (i, i, i))


class PerTurnHookBudgetTest(unittest.TestCase):
    def _build(self, count):
        """合成統治木を作り、(木の根, 編集対象) を返す。"""
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        spec_dir = os.path.join(root, "doctrine_docs", "perf", "spec")
        os.makedirs(os.path.join(root, "doctrine_docs", "_system"),
                    exist_ok=True)
        os.makedirs(spec_dir, exist_ok=True)
        for i in range(count):
            with open(os.path.join(spec_dir, "SPEC-%03d-p.md" % i), "w",
                      encoding="utf-8") as fh:
                fh.write(_fm(i))
        # 対象は必ず実在させる。以前は "SPEC-0001-p.md"(4 桁)を指しており、
        # 生成物は "SPEC-001-p.md"(3 桁)だったため、この門はずっと存在しない
        # ファイルを測っていた。読む対象が無ければ費用は当然出ない(ADR-075)。
        target = os.path.join(spec_dir, "SPEC-%03d-p.md" % 1)
        assert os.path.isfile(target), target
        return root, target

    def _pair_seconds(self, target):
        """1 編集の対(ガード PreToolUse + リンタ PostToolUse)の実時間。"""
        guard_stdin = {
            "hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": target, "old_string": "x",
                           "new_string": "y"},
        }
        linter_stdin = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"file_path": target},
        }
        # ウォームアップ一回(モジュール読み込みの初回費用を除く。フックの実運用
        # でも解釈系の起動はハーネス側の費用であり、ここで測るのは処理の費用)。
        _util.invoke("policy-guard", stdin_obj=dict(guard_stdin))
        _util.invoke("docs-linter", stdin_obj=dict(linter_stdin))

        start = time.monotonic()
        out, code = _util.invoke("policy-guard", stdin_obj=dict(guard_stdin))
        self.assertEqual(code, 0)
        if out.strip():
            json.loads(out)   # 応答が JSON として読めることも門に含める。
        out, code = _util.invoke("docs-linter", stdin_obj=dict(linter_stdin))
        self.assertEqual(code, 0)
        return time.monotonic() - start

    def test_one_edit_hook_pair_stays_within_the_budget_at_1500_docs(self):
        _root, target = self._build(DOCS)
        elapsed = self._pair_seconds(target)
        self.assertLess(
            elapsed, BUDGET_SECONDS,
            "1 編集のフック対が %.3f 秒かかり、ADR-047 の受入 %.1f 秒を超えた。"
            "per-turn の経路に全件走査が紛れ込んでいないか確かめること"
            % (elapsed, BUDGET_SECONDS))

    def test_linter_reads_only_the_edited_document(self):
        """リンタが開く統治文書は、編集された一件だけ(ADR-075)。

        時間の門は機械の速さに隠される。実際、旧実装(依存グラフを丸ごと組む)は
        1500 文書でも 1 秒の門を破らず、規模比の門(10 倍で 2 倍未満)すら通った。
        per-turn の約束「編集された一つの文書だけを点検する」(NONGOAL 第5項・
        仕様 §4.2)は量ではなく構造なので、読んだ件数で決定論的に凍結する。

        数えるのは共有の読み手(_frontmatter.parse_file / read_text)の呼び出しで
        あり、辞書や設定のような統治文書でない小物は対象から外す。
        """
        root, target = self._build(DOCS)
        # 入口は毎回読み直されるが、共有コアは sys.modules から再利用される。
        # よってここを差し替えれば、入口が誰を読んだかを数えられる。
        fm = _util.load_core("_frontmatter")
        docs_dir = os.path.abspath(os.path.join(root, "doctrine_docs"))
        opened = []
        real_read, real_parse = fm.read_text, fm.parse_file

        def _wrap(fn):
            def inner(path, *a, **kw):
                p = os.path.abspath(os.fspath(path))
                if p.startswith(docs_dir) and p.endswith(".md"):
                    opened.append(p)
                return fn(path, *a, **kw)
            return inner

        fm.read_text, fm.parse_file = _wrap(real_read), _wrap(real_parse)
        try:
            _out, code = _util.invoke("docs-linter", stdin_obj={
                "hook_event_name": "PostToolUse",
                "tool_input": {"file_path": target}})
        finally:
            fm.read_text, fm.parse_file = real_read, real_parse

        self.assertEqual(code, 0)
        distinct = sorted(set(opened))
        self.assertEqual(
            1, len(distinct),
            "リンタが統治文書を %d 件開いた(%s ほか)。per-turn は編集された一件"
            "だけを読む(NONGOAL 第5項)。兄弟文書を読む経路が紛れ込んでいる"
            % (len(distinct), distinct[:3]))
        # 開いた一件が編集対象であることまで見る。0 件や別件で通ると、差し替えが
        # 外れただけの空振りを「一件しか読まなかった」と読み違える。
        self.assertEqual([os.path.abspath(target)], distinct,
                         "計数が編集対象を捉えていない。この試験は空振りしている")


if __name__ == "__main__":
    unittest.main()
