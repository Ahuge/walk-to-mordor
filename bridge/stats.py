#!/usr/bin/env python3
"""Live stats from walks.db — shared by the minimap and the CLI.

Usage:
    python bridge/stats.py           # one snapshot
    python bridge/stats.py --watch   # refresh every 2 s (Ctrl-C to stop)
"""

import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.client import api_get  # noqa: E402
from bridge.store import data_dir, open_db  # noqa: E402

M_PER_MI = 1609.344
REFRESH_S = 2


def load_route(pack: str = "lotr") -> dict:
    repo = Path(__file__).resolve().parent.parent
    with open(repo / "packs" / pack / "route.json") as f:
        return json.load(f)


def _local(dt_str: str) -> datetime:
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def march_stats(db: sqlite3.Connection):
    """Returns (today_m, total_m, streak_days)."""
    rows = db.execute(
        "SELECT started_at, distance_m FROM marches ORDER BY started_at"
    ).fetchall()
    today = datetime.now().astimezone().date()
    today_m = 0
    total_m = 0
    days = set()
    for ts, dist in rows:
        local = _local(ts)
        total_m += dist or 0
        days.add(local.date())
        if local.date() == today:
            today_m += dist or 0
    streak = 0
    d = today if today in days else today - timedelta(days=1)
    while d in days:
        streak += 1
        d -= timedelta(days=1)
    return today_m, total_m, streak


def live_status(db: sqlite3.Connection):
    """Returns (text, walking_bool, speed_kmh) from the latest reading."""
    row = db.execute(
        "SELECT ts, speed_kmh FROM readings ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "no data yet", False, 0.0
    ts, speed = row
    age = (datetime.now(timezone.utc)
           - _local(ts).astimezone(timezone.utc)).total_seconds()
    speed = speed or 0.0
    if age < 10 and speed > 0.05:
        return f"walking @ {speed:.1f} km/h", True, speed
    return "idle", False, speed


def route_position(route: dict, total_m: float):
    """Returns (leg_index, leg, fraction_within_leg) for a lifetime distance."""
    total_mi = total_m / M_PER_MI
    legs = route["legs"]
    cum = 0.0
    for i, leg in enumerate(legs):
        start = cum
        cum += leg["distance"]
        if total_mi < cum or i == len(legs) - 1:
            frac = ((total_mi - start) / leg["distance"]
                    if leg["distance"] else 0.0)
            return i, leg, max(0.0, min(1.0, frac))
    return len(legs) - 1, legs[-1], 1.0


def snapshot_from_db() -> dict:
    db = open_db()
    try:
        route = load_route()
        today_m, total_m, streak = march_stats(db)
        status, walking, speed = live_status(db)
        i, leg, frac = route_position(route, total_m)
        return {
            "leg_index": i,
            "leg_count": len(route["legs"]),
            "leg_name": leg["name"],
            "leg_frac": frac,
            "today_km": today_m / 1000,
            "total_km": total_m / 1000,
            "streak": streak,
            "status": status,
            "walking": walking,
            "speed_kmh": speed,
            "db": str(data_dir() / "walks.db"),
            "source": "db",
        }
    finally:
        db.close()


def snapshot() -> dict:
    """Live stats, preferring the daemon's HTTP API.

    The API path avoids touching the SQLite file directly, which is flaky
    over WSL's 9P mount; direct DB is the fallback when the daemon is down.
    """
    data = api_get("/api/stats")
    if isinstance(data, dict) and "leg_index" in data:
        return data
    return snapshot_from_db()


def format_snapshot(s: dict) -> str:
    bar_len = 24
    filled = int(s["leg_frac"] * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    streak = f" · 🔥 {s['streak']}-day streak" if s["streak"] else ""
    return (
        f"Walk to Mordor — Leg {s['leg_index'] + 1}/{s['leg_count']}:"
        f" {s['leg_name']}\n"
        f"[{bar}] {s['leg_frac'] * 100:.0f}%\n"
        f"Status: {s['status']}\n"
        f"Today: {s['today_km']:.1f} km · Total: {s['total_km']:.1f} km{streak}\n"
        f"db: {s['db']}"
    )


def main() -> None:
    watch = "--watch" in sys.argv
    if not watch:
        print(format_snapshot(snapshot()))
        return
    try:
        while True:
            sys.stdout.write("\033[2J\033[H" + format_snapshot(snapshot()))
            sys.stdout.flush()
            time.sleep(REFRESH_S)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
