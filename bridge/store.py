"""Shared SQLite storage for the Walk to Mordor bridge."""

import os
import sqlite3
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


def _wsl_windows_localappdata() -> Optional[Path]:
    """Resolve the Windows %LOCALAPPDATA% from inside WSL, so the CLI and
    the Windows daemon share one database no matter which side you run from."""
    import subprocess
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
        return p if p.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        d = Path(os.environ["LOCALAPPDATA"]) / "walk-to-mordor"
    elif _is_wsl():
        win = _wsl_windows_localappdata()
        d = (win / "walk-to-mordor") if win else (Path.home() / ".walk-to-mordor")
    else:
        d = Path.home() / ".walk-to-mordor"
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_db() -> sqlite3.Connection:
    """Open walks.db (WAL mode, thread-safe handle). Runs SCHEMA idempotently."""
    db = sqlite3.connect(data_dir() / "walks.db", check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL;")
    db.executescript(SCHEMA)
    return db
