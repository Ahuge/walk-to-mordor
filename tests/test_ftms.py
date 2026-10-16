"""Tests for FTMS Treadmill Data parsing."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# reader.py imports bleak at module level; mock it for tests.
sys.modules["bleak"] = MagicMock()

from treadmill.reader import (
    F_DISTANCE,
    F_INCLINE,
    F_UREVO_STEPS,
    parse_treadmill_data,
)


def make_packet(speed_kmh=0.0, distance_m=None, incline_pct=None, steps=None):
    """Build a minimal FTMS Treadmill Data packet."""
    flags = 0
    body = b""
    body += int(speed_kmh * 100).to_bytes(2, "little")
    if distance_m is not None:
        flags |= F_DISTANCE
        body += int(distance_m).to_bytes(3, "little")
    if incline_pct is not None:
        flags |= F_INCLINE
        body += int(incline_pct * 10).to_bytes(2, "little", signed=True)
        body += (0).to_bytes(2, "little")
    if steps is not None:
        flags |= F_UREVO_STEPS
        body += int(steps).to_bytes(3, "little")
    return flags.to_bytes(2, "little") + body


class TestFtms(unittest.TestCase):
    def test_speed_only(self):
        p = parse_treadmill_data(make_packet(speed_kmh=4.5))
        self.assertEqual(p["speed_kmh"], 4.5)
        self.assertNotIn("distance_m", p)

    def test_distance_and_steps(self):
        p = parse_treadmill_data(
            make_packet(speed_kmh=3.0, distance_m=1250, steps=1800))
        self.assertEqual(p["speed_kmh"], 3.0)
        self.assertEqual(p["distance_m"], 1250)
        self.assertEqual(p["steps"], 1800)

    def test_incline_signed(self):
        p = parse_treadmill_data(make_packet(speed_kmh=2.0, incline_pct=5.5))
        self.assertEqual(p["incline_pct"], 5.5)
        p = parse_treadmill_data(make_packet(speed_kmh=2.0, incline_pct=-2.0))
        self.assertEqual(p["incline_pct"], -2.0)

    def test_zero_speed(self):
        p = parse_treadmill_data(make_packet(speed_kmh=0.0))
        self.assertEqual(p["speed_kmh"], 0.0)


if __name__ == "__main__":
    unittest.main()
