#!/usr/bin/env python3
"""Rebuild march summaries from raw readings.

The daemon writes a march row only after it sees the belt idle for 60 s.
If it was killed mid-walk (crash, task restart), the 1/sec readings are
still there but no march row exists — that walking looks "lost" in the
dashboard even though we captured it. This scans for motion segments that
aren't covered by an existing march and inserts summaries for them.

Segments already covered by a march are skipped (no double counting).
Distances accumulate positive odometer deltas, so a pad session reset
mid-walk doesn't zero out the segment.

Usage (run from PowerShell on the Windows side):
    python bridge/rebuild.py            # dry run: show what would be added
    python bridge/rebuild.py --apply    # actually insert the marches
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bridge.store import open_db  # noqa: E402

SPEED_THRESHOLD_KMH = 0.05
IDLE_TIMEOUT_S = 60
OVERLAP_PAD_S = 120
OPEN_MARCH_FRESH_S = 180


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _covered_by(start, end, seg_dist, covered):
    """Return the march covering this segment, if any.

    A segment counts as covered only if a march overlaps most of its time
    range AND recorded most of its distance — a 0 m march row doesn't
    'cover' a 772 m walk just because their timestamps touch.
    """
    seg_s = (end - start).total_seconds()
    if seg_s <= 0:
        return None
    for a, b, d in covered:
        overlap = (min(end.timestamp(), b.timestamp())
                   - max(start.timestamp(), a.timestamp()))
        if overlap > 0.8 * seg_s and d >= 0.5 * seg_dist:
            return (a, b, d)
    return None


def _seg_stats(seg):
    dist = cal = 0.0
    steps = 0
    speed_sum, speed_n, max_incl = 0.0, 0, 0.0
    prev_d = prev_c = prev_s = None
    for r in seg:
        d, c, s = r["distance_m"], r["calories"], r["steps"]
        if d is not None:
            if prev_d is not None and d >= prev_d:
                dist += d - prev_d
            prev_d = d
        if c is not None:
            if prev_c is not None and c >= prev_c:
                cal += c - prev_c
            prev_c = c
        if s is not None:
            if prev_s is not None and s >= prev_s:
                steps += s - prev_s
            prev_s = s
        sp = r["speed_kmh"] or 0.0
        if sp > SPEED_THRESHOLD_KMH:
            speed_sum += sp
            speed_n += 1
        max_incl = max(max_incl, r["incline_pct"] or 0.0)
    duration = int((_parse(seg[-1]["ts"]) - _parse(seg[0]["ts"])).total_seconds())
    avg = round(speed_sum / speed_n, 2) if speed_n else 0.0
    return {
        "started_at": seg[0]["ts"], "ended_at": seg[-1]["ts"],
        "duration_s": duration, "distance_m": int(dist),
        "calories": int(cal), "steps": steps,
        "avg_speed_kmh": avg, "max_incline_pct": max_incl,
    }


def main() -> None:
    apply = "--apply" in sys.argv
    db = open_db()
    try:
        covered = [( _parse(a), _parse(b), d) for a, b, d in db.execute(
            "SELECT started_at, ended_at, distance_m FROM marches").fetchall()]

        # Is the daemon alive in a march right now? If so, the trailing
        # segment belongs to it (covered by open_march), not to us.
        daemon_live = False
        row = db.execute(
            "SELECT value FROM meta WHERE key='open_march'").fetchone()
        if row:
            import json
            upd = _parse(json.loads(row[0])["updated_at"])
            daemon_live = ((datetime.now(timezone.utc) - upd).total_seconds()
                           < OPEN_MARCH_FRESH_S)

        cols = "ts, speed_kmh, distance_m, incline_pct, calories, steps"
        rows = [dict(zip(cols.split(", "),
                         r)) for r in db.execute(
            f"SELECT {cols} FROM readings ORDER BY ts").fetchall()]
        print(f"{len(rows)} readings, {len(covered)} existing marches")

        segments, cur, last_motion = [], [], None
        for r in rows:
            dt = _parse(r["ts"])
            if (r["speed_kmh"] or 0) > SPEED_THRESHOLD_KMH:
                cur.append(r)
                last_motion = dt
            elif cur and (dt - last_motion).total_seconds() > IDLE_TIMEOUT_S:
                segments.append(cur)
                cur = []
        if cur and not daemon_live:
            segments.append(cur)  # daemon died mid-walk; recover it
        elif cur:
            print("skipping trailing segment: daemon is live in a march")

        added = skipped = 0
        for seg in segments:
            start, end = _parse(seg[0]["ts"]), _parse(seg[-1]["ts"])
            st = _seg_stats(seg)
            tag = (f"{start:%H:%M}–{end:%H:%M}  {st['duration_s']//60} min  "
                   f"{st['distance_m']} m  avg {st['avg_speed_kmh']} km/h")
            if st["duration_s"] < 5 and st["distance_m"] == 0:
                print(f"  skip (trivial): {tag}")
                skipped += 1
                continue
            hit = _covered_by(start, end, st["distance_m"], covered)
            if hit:
                a, b, d = hit
                print(f"  skip (march {a:%H:%M}–{b:%H:%M} already has {d} m):"
                      f" {tag}")
                skipped += 1
                continue
            print(f"  {'INSERT' if apply else 'would insert'}: {tag}")
            if apply:
                db.execute(
                    "INSERT INTO marches (started_at, ended_at, duration_s,"
                    " distance_m, calories, steps, avg_speed_kmh,"
                    " max_incline_pct) VALUES (?,?,?,?,?,?,?,?)",
                    (st["started_at"], st["ended_at"], st["duration_s"],
                     st["distance_m"], st["calories"], st["steps"],
                     st["avg_speed_kmh"], st["max_incline_pct"]),
                )
                covered.append((start, end, st["distance_m"]))
                added += 1
        if apply:
            if not daemon_live:
                # The marker only exists to protect a *live* march; clear it
                # so the daemon stops warning about a crash on every start.
                db.execute("DELETE FROM meta WHERE key='open_march'")
            db.commit()
        print(f"done: {added} inserted, {skipped} skipped"
              + ("" if apply else " (dry run — use --apply to write)"))
    finally:
        db.close()


if __name__ == "__main__":
    main()
