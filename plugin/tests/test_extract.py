#!/usr/bin/env python3
"""Tests for term-extract.py (c-TF-IDF candidate generator, read-only).

Covers MASTER §5.7 + slice 07 §B and the critique gap assigned to this
component (term-extract candidate-only / writes-nothing / single-domain notice /
exclusions / determinism):
  - candidate-only + writes-nothing (read-only proof; repo byte-identical)
  - single-domain low-confidence notice
  - default exclusions (_system, archive/, llm_context:never) + --all / --include-system
  - determinism (tie-break by term; byte-identical re-runs)
  - distinctiveness (domain-specific terms outrank shared terms)
  - tokenization approximation (JP bigrams, EN words, digits/len-1 dropped, fences)
  - --top / --min-df honored; json schema stable; robustness on odd files
"""
import os
import sys
import json
import shutil
import hashlib
import subprocess
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _util


def _doc(domain, type_code, status, body, llm_context=None):
    fm = {
        "id": "%s-001" % type_code,
        "type": type_code,
        "domain": domain,
        "status": status,
    }
    if llm_context is not None:
        fm["llm_context"] = llm_context
    return _util.fm_block(fm) + body + "\n"


class ExtractBase(unittest.TestCase):
    def setUp(self):
        self.root = _util.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def write(self, relpath, content):
        abspath = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        return abspath

    def run_extract(self, *extra):
        argv = ["--root", self.root] + list(extra)
        return _util.invoke("term-extract", argv=argv)


class TestTokenization(ExtractBase):
    """B.8-4: JP bigrams, EN words, digits/len-1 dropped, code fences excluded."""

    def test_english_word_tokens(self):
        mod = _util.load_script("term-extract")
        toks = mod.tokenize("refund Policy login_token")
        self.assertIn("refund", toks)
        self.assertIn("policy", toks)      # lowercased
        self.assertIn("login_token", toks)

    def test_japanese_bigrams(self):
        mod = _util.load_script("term-extract")
        toks = mod.tokenize("請求書")
        # '請求書' -> bigrams 請求, 求書
        self.assertIn("請求", toks)
        self.assertIn("求書", toks)

    def test_digits_and_length1_ascii_dropped(self):
        mod = _util.load_script("term-extract")
        toks = mod.tokenize("a 12345 ab")
        self.assertNotIn("a", toks)        # length-1 ascii dropped
        self.assertNotIn("12345", toks)    # pure digit dropped
        self.assertIn("ab", toks)

    def test_code_fences_excluded(self):
        mod = _util.load_script("term-extract")
        body = "realword\n```\nfencedcode fencedcode\n```\nrealword"
        toks = mod.tokenize(body)
        self.assertIn("realword", toks)
        self.assertNotIn("fencedcode", toks)


class TestDistinctiveness(ExtractBase):
    """B.8-1: domain-specific terms outrank shared/common terms (c-TF-IDF)."""

    def setUp(self):
        super().setUp()
        self.write("docs/billing/spec/SPEC-001-refund.md", _doc(
            "billing", "SPEC", "current",
            "refund refund refund refund payment shared shared common"))
        self.write("docs/identity/spec/SPEC-002-login.md", _doc(
            "identity", "SPEC", "current",
            "login login login login session shared shared common"))

    def test_billing_distinctive_term_ranks_first(self):
        out, code = self.run_extract("--min-df", "1", "--top", "10",
                                     "--format", "json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        billing = [r["term"] for r in data["domains"]["billing"]]
        # 'refund' is billing-distinctive; 'shared'/'common' appear in both.
        self.assertEqual(billing[0], "refund")
        self.assertLess(billing.index("refund"), billing.index("shared"))

    def test_symmetric_for_identity(self):
        out, code = self.run_extract("--min-df", "1", "--top", "10",
                                     "--format", "json")
        data = json.loads(out)
        identity = [r["term"] for r in data["domains"]["identity"]]
        self.assertEqual(identity[0], "login")
        self.assertLess(identity.index("login"), identity.index("shared"))


class TestWritesNothing(ExtractBase):
    """B.8-2 (critique gap): read-only proof — the repo is byte-identical after
    a run, and the script writes nothing to the glossary or any doc."""

    def _hash_tree(self):
        h = {}
        for dp, dn, fn in os.walk(self.root):
            for f in sorted(fn):
                p = os.path.join(dp, f)
                with open(p, "rb") as fh:
                    h[os.path.relpath(p, self.root)] = hashlib.sha256(
                        fh.read()).hexdigest()
        return h

    def test_repo_unchanged_after_run(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund 請求"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login 認証"))
        # Seed a glossary; assert term-extract never touches it.
        self.write("docs/_system/glossary.md",
                   _doc("_system", "GLOSSARY", "current", "GLOSSARY-SENTINEL",
                        llm_context="always"))
        before = self._hash_tree()
        out, code = self.run_extract("--min-df", "1")
        self.assertEqual(code, 0)
        after = self._hash_tree()
        self.assertEqual(before, after, "term-extract modified the repo")
        # Output advertises the human-approval contract.
        self.assertIn("採否は人間", out)


class TestSingleDomainNotice(ExtractBase):
    """B.8-5: a single domain has no cross-class contrast -> low-confidence
    notice, still exits 0 and emits the within-class ranking."""

    def test_single_domain_low_confidence_notice(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "refund refund 請求 請求 policy"))
        out, code = self.run_extract("--min-df", "1", "--top", "5")
        self.assertEqual(code, 0)
        self.assertIn("2ドメイン以上が要る", out)
        # Still produced a billing block.
        self.assertIn("domain: billing", out)

    def test_two_domains_no_low_confidence_notice(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1")
        self.assertEqual(code, 0)
        self.assertNotIn("2ドメイン以上が要る", out)

    def test_single_domain_json_flag_true(self):
        # #22: single-domain JSON carries single_domain_low_confidence==True.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        out, code = self.run_extract("--min-df", "1", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["single_domain_low_confidence"])

    def test_two_domain_json_flag_false(self):
        # #22: a two-domain run has single_domain_low_confidence==False.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["single_domain_low_confidence"])


class TestExclusions(ExtractBase):
    """B.8-7: archive/ and llm_context:never excluded by default; present
    under --all. _system excluded by default; present under --include-system."""

    def setUp(self):
        super().setUp()
        # Two live domains so contrast exists.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        # An archive doc with a unique forensic term.
        self.write("docs/billing/archive/ARCHIVE-001.md",
                   _doc("billing", "ARCHIVE", "archived", "forensicword forensicword",
                        llm_context="never"))
        # A RESEARCH doc (llm_context never by default) with a unique term.
        self.write("docs/billing/research/RESEARCH-001.md",
                   _doc("billing", "RESEARCH", "draft", "researchword researchword",
                        llm_context="never"))
        # A _system doc with a unique term.
        self.write("docs/_system/glossary.md",
                   _doc("_system", "GLOSSARY", "current", "systemword systemword",
                        llm_context="always"))

    def _terms_csv(self, out):
        terms = set()
        for line in out.splitlines()[1:]:
            cols = line.split(",")
            if len(cols) >= 3:
                terms.add(cols[2])
        return terms

    def test_archive_and_never_excluded_by_default(self):
        out, code = self.run_extract("--min-df", "1", "--top", "50",
                                     "--format", "csv")
        terms = self._terms_csv(out)
        self.assertNotIn("forensicword", terms)
        self.assertNotIn("researchword", terms)

    def test_all_includes_archive_and_never(self):
        out, code = self.run_extract("--min-df", "1", "--top", "50",
                                     "--format", "csv", "--all")
        terms = self._terms_csv(out)
        self.assertIn("forensicword", terms)

    def test_system_excluded_by_default(self):
        out, code = self.run_extract("--min-df", "1", "--top", "50",
                                     "--format", "csv")
        self.assertNotIn("_system", out)
        terms = self._terms_csv(out)
        self.assertNotIn("systemword", terms)

    def test_include_system_adds_system_class(self):
        out, code = self.run_extract("--min-df", "1", "--top", "50",
                                     "--format", "csv", "--include-system")
        self.assertIn("_system", out)


class TestDeterminism(ExtractBase):
    """B.8-6 (critique gap): byte-identical re-runs; tie-break by term asc."""

    def setUp(self):
        super().setUp()
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "alpha alpha beta beta gamma gamma"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "delta delta"))

    def test_byte_identical_reruns(self):
        out1, _ = self.run_extract("--min-df", "1", "--format", "json")
        out2, _ = self.run_extract("--min-df", "1", "--format", "json")
        self.assertEqual(out1, out2)

    def test_tie_break_by_term_ascending(self):
        # alpha/beta/gamma each appear twice in billing only -> identical score;
        # tie-break must order them alpha < beta < gamma.
        out, code = self.run_extract("--min-df", "1", "--top", "10",
                                     "--format", "json")
        data = json.loads(out)
        billing = [r["term"] for r in data["domains"]["billing"]]
        idx = {t: billing.index(t) for t in ("alpha", "beta", "gamma")}
        self.assertLess(idx["alpha"], idx["beta"])
        self.assertLess(idx["beta"], idx["gamma"])


class TestTopAndMinDf(ExtractBase):
    """B.8-8: --top caps per-domain candidates; --min-df drops hapax noise."""

    def setUp(self):
        super().setUp()
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "one two three four five six seven eight"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))

    def test_top_caps_candidates(self):
        out, code = self.run_extract("--min-df", "1", "--top", "3",
                                     "--format", "json")
        data = json.loads(out)
        self.assertLessEqual(len(data["domains"]["billing"]), 3)

    def test_min_df_drops_hapax(self):
        # Every billing word appears once -> min-df 2 drops them all.
        out, code = self.run_extract("--min-df", "2", "--format", "json")
        data = json.loads(out)
        self.assertEqual(data["domains"].get("billing", []), [])


class TestJsonSchema(ExtractBase):
    """B.8-9: stable JSON schema for docs-curate ingestion."""

    def test_schema_fields_present(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--format", "json")
        data = json.loads(out)
        for key in ("tokenization", "human_approval_required", "domains",
                    "classes_in_contrast", "warnings"):
            self.assertIn(key, data)
        self.assertTrue(data["human_approval_required"])
        self.assertEqual(data["tokenization"], "stdlib-bigram-approx")
        row = data["domains"]["billing"][0]
        for key in ("term", "c_tf_idf", "df"):
            self.assertIn(key, row)


class TestRobustness(ExtractBase):
    """B.8-10 / B.7: empty docs, unknown --domain, no docs/ -> exit 0, no crash."""

    def test_empty_docs_dir_exits_0(self):
        os.makedirs(os.path.join(self.root, "docs"))
        out, code = self.run_extract("--min-df", "1")
        self.assertEqual(code, 0)
        self.assertIn("候補なし", out)

    def test_no_docs_dir_exits_0_with_warning(self):
        out, code = self.run_extract("--min-df", "1", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(any("docs/" in w for w in data["warnings"]))

    def test_unknown_domain_warns_exits_0(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund"))
        out, code = self.run_extract("--min-df", "1", "--domain", "nope",
                                     "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(any("nope" in w for w in data["warnings"]))
        self.assertEqual(data["domains"], {})

    def test_frontmatterless_file_does_not_crash(self):
        # A docs file with no frontmatter still tokenizes its body.
        self.write("docs/billing/spec/SPEC-001.md", "just body text words words")
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1")
        self.assertEqual(code, 0)


class TestDomainFilterKeepsContrast(ExtractBase):
    """B.5: --domain restricts what is PRINTED, but other domains still feed the
    idf contrast (so a filtered single-domain print is NOT low-confidence)."""

    def test_domain_filter_does_not_collapse_contrast(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund shared"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login shared"))
        out, code = self.run_extract("--min-df", "1", "--domain", "billing")
        self.assertEqual(code, 0)
        self.assertIn("domain: billing", out)
        self.assertNotIn("domain: identity", out)
        # Two classes in contrast -> NOT the single-domain notice.
        self.assertNotIn("2ドメイン以上が要る", out)


class TestCsvContract(ExtractBase):
    """#07: CSV must carry the same human-approval contract as text/json:
    a human-approval disclaimer, and (single-domain) the low-confidence notice
    and any warnings — not a bare table."""

    def test_csv_carries_human_approval_disclaimer(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--format", "csv")
        self.assertEqual(code, 0)
        # The human-approval contract appears in CSV just like text/json.
        self.assertIn("採否は人間", out)
        # And it is a comment row (does not corrupt the data table header).
        self.assertIn("domain,rank,term,c_tf_idf,df", out)

    def test_csv_single_domain_low_confidence_marker(self):
        # #07/#22: single-domain CSV carries the low-confidence marker.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        out, code = self.run_extract("--min-df", "1", "--format", "csv")
        self.assertEqual(code, 0)
        self.assertIn("採否は人間", out)
        self.assertIn("2ドメイン以上が要る", out)

    def test_csv_two_domains_no_low_confidence_marker(self):
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--format", "csv")
        self.assertEqual(code, 0)
        self.assertIn("採否は人間", out)
        self.assertNotIn("2ドメイン以上が要る", out)

    def test_csv_carries_warnings(self):
        # Unknown --domain produces a warning; CSV must surface it.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current", "refund refund"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--format", "csv",
                                     "--domain", "nope")
        self.assertEqual(code, 0)
        self.assertIn("警告", out)
        self.assertIn("nope", out)


class TestDocumentFrequency(ExtractBase):
    """#21: the 'df' field is the DOCUMENT frequency (number of docs in the
    class containing the term), not the collection term count. --min-df filters
    on document frequency; c-TF-IDF scoring still uses the term frequency."""

    def test_term_count_is_not_document_frequency(self):
        # 'solo' appears 5x in ONE billing doc -> df=1; 'pair' appears once in
        # each of TWO billing docs -> df=2.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "solo solo solo solo solo pair"))
        self.write("docs/billing/spec/SPEC-002.md",
                   _doc("billing", "SPEC", "current", "pair other"))
        self.write("docs/identity/spec/SPEC-003.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "1", "--top", "50",
                                     "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        dfs = {r["term"]: r["df"] for r in data["domains"]["billing"]}
        self.assertEqual(dfs["solo"], 1, "df must be document count, not 5")
        self.assertEqual(dfs["pair"], 2)

    def test_min_df_filters_on_document_frequency(self):
        # 'solo' has term-count 5 but document frequency 1 -> dropped at min-df 2.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "solo solo solo solo solo pair"))
        self.write("docs/billing/spec/SPEC-002.md",
                   _doc("billing", "SPEC", "current", "pair other"))
        self.write("docs/identity/spec/SPEC-003.md",
                   _doc("identity", "SPEC", "current", "login login"))
        out, code = self.run_extract("--min-df", "2", "--top", "50",
                                     "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        terms = {r["term"] for r in data["domains"].get("billing", [])}
        self.assertNotIn("solo", terms, "df=1 term must be dropped at min-df 2")
        self.assertIn("pair", terms, "df=2 term must survive min-df 2")


class TestSubprocessDeterminism(ExtractBase):
    """#20: in-process re-runs cannot catch PYTHONHASHSEED-dependent set/dict
    ordering. Run term-extract as a SUBPROCESS under two different hash seeds
    with input exercising set/dict order (>=2 unknown --domain values and
    multiple domains/terms) and assert byte-identical stdout."""

    def _run_seeded(self, seed, extra):
        script = os.path.join(_util.SCRIPTS, "term-extract.py")
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = str(seed)
        argv = [sys.executable, script, "--root", self.root] + list(extra)
        proc = subprocess.run(argv, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
        return proc.stdout

    def setUp(self):
        super().setUp()
        # Multiple domains and many terms to stir dict/set iteration order.
        self.write("docs/billing/spec/SPEC-001.md",
                   _doc("billing", "SPEC", "current",
                        "alpha alpha beta beta gamma gamma delta delta"))
        self.write("docs/identity/spec/SPEC-002.md",
                   _doc("identity", "SPEC", "current",
                        "login login session session token token"))
        self.write("docs/payments/spec/SPEC-003.md",
                   _doc("payments", "SPEC", "current",
                        "charge charge invoice invoice ledger ledger"))

    def test_byte_identical_across_hash_seeds(self):
        # >=2 unknown --domain values force the unknown-domain warning loop,
        # whose order was hash-seed dependent before #08.
        extra = ["--min-df", "1", "--top", "50", "--format", "json",
                 "--domain", "zzz", "--domain", "yyy", "--domain", "billing"]
        out1 = self._run_seeded(1, extra)
        out2 = self._run_seeded(2, extra)
        self.assertEqual(out1, out2,
                         "stdout differs across PYTHONHASHSEED values")

    def test_byte_identical_across_hash_seeds_csv(self):
        extra = ["--min-df", "1", "--top", "50", "--format", "csv",
                 "--domain", "zzz", "--domain", "yyy"]
        out1 = self._run_seeded(1, extra)
        out2 = self._run_seeded(2, extra)
        self.assertEqual(out1, out2)


class TestArgErrors(unittest.TestCase):
    """#23: malformed CLI -> usage message on stdout and a non-zero exit."""

    def _invoke(self, *argv):
        return _util.invoke("term-extract", argv=list(argv))

    def test_unknown_flag(self):
        out, code = self._invoke("--bogus")
        self.assertNotEqual(code, 0)
        self.assertIn("usage error", out)

    def test_invalid_format(self):
        out, code = self._invoke("--format", "yaml")
        self.assertNotEqual(code, 0)
        self.assertIn("usage error", out)

    def test_non_integer_top(self):
        out, code = self._invoke("--top", "abc")
        self.assertNotEqual(code, 0)
        self.assertIn("usage error", out)

    def test_non_integer_min_df(self):
        out, code = self._invoke("--min-df", "x")
        self.assertNotEqual(code, 0)
        self.assertIn("usage error", out)


class TestStdlibOnly(unittest.TestCase):
    """B.8-3 / §6 meta: term-extract imports nothing third-party."""

    def test_no_third_party_imports(self):
        path = os.path.join(_util.SCRIPTS, "term-extract.py")
        src = _util.read(path)
        for banned in ("import numpy", "import yaml", "import requests",
                       "import sklearn", "import janome", "import mecab",
                       "from sklearn"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
