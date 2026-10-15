# FTMS protocol notes — UREVO SpaceWalk

Reverse-engineered from the community GATT dump of a **SpaceWalk 3S**
(collected 2026-08-31 with `probe.py` during a real walk;
see [ncr/omarchy-spacewalk](https://github.com/ncr/omarchy-spacewalk),
`docs/gatt-dump.md`). The SpaceWalk **5L was verified live on 2026-10-15**
(device `URTM054`) — FTMS layout matches; see "5L verification" below.

## SpaceWalk 5L verification (2026-10-15, device `URTM054`)

Probed live via `treadmill/probe.py`:

- FTMS `0x1826` present with the full characteristic set: `2acc` (Feature),
  `2acd` (Treadmill Data, notify), `2ad3` (Training Status),
  `2ad4`/`2ad5`/`2ad7` (supported speed/inclination/HR ranges),
  `2ad9` (Control Point, write+indicate), `2ada` (Machine Status, notify).
  Matches the 3S layout — `reader.py` should work unmodified.
- Same vendor services as the 3S (`fff0` notify/write, `fee0` Huami
  leftovers), **plus** one extra unknown service
  `5833ff01-9b8b-5191-6142-22a4536ef123` (write + notify chars) not in the
  3S dump. Purpose unknown; not needed for the read path.
- Advertisement carries the **name only** (`URTM054`) — no FTMS service
  UUID in the adv payload. Discovery keys off the `URTM`/`UREVO` name hint
  (which is why probe.py scores name matches).

## Device (3S, as dumped)

- BLE name `URTM024`, manufacturer UREVO, firmware V90.08.12, hardware V002

## Services

| Service | Role |
|---|---|
| `0x1826` Fitness Machine | the one we use — standard FTMS |
| `0x180a` Device Information | name / model / versions |
| `0xfff0` | UREVO proprietary (`fff1` notify, `fff2` write) — what the phone app likely uses; we ignore it |
| `0xfee0` | Huami leftovers, unused |

## FTMS characteristics used

| Char | Use |
|---|---|
| `0x2acc` Fitness Machine Feature | capability flags; 3S reports speed + incline targets supported |
| `0x2ad4` Supported Speed Range | 3S: 1.0–6.0 km/h, 0.1 steps |
| `0x2ad5` Supported Inclination Range | 3S: 0–9, step 1 |
| `0x2acd` Treadmill Data | **notify, 1/sec** — the live feed |
| `0x2ad9` Fitness Machine Control Point | write + indicate — belt control (see below) |
| `0x2ada` Machine Status | notify — belt state changes |

## Control Point protocol (`0x2ad9`)

Confirmed working (3S dump; 5L matches the layout). Write opcode, await the
indication response `80 <opcode> 01`.

| Write | Meaning |
|---|---|
| `00` | request control |
| `07` | start / resume |
| `02 <u16le>` | target speed, 0.01 km/h |
| `03 <s16le>` | target inclination, 0.1 % |
| `08 01` | stop |

Quirks (from the dump): targets set right after start are lost — the belt
spins up to 1 km/h first, so wait ~8 s and retry until the live reading
matches. A stopped belt accepts no targets at all — remember them and
re-send after start. Start confirmation can take ~7 s — allow a 10 s
response timeout. Machine status (`0x2ada`) reports `04` on belt start,
`02 01` / `02 02` on stop. Implemented in `treadmill/control.py`,
executed by the daemon (which owns the single BLE connection).

## Treadmill Data packet (26 bytes, flags `0x259c`)

Flag bits set: 2, 3, 4, 7, 8, 10 — **and 13**, which is RFU in the FTMS
spec. UREVO hid a step counter there.

| Bytes | Field | Example |
|---|---|---|
| 0–1 | flags | `9c 25` |
| 2–3 | speed, uint16 LE, 0.01 km/h | `fa 00` → 2.50 |
| 4–6 | distance, uint24 LE, meters (device resolution ~10 m) | `64 00 00` → 100 |
| 7–8 | incline, sint16 LE, 0.1 % | `1e 00` → 3.0 |
| 9–10 | ramp angle, sint16 LE, 0.1° | — |
| 11–14 | elevation gain +/−, uint16 LE each, m | — |
| 15–16 | total energy, uint16 LE, kcal | `06 00` → 6 |
| 17–18 | energy/hour, uint16 LE | — |
| 19 | energy/minute, uint8 | — |
| 20 | heart rate, uint8, bpm | — |
| 21–22 | elapsed time, uint16 LE, s | `95 00` → 149 |
| 23–25 | **steps, uint24 LE — UREVO extension** | `b3 00 00` → 179 |

`reader.py` walks the packet by flag bits rather than assuming this exact
layout, so it survives flag variations between models.

## Quirks that matter for the game bridge

1. **Brief advertising.** The pad advertises BLE only for a short window
   after power-on, then goes silent — it can't be found by scan *or* by
   address until the next power-cycle. The bridge must scan continuously
   and grab it the moment it appears.
2. **One connection at a time.** A phone with the UREVO app connected wins
   the race and the pad stops advertising to everyone else. Keep phone
   Bluetooth off (or the app closed) while the bridge runs.
3. **Control timing (if we ever drive the belt).** On the 3S, speed/incline
   commands sent right after start are lost — the belt spins up to 1 km/h
   first and only then accepts targets; start confirmation can take ~7 s;
   a stopped belt accepts no speed commands at all. The Phase-0 reader is
   read-only and sidesteps all of this.
4. **Steps are derived, not sensed.** The step counter is computed from
   distance on-device; at 2.5 km/h it ticked ~1.36 steps/s. Fine for the
   game, but treat it as approximate.
