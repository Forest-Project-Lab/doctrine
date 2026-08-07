#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""MAP_COVERAGE レーンの決定論試験（SDK 不要・通信不要）。

凍結したいこと:
- 索引が実在するものだけを指し、実在しないポインタを解決しないこと。
- 証拠ポインタの無い「実装・試験・証拠あり」が UNKNOWN へ落ちること（緑へ倒さない）。
- 依頼していない key の割当を台帳へ入れないこと。
- 評価へ渡す口に、実装者の会話・弁明を入れる余地が無いこと。
"""
import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import map_coverage, prompts, schemas, system_index  # noqa: E402


def _assign(**over):
    base = {"key": "JERG:k1", "disposition": "実装・試験・証拠あり",
            "reason": "監査が検査を持つ", "evidence": ["adr_not_landed"],
            "recheck_trigger": "検査名の変更", "confidence": "high"}
    base.update(over)
    return base


class SystemIndexTest(unittest.TestCase):
    def setUp(self):
        self.idx = system_index.build()

    def test_index_is_not_empty(self):
        self.assertTrue(self.idx["documents"])
        self.assertTrue(self.idx["scripts"])
        self.assertTrue(self.idx["audit_checks"])

    def test_skill_list_matches_decided_inventory(self):
        """技能の一覧は SPEC-016 が正本（DECIDED-001 事実8・ADR-136）。索引が増減を映す。"""
        self.assertEqual(len(self.idx["skills"]), 8, self.idx["skills"])
        self.assertIn("system-map-draft", self.idx["skills"])

    def test_resolves_each_pointer_kind(self):
        kinds = {
            system_index.resolve_pointer(self.idx, self.idx["documents"][0]["id"]),
            system_index.resolve_pointer(self.idx, self.idx["audit_checks"][0]),
            system_index.resolve_pointer(self.idx, "plugin/scripts/docs-audit.py"),
            system_index.resolve_pointer(self.idx, "SessionEnd"),
        }
        self.assertEqual(
            kinds, {"document", "audit_check", "file", "hook_event"})

    def test_rejects_invented_pointers(self):
        for bogus in ("SPEC-9999", "plugin/scripts/does-not-exist.py",
                      "no_such_check", "", None,
                      "plugin/tests/test_termcheck.py::test_does_not_exist"):
            self.assertIsNone(system_index.resolve_pointer(self.idx, bogus), bogus)

    def test_test_pointer_needs_a_real_function(self):
        real = "plugin/tests/test_termcheck.py::test_hyphen_joined_identifier_is_one_token"
        self.assertEqual(system_index.resolve_pointer(self.idx, real), "test")

    def test_prompt_text_carries_the_index(self):
        text = system_index.as_prompt_text(self.idx)
        self.assertIn("SessionEnd", text)
        self.assertIn("plugin/scripts/docs-audit.py", text)
        self.assertIn(self.idx["documents"][0]["id"], text)


class VerifyAssignmentsTest(unittest.TestCase):
    def _resolve(self, pointer):
        return "audit_check" if pointer == "adr_not_landed" else None

    def test_resolvable_evidence_is_accepted(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign()], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down), len(rej)), (1, 0, 0))
        self.assertEqual(acc[0]["disposition"], "実装・試験・証拠あり")

    def test_green_without_evidence_is_downgraded(self):
        """証拠ポインタの無い『実装・試験・証拠あり』を書かない（ADR-115）。"""
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(evidence=[])], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down)), (0, 1))
        self.assertEqual(down[0]["disposition"], "UNKNOWN")
        self.assertEqual(down[0]["original_disposition"], "実装・試験・証拠あり")

    def test_unresolvable_evidence_is_downgraded_and_recorded(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(evidence=["SPEC-9999", "plugin/scripts/nope.py"])],
            self._resolve, ["JERG:k1"])
        self.assertEqual(len(down), 1)
        self.assertEqual(down[0]["disposition"], "UNKNOWN")
        self.assertEqual(len(down[0]["unresolved_evidence"]), 2)

    def test_other_dispositions_need_no_evidence(self):
        for disp in ("対応計画あり", "非該当で理由あり", "UNKNOWN", "UNASSESSED"):
            acc, down, _rej = prompts.verify_coverage_assignments(
                [_assign(disposition=disp, evidence=[])],
                self._resolve, ["JERG:k1"])
            self.assertEqual((len(acc), len(down)), (1, 0), disp)

    def test_unrequested_key_is_rejected(self):
        acc, down, rej = prompts.verify_coverage_assignments(
            [_assign(key="JERG:not-asked")], self._resolve, ["JERG:k1"])
        self.assertEqual((len(acc), len(down), len(rej)), (0, 0, 1))

    def test_unresolvable_pointers_are_stripped_from_evidence(self):
        acc, _down, _rej = prompts.verify_coverage_assignments(
            [_assign(evidence=["adr_not_landed", "SPEC-9999"])],
            self._resolve, ["JERG:k1"])
        self.assertEqual(acc[0]["evidence"], ["adr_not_landed"])
        self.assertEqual(acc[0]["unresolved_evidence"], ["SPEC-9999"])


class MapCoveragePromptTest(unittest.TestCase):
    def test_signature_has_no_context_parameter(self):
        params = inspect.signature(prompts.build_map_coverage_prompt).parameters
        self.assertEqual(list(params), ["principles", "system_index_text"])

    def test_rejects_empty_batch(self):
        with self.assertRaises(ValueError):
            prompts.build_map_coverage_prompt([], "索引")

    def test_rejects_empty_index(self):
        with self.assertRaises(ValueError):
            prompts.build_map_coverage_prompt([{"key": "k"}], "   ")

    def test_carries_keys_and_states_the_count(self):
        p = prompts.build_map_coverage_prompt(
            [{"key": "JERG:a", "title": "独立検証", "statement": "s",
              "category": "独立性", "applicability": "x", "suggested_oracle": "y"}],
            "索引の本文")
        self.assertIn("JERG:a", p)
        self.assertIn("索引の本文", p)
        self.assertIn("1 件", p)


class CanonStalenessSelectionTest(unittest.TestCase):
    """再判定の選別は正本 is_stale の規則に従う（ADR-143。INC-025 の再来の是正）。

    map_coverage は索引**全体**の指紋の比較を自前で持っていた —— ADR-130 が
    却下し、ADR-134 が正本側から取り除いた、まさにその形である。全体指紋は
    新しい文書や試験が入るだけで動くので、正本が挙げない項の再判定を黙って
    買い直す。選別と計数の規則は一つ（orchestrator.is_stale）でなければならない。
    """

    _CATEGORIES = ("documents", "audit_checks", "linter_codes", "scripts",
                   "test_files", "hooks", "skills")

    def _stamp(self, sha="a"):
        return {c: sha * 64 for c in self._CATEGORIES}

    def _now(self, **moved):
        cats = self._stamp()
        cats.update({k: v * 64 for k, v in moved.items()})
        return {"category_sha256": cats,
                "category_counts": {c: 10 for c in self._CATEGORIES}}

    def _entry(self, key, evidence, disposition="対応計画あり"):
        return {"key": key, "disposition": disposition, "evidence": evidence,
                "assigned_at": "2026-08-07T00:00:00Z",
                # 全体指紋は現行と食い違わせておく。旧規則ならこれだけで
                # 全項が選ばれた —— 選ばれないことが本試験の主張である。
                "assigned_by": {"index_sha256": "0" * 64,
                                "category_sha256": self._stamp(),
                                "category_counts": {c: 10 for c in
                                                    self._CATEGORIES}}}

    def test_map_coverage_selects_only_canon_stale_entries(self):
        resolve = {"ADR-051": "document", "adr_not_landed": "audit_check"}.get
        unchanged = self._entry("K:doc-cited", ["ADR-051"])
        moved = self._entry("K:check-cited", ["adr_not_landed"])
        fresh_unknown = {"key": "K:unmapped", "disposition": "UNKNOWN"}
        # 試験と監査の検査だけが動いた索引。文書は動いていないので、文書を
        # 引いた判定は古びない（試験 1 件の追加が全件を古びさせた INC-025）。
        now = self._now(test_files="z", audit_checks="z")
        got = map_coverage.select_todo(
            [unchanged, moved, fresh_unknown], now, resolve)
        self.assertEqual([e["key"] for e in got],
                         ["K:check-cited", "K:unmapped"])

    def test_settled_entries_are_never_selected(self):
        """終端は評価を買い直さない。再照合は決定論の口（recheck_evidence）が持つ。"""
        for disp in ("実装・試験・証拠あり", "非該当で理由あり"):
            e = self._entry("K:settled", ["adr_not_landed"], disposition=disp)
            got = map_coverage.select_todo(
                [e], self._now(audit_checks="z"),
                {"adr_not_landed": "audit_check"}.get)
            self.assertEqual(got, [], disp)

    def test_judged_unknown_is_not_reselected_when_nothing_moved(self):
        """割当済みの UNKNOWN は、索引が動かない限り引き直さない（INC-006）。"""
        e = self._entry("K:judged-unknown", [], disposition="UNKNOWN")
        self.assertEqual(
            map_coverage.select_todo([e], self._now(), lambda p: None), [])


class CoverageSchemaTest(unittest.TestCase):
    def test_minimal_assignment_validates(self):
        self.assertEqual(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            {"assignments": [_assign()]}), [])

    def test_unknown_disposition_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA,
            {"assignments": [_assign(disposition="たぶん大丈夫")]}))

    def test_empty_assignments_is_a_violation(self):
        self.assertTrue(schemas.validate(
            schemas.COVERAGE_ASSIGNMENT_SCHEMA, {"assignments": []}))


if __name__ == "__main__":
    unittest.main()
