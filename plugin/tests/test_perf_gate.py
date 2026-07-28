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
    return ("---\nid: SPEC-%03d\ntitle: 合成 %d\ntype: SPEC\ndomain: perf\n"
            "status: current\nowner: t\nupdated: 2026-06-01\nsources: []\n---\n\n"
            "# 合成 %d\n\n## 入出力\nx\n\n## 制約\nx\n\n## エラー時挙動\nx\n\n"
            "## 受入基準\nx\n" % (i, i, i))


class PerTurnHookBudgetTest(unittest.TestCase):
    def test_one_edit_hook_pair_stays_within_the_budget_at_1500_docs(self):
        root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        spec_dir = os.path.join(root, "doctrine_docs", "perf", "spec")
        os.makedirs(os.path.join(root, "doctrine_docs", "_system"),
                    exist_ok=True)
        os.makedirs(spec_dir, exist_ok=True)
        for i in range(DOCS):
            with open(os.path.join(spec_dir, "SPEC-%03d-p.md" % i), "w",
                      encoding="utf-8") as fh:
                fh.write(_fm(i))
        target = os.path.join(spec_dir, "SPEC-0001-p.md")

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
        elapsed = time.monotonic() - start

        self.assertLess(
            elapsed, BUDGET_SECONDS,
            "1 編集のフック対が %.3f 秒かかり、ADR-047 の受入 %.1f 秒を超えた。"
            "per-turn の経路に全件走査が紛れ込んでいないか確かめること"
            % (elapsed, BUDGET_SECONDS))


if __name__ == "__main__":
    unittest.main()
