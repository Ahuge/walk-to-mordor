"""Shared SQLite storage for the Walk to Mordor bridge."""

import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

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
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    op TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status, id);
"""


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:  # noqa: BLE001
        return False


def _wsl_walk_to_mordor_dir() -> Optional[Path]:
    """Find the Windows-side walk-to-mordor dir from inside WSL.

    Prefers an existing walks.db (globbed across drive letters and user
    profiles, most recently modified wins); falls back to resolving
    %LOCALAPPDATA% via cmd.exe for a fresh install with no DB yet.
    """
    import subprocess
    try:
        candidates = []
        for db_path in Path("/mnt").glob(
                "*/Users/*/AppData/Local/walk-to-mordor/walks.db"):
            try:
                candidates.append((db_path.stat().st_mtime, db_path.parent))
            except OSError:
                continue
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except Exception:  # noqa: BLE001
        pass
    try:
        out = subprocess.run(
            ["cmd.exe", "/c", "echo", "%LOCALAPPDATA%"],
            capture_output=True, text=True, timeout=10)
        win_path = out.stdout.strip()
        if not win_path or "%" in win_path:
            return None
        out2 = subprocess.run(["wslpath", win_path],
                              capture_output=True, text=True, timeout=10)
        p = Path(out2.stdout.strip())
        return (p / "walk-to-mordor") if p.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        d = Path(os.environ["LOCALAPPDATA"]) / "walk-to-mordor"
    elif _is_wsl():
        win = _wsl_walk_to_mordor_dir()
        if win is not None:
            d = win
        else:
            d = Path.home() / ".walk-to-mordor"
            print("warning: could not find the Windows walk-to-mordor folder;"
                  " using ~/.walk-to-mordor — the daemon will not see this data",
                  file=sys.stderr)
    else:
        d = Path.home() / ".walk-to-mordor"
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_db() -> sqlite3.Connection:
    """Open walks.db (thread-safe handle). Runs SCHEMA idempotently.

    The WAL pragma is only (re)set on Windows: over WSL's 9P mount the
    shm mmap fails with 'disk I/O error'. Journal mode is persistent, so
    a DB created by the Windows daemon stays WAL without re-setting it.
    """
    db = sqlite3.connect(data_dir() / "walks.db", check_same_thread=False)
    # Several writers collide here (1/sec readings, API thread, CLI): wait
    # for the lock instead of failing instantly with "database is locked".
    db.execute("PRAGMA busy_timeout=5000;")
    if os.name == "nt":
        mode = db.execute("PRAGMA journal_mode;").fetchone()[0]
        if mode.lower() != "wal":
            db.execute("PRAGMA journal_mode=WAL;")
    db.executescript(SCHEMA)
    return db
