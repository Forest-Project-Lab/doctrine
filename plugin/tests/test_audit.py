# doctrine:exempt 受入の対応は TEST 文書の sources が持つ。コード側と二重に結ばない(ADR-067)
"""Tests for docs-audit.py (full-corpus audit, SessionEnd/CI) — MASTER §5.5, slice 05 PART B.

Covers every §4.2 audit finding plus the audit↔inject handshake (critique gap C3):
- dead_link (R4): TC-082 pass, TC-083 fail.
- review_by overrun incl. DECIDED/WATCH (R2): TC-084 pass, TC-085/086 fail,
  missing review_by on DECIDED/WATCH = error.
- stale_draft (R8/R2): TC-088 pass, TC-089 fail.
- orphan conjunction 逆参照ゼロ∧stale∧reproducible (R1/R8): TC-090/092 pass,
  TC-091 fail, TC-121 依存-not-参照 distinction.
- reverse_orphan req_no_spec + spec_no_test (R3/R8): TC-093 pass, TC-094/095 fail.
- canonical_conflict (R8): TC-096 pass, TC-097 fail, TC-125 superseded carrier.
- icd_dependency_violation (R7): pseudo-spec message.
- projection_drift (R1/R8): TC-098 pass, TC-099/100 fail.
- near_duplicate advisory Jaccard (R8): TC-126 advisory not error.
- SessionEnd handshake: --json --summary-out --fail-on never non-blocking,
  atomic write, exit 0; --fail-on error gates CI.
- audit summary schema docs-audit/1 round-trips as valid JSON (critique gap).

All dates controlled via --today. Stdlib unittest only.
"""
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util

TODAY = "2026-06-29"


def _fm(doc_id, type_code, domain, status="current", **extra):
    fm = {
        "id": doc_id,
        "title": doc_id,
        "type": type_code,
        "domain": domain,
        "status": status,
        "owner": "t",
        "updated": "2026-06-01",
        "sources": [],
    }
    fm.update(extra)
    return fm


def _loc(domain, type_code, doc_id):
    if type_code == "ICD":
        return "docs/%s/ICD.md" % domain
    if type_code in ("OVERVIEW", "GLOSSARY", "CTXMAP", "DECIDED", "NONGOAL", "WATCH"):
        # _system singletons; filename derives from a stable map
        names = {
            "OVERVIEW": "overview.md", "GLOSSARY": "glossary.md",
            "CTXMAP": "context-map.md", "DECIDED": "decided-facts.md",
            "NONGOAL": "non-goals.md", "WATCH": "watch.md",
        }
        return "docs/_system/%s" % names[type_code]
    sub = {
        "REQ": "", "SPEC": "spec/", "TEST": "test/", "IMPL": "implementation/",
        "ADR": "decisions/", "DATA": "spec/", "API": "spec/",
        "RESEARCH": "research/",
    }.get(type_code, "")
    return "docs/%s/%s%s.md" % (domain, sub, doc_id)


class AuditBase(unittest.TestCase):
    def build(self, docs, projection_bodies=None):
        """docs: list of (fm_dict, body). Writes each at its §3.2 location.

        projection_bodies lets a caller override the body for projection docs.
        Returns docs root (the 'docs' dir under the temp tree).
        """
        files = {}
        for fm, body in docs:
            relpath = _loc(fm["domain"], fm["type"], fm["id"])
            files[relpath] = _util.fm_block(fm) + (body or "")
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def audit_json(self, docs_root, extra_argv=None):
        argv = ["--root", docs_root, "--json", "--today", TODAY]
        if extra_argv:
            argv += extra_argv
        out, code = _util.invoke("docs-audit", argv)
        data = json.loads(out.strip().splitlines()[-1])
        return data, code

    def checks_for(self, data, check):
        return [f for f in data["findings"] if f["check"] == check]


# --- dead_link (TC-082/083, R4) -------------------------------------------

class DeadLinkTest(AuditBase):
    def test_all_resolve_pass(self):
        """TC-082: all depends_on/links resolve -> no dead_link."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "本文"),
            (_fm("REQ-1", "REQ", "billing"), "本文"),
        ])
        data, code = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "dead_link"), [])

    def test_dangling_dep_fail(self):
        """TC-083: depends_on a non-existent id -> dead_link error."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "本文"),
        ])
        data, code = self.audit_json(root)
        dl = self.checks_for(data, "dead_link")
        self.assertTrue(any(f["refs"] == ["SPEC-99"] for f in dl))
        self.assertTrue(all(f["severity"] == "error" for f in dl))


# --- checks_run 検証器の実行証跡 (#95) -------------------------------------

class ChecksRunTest(AuditBase):
    def test_summary_lists_checks_run(self):
        """#95: 要約に checks_run(この版が走らせた検査の一覧)が載る。0 件の検査と
        走らなかった検査を区別できるようにする(沈黙する検証器の禁止。R11)。"""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "本文"),
            (_fm("REQ-1", "REQ", "billing"), "本文"),
        ])
        data, _ = self.audit_json(root)
        self.assertIn("checks_run", data)
        cr = data["checks_run"]
        # 主要な検査が漏れなく載っている(黙って消えたら気づける)。
        for name in ("dead_link", "dep_cycle", "reverse_orphan_spec_no_test",
                     "ext_anchor_broken", "projection_drift", "memory_shadow"):
            self.assertIn(name, cr)
        self.assertEqual(len(cr), len(set(cr)), "checks_run に重複がある")

    def test_every_emitted_check_is_declared(self):
        """発火した所見の check 名は、必ず checks_run に宣言済みであること
        (未宣言の検査名が出る=一覧の更新漏れ、を凍結する)。"""
        # 多くの検査を誘発する木: 循環・逆孤児・dead link。
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-2"]), "本文 [R1]"),
            (_fm("SPEC-2", "SPEC", "billing", depends_on=["SPEC-1"]), "本文 [R1]"),
            (_fm("SPEC-3", "SPEC", "billing", depends_on=["NOPE-9"]), "本文 [R1]"),
        ])
        data, _ = self.audit_json(root)
        declared = set(data["checks_run"])
        for f in data["findings"]:
            self.assertIn(f["check"], declared,
                          "未宣言の検査名 %s(checks_run 更新漏れ)" % f["check"])


# --- ext_anchor hash (ADR-039 / #70) --------------------------------------

class ExtHashTest(AuditBase):
    def _ext_body(self, target, check, digest=None):
        body = ("# ext\n## 期待\n- 対象: `%s`\n- 検査: %s\n" % (target, check))
        if digest is not None:
            body += "- 指紋: sha256:%s\n" % digest
        return body

    def _repo_with_target(self, ext_body, target_rel, target_bytes):
        import hashlib as _hl
        fm = _fm("EXT-1", "EXT", "billing")
        docs_root = self.build([(fm, ext_body)])
        root = os.path.dirname(docs_root)
        tgt = os.path.join(root, target_rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        with open(tgt, "wb") as fh:
            fh.write(target_bytes)
        digest = _hl.sha256(target_bytes).hexdigest()
        return docs_root, digest

    def test_hash_match_is_silent(self):
        data_bytes = b"a,b\n1,2\n"
        # 先に digest を計算し、その値を埋めた EXT で作り直す。
        import hashlib as _hl
        digest = _hl.sha256(data_bytes).hexdigest()
        body = self._ext_body("data/x.csv", "hash", digest)
        docs_root, _ = self._repo_with_target(body, "data/x.csv", data_bytes)
        data, _ = self.audit_json(docs_root)
        self.assertEqual(self.checks_for(data, "ext_anchor_broken"), [])

    def test_hash_mismatch_warns(self):
        import hashlib as _hl
        digest = _hl.sha256(b"OLD").hexdigest()
        body = self._ext_body("data/x.csv", "hash", digest)
        docs_root, _ = self._repo_with_target(body, "data/x.csv", b"NEW-CONTENT")
        data, _ = self.audit_json(docs_root)
        f = self.checks_for(data, "ext_anchor_broken")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "warn")
        self.assertIn("一致しない", f[0]["message"])

    def test_hash_without_digest_warns_not_silent(self):
        body = self._ext_body("data/x.csv", "hash")  # 指紋の行なし
        docs_root, _ = self._repo_with_target(body, "data/x.csv", b"x")
        data, _ = self.audit_json(docs_root)
        f = self.checks_for(data, "ext_anchor_broken")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["severity"], "warn")

    def test_hash_missing_target_is_error(self):
        body = self._ext_body("data/gone.csv", "hash", "0" * 64)
        docs_root = self.build([(_fm("EXT-1", "EXT", "billing"), body)])
        data, _ = self.audit_json(docs_root)
        f = self.checks_for(data, "ext_anchor_broken")
        self.assertTrue(any(x["severity"] == "error" for x in f))


# --- dep_cycle (ADR-038 / #89) --------------------------------------------

class DepCycleTest(AuditBase):
    def test_no_cycle_no_finding(self):
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "本文"),
            (_fm("REQ-1", "REQ", "billing"), "本文"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "dep_cycle"), [])

    def test_self_dependency_warned(self):
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-1"]), "本文"),
        ])
        data, _ = self.audit_json(root)
        cyc = self.checks_for(data, "dep_cycle")
        self.assertEqual(len(cyc), 1)
        self.assertEqual(cyc[0]["severity"], "warn")
        self.assertIn("自己依存", cyc[0]["message"])

    def test_multi_node_cycle_warned(self):
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-2"]), "本文"),
            (_fm("SPEC-2", "SPEC", "billing", depends_on=["SPEC-3"]), "本文"),
            (_fm("SPEC-3", "SPEC", "billing", depends_on=["SPEC-1"]), "本文"),
        ])
        data, _ = self.audit_json(root)
        cyc = self.checks_for(data, "dep_cycle")
        self.assertEqual(len(cyc), 1)
        self.assertEqual(cyc[0]["severity"], "warn")
        self.assertIn("循環", cyc[0]["message"])


# --- review_by overrun (TC-084/085/086, R2) -------------------------------

class ReviewByTest(AuditBase):
    def test_future_review_by_pass(self):
        """TC-084: DECIDED review_by in the future -> no overrun."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2027-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "review_by_overrun"), [])

    def test_past_review_by_decided_fail(self):
        """TC-085: DECIDED review_by past -> warn overrun."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        rb = self.checks_for(data, "review_by_overrun")
        self.assertEqual(len(rb), 1)
        self.assertEqual(rb[0]["severity"], "warn")

    def test_past_review_by_watch_fail(self):
        """TC-086: WATCH review_by past -> warn overrun (DECIDED/WATCH included)."""
        root = self.build([
            (_fm("WATCH-1", "WATCH", "billing", review_by="2026-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(len(self.checks_for(data, "review_by_overrun")), 1)

    def test_missing_review_by_on_decided_is_error(self):
        """MASTER §5.5: missing review_by on DECIDED/WATCH = error severity."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        rb = self.checks_for(data, "review_by_overrun")
        self.assertEqual(len(rb), 1)
        self.assertEqual(rb[0]["severity"], "error")

    def test_review_by_due_today_not_overrun(self):
        """review_by == today(期限当日)はまだ超過ではない(< の境界)。"""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by=TODAY), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "review_by_overrun"), [])


# --- stale_draft (TC-088/089, R8/R2) --------------------------------------

class StaleDraftTest(AuditBase):
    def test_recent_draft_pass(self):
        """TC-088: RESEARCH draft recently updated -> not stale."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stale_draft"), [])

    def test_old_draft_fail(self):
        """TC-089: RESEARCH draft updated long past -> stale_draft warn."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stale_draft")
        self.assertEqual(len(sd), 1)
        self.assertEqual(sd[0]["severity"], "warn")

    def test_draft_with_broken_updated_is_stale(self):
        """updated が解せない draft は古び扱い(不明は安全側 = stale)。"""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="not-a-date", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stale_draft")
        self.assertEqual(len(sd), 1)
        self.assertEqual(sd[0]["severity"], "warn")


# --- orphan conjunction (TC-090/091/092/121, R1/R8) -----------------------

class OrphanTest(AuditBase):
    def test_depended_on_pass(self):
        """TC-090: doc depended on by a current doc -> not orphan."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["RESEARCH-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_conjunction_fail(self):
        """TC-091: zero reverse-deps ∧ stale ∧ reproducible -> orphan error."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "RESEARCH-1")
        self.assertEqual(orph[0]["severity"], "error")

    def test_not_stale_no_orphan(self):
        """TC-092: zero reverse-deps but recently updated -> NOT orphan."""
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_reference_not_dependency_still_orphan(self):
        """TC-121: a mere body 参照 (link) does NOT save from orphan; only 依存 does."""
        # SPEC-2 mentions RESEARCH-1 in its BODY (参照) but does not depends_on it.
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2025-01-01", llm_context="never"), "x"),
            (_fm("SPEC-2", "SPEC", "billing"), "see RESEARCH-1 for context"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertTrue(any(f["doc_id"] == "RESEARCH-1" for f in orph))

    def test_icd_never_orphan(self):
        """Orphan excludes ICD (entry point) even with zero reverse-refs."""
        root = self.build([
            (_fm("ICD-1", "ICD", "billing", updated="2025-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_task_spec_stale_zero_dep_without_reproducible_not_orphan(self):
        """TC #12(1): current SPEC, llm_context:task, stale, zero-dep, NO reproducible
        => NOT orphan. The 'reproducible' conjunct must guard this false positive.

        A normal task-context SPEC that is merely stale and undepended-on is NOT
        reproducible (no reproducible:true, not RESEARCH, not llm_context:never),
        so the third conjunct (再現可能) fails and it is not flagged.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="task", updated="2025-01-01"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_task_spec_stale_zero_dep_with_reproducible_is_orphan(self):
        """TC #12(2): same current SPEC but reproducible:true => orphan (error).

        The third branch of _is_reproducible fires only because build_graph now
        copies the 'reproducible' field into the node dict (defect #06). Without
        that field the node.get('reproducible') would be None and this would
        silently NOT be flagged.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="task", updated="2025-01-01", reproducible=True), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "SPEC-1")
        self.assertEqual(orph[0]["severity"], "error")

    def test_stale_zero_dep_projection_not_orphan(self):
        """TC #13(a): a stale, zero-dep OVERVIEW projection is NOT orphan.

        Projections are excluded from the orphan check per MASTER §5.5
        (entry points / always-injected), regardless of staleness.
        """
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system", updated="2025-01-01"),
             "描画される。手で編集しない。\n"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_stale_zero_dep_always_doc_not_orphan(self):
        """TC #13(b): a stale, zero-dep llm_context:always doc is NOT orphan.

        llm_context:always is excluded from the orphan check per MASTER §5.5,
        even when stale and undepended-on. Use reproducible:true to show the
        exclusion fires BEFORE the reproducible conjunct could.
        """
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="current",
                 llm_context="always", updated="2025-01-01",
                 reproducible=True), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "orphan"), [])

    def test_orphan_review_by_boundary(self):
        """review_by 超過は陳腐化(orphan 成立)、当日はまだ非陳腐化(< の境界)。

        updated は最近(180 日閾値未満)にして updated 経由の陳腐化を切り、
        review_by 経由の陳腐化分岐だけを検証する。
        """
        # 過去の review_by + 最近の updated -> review_by 経由で orphan。
        root = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", review_by="2026-06-28",
                 llm_context="never"), "x"),
        ])
        data, _ = self.audit_json(root)
        orph = self.checks_for(data, "orphan")
        self.assertEqual(len(orph), 1)
        self.assertEqual(orph[0]["doc_id"], "RESEARCH-1")
        # review_by == today -> まだ陳腐化ではない -> not orphan。
        root2 = self.build([
            (_fm("RESEARCH-1", "RESEARCH", "billing", status="draft",
                 updated="2026-06-20", review_by=TODAY,
                 llm_context="never"), "x"),
        ])
        data2, _ = self.audit_json(root2)
        self.assertEqual(self.checks_for(data2, "orphan"), [])


# --- reverse_orphan (TC-093/094/095, R3/R8) -------------------------------

class ReverseOrphanTest(AuditBase):
    def test_complete_chain_pass(self):
        """TC-093: every REQ has SPEC, every SPEC has TEST -> no reverse-orphan."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
            (_fm("TEST-1", "TEST", "billing", depends_on=["SPEC-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "reverse_orphan_req_no_spec"), [])
        self.assertEqual(self.checks_for(data, "reverse_orphan_spec_no_test"), [])

    def test_req_without_spec_fail(self):
        """TC-094: REQ with no SPEC pointing to it -> reverse_orphan error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        f = self.checks_for(data, "reverse_orphan_req_no_spec")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["doc_id"], "REQ-1")
        self.assertEqual(f[0]["severity"], "error")

    def test_spec_without_test_fail(self):
        """TC-095: SPEC (acceptance carrier) with no TEST -> reverse_orphan error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
        ])
        data, _ = self.audit_json(root)
        f = self.checks_for(data, "reverse_orphan_spec_no_test")
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["doc_id"], "SPEC-1")


# --- canonical_conflict (TC-096/097/125, R8) ------------------------------

class CanonicalConflictTest(AuditBase):
    def test_single_canonical_pass(self):
        """TC-096: single doc declares canonical_for [refund] -> no conflict."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "canonical_conflict"), [])

    def test_two_canonicals_fail(self):
        """TC-097: two current docs both canonical_for [refund] -> conflict error."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", canonical_for=["refund"]), "x"),
            (_fm("SPEC-2", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        cc = self.checks_for(data, "canonical_conflict")
        self.assertEqual(len(cc), 2)   # one per carrier
        self.assertTrue(all(f["severity"] == "error" for f in cc))

    def test_superseded_carrier_conflict(self):
        """TC-125: superseded doc still carrying canonical_for + current one -> conflict."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", status="superseded",
                 canonical_for=["refund"], superseded_by="SPEC-2"), "x"),
            (_fm("SPEC-2", "SPEC", "billing", canonical_for=["refund"]), "x"),
        ])
        data, _ = self.audit_json(root)
        cc = self.checks_for(data, "canonical_conflict")
        self.assertTrue(len(cc) >= 2)
        ids = {f["doc_id"] for f in cc}
        self.assertIn("SPEC-1", ids)
        self.assertIn("SPEC-2", ids)


# --- icd_dependency_violation (R7) ----------------------------------------

class IcdViolationTest(AuditBase):
    def test_cross_domain_non_icd_violation(self):
        """ICD violation: billing depends_on identity-internal SPEC -> error with pseudo-spec msg."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-22"]), "x"),
            (_fm("SPEC-22", "SPEC", "identity"), "x"),
        ])
        data, _ = self.audit_json(root)
        v = self.checks_for(data, "icd_dependency_violation")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["severity"], "error")
        self.assertIn("identity の内部です", v[0]["message"])
        self.assertIn("identity の ICD 宛", v[0]["message"])

    def test_cross_domain_icd_allowed(self):
        """Cross-domain dep to an ICD is allowed -> no violation."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["ICD-9"]), "x"),
            (_fm("ICD-9", "ICD", "identity"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "icd_dependency_violation"), [])


# --- projection_drift (TC-098/099/100, R1/R8) -----------------------------

class ProjectionDriftTest(AuditBase):
    def test_overview_matches_pass(self):
        """TC-098: OVERVIEW lists exactly the current source set -> no drift."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n- REQ-1\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_overview_missing_entry_fail(self):
        """TC-099: current doc added but OVERVIEW missing it -> projection drift error."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(f["refs"] == ["REQ-1"] for f in pd))
        self.assertTrue(all(f["severity"] == "error" for f in pd))

    def test_overview_extra_stale_entry_fail(self):
        """TC-100: OVERVIEW lists a removed/non-current doc -> projection drift error."""
        body = "描画される。手で編集しない。\n\n- SPEC-1\n- SPEC-9\n"
        root = self.build([
            (_fm("OVERVIEW-1", "OVERVIEW", "_system"), body),
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
        ])
        data, _ = self.audit_json(root)
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(f["refs"] == ["SPEC-9"] for f in pd))


class IcdIndexDriftTest(AuditBase):
    """icd-index.md の投影ドリフト検査(ICD-005)。overview とは別経路。

    Regression: 既存の ProjectionDriftTest は overview.md のみで、icd-index の
    検査ブロックが丸ごと未実行だった(ミューテーション監査で発見)。"""

    def _repo(self, index_body):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/shipping/ICD.md":
                _util.fm_block(_fm("ICD-2", "ICD", "shipping")) + "x",
            "docs/_system/icd-index.md": _util.fm_block(
                _fm("OVERVIEW-2", "OVERVIEW", "_system"))
                + "描画される。手で編集しない。\n\n" + index_body,
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def test_complete_icd_index_no_drift(self):
        """現行 ICD を全て列挙した icd-index はドリフト無し。"""
        data, _ = self.audit_json(self._repo("- ICD-1\n- ICD-2\n"))
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_missing_icd_in_index_is_drift_error(self):
        """icd-index に現行 ICD が欠けている -> projection_drift error。"""
        data, _ = self.audit_json(self._repo("- ICD-1\n"))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("ICD-2" in (f.get("refs") or []) for f in pd),
                        "missing ICD-2 must be reported: %r" % pd)
        self.assertTrue(all(f["severity"] == "error" for f in pd))


class CtxmapDriftTest(AuditBase):
    """Context Map の投影ドリフト(ICD-005: 構造差 error / ラベル差 warn)。

    Regression: 監査は overview / icd-index しか見ておらず、docstring と
    ICD-005 が約束する Context Map 被覆が未実装だった(全体監査の major 所見)。"""

    _B = "<!-- BEGIN PROJECTION:context-map-skeleton -->"
    _E = "<!-- END PROJECTION:context-map-skeleton -->"

    def _repo(self, region):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/shipping/spec/SPEC-2.md":
                _util.fm_block(_fm("SPEC-2", "SPEC", "shipping",
                                   depends_on=["ICD-1"])) + "x",
            "docs/_system/context-map.md": _util.fm_block(
                _fm("CTXMAP-1", "CTXMAP", "_system"))
                + "描画される。手で編集しない。\n\n%s\n%s\n%s\n" % (self._B, region, self._E),
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return os.path.join(root, "docs")

    def _matching_region(self):
        return ("## ドメインとICD\n\n"
                "- _system: (ICD 未公開)\n"
                "- billing: ICD-1\n"
                "- shipping: (ICD 未公開)\n\n"
                "## ドメイン越えの依存(ICD境界)\n\n"
                "- SPEC-2 --depends_on--> ICD-1\n")

    def test_matching_ctxmap_no_drift(self):
        data, _ = self.audit_json(self._repo(self._matching_region()))
        self.assertEqual(self.checks_for(data, "projection_drift"), [])

    def test_missing_domain_is_error(self):
        region = self._matching_region().replace("- shipping: (ICD 未公開)\n", "")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("shipping" in f["message"] and
                            f["severity"] == "error" for f in pd), pd)

    def test_missing_cross_edge_is_error(self):
        region = self._matching_region().replace(
            "- SPEC-2 --depends_on--> ICD-1\n", "")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any(sorted(f["refs"]) == ["ICD-1", "SPEC-2"] and
                            f["severity"] == "error" for f in pd), pd)

    def test_icd_label_difference_is_warn(self):
        region = self._matching_region().replace("- billing: ICD-1",
                                                 "- billing: (ICD 未公開)")
        data, _ = self.audit_json(self._repo(region))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("ラベル差" in f["message"] and
                            f["severity"] == "warn" for f in pd), pd)
        self.assertFalse(any(f["severity"] == "error" for f in pd), pd)

    def test_unrendered_region_is_error(self):
        files = {
            "docs/billing/ICD.md":
                _util.fm_block(_fm("ICD-1", "ICD", "billing")) + "x",
            "docs/_system/context-map.md": _util.fm_block(
                _fm("CTXMAP-1", "CTXMAP", "_system")) + "印なし本文。\n",
        }
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        pd = self.checks_for(data, "projection_drift")
        self.assertTrue(any("未描画" in f["message"] and
                            f["severity"] == "error" for f in pd), pd)


class StrayDocumentTest(AuditBase):
    """体系外 .md(stray_document, ADR-021): docs/ の外の .md を分類の記録
    (docs/_system/.md-intake)と突き合わせる。"""

    def _proj(self, ledger=None):
        root = self.build([(_fm("SPEC-1", "SPEC", "billing"), "x")])
        proj = os.path.dirname(root)
        if ledger is not None:
            os.makedirs(os.path.join(root, "_system"), exist_ok=True)
            with open(os.path.join(root, "_system", ".md-intake"), "w",
                      encoding="utf-8") as fh:
                fh.write(ledger)
        return root, proj

    def _write(self, proj, rel, text):
        path = os.path.join(proj, rel)
        os.makedirs(os.path.dirname(path) or proj, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_typed_stray_is_warn(self):
        root, proj = self._proj()
        self._write(proj, "notes/SPEC-9-draft.md",
                    _util.fm_block(_fm("SPEC-9", "SPEC", "billing")) + "x")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "warn" and
                            "SPEC" in f["message"] for f in sd), sd)

    def test_unledgered_untyped_is_advisory(self):
        root, proj = self._proj()
        self._write(proj, "MEMO.md", "# メモ\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "advisory" and
                            f["path"] == "MEMO.md" for f in sd), sd)

    def test_ledgered_files_are_silent(self):
        """記録された非文書(完全一致)と配下指定(末尾 /)は挙がらない。"""
        root, proj = self._proj(
            ledger="README.md: 非文書\nvendor/: 非文書\n")
        self._write(proj, "README.md", "# r\n")
        self._write(proj, "vendor/a/b.md", "# b\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stray_document"), [])

    def test_hold_expiry(self):
        """保留は期限まで沈黙し、期限を過ぎると warn で再浮上する。"""
        root, proj = self._proj(
            ledger="old.md: 保留 2026-01-01\nnew.md: 保留 2027-01-01\n")
        self._write(proj, "old.md", "# o\n")
        self._write(proj, "new.md", "# n\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any(f["severity"] == "warn" and f["path"] == "old.md"
                            for f in sd), sd)
        self.assertFalse(any(f["path"] == "new.md" for f in sd), sd)

    def test_dead_ledger_entry_is_advisory(self):
        root, _proj = self._proj(ledger="gone.md: 非文書\n")
        data, _ = self.audit_json(root)
        sd = self.checks_for(data, "stray_document")
        self.assertTrue(any("gone.md" in f["message"] and
                            f["severity"] == "advisory" for f in sd), sd)

    def test_dot_dirs_not_scanned(self):
        root, proj = self._proj()
        self._write(proj, ".hidden/x.md", "# x\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "stray_document"), [])


class ViewStaleTest(AuditBase):
    """ビューの刻印(view_stale, ADR-073): 「ビュー」と分類された体系外 .md の
    刻印を検める。欠落・読めないは warn、古びは advisory。"""

    def _proj(self, ledger):
        root = self.build([(_fm("SPEC-1", "SPEC", "billing"), "x")])
        proj = os.path.dirname(root)
        os.makedirs(os.path.join(root, "_system"), exist_ok=True)
        with open(os.path.join(root, "_system", ".md-intake"), "w",
                  encoding="utf-8") as fh:
            fh.write(ledger)
        return root, proj

    def _write(self, proj, rel, text):
        path = os.path.join(proj, rel)
        os.makedirs(os.path.dirname(path) or proj, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    @staticmethod
    def _stamp(date="2026-06-29", refs="", src="repo", as_of="1.0.0"):
        line = "<!-- doctrine:view src=%s as-of=%s date=%s" % (src, as_of, date)
        if refs:
            line += " refs=%s" % refs
        return line + " -->\n"

    def test_missing_stamp_is_warn(self):
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md", "# v\n")
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "warn" and f["path"] == "V.md"
                            and "刻印が無い" in f["message"] for f in vs), vs)

    def test_unreadable_stamp_is_warn(self):
        """必須欄(src)が欠ける刻印は warn(黙って素通りしない)。"""
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md",
                    "# v\n<!-- doctrine:view date=2026-06-29 -->\n")
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "warn" and
                            "読めない" in f["message"] for f in vs), vs)

    def test_fresh_stamp_with_refs_is_silent(self):
        """refs の updated(2026-06-01) が date 以前 → 何も挙げない。"""
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md",
                    "# v\n" + self._stamp(date="2026-06-29", refs="SPEC-1"))
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "view_stale"), [])

    def test_ref_newer_than_stamp_is_advisory(self):
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md",
                    "# v\n" + self._stamp(date="2026-05-01", refs="SPEC-1"))
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "advisory" and
                            "SPEC-1" in f["message"] and
                            "新しい" in f["message"] for f in vs), vs)

    def test_ref_missing_is_advisory(self):
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md",
                    "# v\n" + self._stamp(refs="SPEC-404"))
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "advisory" and
                            "実在しない" in f["message"] for f in vs), vs)

    def test_ref_not_current_is_advisory(self):
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), "x"),
            (_fm("SPEC-2", "SPEC", "billing", status="deprecated"), "y"),
        ])
        proj = os.path.dirname(root)
        os.makedirs(os.path.join(root, "_system"), exist_ok=True)
        with open(os.path.join(root, "_system", ".md-intake"), "w",
                  encoding="utf-8") as fh:
            fh.write("V.md: ビュー\n")
        self._write(proj, "V.md", "# v\n" + self._stamp(refs="SPEC-2"))
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "advisory" and
                            "現行でない" in f["message"] for f in vs), vs)

    def test_no_refs_stale_is_advisory(self):
        """refs 無し: 正本の updated 最大値(2026-06-01) > date → advisory。"""
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md", "# v\n" + self._stamp(date="2026-05-01"))
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["severity"] == "advisory" and
                            "正本が刻印" in f["message"] for f in vs), vs)

    def test_no_refs_fresh_is_silent(self):
        root, proj = self._proj("V.md: ビュー\n")
        self._write(proj, "V.md", "# v\n" + self._stamp(date="2026-06-29"))
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "view_stale"), [])

    def test_prefix_view_entry_not_checked(self):
        """プレフィクス項目(末尾 /)のビューは view_stale の対象にしない。"""
        root, proj = self._proj("notes/: ビュー\n")
        self._write(proj, "notes/a.md", "# a\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "view_stale"), [])

    def test_exact_entry_overrides_prefix(self):
        """完全一致はプレフィクスに勝つ(ADR-073): vendor/ 一括の非文書の
        配下でも、vendor/V.md: ビュー は刻印の義務を負う。"""
        root, proj = self._proj("vendor/V.md: ビュー\nvendor/: 非文書\n")
        self._write(proj, "vendor/V.md", "# v\n")
        self._write(proj, "vendor/other.md", "# o\n")
        data, _ = self.audit_json(root)
        vs = self.checks_for(data, "view_stale")
        self.assertTrue(any(f["path"] == "vendor/V.md" and
                            f["severity"] == "warn" for f in vs), vs)
        self.assertFalse(any(f["path"] == "vendor/other.md" for f in vs), vs)


# --- near_duplicate advisory (TC-126, R8) ---------------------------------

class NearDuplicateTest(AuditBase):
    def test_near_dup_is_advisory_not_error(self):
        """TC-126: highly overlapping SPEC bodies -> advisory, never error."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), shared + " alpha"),
            (_fm("SPEC-2", "SPEC", "billing"), shared + " beta"),
        ])
        data, _ = self.audit_json(root)
        nd = self.checks_for(data, "near_duplicate")
        self.assertTrue(len(nd) >= 1)
        self.assertTrue(all(f["severity"] == "advisory" for f in nd))

    def test_distinct_bodies_no_dup(self):
        """Distinct bodies -> no near_duplicate finding."""
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), "alpha unique words only here"),
            (_fm("SPEC-2", "SPEC", "billing"), "completely different unrelated text"),
        ])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "near_duplicate"), [])

    def test_scale_gate_skips_pass_and_emits_advisory(self):
        """Current-doc count over near_dup_max_docs -> O(n^2) pass skipped,
        exactly one near_duplicate advisory announcing the skip (no silent
        truncation, severity stays advisory)."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        docs = []
        for k in range(3):
            docs.append((_fm("SPEC-%d" % k, "SPEC", "billing"), shared + " w%d" % k))
        root = self.build(docs)
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"near_dup_max_docs": 1}, fh)
        data, _ = self.audit_json(root, ["--config", cfg])
        nd = self.checks_for(data, "near_duplicate")
        self.assertEqual(len(nd), 1)
        self.assertEqual(nd[0]["severity"], "advisory")
        self.assertIn("省いた", nd[0]["message"])
        # the skip advisory is corpus-wide, not a per-pair finding
        self.assertEqual(nd[0]["refs"], [])

    def test_scale_gate_not_tripped_runs_pass(self):
        """At/under near_dup_max_docs the normal pairwise pass still runs and
        reports the overlapping pair (not the skip advisory)."""
        shared = ("refund policy applies when the customer requests money back "
                  "within thirty days of the original purchase transaction date")
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing"), shared + " alpha"),
            (_fm("SPEC-2", "SPEC", "billing"), shared + " beta"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"near_dup_max_docs": 2}, fh)
        data, _ = self.audit_json(root, ["--config", cfg])
        nd = self.checks_for(data, "near_duplicate")
        self.assertTrue(len(nd) >= 1)
        self.assertTrue(all(f["severity"] == "advisory" for f in nd))
        self.assertTrue(all("省いた" not in f["message"] for f in nd))


# --- summary schema + handshake (critique gap C3) -------------------------

class SummaryHandshakeTest(AuditBase):
    def _docs(self):
        return [
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "x"),
        ]

    def test_respect_docs_level_skips_at_level2_without_summary(self):
        """ADR-019: --respect-docs-level 付きで level: 2 の体系 -> 監査を飛ばし
        exit 0、要約も書かない。フラグ無し(CI)なら Level に依らず監査する。"""
        root = self.build(self._docs())
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, ".docs-level"), "w",
                  encoding="utf-8") as fh:
            fh.write("level: 2\n")
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, "last-audit.json")
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--summary-out", out_path,
             "--fail-on", "never", "--today", TODAY, "--respect-docs-level"])
        self.assertEqual(code, 0)
        self.assertIn("Level 3", out)
        self.assertFalse(os.path.exists(out_path),
                         "level-2 skip must not write a summary")
        # フラグ無し(CI 経路)は Level 2 でも全件監査する。
        data, code2 = self.audit_json(root)
        self.assertEqual(code2, 0)
        self.assertIn("findings", data)

    def test_respect_docs_level_runs_at_level4(self):
        """level: 4(または marker 無し)なら --respect-docs-level 付きでも監査する。"""
        root = self.build(self._docs())
        sysdir = os.path.join(root, "_system")
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, ".docs-level"), "w",
                  encoding="utf-8") as fh:
            fh.write("level: 4\n")
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--today", TODAY,
             "--respect-docs-level"])
        self.assertEqual(code, 0)
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["schema"], "docs-audit/1")

    def test_summary_out_into_existing_dir_and_overwrite(self):
        """出力先ディレクトリ・ファイルが既存でも summary は書かれる。

        Regression guard: SessionEnd は毎回同じ .cache/last-audit.json に書く
        ので、「2回目以降(既存)で書けない」退行は握手を恒久停止させる。"""
        root = self.build(self._docs())
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", out_path,
                "--fail-on", "never", "--today", TODAY]
        _util.invoke("docs-audit", argv)
        out, code = _util.invoke("docs-audit", argv)  # 2回目: 全部既存
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schema"], "docs-audit/1")

    def test_schema_shape_and_json_valid(self):
        """docs-audit/1 schema has exactly the frozen keys and round-trips as JSON."""
        root = self.build(self._docs())
        data, _ = self.audit_json(root)
        self.assertEqual(data["schema"], "docs-audit/1")
        for key in ("schema", "generated_at", "today", "root", "totals",
                    "counts_by_check", "top_findings", "findings"):
            self.assertIn(key, data)
        self.assertEqual(set(data["totals"].keys()),
                         {"error", "warn", "advisory"})
        self.assertEqual(data["today"], TODAY)
        # generated_at is deterministic-injectable from --today.
        self.assertTrue(data["generated_at"].startswith(TODAY))
        # top_findings errors-first and capped.
        self.assertLessEqual(len(data["top_findings"]), 20)
        if data["top_findings"]:
            sevs = [f["severity"] for f in data["top_findings"]]
            # all errors come before any warn/advisory
            seen_non_error = False
            for s in sevs:
                if s != "error":
                    seen_non_error = True
                elif seen_non_error:
                    self.fail("errors not first in top_findings")

    def test_summary_out_round_trip(self):
        """SessionEnd handshake: write summary to a path; it is valid docs-audit/1 JSON."""
        root = self.build(self._docs())
        cache_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cache_dir, ignore_errors=True)
        out_path = os.path.join(cache_dir, ".cache", "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", out_path,
                "--fail-on", "never", "--today", TODAY]
        out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as fh:
            persisted = json.load(fh)        # must be valid JSON
        self.assertEqual(persisted["schema"], "docs-audit/1")
        # The persisted file and stdout describe the same audit.
        stdout_data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(persisted["totals"], stdout_data["totals"])
        self.assertEqual(persisted["counts_by_check"],
                         stdout_data["counts_by_check"])

    def test_session_end_non_blocking_exit_zero(self):
        """SessionEnd: --fail-on never returns 0 even with error findings."""
        root = self.build(self._docs())   # has a dead_link error
        argv = ["--root", root, "--json", "--fail-on", "never", "--today", TODAY]
        _out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)

    def test_session_end_does_not_read_stdin(self):
        """SessionEnd contract: audit does NOT read its stdin and exits 0 regardless.

        main() never consults stdin (it depends only on argv/config). A hook
        envelope on stdin must neither change the result nor cause a hang/error:
        running with the SessionEnd envelope and with empty stdin yields the
        same stdout and exit 0. A closed/unconsumed stdin does not block.
        """
        root = self.build(self._docs())
        stdin_obj = _util.hook_stdin("SessionEnd", reason="clear")
        out_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, out_dir, ignore_errors=True)
        argv = ["--root", root, "--json", "--summary-out",
                os.path.join(out_dir, "a.json"),
                "--fail-on", "never", "--today", TODAY]
        # With the SessionEnd envelope on stdin.
        out_with, code_with = _util.invoke("docs-audit", argv, stdin_obj=stdin_obj)
        # With empty stdin (closed/unconsumed) — must be identical, no hang.
        out_empty, code_empty = _util.invoke("docs-audit", argv, stdin_obj=None)
        self.assertEqual(code_with, 0)
        self.assertEqual(code_empty, 0)
        # Stdin content does not influence the audit: byte-identical stdout.
        self.assertEqual(out_with, out_empty)

    def test_ci_fail_on_error_gates(self):
        """CI: --fail-on error exits 1 when any error finding exists."""
        root = self.build(self._docs())   # dead_link error present
        argv = ["--root", root, "--json", "--fail-on", "error", "--today", TODAY]
        _out, code = self.audit_json(root, extra_argv=["--fail-on", "error"])
        # use direct invoke to read code precisely
        out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 1)

    def test_ci_clean_corpus_exits_zero(self):
        """CI: clean corpus with no errors exits 0 under --fail-on error."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["REQ-1"]), "x"),
            (_fm("TEST-1", "TEST", "billing", depends_on=["SPEC-1"]), "x"),
        ])
        argv = ["--root", root, "--json", "--fail-on", "error", "--today", TODAY]
        out, code = _util.invoke("docs-audit", argv)
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["totals"]["error"], 0)
        self.assertEqual(code, 0)

    def test_atomic_write_failure_still_exit_zero(self):
        """Write fail (summary-out under a path that is a file) -> exit 0 anyway."""
        root = self.build(self._docs())
        # Point summary-out into a path whose parent is a regular file.
        blocker = os.path.join(_util.mkdtemp(), "blocker")
        with open(blocker, "w") as fh:
            fh.write("x")
        bad_out = os.path.join(blocker, "sub", "last-audit.json")
        argv = ["--root", root, "--json", "--summary-out", bad_out,
                "--fail-on", "never", "--today", TODAY]
        _out, code = _util.invoke("docs-audit", argv)
        self.assertEqual(code, 0)


# --- determinism + config knobs -------------------------------------------

class DeterminismTest(AuditBase):
    def test_deterministic_output(self):
        """Same corpus + same --today -> byte-identical JSON (sorted keys)."""
        docs = [
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-99"]), "x"),
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-01-01"), "y"),
        ]
        root = self.build(docs)
        out1, _ = _util.invoke("docs-audit",
                               ["--root", root, "--json", "--today", TODAY])
        out2, _ = _util.invoke("docs-audit",
                               ["--root", root, "--json", "--today", TODAY])
        self.assertEqual(out1, out2)

    def test_config_today_overrides(self):
        """--config today is honored when --today absent (review_by overrun keys on it)."""
        root = self.build([
            (_fm("DECIDED-1", "DECIDED", "billing", review_by="2026-06-15"), "x"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"today": "2026-06-29"}, fh)
        out, _ = _util.invoke("docs-audit",
                              ["--root", root, "--json", "--config", cfg])
        data = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(data["today"], "2026-06-29")
        self.assertEqual(len(self.checks_for(data, "review_by_overrun")), 1)

    def test_bad_today_is_usage_error(self):
        """A supplied but unparseable --today is a usage error (exit 2), NOT a
        silent wall-clock fallback. Guards the 'no uncontrolled wall-clock' promise.
        """
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        out, code = _util.invoke(
            "docs-audit",
            ["--root", root, "--json", "--today", "not-a-date"])
        self.assertEqual(code, 2)
        self.assertIn("usage error", out)

    def test_bad_config_today_is_usage_error(self):
        """A supplied but unparseable config.today (no --today) is also exit 2."""
        root = self.build([
            (_fm("REQ-1", "REQ", "billing"), "x"),
        ])
        cfg_dir = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, cfg_dir, ignore_errors=True)
        cfg = os.path.join(cfg_dir, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({"today": "2026-13-99"}, fh)
        _out, code = _util.invoke(
            "docs-audit", ["--root", root, "--json", "--config", cfg])
        self.assertEqual(code, 2)


# --- §7 detected-fallback: guard misses, audit catches (TC-130) ------------

class DetectedFallbackTest(AuditBase):
    def test_icd_violation_audit_fallback_when_guard_not_fired(self):
        """TC-130 (§7): the guard is preventive but not total; the audit is the
        detective backstop. A cross-domain non-ICD depends_on can reach disk via
        a tool path the guard's matcher does not cover. On such a NON-matched
        event the guard quietly allows (does not fire), yet docs-audit later
        surfaces the same violation as an icd_dependency_violation error.
        """
        # Cross-domain non-ICD dependency written straight to disk (simulating a
        # tool path the PreToolUse Edit|Write|MultiEdit / Bash matcher misses).
        root = self.build([
            (_fm("SPEC-1", "SPEC", "billing", depends_on=["SPEC-22"]), "x"),
            (_fm("SPEC-22", "SPEC", "identity"), "x"),
        ])
        offending = os.path.join(root, "billing", "spec", "SPEC-1.md")
        self.assertTrue(os.path.isfile(offending))

        # 1) policy-guard on a NON-matched event (PreToolUse + a tool the guard
        # does not route, e.g. Read) → quiet allow, the guard does not fire.
        stdin_obj = _util.hook_stdin(
            "PreToolUse", tool_name="Read",
            tool_input={"file_path": offending})
        out, code = _util.invoke("policy-guard", stdin_obj=stdin_obj)
        self.assertEqual(code, 0)
        resp = json.loads(out)
        hso = resp.get("hookSpecificOutput", {})
        # allow / quiet: no deny, no block — the guard did not fire.
        self.assertNotEqual(hso.get("permissionDecision"), "deny")
        self.assertNotEqual(resp.get("decision"), "block")
        self.assertEqual(hso.get("permissionDecision"), "allow")

        # 2) docs-audit catches the same violation (reverse-ref/edge fallback).
        data, _ = self.audit_json(root)
        v = self.checks_for(data, "icd_dependency_violation")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["doc_id"], "SPEC-1")
        self.assertEqual(v[0]["severity"], "error")
        self.assertEqual(v[0]["refs"], ["SPEC-22"])
        self.assertIn("identity の内部です", v[0]["message"])


# --- registration completeness (unregistered / shadowed, R1/R8) -----------

# --- コードと仕様の追跡 (trace_*, ADR-056) -------------------------------

def _tmark(kind, doc_id, lead="# "):
    """印の行を組み立てる(原文に印そのものを書かない)。"""
    return "%sdoctrine:%s %s" % (lead, kind, doc_id)


def _spec_with_fingerprints(doc_id, fingerprints):
    body = "## 入出力\nx\n\n## 制約\nx\n\n## エラー時挙動\nx\n"
    if fingerprints is not None:
        body += "\n## 実装の指紋\n\n"
        body += "".join("- %s\n" % fp for fp in fingerprints)
    body += "\n## 受入基準\nx\n"
    return _util.fm_block(_fm(doc_id, "SPEC", "app")) + body


# ICD-005 / SPEC-011 から独立に転記した検査名の並び(モジュールのリテラルの
# 読み直しではない。ADR-060)。検査を足す・消すときは、この転記表を同じ変更で
# 更新する。ここを AUDIT_CHECKS から生成したら凍結の意味が消える。
EXPECTED_AUDIT_CHECKS = (
    "dead_link", "dep_cycle", "review_by_overrun", "stale_draft", "orphan",
    "reverse_orphan_req_no_spec", "reverse_orphan_spec_no_test",
    "canonical_conflict", "near_duplicate", "icd_dependency_violation",
    "projection_drift", "unregistered_document", "shadowed_document",
    "stray_document", "view_stale", "stale_current", "source_drift",
    "archive_integrity",
    "adr_not_landed", "glossary_seed_drift", "ext_anchor_broken", "memory_shadow",
    "trace_mark_error", "trace_broken_ref", "trace_deprecated_ref",
    "trace_stale", "trace_missing_impl", "trace_marker_suspect",
    "trace_scan_truncated", "trace_unexpected_impl", "trace_undeclared_impl",
    "trace_exempt_conflict", "trace_unmarked_backlog", "guard_liveness_gap",
)


class AuditChecksFreezeTest(AuditBase):
    """検査名の一覧の凍結(ADR-060)。「TEST が凍結する」という宣言を実在させる。

    以前は宣言だけがあって凍結する試験が無く、名前を一つ足しても全試験が通った
    (「文書上の宣言に留まる」欠陥類型のコード内注釈版)。
    """

    def test_audit_checks_matches_the_transcribed_table(self):
        audit = _util.load_script("docs-audit")
        self.assertEqual(tuple(audit.AUDIT_CHECKS), EXPECTED_AUDIT_CHECKS,
                         "検査を足した/消したら、転記表と ICD-005 を同じ変更で更新すること")

    def test_checks_run_equals_the_declared_list_exactly(self):
        root = self.build([(_fm("REQ-1", "REQ", "billing"), "本文")])
        data, _ = self.audit_json(root)
        self.assertEqual(tuple(data["checks_run"]), EXPECTED_AUDIT_CHECKS)

    def test_scanner_codes_have_a_producer_side_canon(self):
        """産出側の所見コード正本と、消費側の畳み込み集合の包含(ADR-060)。"""
        tracescan = _util.load_core("_tracescan")
        trace_mod = _util.load_core("_audit_trace")
        codes = set(tracescan.FINDING_CODES)
        self.assertTrue(set(trace_mod._TRACE_MARK_CODES) <= codes,
                        "消費側だけにあるコードは産出されない死文である")
        self.assertIn("trace_marker_suspect", codes)
        self.assertIn("trace_scan_truncated", codes)


class GuardLivenessTest(AuditBase):
    """拒否経路の欠落の疑い(ADR-062)。印が無ければ沈黙、対の食い違いで advisory。"""

    def test_silent_without_stamps(self):
        root = self.build([(_fm("REQ-1", "REQ", "billing"), "本文")])
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "guard_liveness_gap"), [])

    def test_linter_stamp_without_guard_stamp_is_advisory(self):
        root = self.build([(_fm("REQ-1", "REQ", "billing"), "本文")])
        proj = os.path.dirname(root)
        cache = os.path.join(proj, ".claude", ".cache")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "hook-stamps"), "w",
                  encoding="utf-8") as fh:
            fh.write("hook_docs_linter: 2026-06-29T10:00:00Z\n")
        data, _ = self.audit_json(root)
        hits = self.checks_for(data, "guard_liveness_gap")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "advisory")

    def test_fresh_pair_is_silent(self):
        root = self.build([(_fm("REQ-1", "REQ", "billing"), "本文")])
        proj = os.path.dirname(root)
        cache = os.path.join(proj, ".claude", ".cache")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "hook-stamps"), "w",
                  encoding="utf-8") as fh:
            fh.write("hook_docs_linter: 2026-06-29T10:00:10Z\n"
                     "hook_policy_guard_pre: 2026-06-29T10:00:00Z\n")
        data, _ = self.audit_json(root)
        self.assertEqual(self.checks_for(data, "guard_liveness_gap"), [])


class TraceStatusMatrixTest(AuditBase):
    """状態×指紋の全マス期待表(ADR-060)。添字は正本 ALL_STATUSES から列挙する。

    期待表は手書きで、生成で埋めない(「期待を決めていないマス」が消えるため)。
    状態が増えたら、期待を書き足すまでこの試験は通らない。以前は 16 マス中
    2 マスしか発火せず、しかも発火が他の現行 opt-in の併存に依存していた。
    """

    # (status, 指紋一致か) -> 発火する trace 検査名の集合。
    EXPECTED = {
        ("proposed", True): {"trace_deprecated_ref"},
        ("proposed", False): {"trace_deprecated_ref"},
        ("accepted", True): set(),
        ("accepted", False): {"trace_stale"},
        ("current", True): set(),
        ("current", False): {"trace_stale"},
        ("deprecated", True): {"trace_deprecated_ref"},
        ("deprecated", False): {"trace_deprecated_ref"},
        ("superseded", True): {"trace_deprecated_ref"},
        ("superseded", False): {"trace_deprecated_ref"},
        ("archived", True): {"trace_deprecated_ref"},
        ("archived", False): {"trace_deprecated_ref"},
        ("open", True): {"trace_deprecated_ref"},
        ("open", False): {"trace_deprecated_ref"},
        ("draft", True): {"trace_deprecated_ref"},
        ("draft", False): {"trace_deprecated_ref"},
    }

    def test_expected_keys_match_the_registry_both_ways(self):
        reg = _util.load_core("_registry")
        self.assertEqual(
            set(self.EXPECTED),
            {(s, m) for s in reg.ALL_STATUSES for m in (True, False)},
            "状態の列挙と期待表のキー集合が食い違う。"
            "状態を足したら、期待を決めてこの表へ書き足すこと")

    def _cell(self, status, fp_match):
        root = _util.make_repo({"src/a.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        tracescan = _util.load_core("_tracescan")
        good = tracescan.scan_text(code, "src/a.py")[0][0]["fingerprint"]
        recorded = good if fp_match else "sha256:" + "0" * 64
        body = ("## 入出力\nx\n\n## 制約\nx\n\n## エラー時挙動\nx\n"
                "\n## 実装の指紋\n\n- %s\n\n## 受入基準\nx\n" % recorded)
        doc = _util.fm_block(_fm("SPEC-900", "SPEC", "app", status=status)) + body
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(doc)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        return {f["check"] for f in data["findings"]
                if f["check"].startswith("trace")}

    def test_every_cell_matches_the_expected_table(self):
        reg = _util.load_core("_registry")
        for status in reg.ALL_STATUSES:
            for fp_match in (True, False):
                with self.subTest(status=status, fp_match=fp_match):
                    self.assertIn(
                        (status, fp_match), self.EXPECTED,
                        "期待値の無いマス: status=%r fp一致=%r。"
                        "期待を決めて EXPECTED へ書き足すこと" % (status, fp_match))
                    got = self._cell(status, fp_match)
                    self.assertEqual(
                        self.EXPECTED[(status, fp_match)], got,
                        "マス status=%r fp一致=%r の期待と実測が食い違う"
                        % (status, fp_match))


class CodeTraceTest(AuditBase):
    """ADR-056: 追跡の検査は、仕様が指紋を記録したときだけ効く。

    これが緩むと、導入初日に全ての現行 SPEC へ警告が飛ぶ(近縁の道具が繰り返し
    踏んでいる失敗)。逆に、記録したのに何も検査しない状態は「黙って通る検証器」
    であり、R11 が禁じる沈黙する故障そのものである。両側をここで凍らせる。
    """

    def test_no_opt_in_means_no_findings_at_all(self):
        """節を持つ仕様が無ければ、追跡の所見は一件も出ない(導入初日の静けさ)。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints("SPEC-900", None),
            "src/a.py": "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                                   _tmark("end", "SPEC-900")]),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        for check in ("trace_stale", "trace_missing_impl", "trace_broken_ref",
                      "trace_mark_error", "trace_deprecated_ref"):
            self.assertEqual(self.checks_for(data, check), [], check)

    def test_recorded_fingerprint_that_matches_is_silent(self):
        root = _util.make_repo({"src/a.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(code, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(self.checks_for(data, "trace_stale"), [])
        self.assertEqual(self.checks_for(data, "trace_missing_impl"), [])

    def test_summary_carries_trace_coverage_when_opted_in(self):
        """走査が走ったとき、要約に勘定が載り、保存則の和が合う(ADR-058)。

        所見は増やさない(既存の緑は緑のまま)。何を見て何を見なかったかを、
        数として毎回の監査に残すのが勘定の役目である。
        """
        root = _util.make_repo({"src/a.py": "", "src/plain.py": "print(1)\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(code, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertIn("trace_coverage", data)
        cov = data["trace_coverage"]
        self.assertEqual(cov["annotated_files"], 1)
        self.assertGreaterEqual(cov["unmarked_files"], 1)
        self.assertEqual(
            cov["reached_files"],
            cov["annotated_files"] + cov["unmarked_files"]
            + cov["exempt_files"] + sum(cov["excluded"].values()),
            "保存則が破れている: %r" % (cov,))
        self.assertNotIn("members", cov, "要約に一覧を載せない(件数だけ)")

    def test_suspect_marker_surfaces_as_advisory(self):
        """綴りの揺れた印が advisory で挙がる(ADR-059)。合否は変えない。"""
        root = _util.make_repo({"src/a.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        # 原文に疑いの形を書かない(実行時に連結して作る)。
        with open(os.path.join(root, "src", "b.py"), "w", encoding="utf-8") as fh:
            fh.write("# doctrine:" + " begin SPEC-901\ny=2\n")
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(code, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        sus = self.checks_for(data, "trace_marker_suspect")
        self.assertEqual(len(sus), 1)
        self.assertEqual(sus[0]["severity"], "advisory",
                         "疑いは advisory に留める(合否を変えない。ADR-059)")
        for check in ("trace_marker_suspect",):
            self.assertIn(check, data["checks_run"], check)

    def test_scan_truncation_surfaces_as_advisory(self):
        """走査が告げた切り詰めを、監査が握らず advisory で載せる(ADR-059)。"""
        root = _util.make_repo({"src/a.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        # 大きさの上限(既定 1MiB)を超えるファイル -> 走査は所見で告げる。
        with open(os.path.join(root, "src", "big.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("#" * (1024 * 1024 + 16))
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(code, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        tr = self.checks_for(data, "trace_scan_truncated")
        self.assertEqual(len(tr), 1)
        self.assertEqual(tr[0]["severity"], "advisory")
        self.assertEqual(data["trace_coverage"]["excluded"]["oversize"], 1)

    def test_no_code_declaration_is_silent_when_reality_agrees(self):
        """「コード対応なし」の宣言は、範囲が無ければ何も挙げない(ADR-061)。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints("SPEC-900", None)
            .replace("## 受入基準", "## 実装の指紋\n\n- コード対応なし: 運用手順のみの仕様\n\n## 受入基準"),
            "src/a.py": "print(1)\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        for check in ("trace_unexpected_impl", "trace_missing_impl",
                      "trace_stale"):
            self.assertEqual(self.checks_for(data, check), [], check)
        self.assertEqual(data["trace_coverage"]["spec_coverage"],
                         {"traced": 0, "no_code": 1, "undeclared": 0})

    def test_no_code_declaration_with_ranges_is_a_warn(self):
        """宣言と実態の矛盾(ADR-061): 対応なしと言いながら範囲がある。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints("SPEC-900", None)
            .replace("## 受入基準", "## 実装の指紋\n\n- コード対応なし: 理由\n\n## 受入基準"),
            "src/a.py": "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                                   _tmark("end", "SPEC-900")]),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        hits = self.checks_for(data, "trace_unexpected_impl")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "warn")
        self.assertEqual(hits[0]["doc_id"], "SPEC-900")

    def test_annotation_to_sectionless_current_spec_is_advisory(self):
        """欠陥D(ADR-061): 節の無い現行仕様を注釈が指す。advisory で名指しする。"""
        root = _util.make_repo({"src/a.py": "", "src/b.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        gate_code = "\n".join([_tmark("begin", "SPEC-901"), "y=2",
                               _tmark("end", "SPEC-901")])
        orphan_code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                                 _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(gate_code)
        with open(os.path.join(root, "src", "b.py"), "w", encoding="utf-8") as fh:
            fh.write(orphan_code)
        tracescan = _util.load_core("_tracescan")
        gate_fp = tracescan.scan_text(gate_code, "src/a.py")[0][0]["fingerprint"]
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-901.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints("SPEC-901", [gate_fp]))
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints("SPEC-900", None))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        hits = self.checks_for(data, "trace_undeclared_impl")
        self.assertEqual([h["doc_id"] for h in hits], ["SPEC-900"])
        self.assertEqual(hits[0]["severity"], "advisory")
        self.assertEqual(
            data["trace_coverage"]["spec_coverage"],
            {"traced": 1, "no_code": 0, "undeclared": 1,
             "next_undeclared": "SPEC-900"},
            "キャンペーン(ADR-065)が運ぶ「次の一件」は整列順の先頭")

    def _traced_repo(self, extra_files=None):
        """走査が走る最小 fixture(SPEC-900 traced・一致)。docs root を返す。"""
        files = {"src/a.py": ""}
        files.update(extra_files or {})
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        tracescan = _util.load_core("_tracescan")
        fp = tracescan.scan_text(code, "src/a.py")[0][0]["fingerprint"]
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints("SPEC-900", [fp]))
        return os.path.join(root, "docs")

    def test_stagnation_streak_counts_unchanged_audits(self):
        """停滞の勘定(ADR-065): 印なし+未宣言の和が動かない監査を数え、動けば戻る。"""
        docs_root = self._traced_repo(extra_files={"src/plain.py": "print(1)\n"})
        proj = os.path.dirname(docs_root)
        cache = os.path.join(proj, ".claude", ".cache")
        os.makedirs(cache, exist_ok=True)

        first, _ = self.audit_json(docs_root)
        self.assertEqual(first["trace_coverage"]["stagnation_streak"], 0,
                         "直前の要約が無ければ 0")
        with open(os.path.join(cache, "last-audit.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(first, fh, ensure_ascii=False)

        second, _ = self.audit_json(docs_root)
        self.assertEqual(second["trace_coverage"]["stagnation_streak"], 1)
        with open(os.path.join(cache, "last-audit.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(second, fh, ensure_ascii=False)

        third, _ = self.audit_json(docs_root)
        self.assertEqual(third["trace_coverage"]["stagnation_streak"], 2,
                         "続けば積み上がる")

        # 値が動けば 0 に戻る(ファイルを一つ足して印なしを増やす)。
        with open(os.path.join(proj, "src", "newone.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("print(2)\n")
        moved, _ = self.audit_json(docs_root)
        self.assertEqual(moved["trace_coverage"]["stagnation_streak"], 0)

    def test_exempt_conflict_surfaces_as_warn_for_declarers_only(self):
        """統治外の宣言と実態の矛盾(ADR-067)。宣言したファイルにしか発火しない。"""
        root = _util.make_repo({"src/a.py": "", "src/free.py": ""})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        conflicted = ("# doctrine:" + "exempt 古い宣言\n") + code
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(conflicted)
        with open(os.path.join(root, "src", "free.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("print(1)\n")
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(conflicted, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        data, _ = self.audit_json(os.path.join(root, "docs"))
        hits = self.checks_for(data, "trace_exempt_conflict")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["severity"], "warn")
        # 実態を優先: 範囲は生きるので指紋照合は無音のまま。
        self.assertEqual(self.checks_for(data, "trace_stale"), [])
        self.assertEqual(data["trace_coverage"]["exempt_files"], 0)

    def test_summary_has_no_trace_coverage_without_opt_in(self):
        """opt-in が無ければ走査せず、勘定も載らない(ADR-056 の静けさを保つ)。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints("SPEC-900", None),
            "src/a.py": "print(1)\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertNotIn("trace_coverage", data)

    def test_content_change_raises_trace_stale(self):
        """記録した確認と、いまのコードが食い違えば古びとして挙げる。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints(
                "SPEC-900", ["sha256:" + "0" * 64]),
            "src/a.py": "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                                   _tmark("end", "SPEC-900")]),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        s = self.checks_for(data, "trace_stale")
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["severity"], "warn")

    def test_recorded_but_no_range_raises_missing_impl(self):
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints(
                "SPEC-900", ["sha256:" + "0" * 64]),
            "src/a.py": "print(1)\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(len(self.checks_for(data, "trace_missing_impl")), 1)

    def test_annotation_to_unknown_id_is_error(self):
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints(
                "SPEC-900", ["sha256:" + "0" * 64]),
            "src/a.py": "\n".join([_tmark("begin", "SPEC-999"), "x=1",
                                   _tmark("end", "SPEC-999")]),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        b = self.checks_for(data, "trace_broken_ref")
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["severity"], "error")

    def test_unclosed_mark_is_error(self):
        """印の対応付けの誤りは error。機械で判じきれる欠陥だから(ADR-056)。"""
        root = _util.make_repo({
            "docs/app/spec/SPEC-900.md": _spec_with_fingerprints(
                "SPEC-900", ["sha256:" + "0" * 64]),
            "src/a.py": "\n".join([_tmark("begin", "SPEC-900"), "x=1"]),
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        m = self.checks_for(data, "trace_mark_error")
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["severity"], "error")

    def test_trace_checks_are_declared_in_checks_run(self):
        """走った検査集合に載ること(黙って消えた検査を見つけられるように)。"""
        root = _util.make_repo({"docs/_system/glossary.md": "x"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        for check in ("trace_mark_error", "trace_broken_ref",
                      "trace_deprecated_ref", "trace_stale",
                      "trace_missing_impl"):
            self.assertIn(check, data["checks_run"], check)


class UnregisteredTest(AuditBase):
    def test_frontmatterless_file_is_unregistered(self):
        """docs/ 内の frontmatter/id 無し .md -> unregistered_document error。

        他の検査は g.nodes 上の述語なので、この検査だけが「亡霊」を拾える。
        """
        root = _util.make_repo({
            "docs/notes/scratch.md": "ただの散文。フロントマターも id も無い。\n",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        u = self.checks_for(data, "unregistered_document")
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["severity"], "error")
        self.assertEqual(u[0]["path"], "notes/scratch.md")
        self.assertEqual(u[0]["doc_id"], "")  # 登録簿に id が無い → 空文字（整列安全）

    def test_duplicate_id_shadow_is_flagged(self):
        """同じ id の別ファイル -> 影のパスだけ shadowed_document error。"""
        a = _util.fm_block(_fm("DUP-1", "RESEARCH", "a", llm_context="never")) + "A"
        b = _util.fm_block(_fm("DUP-1", "RESEARCH", "b", llm_context="never")) + "B"
        root = _util.make_repo({
            "docs/a/research/DUP-1.md": a,
            "docs/b/research/DUP-1.md": b,
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        s = self.checks_for(data, "shadowed_document")
        self.assertEqual(len(s), 1)  # 2 ファイル中 1 つが影
        self.assertEqual(s[0]["severity"], "error")
        self.assertEqual(s[0]["doc_id"], "DUP-1")
        self.assertEqual(s[0]["path"], "b/research/DUP-1.md")  # 先勝ちで a を採用
        # 案内が告げる採用先は、グラフ・注入が実際に採る文書と同じ(ADR-049)。
        self.assertIn("採用 a/research/DUP-1.md", s[0]["message"])

    def test_clean_corpus_has_neither(self):
        """全ファイルが一意 id で登録済み -> unregistered/shadowed ゼロ。"""
        root = _util.make_repo({
            "docs/billing/spec/SPEC-1.md":
                _util.fm_block(_fm("SPEC-1", "SPEC", "billing")) + "x",
            "docs/billing/REQ-1.md":
                _util.fm_block(_fm("REQ-1", "REQ", "billing")) + "x",
        })
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        data, code = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(self.checks_for(data, "unregistered_document"), [])
        self.assertEqual(self.checks_for(data, "shadowed_document"), [])


class ExhaustiveTraceTest(AuditBase):
    """ADR-072: 悉皆モードは opt-in。印なしは残高 warn 一件で挙がる。

    既定では何も変わらない(通常の導入先の静けさ)。設定除外は明示管理外へ
    分類され、理由の無い宣言は成立しない。
    """

    def _repo(self, config=None):
        root = _util.make_repo({"src/a.py": "", "src/plain.py": "print(1)\n"})
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code = "\n".join([_tmark("begin", "SPEC-900"), "x=1",
                          _tmark("end", "SPEC-900")])
        with open(os.path.join(root, "src", "a.py"), "w", encoding="utf-8") as fh:
            fh.write(code)
        tracescan = _util.load_core("_tracescan")
        ranges, _ = tracescan.scan_text(code, "src/a.py")
        os.makedirs(os.path.join(root, "docs", "app", "spec"), exist_ok=True)
        with open(os.path.join(root, "docs", "app", "spec", "SPEC-900.md"),
                  "w", encoding="utf-8") as fh:
            fh.write(_spec_with_fingerprints(
                "SPEC-900", [ranges[0]["fingerprint"]]))
        if config is not None:
            os.makedirs(os.path.join(root, "docs", "_system"), exist_ok=True)
            with open(os.path.join(root, "docs", "_system",
                                   ".context-config.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(config, fh)
        return root

    def test_backlog_warn_fires_only_in_exhaustive_mode(self):
        root = self._repo({"trace_mode": "exhaustive"})
        data, _ = self.audit_json(os.path.join(root, "docs"))
        hits = self.checks_for(data, "trace_unmarked_backlog")
        self.assertEqual(len(hits), 1,
                         "残高は一件で告げる(ファイルごとに鳴らさない)")
        self.assertEqual(hits[0]["severity"], "warn")
        self.assertIn("件", hits[0]["message"])

    def test_no_backlog_by_default(self):
        root = self._repo(None)
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(self.checks_for(data, "trace_unmarked_backlog"), [],
                         "モード未設定の既定では現状のまま")

    def test_config_exempt_clears_the_backlog(self):
        root = self._repo({"trace_mode": "exhaustive",
                           "trace_exempt": {"src/plain.py": "使い捨ての補助"}})
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(self.checks_for(data, "trace_unmarked_backlog"), [],
                         "設定除外で印なしが尽きれば残高は出ない")
        self.assertGreaterEqual(data["trace_coverage"]["exempt_files"], 1)

    def test_exempt_without_reason_does_not_count(self):
        root = self._repo({"trace_mode": "exhaustive",
                           "trace_exempt": {"src/plain.py": ""}})
        data, _ = self.audit_json(os.path.join(root, "docs"))
        self.assertEqual(
            len(self.checks_for(data, "trace_unmarked_backlog")), 1,
            "理由の無い宣言は成立しない(宣言なき除外を作らない)")


if __name__ == "__main__":
    unittest.main()
