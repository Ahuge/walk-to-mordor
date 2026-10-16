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

        # Update active challenge (if any)
        if self.active_id:
            self._update_challenge(row)
            return  # one at a time

        # Random encounter trigger with increasing probability
        # Types: vignette, choice, challenge
        since_last = total_km - self._last_trigger_km
        for eid, enc in self.encounters.items():
            meta = enc["meta"]
            if meta.get("type") not in ("vignette", "choice", "challenge"):
                continue
            if self.get_status(eid) != "locked":
                continue
            # Meeting mode: skip red encounters if enabled
            if (self.get_player("meeting_mode", "off") == "on"
                    and meta.get("meeting") == "red"):
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

    def _update_challenge(self, row: dict):
        """Track progress on active speed/stealth/incline challenges."""
        enc = self.get_active()
        if not enc:
            return
        meta = enc["meta"]
        ctype = meta.get("challenge_type")
        if not ctype:
            return
        # Load progress from encounter_state.data
        with self.lock:
            db_row = self.db.execute(
                "SELECT data FROM encounter_state WHERE encounter_id=?",
                (self.active_id,)).fetchone()
        data = json.loads(db_row[0]) if db_row else {}
        speed = row.get("speed_kmh") or 0.0
        incline = row.get("incline_pct") or 0.0

        if ctype == "speed":
            # Must stay ABOVE threshold for target distance
            threshold = float(meta.get("threshold_kmh", 3.5))
            target_m = float(meta.get("target_m", 400))
            if speed >= threshold:
                data["covered_m"] = data.get("covered_m", 0) + (speed / 3.6)
            # 1/sec: distance = speed(m/s) * 1s
            if data.get("covered_m", 0) >= target_m:
                self.adjust_morale(10)
                self.complete_active({"result": "success"})
                return
        elif ctype == "stealth":
            # Must stay BELOW threshold for target distance
            threshold = float(meta.get("threshold_kmh", 1.5))
            target_m = float(meta.get("target_m", 300))
            if speed <= threshold and speed > 0.1:
                data["covered_m"] = data.get("covered_m", 0) + (speed / 3.6)
            elif speed > threshold:
                data["covered_m"] = 0  # reset on violation
            if data.get("covered_m", 0) >= target_m:
                self.adjust_morale(10)
                self.complete_active({"result": "success"})
                return
        elif ctype == "incline":
            # Must hold incline for target seconds
            threshold = float(meta.get("threshold_pct", 5.0))
            target_s = float(meta.get("target_s", 180))
            if incline >= threshold:
                data["held_s"] = data.get("held_s", 0) + 1
            else:
                data["held_s"] = 0  # reset on drop
            if data.get("held_s", 0) >= target_s:
                self.adjust_morale(10)
                self.complete_active({"result": "success"})
                return
        # Save progress
        self.set_status(self.active_id, "active", data)

    def defer_active(self, defer_km: float = 2.0):
        """Defer a challenge (for meetings). Retriggers after defer_km."""
        if self.active_id:
            # Mark as locked again; engine will retrigger via probability
            # (we'd need defer tracking — for now just dismiss)
            self.set_status(self.active_id, "dismissed",
                            {"deferred": True, "defer_km": defer_km})
            log.info("encounter deferred: %s", self.active_id)
            self.active_id = None

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
        # Include progress data from encounter_state
        with self.lock:
            row = self.db.execute(
                "SELECT data FROM encounter_state WHERE encounter_id=?",
                (self.active_id,)).fetchone()
        data = json.loads(row[0]) if row else {}
        return {"id": self.active_id, "meta": enc["meta"], "body": enc["body"],
                "progress": data}

    def respond_to_active(self, choice_id: str) -> dict | None:
        """Apply a choice. Returns consequence text, or None if invalid."""
        enc = self.get_active()
        if not enc:
            return None
        meta = enc["meta"]
        choices = meta.get("choices", [])
        # Choices are stored as "id:label:consequence" strings in frontmatter
        for c in choices:
            parts = c.split(":", 2)
            if len(parts) >= 2 and parts[0].strip() == choice_id:
                label = parts[1].strip()
                consequence = parts[2].strip() if len(parts) > 2 else ""
                # Apply morale/supply effects from consequence tags
                # Format: "morale+10" or "supplies+1" or "unlock:encounter_id"
                for tag in consequence.split(","):
                    tag = tag.strip()
                    if tag.startswith("morale"):
                        try:
                            self.adjust_morale(float(tag[6:]))
                        except ValueError:
                            pass
                    elif tag.startswith("supplies"):
                        try:
                            cur = int(self.get_player("supplies", "0"))
                            self.set_player("supplies", str(cur + int(tag[8:])))
                        except ValueError:
                            pass
                    elif tag.startswith("unlock:"):
                        unlock_id = tag[7:]
                        self.set_status(unlock_id, "unlocked")
                self.complete_active({"choice": choice_id})
                return {"label": label, "consequence": consequence}
        return None
