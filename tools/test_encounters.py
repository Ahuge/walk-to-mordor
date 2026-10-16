#!/usr/bin/env python3
"""Encounter test utility: trigger and inspect encounters via the daemon API.

Usage:
    python tools/test_encounters.py list              # list all encounters
    python tools/test_encounters.py trigger <id>      # force-trigger one
    python tools/test_encounters.py state             # show player state
    python tools/test_encounters.py camp              # take a rest
    python tools/test_encounters.py reset             # wipe encounter state
    python tools/test_encounters.py stress <n>        # trigger n random encounters

Requires the daemon running at http://127.0.0.1:8471/
"""

import json
import random
import sys
import urllib.request

API = "http://127.0.0.1:8471"


def get(path):
    with urllib.request.urlopen(API + path) as r:
        return json.loads(r.read())


def post(path, data=None):
    req = urllib.request.Request(
        API + path, data=json.dumps(data or {}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def cmd_list():
    d = get("/api/encounters/list")
    print(f"{'ID':<35} {'TYPE':<12} {'MEET':<7} {'STATUS'}")
    print("-" * 70)
    for e in d["encounters"]:
        print(f"{e['id']:<35} {e['type']:<12} {e['meeting']:<7} {e['status']}")


def cmd_trigger(eid):
    r = post("/api/encounters/trigger", {"encounter_id": eid})
    print("triggered!" if r.get("ok") else "failed - unknown ID?")


def cmd_state():
    s = get("/api/player/state")
    print(f"Morale:   {s['morale']:.1f}")
    print(f"Supplies: {s['supplies']}")
    print(f"Fatigue:  {s['fatigue_m']:.0f}m")
    print(f"Companion:{s['companion'] or '(none)'}")
    print(f"Tales:    {s['tales'] or '(none)'}")


def cmd_camp():
    r = post("/api/encounters/camp")
    print(f"Rested! Morale +{r['morale_gain']:.0f}")
    print(f"Meal: {'yes' if r['had_meal'] else 'no (no supplies)'}")
    print(f"Tale unlocked: {r['tale_unlocked']}")


def cmd_reset():
    post("/api/encounters/reset")
    print("all encounter state wiped")


def cmd_stress(n):
    d = get("/api/encounters/list")
    ids = [e["id"] for e in d["encounters"]]
    if not ids:
        print("no encounters loaded")
        return
    print(f"triggering {n} random encounters (check the dashboard)...")
    import time
    for i in range(n):
        eid = random.choice(ids)
        post("/api/encounters/trigger", {"encounter_id": eid})
        print(f"  [{i+1}/{n}] {eid}")
        time.sleep(3)  # give each time to display
    print("done! Dismiss each in the dashboard to continue.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "list":
            cmd_list()
        elif cmd == "trigger" and len(sys.argv) > 2:
            cmd_trigger(sys.argv[2])
        elif cmd == "state":
            cmd_state()
        elif cmd == "camp":
            cmd_camp()
        elif cmd == "reset":
            cmd_reset()
        elif cmd == "stress" and len(sys.argv) > 2:
            cmd_stress(int(sys.argv[2]))
        else:
            print(__doc__)
    except urllib.error.URLError:
        print("daemon not running at " + API, file=sys.stderr)
        sys.exit(1)
