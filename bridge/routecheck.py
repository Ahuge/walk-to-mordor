"""Route/map consistency checks for content packs.

The dashboard draws the token and leg milestones on the journey path, while
route distances drive the token's progress.  A leg can therefore look correct
in JSON but place its milestone miles away from the map marker.  These helpers
compare route fractions, path geometry, and marker coordinates so that drift is
caught by tests instead of by eye.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

KM_PER_MI = 1.609344

MARKER_ALIASES = {
    "Bag End": "Hobbiton",
    "The Prancing Pony": "Bree",
    "Weathertop summit": "Weathertop",
    "Dimrill Dale": "Moria",
    "Cerim Amroth": "Lothlórien",
    "Morannon": "Black Gate",
    "The Black Gate": "Black Gate",
    "The Sammath Naur": "Mount Doom",
}


def load_pack(pack_dir: Path) -> tuple[dict, dict, list[dict]]:
    pack_dir = Path(pack_dir)
    route = json.loads((pack_dir / "route.json").read_text(encoding="utf-8"))
    journey = json.loads(
        (pack_dir / "art" / "journey.json").read_text(encoding="utf-8")
    )
    markers = json.loads(
        (pack_dir / "art" / "markers.json").read_text(encoding="utf-8")
    )
    return route, journey, markers


def path_points(journey: dict) -> list[tuple[float, float]]:
    """Return the journey path in image coordinates (x right, y down)."""
    y_top = journey["yTop"]
    return [(lon, y_top - lat) for lat, lon in journey["path"]]


def point_at_px(journey: dict, px: float) -> tuple[float, float]:
    """Interpolate a point on the journey path at a cumulative pixel value."""
    cum = journey["cumPx"]
    path = journey["path"]
    total = journey["totalPx"]
    px = max(0.0, min(total, px))
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < px:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    d0, d1 = cum[i - 1], cum[i]
    t = (px - d0) / (d1 - d0) if d1 > d0 else 0.0
    a, b = path[i - 1], path[i]
    lat = a[0] + (b[0] - a[0]) * t
    lon = a[1] + (b[1] - a[1]) * t
    return (lon, journey["yTop"] - lat)


def nearest_path(
    points: list[tuple[float, float]], cum: list[float], xy: tuple[float, float]
) -> tuple[float, float, float, float]:
    """Return (distance_px, nearest_xy, path_px, path_fraction)."""
    best = None
    for i, (x, y) in enumerate(points):
        d = math.hypot(x - xy[0], y - xy[1])
        if best is None or d < best[0]:
            best = (d, i)
    assert best is not None
    d, i = best
    return d, points[i], cum[i], cum[i] / cum[-1]


def check_pack(
    pack_dir: Path,
    *,
    min_km: float = 80.0,
    max_km: float = 200.0,
    anchor_tol_px: float = 75.0,
) -> tuple[list[dict], list[str]]:
    """Check route legs against the journey path and map markers.

    Returns (rows, issues).  Rows are suitable for a CLI table; issues are
    human-readable failures.  A route with no issues has every leg within the
    requested length band, every leg endpoint on the path, and every known
    place's route fraction matching its marker's path fraction.
    """
    route, journey, markers = load_pack(pack_dir)
    legs = route["legs"]
    total_mi = sum(float(leg["distance"]) for leg in legs)
    total_px = float(journey["totalPx"])
    points = path_points(journey)
    cum = journey["cumPx"]
    by_title = {m["title"]: m for m in markers}
    issues: list[str] = []
    rows: list[dict] = []

    if abs(total_mi - float(route.get("total_distance", total_mi))) > 0.01:
        issues.append(
            f"leg distances sum to {total_mi:.2f} mi, "
            f"but total_distance is {route.get('total_distance')}"
        )

    cum_mi = 0.0
    prev_end = None
    for i, leg in enumerate(legs):
        if i and leg.get("from") != legs[i - 1].get("to"):
            issues.append(
                f"leg {i + 1} starts at {leg.get('from')!r}, but leg {i} "
                f"ends at {legs[i - 1].get('to')!r}"
            )
        if float(leg["distance"]) <= 0:
            issues.append(f"leg {i + 1}: distance must be positive")
        cum_mi += float(leg["distance"])
        route_frac = cum_mi / total_mi if total_mi else 0.0
        km = float(leg["distance"]) * KM_PER_MI
        to_xy = leg.get("to_xy")
        map_start = leg.get("map_start")
        map_end = leg.get("map_end")

        if map_start is not None:
            map_start = float(map_start)
            if prev_end is not None and abs(map_start - prev_end) > 0.01:
                issues.append(
                    f"leg {i + 1}: map_start {map_start:.1f} != "
                    f"previous map_end {prev_end:.1f}"
                )
            if not 0.0 <= map_start <= total_px + 0.01:
                issues.append(
                    f"leg {i + 1}: map_start {map_start:.1f} outside path "
                    f"(0..{total_px:.1f})"
                )
        if map_end is not None:
            map_end = float(map_end)
            if not 0.0 <= map_end <= total_px + 0.01:
                issues.append(
                    f"leg {i + 1}: map_end {map_end:.1f} outside path "
                    f"(0..{total_px:.1f})"
                )
            if map_start is not None and map_end < map_start - 0.01:
                issues.append(
                    f"leg {i + 1}: map_end {map_end:.1f} before "
                    f"map_start {map_start:.1f}"
                )
            prev_end = map_end

        if to_xy is None:
            to_xy = point_at_px(journey, route_frac * total_px)
            anchor_source = "distance"
        else:
            to_xy = (float(to_xy[0]), float(to_xy[1]))
            anchor_source = "to_xy"

        d, nearest_xy, nearest_px, nearest_frac = nearest_path(points, cum, to_xy)
        if map_end is None:
            map_end = nearest_px
        map_frac = map_end / total_px
        delta_km = (route_frac - map_frac) * total_mi * KM_PER_MI

        marker_name = MARKER_ALIASES.get(leg.get("to", ""), leg.get("to", ""))
        marker = by_title.get(marker_name)
        marker_frac = None
        marker_delta_km = None
        marker_d = None
        if marker is not None:
            marker_xy = (float(marker["x"]), float(marker["y"]))
            marker_d, _, _, marker_frac = nearest_path(points, cum, marker_xy)
            marker_delta_km = (route_frac - marker_frac) * total_mi * KM_PER_MI

        if km < min_km or km > max_km:
            issues.append(
                f"leg {i + 1} ({leg['name']}): {km:.1f} km outside "
                f"{min_km:.0f}..{max_km:.0f} km"
            )
        if d > anchor_tol_px:
            issues.append(
                f"leg {i + 1} ({leg['name']}): endpoint {to_xy} is "
                f"{d:.1f} px from the path (limit {anchor_tol_px:.0f})"
            )
        if marker_delta_km is not None and abs(marker_delta_km) > 0.5:
            issues.append(
                f"leg {i + 1} ({leg['name']}): route fraction {route_frac:.4f} "
                f"differs from {marker_name} marker by {marker_delta_km:+.1f} km"
            )

        rows.append(
            {
                "leg": i + 1,
                "name": leg["name"],
                "to": leg["to"],
                "km": km,
                "route_frac": route_frac,
                "map_frac": map_frac,
                "delta_km": delta_km,
                "anchor_px": map_end,
                "to_xy": to_xy,
                "nearest_xy": nearest_xy,
                "anchor_d": d,
                "anchor_source": anchor_source,
                "marker": marker_name if marker else None,
                "marker_frac": marker_frac,
                "marker_delta_km": marker_delta_km,
                "marker_d": marker_d,
            }
        )

    return rows, issues


def overlay_html(pack_dir: Path, rows: list[dict], out_path: Path) -> str:
    """Render a self-contained HTML overlay for visual verification."""
    route, journey, markers = load_pack(pack_dir)
    width, height = journey["width"], journey["height"]
    map_path = (pack_dir / "art" / "map.webp").resolve()
    rel_map = Path(
        os.path.relpath(map_path, out_path.resolve().parent)
    ).as_posix()
    points = path_points(journey)
    path_d = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    marker_svg = []
    for m in markers:
        marker_svg.append(
            f'<circle cx="{m["x"]}" cy="{m["y"]}" r="7" fill="#6fa8dc" '
            f'opacity="0.8"><title>{m["title"]}</title></circle>'
        )

    anchor_svg = []
    for row in rows:
        x, y = row["to_xy"]
        color = "#ffd966" if row["delta_km"] == 0 else "#e06666"
        anchor_svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="none" '
            f'stroke="{color}" stroke-width="3"/>'
            f'<text x="{x + 13:.1f}" y="{y + 5:.1f}" fill="#fff" '
            f'font-size="18" font-family="sans-serif">{row["leg"]}</text>'
        )

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Walk to Mordor route check</title>
<style>
  html,body {{ margin:0; background:#111; color:#eee; font-family:sans-serif; }}
  #wrap {{ position:relative; width:min(100vw, {width}px); }}
  img {{ width:100%; display:block; opacity:.85; }}
  svg {{ position:absolute; inset:0; width:100%; height:100%; }}
  .legend {{ padding:10px 16px; }}
  .legend b {{ color:#ffd966; }}
</style>
<div class="legend">
  <b>Yellow</b> leg endpoint matches path fraction ·
  <b>red</b> route/map drift ·
  blue = map markers · numbers = leg order.
</div>
<div id="wrap">
  <img src="{rel_map}" alt="Middle-earth map">
  <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">
    <polyline points="{path_d}" fill="none" stroke="#f5edd8"
      stroke-width="9" opacity=".9"/>
    <polyline points="{path_d}" fill="none" stroke="#b3401e"
      stroke-width="4.5" opacity=".95"/>
    {''.join(marker_svg)}
    {''.join(anchor_svg)}
  </svg>
</div>
"""
