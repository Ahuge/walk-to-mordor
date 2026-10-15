"""Shared SQLite storage for the Walk to Mordor bridge."""

import os
import sqlite3
from pathlib import Path

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


def data_dir() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        d = Path(os.environ["LOCALAPPDATA"]) / "walk-to-mordor"
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
