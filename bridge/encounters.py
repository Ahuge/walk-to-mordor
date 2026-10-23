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
        from bridge.encounter_content import load_encounters, validate_encounter
        self.encounters = load_encounters(self.pack_dir)
        # Validate and log issues
        for eid, enc in self.encounters.items():
            for err in validate_encounter(enc):
                log.warning("encounter validation: %s", err)
        # Load POIs
        import json
        poi_path = self.pack_dir / "pois.json"
        self.pois = []
        if poi_path.exists():
            try:
                data = json.loads(poi_path.read_text(encoding="utf-8"))
                self.pois = data.get("pois", [])
                log.info("loaded %d POIs", len(self.pois))
            except Exception:
                log.exception("failed to load pois.json")
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

    def on_reading(self, ts: str, row: dict, total_km: float,
                   journey_frac: float = 0.0):
        """Check triggers. total_km is cumulative journey distance."""
        # Morale decay (1-2hr half-life approx)
        m = self.get_morale()
        if m != 0:
            self.set_morale(m * 0.9995)

        # Companion dialogue tracking
        self._update_companion(row)

        # Fatigue accumulation (distance-based)
        speed = row.get("speed_kmh") or 0.0
        if speed > 0.1:
            self.add_fatigue(speed / 3.6)  # meters per second

        # Update active challenge (if any)
        if self.active_id:
            self._update_challenge(row)
            return  # one at a time

        # POI location triggers
        self._check_pois(journey_frac)
        if self.active_id:
            return

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

    def _check_pois(self, journey_frac: float):
        """Trigger POI encounters when within radius."""
        for poi in self.pois:
            pid = f"poi_{poi['id']}"
            if self.get_status(pid) != "locked":
                continue
            pfrac = poi["journey_frac"]
            radius = poi.get("radius_frac", 0.01)
            if abs(journey_frac - pfrac) <= radius:
                # Create a synthetic encounter for this POI
                self._activate_poi(poi)
                break

    # --- hazards ---

    def _load_hazards(self):
        import json
        hpath = self.pack_dir / "hazards.json"
        self.hazards = []
        if hpath.exists():
            try:
                data = json.loads(hpath.read_text(encoding="utf-8"))
                self.hazards = data.get("hazards", [])
                log.info("loaded %d hazards", len(self.hazards))
            except Exception:
                log.exception("failed to load hazards.json")

    def get_active_hazard(self, journey_frac: float) -> dict | None:
        """Check if journey_frac is in a hazard zone (from hazards.json)."""
        if not hasattr(self, "hazards"):
            self._load_hazards()
        for h in self.hazards:
            if h["start"] <= journey_frac <= h["end"]:
                return h
        return None

    def hazard_incline_target(self, journey_frac: float,
                              total_m: float) -> float | None:
        """For mountain hazards: compute wave incline target."""
        h = self.get_active_hazard(journey_frac)
        if not h or h["type"] != "mountain":
            return None
        import math
        # Sine wave over distance
        return h["amplitude"] * (0.5 + 0.5 * math.sin(
            total_m * 2 * math.pi / h["wavelength_m"]))

    # --- rest & fatigue ---

    def get_fatigue_m(self) -> float:
        try:
            return float(self.get_player("fatigue_m", "0"))
        except ValueError:
            return 0.0

    def add_fatigue(self, meters: float):
        self.set_player("fatigue_m", str(self.get_fatigue_m() + meters))

    def reset_fatigue(self):
        self.set_player("fatigue_m", "0")
        log.info("fatigue reset (rested)")

    def get_supplies(self) -> int:
        try:
            return int(self.get_player("supplies", "0"))
        except ValueError:
            return 0

    def spend_supplies(self, n: int) -> bool:
        cur = self.get_supplies()
        if cur < n:
            return False
        self.set_player("supplies", str(cur - n))
        return True

    def camp(self) -> dict:
        """Take a night's rest. Returns summary."""
        morale_before = self.get_morale()
        # Consume 1 supply for hearty meal if available
        had_meal = self.spend_supplies(1)
        self.adjust_morale(15 if had_meal else 5)
        self.reset_fatigue()
        # Dismiss companion for the night (they'll return)
        # Unlock next campfire tale
        tales = self.get_player("tales_unlocked", "").split(",")
        tales = [t for t in tales if t]
        next_tale = len(tales) + 1
        tales.append(f"leg{next_tale:02d}")
        self.set_player("tales_unlocked", ",".join(tales))
        return {
            "morale_gain": self.get_morale() - morale_before,
            "had_meal": had_meal,
            "tale_unlocked": f"leg{next_tale:02d}",
        }

    # --- companions ---

    def set_companion(self, npc_id: str):
        self.set_player("companion_id", npc_id)
        self.set_player(f"companion_{npc_id}_km", "0")
        log.info("companion joined: %s", npc_id)

    def dismiss_companion(self):
        cid = self.get_player("companion_id", "")
        if cid:
            log.info("companion left: %s", cid)
        self.set_player("companion_id", "")

    def get_companion(self) -> str:
        return self.get_player("companion_id", "")

    def _update_companion(self, row: dict):
        """Track companion distance, trigger dialogue every 0.5-1km."""
        cid = self.get_companion()
        if not cid:
            return
        # Accumulate distance (simplified: use speed)
        speed = row.get("speed_kmh") or 0.0
        if speed > 0.1:
            key = f"companion_{cid}_km"
            try:
                cur = float(self.get_player(key, "0"))
            except ValueError:
                cur = 0.0
            cur += speed / 3600.0  # km per second
            self.set_player(key, str(cur))
            # Dialogue every 0.75km
            last_dlg = float(self.get_player(f"companion_{cid}_last_dlg", "0"))
            if cur - last_dlg >= 0.75:
                self.set_player(f"companion_{cid}_last_dlg", str(cur))
                # Queue dialogue as a toast encounter (simplified)
                log.info("companion %s dialogue at %.2fkm", cid, cur)

    def _activate_poi(self, poi: dict):
        """Activate a POI as an encounter."""
        pid = f"poi_{poi['id']}"
        # Build encounter from POI data
        ptype = poi["type"]  # history, battlefield, inn, campsite
        title = poi["name"]
        body = f"# {title}\n\n"
        if ptype == "history":
            body += f"You've reached {title}. "
            if poi.get("wiki"):
                body += f"\n\nRead more: {poi['wiki']}"
        elif ptype == "battlefield":
            body += f"This is the site of a great battle. {title} saw..."
            if poi.get("wiki"):
                body += f"\n\nRead more: {poi['wiki']}"
        elif ptype == "inn":
            body += f"You've arrived at {title}. Rest? (+morale)"
        elif ptype == "campsite":
            body += f"A good spot to camp: {title}."
        # Detour info
        detour = poi.get("detour_km", 0)
        if detour > 0 and detour <= 10:
            body += f"\n\n[Detour available: {detour}km off path]"
        # Store as synthetic encounter
        self.encounters[pid] = {
            "id": pid,
            "meta": {"type": "poi", "poi_type": ptype, "meeting": "green",
                     "detour_km": detour, "wiki": poi.get("wiki", "")},
            "body": body,
        }
        self._activate(pid)

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

    # --- test mode ---

    def list_all(self) -> list[dict]:
        """List all encounters with their current status (for test UI)."""
        out = []
        for eid, enc in self.encounters.items():
            out.append({
                "id": eid,
                "type": enc["meta"].get("type", "?"),
                "meeting": enc["meta"].get("meeting", "?"),
                "status": self.get_status(eid),
            })
        return sorted(out, key=lambda e: e["id"])

    def force_trigger(self, eid: str) -> bool:
        """Force-activate an encounter (test mode). Returns success."""
        if eid not in self.encounters:
            return False
        if getattr(self, "_pending_unlock", None) == eid:
            self._pending_unlock = None
        if self.active_id:
            self.dismiss_active()
        # Reset to locked so it can trigger, then activate
        self.set_status(eid, "locked")
        self._activate(eid)
        log.info("test: force-triggered %s", eid)
        return True

    def reset_all(self):
        """Reset all encounter state (test mode)."""
        with self.lock:
            self.db.execute("DELETE FROM encounter_state")
            self.db.commit()
        self.active_id = None
        self._last_trigger_km = 0.0
        log.info("test: reset all encounter state")

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
                unlock_id = None
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
                # Get followup dialogue if defined
                followups = meta.get("followups", {})
                followup = followups.get(choice_id, "") if isinstance(followups, dict) else ""
                # Queue unlock for auto-trigger (after followup is dismissed)
                if unlock_id:
                    self._pending_unlock = unlock_id
                return {"label": label, "consequence": consequence,
                        "followup": followup,
                        "unlock_id": unlock_id}
        return None

    def peek_pending_unlock(self) -> str | None:
        """Return the queued unlock ID without consuming it (safe for GET)."""
        unlock_id = getattr(self, "_pending_unlock", None)
        return unlock_id if unlock_id in self.encounters else None

    def check_pending_unlock(self) -> str | None:
        """Return and consume the pending unlock (for callers that trigger)."""
        unlock_id = self.peek_pending_unlock()
        if unlock_id:
            self._pending_unlock = None
        return unlock_id
