"""Encounter engine: trigger evaluation and state management.

Runs in the daemon. Evaluated on each BLE reading (1/sec) and on
march start/finish. Manages encounter lifecycle:
locked -> unlocked -> active -> completed/dismissed.
"""

import json
import logging
import random
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("walk-to-mordor")


class EncounterEngine:
    def __init__(self, db: sqlite3.Connection, lock: threading.Lock,
                 pack_dir: Path):
        self.db = db
        self.lock = lock
        self.pack_dir = pack_dir
        self.encounters = {}  # id -> {meta, body}
        self.active_id = None
        self._last_trigger_km = 0.0
        self._load()

    def _load(self):
        from bridge.encounter_content import load_encounters
        self.encounters = load_encounters(self.pack_dir)
        log.info("loaded %d encounters", len(self.encounters))

    # --- player state helpers ---

    def get_player(self, key: str, default: str = "") -> str:
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM player_state WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_player(self, key: str, value: str):
        with self.lock:
            self.db.execute(
                "INSERT INTO player_state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self.db.commit()

    def get_morale(self) -> float:
        try:
            return float(self.get_player("morale", "0"))
        except ValueError:
            return 0.0

    def set_morale(self, v: float):
        self.set_player("morale", str(max(-100.0, min(100.0, v))))

    def adjust_morale(self, delta: float):
        self.set_morale(self.get_morale() + delta)

    # --- encounter state ---

    def get_status(self, eid: str) -> str:
        with self.lock:
            row = self.db.execute(
                "SELECT status FROM encounter_state WHERE encounter_id=?",
                (eid,)).fetchone()
        return row[0] if row else "locked"

    def set_status(self, eid: str, status: str, data: dict | None = None):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.lock:
            self.db.execute(
                "INSERT INTO encounter_state"
                " (encounter_id, status, unlocked_at, data)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(encounter_id) DO UPDATE SET"
                " status=excluded.status, data=excluded.data",
                (eid, status, now, json.dumps(data or {})))
            self.db.commit()

    # --- trigger evaluation (called from MarchTracker.reading) ---

    def on_reading(self, ts: str, row: dict, total_km: float):
        """Check triggers. total_km is cumulative journey distance."""
        # Morale decay (1-2hr half-life approx)
        m = self.get_morale()
        if m != 0:
            self.set_morale(m * 0.9995)

        if self.active_id:
            return  # one at a time

        # Random vignette trigger with increasing probability
        since_last = total_km - self._last_trigger_km
        for eid, enc in self.encounters.items():
            meta = enc["meta"]
            if meta.get("type") != "vignette":
                continue
            if self.get_status(eid) != "locked":
                continue
            base = float(meta.get("probability_base", 0.1))
            growth = float(meta.get("probability_growth", 0.05))
            cooldown = float(meta.get("cooldown_km", 3))
            if since_last < cooldown:
                continue
            p = base + growth * (since_last - cooldown)
            if random.random() < min(p, 0.8):
                self._activate(eid)
                self._last_trigger_km = total_km
                break

    def _activate(self, eid: str):
        self.active_id = eid
        self.set_status(eid, "active")
        log.info("encounter active: %s", eid)

    def dismiss_active(self):
        if self.active_id:
            self.set_status(self.active_id, "dismissed")
            log.info("encounter dismissed: %s", self.active_id)
            self.active_id = None

    def complete_active(self, data: dict | None = None):
        if self.active_id:
            self.set_status(self.active_id, "completed", data)
            log.info("encounter completed: %s", self.active_id)
            self.active_id = None

    def get_active(self) -> dict | None:
        if not self.active_id:
            return None
        enc = self.encounters.get(self.active_id)
        if not enc:
            return None
        return {"id": self.active_id, "meta": enc["meta"], "body": enc["body"]}
