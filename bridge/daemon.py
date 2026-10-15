#!/usr/bin/env python3
"""daemon.py — Walk to Mordor background bridge.

Long-running process (runs under pythonw on Windows: no console window):
  * watches for the UREVO pad over BLE and auto-connects when it appears
  * streams 1/sec FTMS treadmill data into SQLite
  * detects marches (belt start/stop with idle tolerance) and writes summaries

Storage:
  Windows: %LOCALAPPDATA%\\walk-to-mordor\\walks.db (+ daemon.log)
  Other:   ~/.walk-to-mordor/

Usage:
  Foreground (verify it works):  python bridge/daemon.py
  Install as a logon task:       python tools/install_windows.py
"""

import asyncio
import logging
import os
import signal
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bleak import BleakClient  # noqa: E402

from treadmill.reader import (  # noqa: E402
    TREADMILL_DATA_UUID,
    find_pad,
    parse_treadmill_data,
)

SCAN_PAUSE_S = 15          # wait between scans when the pad isn't around
MARCH_IDLE_TIMEOUT_S = 60  # belt stopped this long -> march is over
SPEED_THRESHOLD_KMH = 0.05

log = logging.getLogger("walk-to-mordor")
stop_requested = threading.Event()

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts TEXT PRIMARY KEY,
    speed_kmh REAL,
    distance_m INTEGER,
    incline_pct REAL,
    calories INTEGER,
    elapsed_s INTEGER,
    steps INTEGER
);
CREATE TABLE IF NOT EXISTS marches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    distance_m INTEGER NOT NULL,
    calories INTEGER,
    steps INTEGER,
    avg_speed_kmh REAL,
    max_incline_pct REAL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        d = Path(os.environ["LOCALAPPDATA"]) / "walk-to-mordor"
    else:
        d = Path.home() / ".walk-to-mordor"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(log_path: Path) -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    ch = logging.StreamHandler()  # harmless under pythonw (no console)
    ch.setFormatter(fmt)
    log.addHandler(ch)


class MarchTracker:
    """Turns the 1/sec stream into march summaries.

    A march starts on the first reading above the speed threshold and ends
    after MARCH_IDLE_TIMEOUT_S of no belt motion, or on disconnect.
    """

    def __init__(self, db: sqlite3.Connection, lock: threading.Lock):
        self.db = db
        self.lock = lock
        self.in_march = False
        self.start_ts = ""
        self.start_dt = None
        self.first = {}
        self.last = {}
        self.last_motion = None
        self.speed_sum = 0.0
        self.speed_n = 0
        self.max_incline = 0.0

    def reading(self, ts: str, row: dict) -> None:
        now = datetime.now(timezone.utc)
        speed = row.get("speed_kmh") or 0.0
        if not self.in_march:
            if speed > SPEED_THRESHOLD_KMH:
                self.in_march = True
                self.start_ts = ts
                self.start_dt = now
                self.first = row
                self.last_motion = now
                self.speed_sum = 0.0
                self.speed_n = 0
                self.max_incline = 0.0
                log.info("march started")
                return
        # in a march: track stats, watch for the belt stopping
        self.last = row
        if speed > SPEED_THRESHOLD_KMH:
            self.last_motion = now
            self.speed_sum += speed
            self.speed_n += 1
        self.max_incline = max(self.max_incline, row.get("incline_pct") or 0.0)
        idle = (now - self.last_motion).total_seconds()
        if idle > MARCH_IDLE_TIMEOUT_S:
            self.finish(self.last_motion)

    def finish(self, end_dt) -> None:
        if not self.in_march:
            return
        end_ts = end_dt.isoformat(timespec="seconds")
        first, last = self.first, self.last
        dist = max(0, (last.get("distance_m") or 0) - (first.get("distance_m") or 0))
        cal = max(0, (last.get("calories") or 0) - (first.get("calories") or 0))
        steps = None
        if last.get("steps") is not None and first.get("steps") is not None:
            steps = max(0, last["steps"] - first["steps"])
        avg_speed = round(self.speed_sum / self.speed_n, 2) if self.speed_n else 0.0
        duration = max(0, int((end_dt - self.start_dt).total_seconds()))
        with self.lock:
            self.db.execute(
                "INSERT INTO marches (started_at, ended_at, duration_s,"
                " distance_m, calories, steps, avg_speed_kmh, max_incline_pct)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (self.start_ts, end_ts, duration, dist, cal, steps,
                 avg_speed, self.max_incline),
            )
            self.db.commit()
        log.info("march finished: %d m in %d s (avg %.2f km/h)",
                 dist, duration, avg_speed)
        self.in_march = False
        self.first = {}
        self.last = {}


async def sleep_or_stop(seconds: float) -> None:
    """Sleep, but wake early if a stop was requested."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(stop_requested.wait, seconds),
            timeout=seconds + 5,
        )
    except (asyncio.TimeoutError, TimeoutError):
        pass


async def run() -> None:
    ddir = data_dir()
    setup_logging(ddir / "daemon.log")
    # check_same_thread=False: bleak may invoke notify callbacks off the
    # event-loop thread on some backends; all writes go through the lock.
    lock = threading.Lock()
    db = sqlite3.connect(ddir / "walks.db", check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL;")
    db.executescript(SCHEMA)
    tracker = MarchTracker(db, lock)
    log.info("daemon started, db=%s", ddir / "walks.db")

    def on_signal(signum, frame):
        log.info("stop requested (signal %s)", signum)
        stop_requested.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    while not stop_requested.is_set():
        device = await find_pad("URTM", quiet=True)
        if device is None:
            await sleep_or_stop(SCAN_PAUSE_S)
            continue
        log.info("pad found: %s (%s)", device.name, device.address)
        try:
            async with BleakClient(device) as client:
                log.info("connected")

                def on_notify(_sender, data: bytearray):
                    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    row = parse_treadmill_data(bytes(data))
                    with lock:
                        db.execute(
                            "INSERT OR IGNORE INTO readings"
                            " (ts, speed_kmh, distance_m, incline_pct,"
                            " calories, elapsed_s, steps)"
                            " VALUES (?,?,?,?,?,?,?)",
                            (ts, row.get("speed_kmh"), row.get("distance_m"),
                             row.get("incline_pct"), row.get("calories"),
                             row.get("elapsed_s"), row.get("steps")),
                        )
                        db.commit()
                    tracker.reading(ts, row)

                await client.start_notify(TREADMILL_DATA_UUID, on_notify)
                while not stop_requested.is_set() and client.is_connected:
                    await asyncio.sleep(1)
                try:
                    await client.stop_notify(TREADMILL_DATA_UUID)
                except Exception:
                    pass
                if not client.is_connected:
                    log.info("disconnected")
        except Exception:
            log.exception("connection error")
        finally:
            tracker.finish(datetime.now(timezone.utc))
        await sleep_or_stop(5)

    tracker.finish(datetime.now(timezone.utc))
    db.close()
    log.info("daemon stopped")


if __name__ == "__main__":
    asyncio.run(run())
