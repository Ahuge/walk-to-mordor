"""Tests for store: march_stats and command queue."""

import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.stats import march_stats
from bridge.store import SCHEMA, queue_command_row


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return db


class TestStore(unittest.TestCase):
    def test_march_stats_empty(self):
        db = make_db()
        today_m, total_m, streak, today_steps, total_steps = march_stats(db)
        self.assertEqual(today_m, 0)
        self.assertEqual(total_m, 0)
        self.assertEqual(today_steps, 0)

    def test_march_stats_sums_today(self):
        db = make_db()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for dist, steps in [(1000, 1500), (500, 750)]:
            db.execute(
                "INSERT INTO marches (started_at, ended_at, duration_s,"
                " distance_m, calories, steps, avg_speed_kmh, max_incline_pct)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (now, now, 600, dist, 50, steps, 3.0, 2.0),
            )
        db.commit()
        today_m, total_m, streak, today_steps, total_steps = march_stats(db)
        self.assertEqual(today_m, 1500)
        self.assertEqual(total_m, 1500)
        self.assertEqual(today_steps, 2250)

    def test_queue_command_row(self):
        db = make_db()
        cid = queue_command_row(db, "set_speed", {"kmh": 4.0})
        self.assertGreater(cid, 0)
        row = db.execute(
            "SELECT op, status FROM commands WHERE id=?", (cid,)).fetchone()
        self.assertEqual(row[0], "set_speed")
        self.assertEqual(row[1], "pending")


if __name__ == "__main__":
    unittest.main()
