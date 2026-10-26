"""Keep the packaged installer version in step with the app version."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.version import __version__  # noqa: E402

ISS = Path(__file__).resolve().parent.parent / "installer" / "walk-to-mordor.iss"


class TestVersion(unittest.TestCase):
    def test_installer_matches_app_version(self):
        match = re.search(r'#define MyAppVersion "([^"]*)"',
                          ISS.read_text(encoding="utf-8"))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)


if __name__ == "__main__":
    unittest.main()
