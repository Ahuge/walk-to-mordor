"""Tests for encounter content loading."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.encounter_content import parse_frontmatter, validate_encounter


class TestContent(unittest.TestCase):
    def test_parse_simple(self):
        text = "---\nid: foo\ntype: vignette\n---\n# Hello\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["id"], "foo")
        self.assertEqual(meta["type"], "vignette")
        self.assertTrue(body.startswith("# Hello"))

    def test_parse_list(self):
        text = """---
id: bar
type: choice
choices:
  - "a:Option A:morale+5"
  - "b:Option B:morale-5"
---
Body
"""
        meta, body = parse_frontmatter(text)
        self.assertEqual(len(meta["choices"]), 2)
        self.assertEqual(meta["choices"][0], "a:Option A:morale+5")

    def test_parse_types(self):
        text = "---\ncount: 5\nratio: 1.5\nenabled: true\n---\nX"
        meta, _ = parse_frontmatter(text)
        self.assertEqual(meta["count"], 5)
        self.assertEqual(meta["ratio"], 1.5)
        self.assertTrue(meta["enabled"])

    def test_validate(self):
        enc = {"id": "x", "meta": {"type": "vignette"}, "body": "hi"}
        self.assertEqual(validate_encounter(enc), [])
        bad = {"id": "y", "meta": {}, "body": ""}
        errors = validate_encounter(bad)
        self.assertTrue(len(errors) >= 2)


if __name__ == "__main__":
    unittest.main()
