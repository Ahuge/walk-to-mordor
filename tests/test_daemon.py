"""Tests for daemon lifecycle guards."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# daemon.py imports bleak at module level; mock it for tests.
sys.modules["bleak"] = MagicMock()

from bridge.daemon import acquire_instance_lock  # noqa: E402


class TestInstanceLock(unittest.TestCase):
    def test_second_instance_is_locked_out(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "daemon.lock"
            first = acquire_instance_lock(path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(acquire_instance_lock(path))
            finally:
                first.close()
            again = acquire_instance_lock(path)
            self.assertIsNotNone(again)
            again.close()


if __name__ == "__main__":
    unittest.main()
