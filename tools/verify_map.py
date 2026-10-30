#!/usr/bin/env python3
"""Verify route legs against the journey path and canonical map markers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bridge.routecheck import check_pack, overlay_html  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", default=str(ROOT / "packs" / "lotr"))
    ap.add_argument("--min-km", type=float, default=80.0)
    ap.add_argument("--max-km", type=float, default=200.0)
    ap.add_argument("--anchor-tol-px", type=float, default=75.0)
    ap.add_argument("--overlay", help="write an HTML overlay to this path")
    ap.add_argument("--strict", action="store_true", help="exit 1 on issues")
    args = ap.parse_args()

    pack = Path(args.pack)
    rows, issues = check_pack(
        pack,
        min_km=args.min_km,
        max_km=args.max_km,
        anchor_tol_px=args.anchor_tol_px,
    )

    print(
        f"{'leg':>3}  {'destination':28s} {'km':>6}  {'route':>7}  "
        f"{'map':>7}  {'drift':>8}  {'anchor':>7}  marker"
    )
    for r in rows:
        marker = ""
        if r["marker"]:
            marker = f"{r['marker']} {r['marker_delta_km']:+.1f} km"
        print(
            f"{r['leg']:3d}  {r['to'][:28]:28s} {r['km']:6.1f}  "
            f"{r['route_frac']:7.4f}  {r['map_frac']:7.4f}  "
            f"{r['delta_km']:+8.1f}  {r['anchor_d']:6.1f}px  {marker}"
        )

    if args.overlay:
        out = Path(args.overlay)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(overlay_html(pack, rows, out), encoding="utf-8")
        print(f"\noverlay: {out}")

    if issues:
        print("\nISSUES")
        for issue in issues:
            print(f"  - {issue}")
        if args.strict:
            return 1
    else:
        print("\nOK: route fractions, markers, and leg lengths agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
