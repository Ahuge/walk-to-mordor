#!/usr/bin/env python3
"""reader.py — live FTMS treadmill data stream (read-only proof of concept).

Connects to a UREVO SpaceWalk walking pad over Bluetooth LE using the
standard Fitness Machine Service (0x1826) and prints parsed treadmill data
once per second. Optionally logs every reading to CSV.

Packet layout follows the community GATT dump for the SpaceWalk 3S
(see docs/protocol.md); the 5L is expected to match.

Usage:
    python treadmill/reader.py [--csv walks.csv] [--name URTM]

Notes:
    - Power-cycle the treadmill first: it advertises BLE only briefly
      after power-on, then goes silent.
    - One BLE connection at a time: keep the UREVO phone app closed
      (turn phone Bluetooth off while testing).
    - READ-ONLY: this script never sends belt control commands.
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

FTMS_UUID = "00001826-0000-1000-8000-00805f9b34fb"
TREADMILL_DATA_UUID = "00002acd-0000-1000-8000-00805f9b34fb"

# FTMS Treadmill Data flag bits (Bluetooth SIG). Bit 13 is RFU in the spec;
# UREVO uses it for a proprietary step counter (uint24 appended at the end).
F_AVG_SPEED = 1 << 1
F_DISTANCE = 1 << 2
F_INCLINE = 1 << 3
F_ELEVATION = 1 << 4
F_ENERGY = 1 << 7
F_HR = 1 << 8
F_ELAPSED = 1 << 10
F_UREVO_STEPS = 1 << 13


def parse_treadmill_data(raw: bytes) -> dict:
    """Parse an FTMS Treadmill Data notification. Fields are walked according
    to the flags so the parser survives flag variations between models."""
    p: dict = {}
    flags = int.from_bytes(raw[0:2], "little")
    i = 2

    p["speed_kmh"] = int.from_bytes(raw[i : i + 2], "little") / 100
    i += 2
    if flags & F_AVG_SPEED:
        p["avg_speed_kmh"] = int.from_bytes(raw[i : i + 2], "little") / 100
        i += 2
    if flags & F_DISTANCE:
        p["distance_m"] = int.from_bytes(raw[i : i + 3], "little")
        i += 3
    if flags & F_INCLINE:
        p["incline_pct"] = int.from_bytes(raw[i : i + 2], "little", signed=True) / 10
        i += 2
        i += 2  # ramp angle, sint16 0.1 deg (unused)
    if flags & F_ELEVATION:
        i += 4  # positive + negative elevation gain, uint16 each (unused)
    if flags & F_ENERGY:
        p["calories"] = int.from_bytes(raw[i : i + 2], "little")
        i += 2 + 2 + 1  # total kcal, kcal/h (uint16), kcal/min (uint8)
    if flags & F_HR:
        p["hr_bpm"] = raw[i]
        i += 1
    if flags & F_ELAPSED:
        p["elapsed_s"] = int.from_bytes(raw[i : i + 2], "little")
        i += 2
    if flags & F_UREVO_STEPS:
        p["steps"] = int.from_bytes(raw[i : i + 3], "little")
        i += 3
    return p


async def find_pad(name_hint: str, quiet: bool = False):
    """Scan for the pad. Returns (device, display_name) or None."""
    if not quiet:
        print("Scanning for the treadmill (10s)...")
    found: dict = {}

    def on_detect(device, adv):
        found[device.address] = (device, adv)

    async with BleakScanner(on_detect):
        await asyncio.sleep(10.0)

    hint = name_hint.upper()
    for _address, (d, adv) in found.items():
        display = d.name or adv.local_name or "pad"
        name = display.upper()
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        is_ftms = FTMS_UUID in uuids
        if hint in name or (is_ftms and ("URTM" in name or "UREVO" in name)):
            return d, display
    # Never fall back to an arbitrary FTMS device: the daemon can control it.
    if not quiet:
        print("No matching pad found (pass an empty --name to allow any"
              " FTMS device).")
    return None


async def stream(csv_path: str | None, name_hint: str) -> None:
    found = await find_pad(name_hint)
    if found is None:
        print("Pad not found. Power-cycle the treadmill and retry "
              "(it advertises only briefly after power-on).")
        sys.exit(1)
    device, name = found

    print(f"Found {name} ({device.address}) — connecting...")
    csv_file = open(csv_path, "a", newline="") if csv_path else None
    writer = None

    def on_notify(_sender, data: bytearray):
        row = parse_treadmill_data(bytes(data))
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = (
            f"{ts}  speed={row.get('speed_kmh', 0):.2f} km/h  "
            f"dist={row.get('distance_m', 0)} m  "
            f"incline={row.get('incline_pct', 0):.1f}%  "
            f"kcal={row.get('calories', 0)}  "
            f"time={row.get('elapsed_s', 0)}s  "
            f"steps={row.get('steps', 'n/a')}"
        )
        print(line, flush=True)
        if writer:
            writer.writerow(
                {
                    "ts": ts,
                    "speed_kmh": row.get("speed_kmh"),
                    "distance_m": row.get("distance_m"),
                    "incline_pct": row.get("incline_pct"),
                    "calories": row.get("calories"),
                    "elapsed_s": row.get("elapsed_s"),
                    "steps": row.get("steps"),
                }
            )
            csv_file.flush()

    async with BleakClient(device) as client:
        if writer is None and csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["ts", "speed_kmh", "distance_m", "incline_pct",
                            "calories", "elapsed_s", "steps"],
            )
            if csv_file.tell() == 0:
                writer.writeheader()
        print("Connected. Streaming 1/sec — walk! (Ctrl-C to stop)")
        await client.start_notify(TREADMILL_DATA_UUID, on_notify)
        try:
            while True:
                await asyncio.sleep(3600)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            await client.stop_notify(TREADMILL_DATA_UUID)
            if csv_file:
                csv_file.close()
    print("Done.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Live FTMS treadmill data reader")
    ap.add_argument("--csv", metavar="FILE", help="append readings to CSV file")
    ap.add_argument("--name", default="URTM", help="BLE name hint (default: URTM)")
    args = ap.parse_args()
    asyncio.run(stream(args.csv, args.name))


if __name__ == "__main__":
    main()
