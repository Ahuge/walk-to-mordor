# Walk to Mordor

Turn an under-desk walking pad into a journey across Middle-earth.

**Phase 0 (this repo, right now):** prove the UREVO SpaceWalk pad speaks
standard Bluetooth FTMS and stream live workout data into Python —
1 reading per second: speed, distance, incline, calories, time, steps.

**Later phases:** the game itself — see [docs/game-design.md](docs/game-design.md).

## Quick start

```bash
pip install -r requirements.txt

# 1. Power-cycle the treadmill (it advertises BLE only briefly after power-on).
#    Keep the UREVO phone app closed / phone Bluetooth off — the pad takes
#    one BLE connection at a time.

# 2. Find the pad and dump what it exposes:
python treadmill/probe.py

# 3. Stream live data (also logs to CSV with --csv):
python treadmill/reader.py --csv walks.csv
```

The reader is **read-only**: it never sends belt control commands.

## How it works

UREVO SpaceWalk pads expose the standard Bluetooth
[Fitness Machine Service](https://www.bluetooth.com/specifications/specs/fitness-machine-service-1-0/)
(`0x1826`). The `Treadmill Data` characteristic (`0x2ACD`) notifies once per
second with a 26-byte packet: flags, speed, distance, incline, calories,
heart rate, elapsed time — plus a UREVO-specific step counter tucked into
flag bit 13. Full byte map in [docs/protocol.md](docs/protocol.md),
reverse-engineered from a community GATT dump of the SpaceWalk 3S
([ncr/omarchy-spacewalk](https://github.com/ncr/omarchy-spacewalk)).

## Project layout

```
treadmill/
  probe.py    scan for the pad, dump its BLE services (verify a new model)
  reader.py   live 1/sec FTMS stream -> console (+ optional CSV log)
docs/
  protocol.md    FTMS byte map, quirks, 5L expectations
  game-design.md the full Walk to Mordor game design
```

## Notes

- Tested against the protocol dump for the SpaceWalk 3S; the 5L is expected
  to match (same product line, same app, same 0–9% incline range) — run
  `probe.py` against your pad to confirm.
- Your Python machine needs Bluetooth within ~10 m of the desk.
- Alternative library: [pyftms](https://pypi.org/project/pyftms/) (also
  bleak-based) if you prefer a packaged FTMS client.
