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

## Daemon (Phase 1) — always-on background bridge

`bridge/daemon.py` watches for the pad, auto-connects when you power it on,
and logs everything to SQLite — 1/sec readings plus per-march summaries
(start/end, distance, calories, steps, avg speed, max incline). Storage:

- Windows: `%LOCALAPPDATA%\walk-to-mordor\walks.db` (log: `daemon.log` alongside)
- Other: `~/.walk-to-mordor/`

A march starts when the belt moves and ends after 60 s of no motion (or on
disconnect). The `meta` table is reserved for future state (e.g. nudge bookkeeping).

```powershell
# 1. Run in the foreground first to verify it works:
python bridge/daemon.py

# 2. Install as a logon task (pythonw, no console window):
python tools/install_windows.py

# 3. Start it now without logging off:
schtasks /run /tn "WalkToMordor"

# Remove it:
python tools/install_windows.py --uninstall
```

March summaries are the source for everything next: the nudge ("active on
PC, no march today") and the minimap overlay both read `walks.db`.

## Belt controls

The daemon owns the pad's single Bluetooth connection, so all belt
commands go through it via a `commands` table in the DB:

```powershell
python treadmill/control.py start          # 3-2-1 countdown, then belt starts
python treadmill/control.py stop           # stop the belt
python treadmill/control.py speed 4.0      # set target speed (km/h)
python treadmill/control.py incline 3      # set target incline (%)
python treadmill/control.py status         # show recent commands + results
```

The CLI queues the command and waits for the daemon to execute it
(`--no-wait` to skip waiting). Commands older than 10 minutes are ignored
as stale. Speed/incline are clamped to the pad's reported supported range.

**Safety:**
- The CLI counts down 3-2-1 before `start` — make sure the belt area is
  clear (kids, pets) and the safety key is in before you confirm.
- `stop` always works and clears any queued targets.
- Targets are verified against the live 1/sec readings and retried if the
  belt doesn't reach them; a stopped belt queues targets for the next start
  instead of sending them (the pad ignores them otherwise).

## Localhost API

The daemon also serves a tiny HTTP API on `127.0.0.1:8471` (stdlib only,
no extra dependencies):

- `GET /api/stats` — live snapshot (leg, progress, today/total, streak,
  belt status) as JSON
- `POST /api/commands` — `{"op": "start"|"stop"|"set_speed"|"set_incline",
  "args": {...}}` → `{"id": …}` (202)
- `GET /api/commands/<id>` — command status + result

The CLI and stats tools prefer the API and fall back to direct DB access
when the daemon isn't running. The API path is what makes WSL-side tools
reliable: SQLite over WSL's 9P mount is flaky, HTTP is not. The future
web dashboard (real map) will be served from this same API.

## Live stats & minimap

`bridge/stats.py` reads `walks.db` — one snapshot, or a live terminal view:

```bash
python bridge/stats.py            # snapshot: leg, progress, today/total, streak
python bridge/stats.py --watch    # refresh every 2 s (Ctrl-C to stop)
```

`ui/minimap.py` is the same stats in a tiny always-on-top window
(tkinter, no extra dependencies), with Start / Stop / − / + belt buttons
that queue commands for the daemon. Close the window to hide it.

```powershell
python ui/minimap.py      # console window (testing)
pythonw ui/minimap.py     # no console
# auto-start it at logon alongside the daemon:
python tools/install_windows.py --minimap
```

## Troubleshooting

**`BleakDBusError: org.bluez was not provided` (WSL):** you're running inside
Windows Subsystem for Linux, which can't see the Bluetooth adapter. Run the
scripts in *native Windows Python* instead — the repo lives on a Windows
drive, so open PowerShell, `cd` into it, `pip install bleak`,
`python treadmill/probe.py`. No code changes needed; bleak picks the right
Bluetooth backend per OS.

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
  game-design.md the full game design (engine + content packs)
packs/
  README.md      content-pack spec (route/encounters/art format)
  lotr/          Pack 1: Walk to Mordor (route.json drafted)
```

## Notes

- Tested against the protocol dump for the SpaceWalk 3S; the 5L is expected
  to match (same product line, same app, same 0–9% incline range) — run
  `probe.py` against your pad to confirm.
- Your Python machine needs Bluetooth within ~10 m of the desk.
- Alternative library: [pyftms](https://pypi.org/project/pyftms/) (also
  bleak-based) if you prefer a packaged FTMS client.
