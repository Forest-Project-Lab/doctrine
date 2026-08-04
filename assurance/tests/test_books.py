#!/usr/bin/env python3
# doctrine:exempt 開発専用保証レーン(ADR-114)。仕様との対応はコード側に持たない
"""チャンク分割と引用照合の決定論試験（冊子の実物には依存しない）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness import books, prompts  # noqa: E402


class ChunkTest(unittest.TestCase):
    def test_deterministic(self):
        text = "\n".join("行%d の本文" % i for i in range(1, 101))
        a = books.chunk_lines(text, max_chars=300, overlap_lines=3)
        b = books.chunk_lines(text, max_chars=300, overlap_lines=3)
        self.assertEqual(a, b)

    def test_line_numbers_are_absolute_and_1_based(self):
        text = "\n".join("x%d" % i for i in range(1, 21))
        chunks = books.chunk_lines(text, max_chars=40, overlap_lines=2)
        self.assertEqual(chunks[0]["start_line"], 1)
        for c in chunks:
            body_lines = c["text"].splitlines()
            self.assertEqual(len(body_lines), c["end_line"] - c["start_line"] + 1)

    def test_overlap_present(self):
        text = "\n".join("y%d" % i for i in range(1, 31))
        chunks = books.chunk_lines(text, max_chars=60, overlap_lines=4)
        self.assertGreater(len(chunks), 1)
        self.assertLess(chunks[1]["start_line"], chunks[0]["end_line"] + 1)

    def test_numbered_uses_absolute_lines(self):
        text = "\n".join("z%d" % i for i in range(1, 11))
        chunks = books.chunk_lines(text, max_chars=30, overlap_lines=1)
        second = books.numbered(chunks[1])
        self.assertIn("L%d: " % chunks[1]["start_line"], second)

    def test_unknown_book_id_raises(self):
        """未知の冊子 id を黙って空にしない。"""
        with self.assertRaises(ValueError):
            books.load_book("iso26262")


class QuoteVerificationTest(unittest.TestCase):
    """引用の実在照合（反幻覚 oracle）が本当に棄却することの凍結。"""

    CHUNK = "検証は独立した組織が実施しなければならない。記録は追跡可能であること。"

    def _p(self, quote):
        return {"source_quote": quote, "title": "t", "statement": "s"}

    def test_real_quote_accepted(self):
        acc, rej = prompts.verify_principles(
            self.CHUNK, [self._p("独立した組織が実施しなければならない")])
        self.assertEqual(len(acc), 1)
        self.assertEqual(rej, [])

    def test_fabricated_quote_rejected(self):
        acc, rej = prompts.verify_principles(
            self.CHUNK, [self._p("全ての試験は自動化しなければならない")])
        self.assertEqual(acc, [])
        self.assertEqual(len(rej), 1)

    def test_too_short_quote_rejected(self):
        acc, rej = prompts.verify_principles(self.CHUNK, [self._p("検証")])
        self.assertEqual(acc, [])
        self.assertEqual(len(rej), 1)

    def test_whitespace_difference_tolerated(self):
        acc, _rej = prompts.verify_principles(
            self.CHUNK, [self._p("独立した組織が 実施しなければ\nならない")])
        self.assertEqual(len(acc), 1)


if __name__ == "__main__":
    unittest.main()
