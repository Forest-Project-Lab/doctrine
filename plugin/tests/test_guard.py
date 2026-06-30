"""policy-guard.py — the three guards (PreToolUse + PostToolUse).

R7 (the ICD cross-domain dependency boundary) is the central self-test, proved
verbatim. Covers the guard rows of design/10-scenarios.md:

  B10 (TC-070/071/072) ICD cross-domain dep guard DENY/ALLOW
  B11 (TC-073/074)     Edit/MultiEdit post-block for the same violation
  B12 (TC-075/076/077) immutability deny on archive/** and existing ADR (+ carve-out)
  B13 (TC-078/079/080/081) delete-safety with / without remaining current dependents
  TC-117  cross-domain dep to a deprecated ICD -> guard ALLOWS (status-blind, C12)
  TC-118  demote-blocked -> re-point -> demote-allowed (sequence)
  TC-119  Write pre-deny vs Edit post-block for the SAME ICD violation (C4)
  TC-123  unclassifiable dep -> fail-closed deny (C13 deny side)
  C13 companion: dangling (valid prefix, absent from graph) -> guard ALLOWS
  TC-132  Bash-matcher delete-safety emits ONLY permissionDecision:deny (no context)

The block on PostToolUse is asserted to be emitted by policy-guard itself (C4 /
critique gap 3): docs-linter never emits `decision`.
"""

import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pre(resp):
    """Extract (permissionDecision, reason) from a PreToolUse response object."""
    hso = resp.get("hookSpecificOutput", {})
    return hso.get("permissionDecision"), hso.get("permissionDecisionReason")


def _doc(domain, fm_extra=None, body="本文。\n", status=None, doc_id="SPEC-01",
         type_code="SPEC"):
    fm = {
        "id": doc_id, "title": "t", "type": type_code, "domain": domain,
        "status": status or "current", "owner": "o", "updated": "2026-06-01",
        "sources": [],
    }
    if fm_extra:
        fm.update(fm_extra)
    return fm


class GuardTestBase(unittest.TestCase):
    def _repo(self, files):
        root = _util.make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _two_domain_repo(self):
        """billing + identity, with an identity ICD and an identity-internal SPEC,
        a billing SPEC that some billing TEST depends on."""
        root = self._repo({
            "docs/identity/ICD.md": _util.fm_block(_doc(
                "identity", doc_id="ICD-09", type_code="ICD",
                fm_extra={"canonical_for": ["identity-boundary"]})) + "ICD本文。\n",
            "docs/identity/spec/SPEC-22-internal.md": _util.fm_block(_doc(
                "identity", doc_id="SPEC-22")) + "内部仕様。\n",
        })
        return root


# ---------------------------------------------------------------------------
# B10 / R7 central — ICD cross-domain dependency guard (Write pre-deny)
# ---------------------------------------------------------------------------

class TestR7IcdDependency(GuardTestBase):
    """B10 / §6 R7-row — the R7 self-test (central)."""

    def test_tc071_cross_domain_non_icd_dep_denied_verbatim(self):
        """TC-071: billing SPEC depends_on identity-internal SPEC-22 -> deny, the
        EXACT spec message (R7 acceptance test, §6)."""
        root = self._two_domain_repo()
        new = _util.fm_block(_doc("billing", doc_id="SPEC-30",
                                  fm_extra={"depends_on": ["SPEC-22"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-30-x.md"),
               "content": new + "本文。\n"}
        out, code = _util.invoke("policy-guard",
                                 stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        self.assertEqual(code, 0)
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertEqual(
            reason, "SPEC-22 は identity の内部です。identity の ICD 宛にしてください。")

    def test_tc070_cross_domain_icd_dep_allowed(self):
        """TC-070: billing SPEC depends_on identity ICD-09 -> allow (cross-domain
        but ICD-targeted)."""
        root = self._two_domain_repo()
        new = _util.fm_block(_doc("billing", doc_id="SPEC-30",
                                  fm_extra={"depends_on": ["ICD-09"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-30-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_tc072_intra_domain_dep_allowed(self):
        """TC-072: same-domain internal dep (billing -> billing SPEC) -> allow."""
        root = self._repo({
            "docs/billing/spec/SPEC-40.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-40")) + "本文。\n",
        })
        new = _util.fm_block(_doc("billing", doc_id="SPEC-41",
                                  fm_extra={"depends_on": ["SPEC-40"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-41-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_tc117_cross_domain_dep_to_deprecated_icd_allowed(self):
        """TC-117 / C12: target IS the ICD but status:deprecated -> guard ALLOWS.
        R7 is purely structural (domain + type==ICD); currency is an audit concern.
        Guard must NOT add a status check."""
        root = self._repo({
            "docs/identity/ICD.md": _util.fm_block(_doc(
                "identity", doc_id="ICD-09", type_code="ICD", status="deprecated"))
            + "ICD本文。\n",
        })
        new = _util.fm_block(_doc("billing", doc_id="SPEC-50",
                                  fm_extra={"depends_on": ["ICD-09"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-50-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_tc123_unclassifiable_dep_fail_closed_deny(self):
        """TC-123 / C13 deny side: depends_on [XYZ-01] whose prefix the registry
        cannot classify -> fail-closed deny."""
        root = self._repo({
            "docs/billing/spec/SPEC-60.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-60")) + "本文。\n",
        })
        new = _util.fm_block(_doc("billing", doc_id="SPEC-61",
                                  fm_extra={"depends_on": ["XYZ-01"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-61-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("XYZ-01", reason)

    def test_c13_dangling_companion_allowed(self):
        """C13 companion (critique gap 4): a syntactically valid id with a known
        prefix but absent from the graph (dangling) -> guard ALLOWS; dead-link is
        audit's job. Pairs with TC-123 deny side."""
        root = self._repo({
            "docs/billing/spec/SPEC-70.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-70")) + "本文。\n",
        })
        # DATA-999 is a valid TYPE prefix but no such doc exists -> dangling.
        new = _util.fm_block(_doc("billing", doc_id="SPEC-71",
                                  fm_extra={"depends_on": ["DATA-999"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-71-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_status_blind_current_icd_irrelevant(self):
        """C12 restated: even a non-ICD cross-domain dep that is itself `current`
        is denied — status of the dep never saves a non-ICD cross-domain link."""
        root = self._repo({
            "docs/identity/spec/SPEC-22.md": _util.fm_block(_doc(
                "identity", doc_id="SPEC-22", status="current")) + "本文。\n",
        })
        new = _util.fm_block(_doc("billing", doc_id="SPEC-80",
                                  fm_extra={"depends_on": ["SPEC-22"]}))
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-80-x.md"),
               "content": new + "本文。\n"}
        out, _ = _util.invoke("policy-guard",
                              stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertEqual(
            reason, "SPEC-22 は identity の内部です。identity の ICD 宛にしてください。")


# ---------------------------------------------------------------------------
# B11 / TC-119 — Edit/MultiEdit post-apply block for the same violation (C4)
# ---------------------------------------------------------------------------

class TestPostBlock(GuardTestBase):
    """B11 (TC-073/074) + TC-119 — post-apply decision:block emitted by policy-guard."""

    def _identity_internal_repo(self):
        return self._repo({
            "docs/identity/spec/SPEC-22.md": _util.fm_block(_doc(
                "identity", doc_id="SPEC-22")) + "内部仕様。\n",
        })

    def test_tc073_edit_pre_allow_then_post_block(self):
        """TC-073: an Edit that introduces the cross-domain non-ICD dep cannot be
        pre-denied (allow at PreToolUse); after apply, policy-guard on PostToolUse
        re-reads the file and emits decision:block with the same message."""
        root = self._identity_internal_repo()
        # The billing SPEC, already on disk, now WITH the offending dep (post-apply state).
        billing_path = os.path.join(root, "docs/billing/spec/SPEC-90.md")
        os.makedirs(os.path.dirname(billing_path), exist_ok=True)
        with open(billing_path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="SPEC-90",
                                         fm_extra={"depends_on": ["SPEC-22"]}))
                     + "本文。\n")

        # PreToolUse Edit -> allow (cannot reconstruct full frontmatter pre-apply).
        edit_tin = {"file_path": billing_path,
                    "old_string": "本文。", "new_string": "本文(更新)。"}
        out_pre, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", edit_tin))
        decision, _ = _pre(json.loads(out_pre))
        self.assertEqual(decision, "allow")

        # PostToolUse Edit -> decision:block, same R7 message.
        out_post, code = _util.invoke(
            "policy-guard",
            stdin_obj=_util.hook_stdin("PostToolUse", "Edit", edit_tin,
                                       tool_response={"filePath": billing_path}))
        self.assertEqual(code, 0)
        resp = json.loads(out_post)
        self.assertEqual(resp.get("decision"), "block")
        self.assertEqual(
            resp.get("reason"),
            "SPEC-22 は identity の内部です。identity の ICD 宛にしてください。")
        # additionalContext carries the same message (C4).
        self.assertEqual(
            resp["hookSpecificOutput"]["additionalContext"],
            "SPEC-22 は identity の内部です。identity の ICD 宛にしてください。")

    def test_tc074_multiedit_post_block(self):
        """TC-074: a MultiEdit introducing the same violation -> decision:block."""
        root = self._identity_internal_repo()
        path = os.path.join(root, "docs/billing/spec/SPEC-91.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="SPEC-91",
                                         fm_extra={"depends_on": ["SPEC-22"]}))
                     + "本文。\n")
        tin = {"file_path": path,
               "edits": [{"old_string": "本文。", "new_string": "改。"}]}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "MultiEdit", tin))
        resp = json.loads(out)
        self.assertEqual(resp.get("decision"), "block")
        self.assertIn("identity の ICD 宛に", resp.get("reason"))

    def test_tc119_write_deny_vs_edit_block_same_violation(self):
        """TC-119: the SAME ICD violation -> Write gives permissionDecision:deny
        (no disk change), Edit gives decision:block (disk transiently inconsistent).
        Two code paths, same message, different output grammar."""
        root = self._identity_internal_repo()
        msg = "SPEC-22 は identity の内部です。identity の ICD 宛にしてください。"

        # Write path -> pre-deny.
        wpath = os.path.join(root, "docs/billing/spec/SPEC-92.md")
        wtin = {"file_path": wpath,
                "content": _util.fm_block(_doc("billing", doc_id="SPEC-92",
                                               fm_extra={"depends_on": ["SPEC-22"]}))
                + "本文。\n"}
        out_w, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", wtin))
        dec_w, reason_w = _pre(json.loads(out_w))
        self.assertEqual(dec_w, "deny")
        self.assertEqual(reason_w, msg)
        # Write must NOT have written the offending file (pre-deny -> no disk change
        # by the guard; the guard never writes).
        self.assertFalse(os.path.exists(wpath))

        # Edit path -> post-block (disk already inconsistent).
        epath = os.path.join(root, "docs/billing/spec/SPEC-93.md")
        os.makedirs(os.path.dirname(epath), exist_ok=True)
        with open(epath, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="SPEC-93",
                                         fm_extra={"depends_on": ["SPEC-22"]}))
                     + "本文。\n")
        etin = {"file_path": epath, "old_string": "本文。", "new_string": "改。"}
        out_e, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", etin))
        resp = json.loads(out_e)
        self.assertEqual(resp.get("decision"), "block")
        self.assertEqual(resp.get("reason"), msg)

    def test_linter_never_emits_decision(self):
        """Critique gap 3: docs-linter stays pure-advisory (never `decision`).
        Bind the post-apply block to policy-guard, not the linter. We assert the
        guard emits `decision:block` AND, if docs-linter exists, that it does not."""
        root = self._identity_internal_repo()
        path = os.path.join(root, "docs/billing/spec/SPEC-94.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="SPEC-94",
                                         fm_extra={"depends_on": ["SPEC-22"]}))
                     + "本文。\n")
        tin = {"file_path": path, "old_string": "本文。", "new_string": "改。"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(json.loads(out).get("decision"), "block")

        linter = os.path.join(_util.SCRIPTS, "docs-linter.py")
        if os.path.isfile(linter):
            out_l, _ = _util.invoke(
                "docs-linter",
                stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
            if out_l.strip():
                resp_l = json.loads(out_l)
                self.assertNotIn("decision", resp_l)


# ---------------------------------------------------------------------------
# B12 — immutability (archive + existing ADR), TC-075/076/077
# ---------------------------------------------------------------------------

class TestImmutability(GuardTestBase):
    """B12 (TC-075/076/077) — Guard1 immutability."""

    def test_tc075_edit_plain_current_doc_allowed(self):
        """TC-075: editing a non-archive, non-ADR current doc with no deps -> allow."""
        root = self._repo({
            "docs/billing/spec/SPEC-01.md": _util.fm_block(_doc("billing"))
            + "本文。\n",
        })
        path = os.path.join(root, "docs/billing/spec/SPEC-01.md")
        tin = {"file_path": path, "old_string": "本文。", "new_string": "本文改。"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_tc076_write_under_archive_denied(self):
        """TC-076: any Write/Edit under <domain>/archive/** -> deny (immutable)."""
        root = self._repo({})
        path = os.path.join(root, "docs/billing/archive/ARCHIVE-03-old.md")
        tin = {"file_path": path,
               "content": _util.fm_block(_doc("billing", doc_id="ARCHIVE-03",
                                              type_code="ARCHIVE", status="archived"))}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("アーカイブ", reason)

    def test_tc076_edit_under_archive_denied(self):
        """TC-076 (edit variant): editing an existing archived doc -> deny."""
        root = self._repo({
            "docs/billing/archive/ARCHIVE-03-old.md": _util.fm_block(_doc(
                "billing", doc_id="ARCHIVE-03", type_code="ARCHIVE",
                status="archived")) + "古い本文。\n",
        })
        path = os.path.join(root, "docs/billing/archive/ARCHIVE-03-old.md")
        tin = {"file_path": path, "old_string": "古い本文。", "new_string": "改ざん。"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "deny")

    def test_tc077_edit_existing_adr_denied(self):
        """TC-077: editing an existing ADR body -> deny (existing ADR immutable)."""
        root = self._repo({
            "docs/billing/decisions/ADR-07-choice.md": _util.fm_block(_doc(
                "billing", doc_id="ADR-07", type_code="ADR", status="accepted"))
            + "決定の本文。\n",
        })
        path = os.path.join(root, "docs/billing/decisions/ADR-07-choice.md")
        tin = {"file_path": path, "old_string": "決定の本文。",
               "new_string": "別の決定。"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("ADR", reason)

    def test_tc077_sub_new_adr_via_write_allowed(self):
        """TC-077 sub: creating a NEW ADR via Write (no file on disk) -> allow."""
        root = self._repo({})
        path = os.path.join(root, "docs/billing/decisions/ADR-08-new.md")
        tin = {"file_path": path,
               "content": _util.fm_block(_doc("billing", doc_id="ADR-08",
                                              type_code="ADR", status="accepted"))
               + "新しい決定。\n"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_adr_carveout_status_move_allowed(self):
        """D0.8 carve-out: an Edit that only moves ADR status accepted->superseded
        and adds superseded_by -> allow."""
        root = self._repo({
            "docs/billing/decisions/ADR-09.md": _util.fm_block(_doc(
                "billing", doc_id="ADR-09", type_code="ADR", status="accepted"))
            + "決定本文。\n",
        })
        path = os.path.join(root, "docs/billing/decisions/ADR-09.md")
        # Two edits: status line + add superseded_by line. Body untouched.
        tin = {"file_path": path,
               "edits": [
                   {"old_string": "status: accepted",
                    "new_string": "status: superseded\nsuperseded_by: ADR-10"},
               ]}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "MultiEdit", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "allow", reason)

    def test_adr_carveout_body_change_denied(self):
        """Carve-out boundary: an Edit moving ADR status BUT also rewriting the body
        -> deny (body change is outside the carve-out)."""
        root = self._repo({
            "docs/billing/decisions/ADR-11.md": _util.fm_block(_doc(
                "billing", doc_id="ADR-11", type_code="ADR", status="accepted"))
            + "元の決定本文。\n",
        })
        path = os.path.join(root, "docs/billing/decisions/ADR-11.md")
        tin = {"file_path": path,
               "edits": [
                   {"old_string": "status: accepted", "new_string": "status: superseded"},
                   {"old_string": "元の決定本文。", "new_string": "書き換えた決定。"},
               ]}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "MultiEdit", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "deny")


# ---------------------------------------------------------------------------
# B13 — delete-safety, TC-078/079/080/081, TC-118 sequence
# ---------------------------------------------------------------------------

class TestDeleteSafety(GuardTestBase):
    """B13 (TC-078..081) + TC-118 — Guard3 delete-safety."""

    def _depended_repo(self, target_status="current"):
        """SPEC-14 (current) depended on by current TEST-20."""
        return self._repo({
            "docs/billing/spec/SPEC-14.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-14", status=target_status)) + "仕様本文。\n",
            "docs/billing/test/TEST-20.md": _util.fm_block(_doc(
                "billing", doc_id="TEST-20", type_code="TEST", status="current",
                fm_extra={"depends_on": ["SPEC-14"]})) + "試験本文。\n",
        })

    def test_tc078_demote_with_dependents_denied(self):
        """TC-078: Edit sets status:current->deprecated while a current doc still
        depends_on it -> deny, names the dependents."""
        root = self._depended_repo()
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"file_path": path, "old_string": "status: current",
               "new_string": "status: deprecated"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("TEST-20", reason)
        self.assertIn("SPEC-14", reason)

    def test_tc079_empty_body_with_dependents_denied(self):
        """TC-079: Write that empties the body of a depended-on current doc -> deny."""
        root = self._depended_repo()
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"file_path": path,
               "content": _util.fm_block(_doc("billing", doc_id="SPEC-14",
                                              status="current"))}  # no body
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("TEST-20", reason)

    def test_tc081_demote_with_zero_dependents_allowed(self):
        """TC-081 / TC-044: demote a doc with ZERO current dependents -> allow."""
        root = self._repo({
            "docs/billing/spec/SPEC-15.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-15", status="current")) + "本文。\n",
        })
        path = os.path.join(root, "docs/billing/spec/SPEC-15.md")
        tin = {"file_path": path, "old_string": "status: current",
               "new_string": "status: deprecated"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_tc080_bash_rm_depended_doc_denied(self):
        """TC-080: Bash rm of a doc with current dependents -> deny."""
        root = self._depended_repo()
        target = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"command": "rm %s" % target}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        decision, reason = _pre(json.loads(out))
        self.assertEqual(decision, "deny")
        self.assertIn("TEST-20", reason)

    def test_bash_git_rm_denied(self):
        """D3: Bash `git rm` of a current doc with dependents -> deny."""
        root = self._depended_repo()
        target = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"command": "git rm %s" % target}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "deny")

    def test_bash_mv_depended_doc_denied(self):
        """D4: Bash `mv` of a current doc with dependents -> deny (D0.5)."""
        root = self._depended_repo()
        target = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        dst = os.path.join(root, "docs/billing/archive/")
        tin = {"command": "mv %s %s" % (target, dst)}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "deny")

    def test_bash_rm_no_dependents_allowed(self):
        """D2: Bash rm of a doc with ZERO dependents -> allow."""
        root = self._repo({
            "docs/billing/spec/SPEC-16.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-16", status="current")) + "本文。\n",
        })
        target = os.path.join(root, "docs/billing/spec/SPEC-16.md")
        tin = {"command": "rm %s" % target}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")

    def test_bash_chained_command_one_violates_denies_all(self):
        """D5: `rm a && rm b` where b has dependents -> deny the WHOLE command (D0.6)."""
        root = self._depended_repo()
        a = os.path.join(root, "docs/billing/spec/SPEC-17.md")  # no such doc -> harmless
        b = os.path.join(root, "docs/billing/spec/SPEC-14.md")  # depended on
        tin = {"command": "rm %s && rm %s" % (a, b)}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "deny")

    def test_bash_rm_with_redirect_no_false_deny(self):
        """#10: shell redirection operands are NOT deletion targets. `rm <doc> >
        <log>` and `rm <doc> 2>/dev/null` must judge only <doc>; the redirect
        target (even if it spells a depended-on doc path) must not produce a
        false deny. Here the rm target has ZERO dependents -> allow, and the
        redirect destination IS a depended-on doc path that must be ignored."""
        root = self._depended_repo()  # SPEC-14 depended on by TEST-20
        depended = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        # A standalone doc with no dependents — the actual rm target.
        free_path = os.path.join(root, "docs/billing/spec/SPEC-16.md")
        os.makedirs(os.path.dirname(free_path), exist_ok=True)
        with open(free_path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="SPEC-16",
                                         status="current")) + "本文。\n")

        # Redirect the rm output INTO the depended-on doc path: `> SPEC-14.md`.
        # The old buggy tokenizer would treat SPEC-14.md as a deletion target
        # and falsely deny. The fix drops the redirect operand.
        for cmd in ("rm %s > %s" % (free_path, depended),
                    "rm %s 2>%s" % (free_path, depended),
                    "rm %s 2>/dev/null" % depended):  # last: rm the depended doc but redirect-only token follows
            tin = {"command": cmd}
            out, _ = _util.invoke(
                "policy-guard",
                stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
            decision, reason = _pre(json.loads(out))
            if cmd.startswith("rm %s 2>/dev/null" % depended):
                # rm of the depended-on doc itself -> deny (redirect is separate).
                self.assertEqual(decision, "deny", cmd)
                self.assertIn("TEST-20", reason)
            else:
                self.assertEqual(decision, "allow", cmd)

    def test_tc118_demote_blocked_then_repoint_then_allowed(self):
        """TC-118: step1 demote SPEC-14 (deps remain) -> deny; step2 re-point the
        dependent to a successor; step3 re-demote SPEC-14 -> allowed (sequence)."""
        root = self._depended_repo()
        spec_path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        test_path = os.path.join(root, "docs/billing/test/TEST-20.md")

        # step1: demote -> deny.
        tin = {"file_path": spec_path, "old_string": "status: current",
               "new_string": "status: deprecated"}
        out1, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        self.assertEqual(_pre(json.loads(out1))[0], "deny")

        # step2: re-point the dependent away from SPEC-14 (edit on disk).
        with open(test_path, "w", encoding="utf-8") as fh:
            fh.write(_util.fm_block(_doc("billing", doc_id="TEST-20", type_code="TEST",
                                         status="current",
                                         fm_extra={"depends_on": ["SPEC-99"]}))
                     + "試験本文。\n")

        # step3: re-demote -> allow (zero current dependents now).
        out3, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        self.assertEqual(_pre(json.loads(out3))[0], "allow")

    def test_demote_non_current_target_allowed(self):
        """A doc that is already deprecated has no `current` demotion to block even
        with dependents: demotion invariant is keyed on the CURRENT->demoted move."""
        root = self._depended_repo(target_status="deprecated")
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"file_path": path, "old_string": "status: deprecated",
               "new_string": "status: archived"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Edit", tin))
        decision, _ = _pre(json.loads(out))
        self.assertEqual(decision, "allow")


# ---------------------------------------------------------------------------
# #00/#01 — PostToolUse delete-safety is a TRANSITION, not a POST-state read
# ---------------------------------------------------------------------------

class TestPostDeleteSafetyTransition(GuardTestBase):
    """The PostToolUse delete-safety re-judge must key on an actual
    current/accepted -> demoted (or non-empty -> empty) transition, mirroring
    guard_delete_safety_edit. POST-state alone wrongly blocks an unrelated edit
    of an already-demoted or already-empty depended-on doc (#00/#01)."""

    def _depended(self, spec_status="current", spec_body="仕様本文。\n"):
        """SPEC-14 depended on by a current TEST-20."""
        return self._repo({
            "docs/billing/spec/SPEC-14.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-14", status=spec_status)) + spec_body,
            "docs/billing/test/TEST-20.md": _util.fm_block(_doc(
                "billing", doc_id="TEST-20", type_code="TEST", status="current",
                fm_extra={"depends_on": ["SPEC-14"]})) + "試験本文。\n",
        })

    def test_already_deprecated_depended_doc_body_edit_no_block(self):
        """#00: a body-only Edit of an ALREADY-deprecated depended-on doc that
        STAYS deprecated -> NO decision:block (no current->demoted transition).
        The doc was deprecated before AND after; only its body changed."""
        root = self._depended(spec_status="deprecated")
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        # Apply the edit on disk (post-apply state) and feed the SAME edit to post.
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new_text = text.replace("仕様本文。", "仕様本文(更新)。")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        tin = {"file_path": path, "old_string": "仕様本文。",
               "new_string": "仕様本文(更新)。"}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertNotEqual(resp.get("decision"), "block")

    def test_already_empty_body_depended_doc_frontmatter_edit_no_block(self):
        """#01: a frontmatter-only Edit of a current depended-on doc whose body
        was ALREADY empty -> NO decision:block (no non-empty->empty transition)."""
        # SPEC-14 current but body already empty; edit only the owner line.
        root = self._depended(spec_status="current", spec_body="")
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new_text = text.replace("owner: o", "owner: o2")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        tin = {"file_path": path, "old_string": "owner: o",
               "new_string": "owner: o2"}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertNotEqual(resp.get("decision"), "block")

    def test_genuine_current_to_deprecated_transition_blocks(self):
        """Positive: a genuine current->deprecated PostToolUse Edit with current
        dependents -> decision:block (the transition this guard exists to catch)."""
        root = self._depended(spec_status="current")
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new_text = text.replace("status: current", "status: deprecated")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        tin = {"file_path": path, "old_string": "status: current",
               "new_string": "status: deprecated"}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(resp.get("decision"), "block")
        self.assertIn("TEST-20", resp.get("reason"))
        self.assertIn("SPEC-14", resp.get("reason"))

    def test_frontmatter_region_edit_already_deprecated_no_block(self):
        """#00 hardening (raw-text inversion): a frontmatter-region Edit of an
        ALREADY-deprecated depended-on doc, where the edited line does NOT
        round-trip byte-identically through a re-render, must NOT block.

        The edit touches a DOUBLE-QUOTED title (`title: "x: 注記つき"`). A
        _render_doc() re-render drops the quotes, so the old render-based
        reconstruction cannot find `old_string`, falls back to the safe default
        ('current', non-empty) and FALSELY blocks (current->deprecated). The raw
        on-disk bytes contain the quoted line verbatim, so inverting against them
        recovers the true pre-state ('deprecated') -> no transition -> no block.
        This case fails under the pre-hardening code and passes only with the
        raw_post_text path in _reconstruct_pre_edit_state."""
        spec = (
            "---\n"
            "id: SPEC-14\n"
            'title: "x: 注記つき改"\n'        # post-edit state already on disk
            "type: SPEC\n"
            "domain: billing\n"
            "status: deprecated\n"
            "owner: o\n"
            "updated: 2026-01-01\n"
            "sources: [a, b]\n"
            "depends_on: [REQ-1]\n"
            "---\n"
            "# 入出力\n本文。\n# 制約\n# エラー時挙動\n# 受入基準\n"
        )
        root = self._repo({
            "docs/billing/spec/SPEC-14.md": spec,
            "docs/billing/test/TEST-20.md": _util.fm_block(_doc(
                "billing", doc_id="TEST-20", type_code="TEST", status="current",
                fm_extra={"depends_on": ["SPEC-14"]})) + "試験本文。\n",
        })
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"file_path": path, "old_string": 'title: "x: 注記つき"',
               "new_string": 'title: "x: 注記つき改"'}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertNotEqual(resp.get("decision"), "block")

    def test_genuine_nonempty_to_empty_body_transition_blocks(self):
        """Positive: an Edit that empties a non-empty depended-on current doc's
        body -> decision:block (non-empty -> empty transition)."""
        root = self._depended(spec_status="current", spec_body="仕様本文。\n")
        path = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        # Remove the body, leaving frontmatter only.
        new_text = text.replace("仕様本文。\n", "")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        tin = {"file_path": path, "old_string": "仕様本文。\n", "new_string": ""}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Edit", tin))
        self.assertEqual(code, 0)
        resp = json.loads(out)
        self.assertEqual(resp.get("decision"), "block")
        self.assertIn("本文を空にする前に", resp.get("reason"))


# ---------------------------------------------------------------------------
# TC-132 / §3.5 — Bash matcher output grammar (deny-only)
# ---------------------------------------------------------------------------

class TestBashOutputGrammar(GuardTestBase):
    """TC-132 / D9 — Bash branch is deny-only; no additionalContext, no decision."""

    def test_tc132_bash_deny_has_no_additional_context_or_block(self):
        root = self._repo({
            "docs/billing/spec/SPEC-14.md": _util.fm_block(_doc(
                "billing", doc_id="SPEC-14", status="current")) + "本文。\n",
            "docs/billing/test/TEST-20.md": _util.fm_block(_doc(
                "billing", doc_id="TEST-20", type_code="TEST", status="current",
                fm_extra={"depends_on": ["SPEC-14"]})) + "試験。\n",
        })
        target = os.path.join(root, "docs/billing/spec/SPEC-14.md")
        tin = {"command": "rm %s" % target}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Bash", tin))
        resp = json.loads(out)
        self.assertEqual(_pre(resp)[0], "deny")
        # Only the PreToolUse permission grammar is present.
        self.assertNotIn("decision", resp)
        self.assertNotIn("additionalContext", resp.get("hookSpecificOutput", {}))


# ---------------------------------------------------------------------------
# Routing / robustness — W2/W3/W4
# ---------------------------------------------------------------------------

class TestRoutingRobustness(GuardTestBase):
    """W2/W3/W4 — self-routing and fail-closed/open."""

    def test_w4_allowed_write_explicit_allow_exit0(self):
        """W4: a clean Write emits permissionDecision:allow, exit 0."""
        root = self._repo({})
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-01.md"),
               "content": _util.fm_block(_doc("billing")) + "本文。\n"}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        self.assertEqual(code, 0)
        self.assertEqual(_pre(json.loads(out))[0], "allow")

    def test_unknown_tool_pretooluse_allows(self):
        """A PreToolUse for a tool we don't match (e.g. Read) -> allow."""
        out, code = _util.invoke(
            "policy-guard",
            stdin_obj=_util.hook_stdin("PreToolUse", "Read", {"file_path": "x"}))
        self.assertEqual(code, 0)
        self.assertEqual(_pre(json.loads(out))[0], "allow")

    def test_empty_stdin_never_crashes(self):
        """main never raises; empty stdin -> exit 0, valid JSON."""
        out, code = _util.invoke("policy-guard", stdin_obj="")
        self.assertEqual(code, 0)
        json.loads(out)  # must be valid JSON

    def test_w3_fail_open_non_doc_write_outside_docs(self):
        """W3 / D0.4: a Write of a genuine non-doc file (no frontmatter) OUTSIDE
        docs/** -> Guard2 fail-open allow even though it can't be parsed as a doc."""
        root = self._repo({})
        tin = {"file_path": os.path.join(root, "src/main.py"),
               "content": "print('hello')\n"}
        out, _ = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PreToolUse", "Write", tin))
        self.assertEqual(_pre(json.loads(out))[0], "allow")

    def test_post_write_quiet(self):
        """PostToolUse on Write is not handled by the post block path (Write was
        pre-judged) -> quiet empty response."""
        root = self._repo({
            "docs/billing/spec/SPEC-01.md": _util.fm_block(_doc("billing"))
            + "本文。\n",
        })
        tin = {"file_path": os.path.join(root, "docs/billing/spec/SPEC-01.md"),
               "content": _util.fm_block(_doc("billing")) + "本文。\n"}
        out, code = _util.invoke(
            "policy-guard", stdin_obj=_util.hook_stdin("PostToolUse", "Write", tin))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {})


if __name__ == "__main__":
    unittest.main()
