"""Tests for live_status: stale feeds must never look like a stopped belt."""

import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.stats import live_status, snapshot_from_db
from bridge.store import SCHEMA


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return db


def add_reading(db, when, speed):
    db.execute(
        "INSERT INTO readings (ts, speed_kmh) VALUES (?,?)",
        (when.isoformat(timespec="seconds"), speed),
    )
    db.commit()


class TestLiveStatus(unittest.TestCase):
    def test_no_readings(self):
        db = make_db()
        self.addCleanup(db.close)
        text, walking, speed, age = live_status(db)
        self.assertEqual(text, "no data yet")
        self.assertFalse(walking)
        self.assertEqual(speed, 0.0)
        self.assertIsNone(age)

    def test_fresh_walking(self):
        db = make_db()
        self.addCleanup(db.close)
        add_reading(db, datetime.now(timezone.utc), 1.4)
        text, walking, speed, age = live_status(db)
        self.assertTrue(walking)
        self.assertEqual(speed, 1.4)
        self.assertIn("walking", text)
        self.assertLess(age, 10)

    def test_fresh_idle(self):
        db = make_db()
        self.addCleanup(db.close)
        add_reading(db, datetime.now(timezone.utc), 0.0)
        text, walking, speed, age = live_status(db)
        self.assertFalse(walking)
        self.assertEqual(text, "idle")
        self.assertLess(age, 10)

    def test_stale_reading_is_no_signal_not_idle(self):
        db = make_db()
        self.addCleanup(db.close)
        add_reading(db, datetime.now(timezone.utc) - timedelta(seconds=300), 1.4)
        text, walking, speed, age = live_status(db)
        self.assertFalse(walking)
        self.assertIn("no signal", text)
        self.assertIn("1.4", text)
        self.assertGreater(age, 10)

    def test_stale_zero_speed_is_also_no_signal(self):
        db = make_db()
        self.addCleanup(db.close)
        add_reading(db, datetime.now(timezone.utc) - timedelta(seconds=300), 0.0)
        text, walking, _speed, _age = live_status(db)
        self.assertFalse(walking)
        self.assertEqual(text, "no signal")


class TestSnapshotStatus(unittest.TestCase):
    def test_snapshot_exposes_status_kind_and_age(self):
        db = make_db()
        add_reading(db, datetime.now(timezone.utc) - timedelta(seconds=300), 1.4)
        with patch("bridge.stats.open_db", return_value=db), \
                patch("bridge.stats.data_dir", return_value=Path("/tmp")):
            snap = snapshot_from_db()
        self.assertEqual(snap["status_kind"], "stale")
        self.assertFalse(snap["walking"])
        self.assertGreater(snap["reading_age_s"], 10)


if __name__ == "__main__":
    unittest.main()
