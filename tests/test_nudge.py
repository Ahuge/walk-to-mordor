"""Tests for the daily nudge helper."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import nudge  # noqa: E402


class TestWalkedToday(unittest.TestCase):
    def test_uses_stats_march_stats(self):
        db = MagicMock()
        with patch("bridge.store.open_db", return_value=db), \
                patch("bridge.stats.march_stats",
                      return_value=(60.0, 60.0, 1, 80, 80)) as stats:
            self.assertTrue(nudge.walked_today())
        stats.assert_called_once_with(db)
        db.close.assert_called_once()

    def test_short_walk_does_not_count(self):
        db = MagicMock()
        with patch("bridge.store.open_db", return_value=db), \
                patch("bridge.stats.march_stats",
                      return_value=(10.0, 10.0, 0, 14, 14)):
            self.assertFalse(nudge.walked_today())


if __name__ == "__main__":
    unittest.main()
