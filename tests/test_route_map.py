"""The route must line up with the journey path and canonical map markers."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.routecheck import KM_PER_MI, check_pack

PACK = Path(__file__).resolve().parent.parent / "packs" / "lotr"


class TestRouteMap(unittest.TestCase):
    def test_route_is_consistent_with_map(self):
        rows, issues = check_pack(PACK)
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 21)
        self.assertAlmostEqual(
            sum(row["km"] for row in rows), 1779 * KM_PER_MI, places=1
        )

    def test_known_markers_match_route_fractions(self):
        rows, _ = check_pack(PACK)
        by_marker = {row["marker"]: row for row in rows if row["marker"]}
        for name in ("Bree", "Weathertop", "Rivendell", "Moria", "Lothlórien",
                     "Black Gate", "Mount Doom"):
            self.assertIn(name, by_marker)
            self.assertLess(abs(by_marker[name]["marker_delta_km"]), 0.5, name)

    def test_leg_lengths_are_walkable(self):
        rows, _ = check_pack(PACK)
        for row in rows:
            self.assertGreaterEqual(row["km"], 80.0, row["name"])
            self.assertLessEqual(row["km"], 200.0, row["name"])

    def test_detects_an_anchor_off_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "lotr"
            (copy / "art").mkdir(parents=True)
            shutil.copy(PACK / "route.json", copy / "route.json")
            for name in ("journey.json", "markers.json"):
                shutil.copy(PACK / "art" / name, copy / "art" / name)
            route = json.loads((copy / "route.json").read_text(encoding="utf-8"))
            route["legs"][2]["to_xy"] = [100, 100]
            (copy / "route.json").write_text(
                json.dumps(route), encoding="utf-8"
            )
            _, issues = check_pack(copy)
            self.assertTrue(
                any("from the path" in issue for issue in issues), issues
            )


if __name__ == "__main__":
    unittest.main()
