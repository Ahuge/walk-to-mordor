#!/usr/bin/env python3
"""probe.py — find the UREVO walking pad over BLE and dump its GATT services.

Use this first, especially on a model not yet verified (e.g. the SpaceWalk 5L):
it shows whether the pad exposes the standard Fitness Machine Service (0x1826)
that reader.py depends on.

Usage:
    1. Power-cycle the treadmill (it advertises BLE only briefly after power-on).
    2. Keep the UREVO phone app closed / phone Bluetooth off.
    3. python treadmill/probe.py

Note: on Windows, run this in native Windows Python, not WSL
(WSL can't see the Bluetooth adapter).
"""

import asyncio

from bleak import BleakClient, BleakScanner

FTMS_UUID = "00001826-0000-1000-8000-00805f9a34fb"


async def main() -> None:
    print("Scanning for BLE devices (10s) — power-cycle the pad if nothing shows...")
    found: dict = {}

    def on_detect(device, adv):
        found[device.address] = (device, adv)

    async with BleakScanner(on_detect):
        await asyncio.sleep(10.0)

    candidates = []
    for address, (d, adv) in found.items():
        name = (d.name or adv.local_name or "").upper()
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        score = 0
        if FTMS_UUID in uuids:
            score += 2
        if "URTM" in name or "UREVO" in name:
            score += 2
        if score:
            candidates.append((score, d))

    if not candidates:
        print("No FTMS/UREVO devices found. Power-cycle the treadmill and retry.")
        return

    candidates.sort(key=lambda c: -c[0])
    for score, d in candidates:
        print(f"  [score {score}] {d.address}  name={d.name!r}")

    _, device = candidates[0]
    print(f"\nConnecting to {device.address} ({device.name})...")
    async with BleakClient(device) as client:
        print(f"Connected. Services on {device.name}:")
        for service in client.services:
            print(f"  service {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    char {char.uuid}  [{props}]  ({char.description})")


if __name__ == "__main__":
    asyncio.run(main())
