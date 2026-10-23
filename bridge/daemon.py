#!/usr/bin/env python3
"""daemon.py — Walk to Mordor background bridge.

Long-running process (runs under pythonw on Windows: no console window):
  * watches for the UREVO pad over BLE and auto-connects when it appears
  * streams 1/sec FTMS treadmill data into SQLite
  * detects marches (belt start/stop with idle tolerance) and writes summaries
  * executes queued belt-control commands (start/stop/speed/incline)

Storage:
  Windows: %LOCALAPPDATA%\\walk-to-mordor\\walks.db (+ daemon.log)
  Other:   ~/.walk-to-mordor/

Usage:
  Foreground (verify it works):  python bridge/daemon.py
  Install as a logon task:       python tools/install_windows.py
  Queue a belt command:           python treadmill/control.py start|stop|speed|incline
"""

import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Ensure repo root is on sys.path before importing bridge modules.
# (When run as `python bridge/daemon.py`, only bridge/ is on the path.)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.store import repo_root  # noqa: E402

from bleak import BleakClient  # noqa: E402

from bridge.stats import STALE_AFTER_S, snapshot_from_db  # noqa: E402
from bridge.store import data_dir, open_db, queue_command_row  # noqa: E402
from bridge.version import __version__  # noqa: E402
from treadmill.control import (  # noqa: E402
    COMMAND_TTL_S,
    CONTROL_POINT_UUID,
    TreadmillController,
)
from treadmill.reader import (  # noqa: E402
    TREADMILL_DATA_UUID,
    find_pad,
    parse_treadmill_data,
)

SCAN_PAUSE_S = 15          # wait between scans when the pad isn't around
MARCH_IDLE_TIMEOUT_S = 60  # belt stopped this long -> march is over
SPEED_THRESHOLD_KMH = 0.05
NOTIFY_TIMEOUT_S = 10      # no unsolicited data this long -> drop the link
RECONNECT_BACKOFF_S = 5
MAX_RECONNECT_BACKOFF_S = 60
CONNECT_ERROR_LOG_EVERY = 20

log = logging.getLogger("walk-to-mordor")
stop_requested = threading.Event()


def setup_logging(log_path: Path) -> None:
    if log.handlers:  # idempotent: main() and run() may both call this
        return
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    # pythonw has no stderr; don't add a handler that would fail on emit.
    if sys.stderr is not None:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        log.addHandler(ch)


def acquire_instance_lock(path: Path):
    """Hold an exclusive OS lock for the daemon's lifetime.

    Returns the open file handle, or None if another daemon owns it. The
    OS releases the lock automatically if the process crashes, so a stale
    lock file can never wedge startup.
    """
    try:
        f = open(path, "a+")
    except OSError:
        return None
    try:
        if f.tell() == 0:
            f.write(" ")
            f.flush()
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    return f


def short_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


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
        self._tick = 0
        # Accumulated positive deltas (robust to pad counter resets when a
        # new session starts mid-march; last-minus-first would undercount).
        self.acc_dist = 0
        self.acc_cal = 0
        self.acc_steps = 0
        self._prev = {}

    def reading(self, ts: str, row: dict) -> None:
        now = datetime.now(timezone.utc)
        speed = row.get("speed_kmh") or 0.0
        if not self.in_march:
            if speed <= SPEED_THRESHOLD_KMH:
                return  # belt idle and no march open: nothing to do
            self.in_march = True
            self.start_ts = ts
            self.start_dt = now
            self.first = row
            self.last = row
            self.last_motion = now
            self.speed_sum = 0.0
            self.speed_n = 0
            self.max_incline = 0.0
            self._tick = 0
            self.acc_dist = 0
            self.acc_cal = 0
            self.acc_steps = 0
            self._prev = {k: row.get(k)
                          for k in ("distance_m", "calories", "steps")}
            log.info("march started")
            return
        # in a march: track stats, watch for the belt stopping
        self.last = row
        for key, attr in (("distance_m", "acc_dist"),
                          ("calories", "acc_cal"),
                          ("steps", "acc_steps")):
            cur = row.get(key)
            prev = self._prev.get(key)
            if cur is not None:
                if prev is not None and cur >= prev:
                    setattr(self, attr, getattr(self, attr) + (cur - prev))
                # cur < prev: counter reset (new session) — re-baseline.
                self._prev[key] = cur
        if speed > SPEED_THRESHOLD_KMH:
            self.last_motion = now
            self.speed_sum += speed
            self.speed_n += 1
        self.max_incline = max(self.max_incline, row.get("incline_pct") or 0.0)
        self._tick += 1
        if self._tick % 15 == 0:
            self._publish_open(now)
        idle = (now - self.last_motion).total_seconds()
        if idle > MARCH_IDLE_TIMEOUT_S:
            self.finish(self.last_motion)

    def _publish_open(self, now) -> None:
        """Publish the in-progress march so stats/dashboards show live distance."""
        dur = max(0, int((now - self.start_dt).total_seconds()))
        with self.lock:
            self.db.execute(
                "INSERT INTO meta (key, value) VALUES ('open_march', ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps({"started_at": self.start_ts,
                             "distance_m": self.acc_dist,
                             "steps": self.acc_steps,
                             "duration_s": dur,
                             "updated_at": now.isoformat(timespec="seconds")}),),
            )
            self.db.commit()

    def finish(self, end_dt) -> None:
        if not self.in_march:
            return
        end_ts = end_dt.isoformat(timespec="seconds")
        dist = self.acc_dist
        cal = self.acc_cal
        steps = self.acc_steps if self._prev.get("steps") is not None else None
        avg_speed = round(self.speed_sum / self.speed_n, 2) if self.speed_n else 0.0
        duration = max(0, int((end_dt - self.start_dt).total_seconds()))
        if duration < 5 and dist == 0:
            log.info("ignoring trivial march (<5s, 0m)")
            self.in_march = False
            self.first = {}
            self.last = {}
            return
        with self.lock:
            self.db.execute(
                "INSERT INTO marches (started_at, ended_at, duration_s,"
                " distance_m, calories, steps, avg_speed_kmh, max_incline_pct)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (self.start_ts, end_ts, duration, dist, cal, steps,
                 avg_speed, self.max_incline),
            )
            self.db.execute("DELETE FROM meta WHERE key='open_march'")
            self.db.commit()
        log.info("march finished: %d m in %d s (avg %.2f km/h)",
                 dist, duration, avg_speed)
        self.in_march = False
        self.first = {}
        self.last = {}


def claim_next_command(db: sqlite3.Connection, lock: threading.Lock):
    with lock:
        row = db.execute(
            "SELECT id, op, args, created_at FROM commands"
            " WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        cur = db.execute(
            "UPDATE commands SET status='running'"
            " WHERE id=? AND status='pending'", (row[0],))
        db.commit()
        return row if cur.rowcount else None


def finish_command(db, lock, cmd_id, status, result) -> None:
    with lock:
        db.execute(
            "UPDATE commands SET status=?, result=?, done_at=? WHERE id=?",
            (status, json.dumps(result),
             datetime.now(timezone.utc).isoformat(timespec="seconds"), cmd_id),
        )
        db.commit()


async def command_worker(controller: TreadmillController,
                         db: sqlite3.Connection,
                         lock: threading.Lock) -> None:
    """Execute queued belt-control commands sequentially while connected."""
    while not stop_requested.is_set():
        cmd = claim_next_command(db, lock)
        if cmd is None:
            await asyncio.sleep(1)
            continue
        cmd_id, op, args_json, created_at = cmd
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(created_at)).total_seconds()
        if age > COMMAND_TTL_S:
            finish_command(db, lock, cmd_id, "expired",
                           {"ok": False, "reason": f"stale ({int(age)}s old)"})
            log.info("command %d expired (stale)", cmd_id)
            continue
        args = json.loads(args_json or "{}")
        log.info("executing command %d: %s %s", cmd_id, op, args)
        try:
            if op == "start":
                ok = await controller.start()
            elif op == "stop":
                ok = await controller.stop()
            elif op == "set_speed":
                ok = await controller.set_speed(float(args["kmh"]))
            elif op == "set_incline":
                ok = await controller.set_incline(float(args["pct"]))
            else:
                finish_command(db, lock, cmd_id, "error",
                               {"ok": False, "reason": f"unknown op {op!r}"})
                continue
            finish_command(db, lock, cmd_id,
                           "done" if ok else "error", {"ok": ok})
        except Exception as e:  # noqa: BLE001
            log.exception("command %d (%s) failed", cmd_id, op)
            try:
                finish_command(db, lock, cmd_id, "error",
                               {"ok": False, "reason": str(e)})
            except Exception:  # noqa: BLE001
                # Status write failed too (e.g. lock contention): back off so
                # we don't hot-loop re-claiming the same pending command.
                log.exception("command %d: could not write failure status",
                              cmd_id)
                await asyncio.sleep(2)


async def sleep_or_stop(seconds: float) -> None:
    """Sleep, but wake early if a stop was requested."""
    try:
        await asyncio.wait_for(
            asyncio.to_thread(stop_requested.wait, seconds),
            timeout=seconds + 5,
        )
    except (asyncio.TimeoutError, TimeoutError):
        pass


API_PORT = 8471


class _ApiHandler(BaseHTTPRequestHandler):
    """Localhost API: stats and belt commands without touching the DB file.

    This is what WSL-side tools (and later the web dashboard) talk to —
    SQLite over WSL's 9P mount is flaky, HTTP is not.
    """

    server_version = "WalkToMordor/1"
    # Set by run(): the daemon's shared DB connection and lock. The handler
    # writes through these directly — never via control.queue_command, which
    # would POST back to this same server (infinite regress).
    db = None
    lock = None
    # BLE connection state, updated by the connection loop, read by /api/stats.
    ble_state = {
        "connected": False,
        "device_name": None,
        "device_address": None,
        "last_error": None,
        "last_reading_ts": None,
        "consecutive_failures": 0,
    }
    # Encounter engine, set by run().
    engine = None

    def log_message(self, *args):  # quiet
        pass

    def _serve_repo_file(self, rel: str, content_type: str):
        body = (repo_root() / rel).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Localhost dashboard: never serve a stale cached page.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                return self._serve_repo_file("ui/dashboard.html",
                                             "text/html; charset=utf-8")
            static = {
                "/map.webp": ("packs/lotr/art/map.webp", "image/webp"),
                "/journey.json": ("packs/lotr/art/journey.json",
                                  "application/json"),
                "/markers.json": ("packs/lotr/art/markers.json",
                                  "application/json"),
                "/icon.png": ("packs/lotr/art/icon.png", "image/png"),
                "/leaflet.js": ("ui/vendor/leaflet/leaflet.js",
                                "text/javascript"),
                "/leaflet.css": ("ui/vendor/leaflet/leaflet.css", "text/css"),
            }
            if path in static:
                return self._serve_repo_file(*static[path])
            if path.startswith("/icons/") and path.endswith(".svg") and \
                    "/" not in path[len("/icons/"):]:
                return self._serve_repo_file(
                    "packs/lotr/art/icons/" + path[len("/icons/"):],
                    "image/svg+xml")
            if path == "/api/route":
                route = (repo_root()
                         / "packs" / "lotr" / "route.json").read_text(
                             encoding="utf-8")
                body = route.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/marches":
                limit = int(parse_qs(parsed.query).get("limit", ["20"])[0])
                limit = max(1, min(500, limit))
                db = open_db()
                try:
                    rows = db.execute(
                        "SELECT id, started_at, ended_at, duration_s,"
                        " distance_m, calories, steps, avg_speed_kmh,"
                        " max_incline_pct FROM marches"
                        " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
                finally:
                    db.close()
                self._send_json({"marches": [
                    {"id": r[0], "started_at": r[1], "ended_at": r[2],
                     "duration_s": r[3], "distance_m": r[4], "calories": r[5],
                     "steps": r[6], "avg_speed_kmh": r[7],
                     "max_incline_pct": r[8]} for r in rows]})
                return
            if path == "/api/stats":
                s = snapshot_from_db()
                s["source"] = "api"
                s["version"] = __version__
                ble = dict(_ApiHandler.ble_state)
                age = None
                ts = ble.get("last_reading_ts")
                if ts:
                    try:
                        age = (datetime.now(timezone.utc)
                               - datetime.fromisoformat(ts)).total_seconds()
                    except (TypeError, ValueError):
                        age = None
                ble["last_reading_age_s"] = round(age, 1) if age is not None else None
                ble["stale"] = age is not None and age > STALE_AFTER_S
                s["ble"] = ble
                self._send_json(s)
            elif path == "/api/log":
                try:
                    n = int(parse_qs(parsed.query).get("n", ["50"])[0])
                except ValueError:
                    n = 50
                n = max(1, min(200, n))
                log_file = data_dir() / "daemon.log"
                lines = []
                if log_file.exists():
                    with open(log_file, encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()[-n:]
                self._send_json({"lines": [l.rstrip("\n") for l in lines]})
            elif path == "/api/encounters/active":
                eng = type(self).engine
                self._send_json({"encounter": eng.get_active() if eng else None})
            elif path == "/api/encounters/list":
                eng = type(self).engine
                self._send_json({"encounters": eng.list_all() if eng else []})
            elif path == "/api/encounters/pending":
                eng = type(self).engine
                unlock_id = eng.check_pending_unlock() if eng else None
                self._send_json({"unlock_id": unlock_id})
            elif path == "/api/pois":
                eng = type(self).engine
                pois = eng.pois if eng and hasattr(eng, "pois") else []
                self._send_json({"pois": pois})
            elif path == "/api/player/state":
                eng = type(self).engine
                if eng:
                    self._send_json({
                        "morale": eng.get_morale(),
                        "supplies": eng.get_supplies(),
                        "fatigue_m": eng.get_fatigue_m(),
                        "companion": eng.get_companion(),
                        "tales": eng.get_player("tales_unlocked", ""),
                    })
                else:
                    self._send_json({"error": "engine not ready"}, 503)
            elif path == "/advanced":
                return self._serve_repo_file("ui/advanced.html",
                                             "text/html; charset=utf-8")
            elif path.startswith("/api/commands/"):
                try:
                    cmd_id = int(path.rsplit("/", 1)[-1])
                except ValueError:
                    return self._send_json({"error": "bad id"}, 400)
                db = open_db()
                try:
                    row = db.execute(
                        "SELECT id, op, args, status, result, done_at"
                        " FROM commands WHERE id=?", (cmd_id,)).fetchone()
                finally:
                    db.close()
                if not row:
                    return self._send_json({"error": "not found"}, 404)
                self._send_json({
                    "id": row[0], "op": row[1],
                    "args": json.loads(row[2] or "{}"),
                    "status": row[3],
                    "result": json.loads(row[4] or "{}"),
                    "done_at": row[5],
                })
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/encounters/dismiss":
                eng = type(self).engine
                if eng:
                    eng.dismiss_active()
                return self._send_json({"ok": True})
            if path == "/api/encounters/defer":
                eng = type(self).engine
                if eng:
                    eng.defer_active()
                return self._send_json({"ok": True})
            if path == "/api/encounters/trigger":
                length = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    return self._send_json({"error": "bad json"}, 400)
                eng = type(self).engine
                ok = eng.force_trigger(data.get("encounter_id", "")) if eng else False
                return self._send_json({"ok": ok})
            if path == "/api/encounters/reset":
                eng = type(self).engine
                if eng:
                    eng.reset_all()
                return self._send_json({"ok": True})
            if path == "/api/encounters/camp":
                eng = type(self).engine
                result = eng.camp() if eng else {"error": "no engine"}
                return self._send_json(result)
            if path == "/api/encounters/complete":
                eng = type(self).engine
                if eng:
                    eng.complete_active()
                return self._send_json({"ok": True})
            if path == "/api/encounters/respond":
                length = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    data = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    return self._send_json({"error": "bad json"}, 400)
                eng = type(self).engine
                result = eng.respond_to_active(data.get("choice_id", "")) if eng else None
                if result:
                    return self._send_json({"ok": True, **result})
                return self._send_json({"error": "invalid choice"}, 400)
            if path != "/api/commands":
                return self._send_json({"error": "not found"}, 404)
            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except Exception:  # noqa: BLE001
                return self._send_json({"error": "bad json"}, 400)
            op = data.get("op")
            args = data.get("args") or {}
            if op not in ("start", "stop", "set_speed", "set_incline"):
                return self._send_json({"error": f"unknown op {op!r}"}, 400)
            with type(self).lock:
                cmd_id = queue_command_row(type(self).db, op, args)
                type(self).db.commit()
            log.info("API: queued command %d (%s %s) from %s",
                     cmd_id, op, args, self.client_address[0])
            self._send_json({"id": cmd_id}, 202)
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/api/commands":
                return self._send_json({"error": "not found"}, 404)
            only = parse_qs(parsed.query).get("status", ["pending"])[0]
            with type(self).lock:
                cur = type(self).db.execute(
                    "DELETE FROM commands WHERE status=?", (only,))
                type(self).db.commit()
            log.info("API: cleared %d '%s' commands", cur.rowcount, only)
            self._send_json({"cleared": cur.rowcount})
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, 500)


def _make_api_server() -> ThreadingHTTPServer:
    # 0.0.0.0 so WSL2 can reach it via the host IP (Windows localhost
    # forwarding is unreliable). Home-LAN only in practice; the port is
    # arbitrary and the API is belt controls, so keep it firewalled.
    server = ThreadingHTTPServer(("0.0.0.0", API_PORT), _ApiHandler)
    server.daemon_threads = True
    return server


def _serve_api(server: ThreadingHTTPServer) -> None:
    try:
        server.serve_forever()
    except Exception:  # noqa: BLE001
        log.exception("API server error")
    finally:
        server.server_close()


async def run() -> None:
    ddir = data_dir()
    setup_logging(ddir / "daemon.log")
    instance_lock = acquire_instance_lock(ddir / "daemon.lock")
    if instance_lock is None:
        log.error("another daemon already holds %s; exiting", ddir / "daemon.lock")
        return
    # check_same_thread=False: bleak may invoke notify callbacks off the
    # event-loop thread on some backends; all writes go through the lock.
    lock = threading.Lock()
    db = open_db()
    tracker = MarchTracker(db, lock)
    # Crash recovery: a command stuck in 'running' never got its result
    # written; re-queue it so it isn't lost.
    db.execute("UPDATE commands SET status='pending' WHERE status='running'")
    db.commit()
    if db.execute("SELECT 1 FROM meta WHERE key='open_march'").fetchone():
        log.warning("found an open march from a previous run; run"
                    " `python bridge/rebuild.py --apply` to recover any"
                    " distance captured after the crash")
    from bridge.encounters import EncounterEngine
    engine = EncounterEngine(db, lock, repo_root() / "packs" / "lotr")
    _ApiHandler.db = db
    _ApiHandler.lock = lock
    _ApiHandler.engine = engine
    log.info("daemon started, version=%s pid=%d db=%s",
             __version__, os.getpid(), ddir / "walks.db")

    try:
        api_server = _make_api_server()
    except OSError as e:
        log.error("API bind failed on 0.0.0.0:%d: %s", API_PORT, e)
        raise
    api_thread = threading.Thread(target=_serve_api, args=(api_server,),
                                  daemon=True, name="api")
    api_thread.start()
    log.info("API listening on 0.0.0.0:%d", API_PORT)

    def on_signal(signum, frame):
        log.info("stop requested (signal %s)", signum)
        stop_requested.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    failures = 0
    scan_misses = 0
    while not stop_requested.is_set():
        try:
            found = await find_pad("URTM", quiet=True)
        except Exception as e:  # noqa: BLE001
            log.warning("BLE scan failed: %s", short_error(e))
            log.debug("scan failure detail", exc_info=True)
            _ApiHandler.ble_state["last_error"] = f"scan failed: {short_error(e)}"
            await sleep_or_stop(SCAN_PAUSE_S)
            continue
        if found is None:
            scan_misses += 1
            _ApiHandler.ble_state["connected"] = False
            _ApiHandler.ble_state["last_error"] = (
                "pad not found — power-cycle the treadmill if it stays off")
            if scan_misses == 1 or scan_misses % 10 == 0:
                log.info("pad not found (scan %d)", scan_misses)
            await sleep_or_stop(SCAN_PAUSE_S)
            continue
        device, name = found
        scan_misses = 0
        _ApiHandler.ble_state["device_name"] = name
        _ApiHandler.ble_state["device_address"] = device.address
        log.info("pad found: %s (%s)", name, device.address)
        try:
            async with BleakClient(device) as client:
                failures = 0
                _ApiHandler.ble_state["connected"] = True
                _ApiHandler.ble_state["consecutive_failures"] = 0
                _ApiHandler.ble_state["last_error"] = None
                log.info("connected")
                state = {"row": {}}
                controller = TreadmillController(
                    client,
                    lambda: (state["row"].get("speed_kmh") or 0.0),
                    log,
                )
                await controller.setup()
                if not await controller.request_control():
                    log.warning("request control failed;"
                                " belt commands will error")

                last_notify = time.monotonic()

                def on_notify(_sender, data: bytearray):
                    nonlocal last_notify
                    last_notify = time.monotonic()
                    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    row = parse_treadmill_data(bytes(data))
                    _ApiHandler.ble_state["last_reading_ts"] = ts
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
                    state["row"] = row
                    tracker.reading(ts, row)
                    # Encounter triggers (needs total journey km + fraction)
                    try:
                        from bridge.stats import march_stats, route_position, load_route
                        _, total_m, _, _, _ = march_stats(db)
                        route = load_route()
                        _, _, journey_frac = route_position(route, total_m)
                        engine.on_reading(ts, row, total_m / 1000.0, journey_frac)
                    except Exception:
                        log.exception("encounter on_reading failed")

                await client.start_notify(TREADMILL_DATA_UUID, on_notify)
                last_notify = time.monotonic()
                worker = asyncio.create_task(
                    command_worker(controller, db, lock))
                try:
                    while not stop_requested.is_set() and client.is_connected:
                        if time.monotonic() - last_notify > NOTIFY_TIMEOUT_S:
                            msg = (f"no treadmill data for {NOTIFY_TIMEOUT_S}s;"
                                   " dropping the link to reconnect")
                            log.warning(msg)
                            _ApiHandler.ble_state["last_error"] = msg
                            break
                        await asyncio.sleep(1)
                finally:
                    worker.cancel()
                    try:
                        await worker
                    except asyncio.CancelledError:
                        pass
                    for uuid in (CONTROL_POINT_UUID, TREADMILL_DATA_UUID):
                        try:
                            await client.stop_notify(uuid)
                        except Exception:  # noqa: BLE001
                            pass
                if not client.is_connected:
                    log.info("disconnected")
                _ApiHandler.ble_state["connected"] = False
        except Exception as e:  # noqa: BLE001
            failures += 1
            _ApiHandler.ble_state["connected"] = False
            _ApiHandler.ble_state["consecutive_failures"] = failures
            _ApiHandler.ble_state["last_error"] = (
                "pad unreachable — power-cycle the treadmill if it stays off"
                if failures >= 3 else short_error(e))
            if failures == 1:
                log.exception("connection error (will retry)")
            elif failures % CONNECT_ERROR_LOG_EVERY == 0:
                log.warning("still cannot connect (%d failures): %s",
                            failures, short_error(e))
            else:
                log.debug("connection error (%d): %s", failures,
                          short_error(e), exc_info=True)
        finally:
            _ApiHandler.ble_state["connected"] = False
            if tracker.in_march:
                end = tracker.last_motion or datetime.now(timezone.utc)
                if stop_requested.is_set():
                    log.info("daemon stopping mid-march; ending at last motion")
                else:
                    log.warning("link lost mid-march; ending at last motion")
                tracker.finish(end)
        delay = (min(MAX_RECONNECT_BACKOFF_S,
                     RECONNECT_BACKOFF_S * (2 ** min(failures, 4)))
                 if failures else RECONNECT_BACKOFF_S)
        await sleep_or_stop(delay)

    tracker.finish(tracker.last_motion or datetime.now(timezone.utc))
    db.close()
    instance_lock.close()
    log.info("daemon stopped")


def main() -> None:
    ddir = data_dir()
    setup_logging(ddir / "daemon.log")
    try:
        asyncio.run(run())
    except Exception:
        log.exception("daemon crashed")
        raise


if __name__ == "__main__":
    main()
