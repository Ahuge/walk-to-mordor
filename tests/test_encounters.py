"""Tests for EncounterEngine: triggers, choices, challenges, POIs."""

import json
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.modules["bleak"] = MagicMock()

from bridge.encounters import EncounterEngine
from bridge.store import SCHEMA


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    return db


def make_engine(tmp_path):
    # Create minimal pack structure
    enc_dir = tmp_path / "encounters" / "vignettes"
    enc_dir.mkdir(parents=True)
    (enc_dir / "test_01.md").write_text("""---
id: test_vignette_01
type: vignette
meeting: green
probability_base: 1.0
probability_growth: 0.0
cooldown_km: 0
---

# Test Vignette

Hello world.
""")
    db = make_db()
    return EncounterEngine(db, threading.Lock(), tmp_path)


class TestEncounters(unittest.TestCase):
    def test_load_encounters(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(Path(td))
            self.assertIn("test_vignette_01", eng.encounters)

    def test_vignette_triggers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(Path(td))
            # probability 1.0, cooldown 0 -> should trigger immediately
            eng.on_reading("2026-01-01T00:00:00", {"speed_kmh": 3.0}, 10.0, 0.1)
            self.assertIsNotNone(eng.active_id)
            self.assertEqual(eng.active_id, "test_vignette_01")

    def test_morale_decay(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(Path(td))
            eng.set_morale(50.0)
            eng.on_reading("2026-01-01T00:00:00", {"speed_kmh": 0}, 0, 0)
            self.assertLess(eng.get_morale(), 50.0)
            self.assertGreater(eng.get_morale(), 49.0)

    def test_dismiss_and_complete(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            eng = make_engine(Path(td))
            eng.on_reading("2026-01-01T00:00:00", {"speed_kmh": 3.0}, 10.0, 0.1)
            self.assertIsNotNone(eng.active_id)
            eng.dismiss_active()
            self.assertIsNone(eng.active_id)
            self.assertEqual(eng.get_status("test_vignette_01"), "dismissed")

    def test_poi_trigger(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "pois.json").write_text(json.dumps({
                "pois": [{
                    "id": "test_poi",
                    "name": "Test Point",
                    "journey_frac": 0.5,
                    "radius_frac": 0.01,
                    "type": "history",
                    "leg": 1,
                }]
            }))
            eng = make_engine(p)
            # Within radius -> should trigger
            eng.on_reading("2026-01-01T00:00:00", {"speed_kmh": 3.0}, 10.0, 0.505)
            self.assertIsNotNone(eng.active_id)
            self.assertTrue(eng.active_id.startswith("poi_"))


if __name__ == "__main__":
    unittest.main()
