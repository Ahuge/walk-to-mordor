"""Tests for MarchTracker: march start/finish/idle/counter-reset logic."""

import sqlite3
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# daemon.py imports bleak at module level; mock it for tests.
sys.modules["bleak"] = MagicMock()

from bridge.daemon import MarchTracker
from bridge.store import SCHEMA


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return db


def reading(speed=0.0, distance_m=0, steps=0, calories=0, incline=0.0):
    return {
        "speed_kmh": speed,
        "distance_m": distance_m,
        "steps": steps,
        "calories": calories,
        "incline_pct": incline,
    }


def ts(dt):
    return dt.isoformat(timespec="seconds")


class TestMarchTracker(unittest.TestCase):
    def test_starts_on_motion(self):
        db = make_db()
        t = MarchTracker(db, threading.Lock())
        now = datetime.now(timezone.utc)
        t.reading(ts(now), reading(speed=0.0))
        self.assertFalse(t.in_march)
        t.reading(ts(now), reading(speed=3.0, distance_m=10))
        self.assertTrue(t.in_march)

    def test_closes_after_idle(self):
        db = make_db()
        t = MarchTracker(db, threading.Lock())
        now = datetime.now(timezone.utc)
        t.reading(ts(now), reading(speed=3.0, distance_m=100, steps=150))
        self.assertTrue(t.in_march)
        later = now + timedelta(seconds=61)
        with patch("bridge.daemon.datetime") as mock_dt:
            mock_dt.now.return_value = later
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            t.reading(ts(later), reading(speed=0.0, distance_m=500, steps=700))
        self.assertFalse(t.in_march)
        row = db.execute("SELECT distance_m, steps FROM marches").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 400)
        self.assertEqual(row[1], 550)

    def test_counter_reset_does_not_undercount(self):
        db = make_db()
        t = MarchTracker(db, threading.Lock())
        now = datetime.now(timezone.utc)
        t.reading(ts(now), reading(speed=3.0, distance_m=1000, steps=1500))
        t.reading(ts(now), reading(speed=3.0, distance_m=0, steps=0))
        t.reading(ts(now), reading(speed=3.0, distance_m=200, steps=300))
        self.assertEqual(t.acc_dist, 200)
        self.assertEqual(t.acc_steps, 300)

    def test_trivial_march_ignored(self):
        db = make_db()
        t = MarchTracker(db, threading.Lock())
        now = datetime.now(timezone.utc)
        t.reading(ts(now), reading(speed=3.0, distance_m=0))
        t.finish(now + timedelta(seconds=2))
        count = db.execute("SELECT COUNT(*) FROM marches").fetchone()[0]
        self.assertEqual(count, 0)

    def test_finish_saves_stats(self):
        db = make_db()
        t = MarchTracker(db, threading.Lock())
        now = datetime.now(timezone.utc)
        t.reading(ts(now), reading(speed=3.0, distance_m=100, steps=150))
        t.reading(ts(now), reading(speed=3.0, distance_m=600, steps=800))
        t.finish(now + timedelta(seconds=120))
        row = db.execute(
            "SELECT distance_m, steps, duration_s FROM marches").fetchone()
        self.assertEqual(row[0], 500)
        self.assertEqual(row[1], 650)
        self.assertIn(row[2], (119, 120))  # int() truncation edge


if __name__ == "__main__":
    unittest.main()
