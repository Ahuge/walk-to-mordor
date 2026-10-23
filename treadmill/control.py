#!/usr/bin/env python3
"""FTMS treadmill belt control (Control Point 0x2ad9).

The daemon (bridge/daemon.py) owns the pad's single BLE connection and
executes commands queued in the SQLite `commands` table. This module
provides:

  * TreadmillController — the FTMS control-point driver used by the daemon
  * a CLI that queues commands for the daemon (and waits for the result):

      python treadmill/control.py start
      python treadmill/control.py stop
      python treadmill/control.py speed 4.0
      python treadmill/control.py incline 3
      python treadmill/control.py status

Confirmed against the 3S GATT dump (the 5L matches the layout):
  00          request control     -> 80 00 01
  07          start / resume      -> 80 07 01
  02 <u16le>  target speed        -> 80 02 01   (0.01 km/h)
  03 <s16le>  target inclination  -> 80 03 01   (0.1 %)
  08 01       stop                -> 80 08 01

Quirks: targets sent right after start are lost (the belt spins up to
1 km/h first) -> wait for the first live movement, then retry until the
reading matches. A stopped belt accepts no targets at all -> remembered
and re-sent after start. Start confirmation can take ~7 s -> 10 s
response timeout.
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.client import api_delete, api_get, api_post  # noqa: E402
from bridge.store import data_dir, open_db, queue_command_row  # noqa: E402

CONTROL_POINT_UUID = "00002ad9-0000-1000-8000-00805f9b34fb"
SPEED_RANGE_UUID = "00002ad4-0000-1000-8000-00805f9b34fb"
INCLINE_RANGE_UUID = "00002ad5-0000-1000-8000-00805f9b34fb"

OP_REQUEST_CONTROL = 0x00
OP_SET_SPEED = 0x02
OP_SET_INCLINE = 0x03
OP_START = 0x07
OP_STOP = 0x08

RESULT_SUCCESS = 0x01
RESPONSE_TIMEOUT_S = 10
SPINUP_TIMEOUT_S = 15
SPINUP_POLL_S = 0.25
TARGET_RETRIES = 4
COMMAND_TTL_S = 600  # daemon ignores commands older than this


class TreadmillController:
    """Drives the FTMS Control Point. Owned by the daemon (one BLE link)."""

    def __init__(self, client, get_speed, log):
        self.client = client
        self.get_speed = get_speed  # callable -> current belt speed, km/h
        self.log = log
        self._responses: asyncio.Queue = asyncio.Queue()
        self._loop = None
        self.pending_speed = None
        self.pending_incline = None
        self.min_speed = 0.5
        self.max_speed = 6.0
        self.min_incline = 0.0
        self.max_incline = 9.0

    async def setup(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self.client.start_notify(CONTROL_POINT_UUID, self._on_indication)
        try:
            raw = await self.client.read_gatt_char(SPEED_RANGE_UUID)
            low = int.from_bytes(raw[0:2], "little") / 100
            high = int.from_bytes(raw[2:4], "little") / 100
            if 0 <= low < high:
                self.min_speed, self.max_speed = low, high
            else:
                self.log.warning("ignoring odd speed range %s..%s", low, high)
            self.log.info("pad reports speed range: %.1f..%.1f km/h",
                          self.min_speed, self.max_speed)
        except Exception as e:  # noqa: BLE001
            self.log.warning("could not read speed range: %s", e)
        try:
            raw = await self.client.read_gatt_char(INCLINE_RANGE_UUID)
            low = int.from_bytes(raw[0:2], "little", signed=True) / 10
            high = int.from_bytes(raw[2:4], "little", signed=True) / 10
            if low <= high:
                self.min_incline, self.max_incline = low, high
            else:
                self.log.warning("ignoring odd incline range %s..%s", low, high)
            self.log.info("pad reports incline range: %.1f..%.1f %%",
                          self.min_incline, self.max_incline)
        except Exception as e:  # noqa: BLE001
            self.log.warning("could not read incline range: %s", e)

    async def teardown(self) -> None:
        try:
            await self.client.stop_notify(CONTROL_POINT_UUID)
        except Exception:  # noqa: BLE001
            pass

    def _on_indication(self, _sender, data: bytearray) -> None:
        # bleak may call this from a background thread; asyncio.Queue is only
        # safe to touch from the event loop.
        data = bytes(data)
        loop = self._loop
        if loop is None or loop.is_closed():
            self.log.warning("control indication before setup; dropping %s",
                             data.hex())
            return
        try:
            loop.call_soon_threadsafe(self._responses.put_nowait, data)
        except RuntimeError:
            self.log.warning("event loop closed; dropping control indication")

    async def _command(self, payload: bytes, expect_op: int) -> bool:
        while not self._responses.empty():
            self._responses.get_nowait()
        await self.client.write_gatt_char(CONTROL_POINT_UUID, payload,
                                          response=True)
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT_S):
                while True:
                    data = await self._responses.get()
                    if len(data) >= 3 and data[0] == 0x80 and data[1] == expect_op:
                        ok = data[2] == RESULT_SUCCESS
                        if not ok:
                            self.log.warning("control op 0x%02x rejected: %s",
                                             expect_op, data.hex())
                        return ok
        except TimeoutError:
            self.log.warning("no response to control op 0x%02x", expect_op)
            return False

    async def request_control(self) -> bool:
        return await self._command(bytes([OP_REQUEST_CONTROL]),
                                   OP_REQUEST_CONTROL)

    async def start(self) -> bool:
        if not await self._command(bytes([OP_START]), OP_START):
            return False
        # Belt spins up to 1 km/h first; targets sent before movement are lost.
        if not await self._wait_for_motion():
            self.log.warning("belt did not report motion after start")
            return False
        await self._apply_pending()
        return True

    async def _wait_for_motion(self) -> bool:
        deadline = time.monotonic() + SPINUP_TIMEOUT_S
        while time.monotonic() < deadline:
            if (self.get_speed() or 0.0) > 0.05:
                return True
            await asyncio.sleep(SPINUP_POLL_S)
        return False

    async def stop(self) -> bool:
        self.pending_speed = None
        self.pending_incline = None
        return await self._command(bytes([OP_STOP, 0x01]), OP_STOP)

    async def set_speed(self, kmh: float) -> bool:
        # The pad can report a 0 minimum; 0.5 is the slowest useful belt speed.
        kmh = max(max(self.min_speed, 0.5), min(self.max_speed, kmh))
        if (self.get_speed() or 0.0) <= 0.05:
            # A stopped belt accepts no targets; remember for after start.
            self.pending_speed = kmh
            self.log.info("belt stopped; queuing speed %.1f km/h for start", kmh)
            return True
        return await self._set_speed_now(kmh)

    async def _set_speed_now(self, kmh: float) -> bool:
        payload = (bytes([OP_SET_SPEED])
                   + int(round(kmh * 100)).to_bytes(2, "little"))
        for attempt in range(1, TARGET_RETRIES + 1):
            if await self._command(payload, OP_SET_SPEED):
                await asyncio.sleep(2)
                actual = self.get_speed() or 0.0
                if abs(actual - kmh) <= 0.15:
                    return True
                self.log.info("speed target %.1f not reached (%.2f), retry %d",
                              kmh, actual, attempt)
            await asyncio.sleep(2)
        return False

    async def set_incline(self, pct: float) -> bool:
        pct = max(self.min_incline, min(self.max_incline, pct))
        if (self.get_speed() or 0.0) <= 0.05:
            self.pending_incline = pct
            self.log.info("belt stopped; queuing incline %.0f%% for start", pct)
            return True
        payload = (bytes([OP_SET_INCLINE])
                   + int(round(pct * 10)).to_bytes(2, "little", signed=True))
        for _ in range(TARGET_RETRIES):
            if await self._command(payload, OP_SET_INCLINE):
                return True
            await asyncio.sleep(2)
        return False

    async def _apply_pending(self) -> None:
        if self.pending_speed is not None:
            kmh = self.pending_speed
            self.pending_speed = None
            if not await self._set_speed_now(kmh):
                self.log.warning("queued speed %.1f km/h could not be applied",
                                 kmh)
        if self.pending_incline is not None:
            pct = self.pending_incline
            self.pending_incline = None
            if not await self.set_incline(pct):
                self.log.warning("queued incline %.1f%% could not be applied",
                                 pct)


# ---------------------------------------------------------------------------
# CLI: queue commands for the daemon
# ---------------------------------------------------------------------------

def queue_command(op: str, args: dict):
    """Queue a belt command. Returns (id, via_api).

    Prefers the daemon's HTTP API (robust over WSL); falls back to a direct
    DB insert when the daemon isn't reachable (it'll execute on next run).
    """
    res = api_post("/api/commands", {"op": op, "args": args})
    if isinstance(res, dict) and "id" in res:
        return res["id"], True
    # daemon not reachable: write directly (it'll execute on next run)
    db = open_db()
    cmd_id = queue_command_row(db, op, args)
    db.commit()
    db.close()
    return cmd_id, False


def clear_commands(status: str = "pending") -> int:
    """Delete queued commands. Returns the count cleared."""
    res = api_delete(f"/api/commands?status={status}")
    if isinstance(res, dict) and "cleared" in res:
        return res["cleared"]
    db = open_db()
    cur = db.execute("DELETE FROM commands WHERE status=?", (status,))
    db.commit()
    n = cur.rowcount
    db.close()
    return n


def _command_status(cmd_id: int):
    """(status, result) via API first, direct DB as fallback."""
    res = api_get(f"/api/commands/{cmd_id}")
    if isinstance(res, dict) and res.get("status") in (
            "done", "error", "expired"):
        return res["status"], res.get("result", {})
    db = open_db()
    try:
        row = db.execute(
            "SELECT status, result FROM commands WHERE id = ?", (cmd_id,)
        ).fetchone()
        if row and row[0] in ("done", "error", "expired"):
            return row[0], json.loads(row[1] or "{}")
    finally:
        db.close()
    return None, None


def wait_for_result(cmd_id: int, timeout_s: int = 45):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, result = _command_status(cmd_id)
        if status is not None:
            return status, result
        time.sleep(0.5)
    return "timeout", {"ok": False, "reason": "daemon did not respond"}


def show_status() -> None:
    db = open_db()
    rows = db.execute(
        "SELECT id, created_at, op, args, status, result FROM commands"
        " ORDER BY id DESC LIMIT 10"
    ).fetchall()
    db.close()
    if not rows:
        print("no commands yet")
        return
    for cid, ts, op, args, status, result in rows:
        print(f"#{cid} {ts} {op} {args} -> {status} {result or ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Queue belt-control commands")
    flags = argparse.ArgumentParser(add_help=False)
    flags.add_argument("--now", action="store_true",
                       help="skip the start countdown")
    flags.add_argument("--no-wait", action="store_true",
                       help="don't wait for the daemon's result")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", parents=[flags],
                   help="start the belt (3-2-1 countdown)")
    sub.add_parser("stop", parents=[flags], help="stop the belt")
    p_speed = sub.add_parser("speed", parents=[flags],
                             help="set target speed km/h")
    p_speed.add_argument("kmh", type=float)
    p_incline = sub.add_parser("incline", parents=[flags],
                               help="set target incline %")
    p_incline.add_argument("pct", type=float)
    sub.add_parser("status", parents=[flags],
                   help="show recent commands")
    sub.add_parser("clear", help="delete pending commands from the queue")
    args = ap.parse_args()

    if args.cmd == "status":
        show_status()
        return

    if args.cmd == "clear":
        n = clear_commands()
        print(f"cleared {n} pending command(s)")
        return

    if args.cmd == "start" and not args.now:
        print("Make sure the belt area is clear, safety key in.")
        for i in (3, 2, 1):
            print(f"belt starts in {i}...", flush=True)
            time.sleep(1)

    if args.cmd == "start":
        op, op_args = "start", {}
    elif args.cmd == "stop":
        op, op_args = "stop", {}
    elif args.cmd == "speed":
        op, op_args = "set_speed", {"kmh": args.kmh}
    elif args.cmd == "incline":
        op, op_args = "set_incline", {"pct": args.pct}
    else:
        ap.error(f"unknown command {args.cmd}")
    cmd_id, via_api = queue_command(op, op_args)
    where = "daemon API" if via_api else f"db: {data_dir() / 'walks.db'}"
    print(f"queued #{cmd_id}: {op} {op_args or ''} ({where})")
    if args.no_wait:
        return
    print("waiting for the daemon...", flush=True)
    status, result = wait_for_result(cmd_id)
    print(f"-> {status}: {result}")


if __name__ == "__main__":
    main()
