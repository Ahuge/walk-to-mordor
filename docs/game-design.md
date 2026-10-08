# Walk to Mordor — game design

*Status: design draft. The pad isn't here yet (arrives ~Oct 12–14); Phase 0
(the BLE bridge) is built and waiting for hardware.*

## 1. Vision

Walking under a desk is boring. Walking *to Mordor* is not. Every step on
the pad moves a little party token across Middle-earth, from Bag End to
Mount Doom. The game turns raw FTMS data (1/sec: speed, distance, incline,
time, steps) into a living journey with story, suspense, and small daily
rituals — engagement hooks that make you *want* to get on the pad.

**Design pillars**

1. **The walk is the game.** No grinding menus, no pay-to-win. Distance
   walked is the only currency that matters.
2. **Story pays out regularly.** Something happens often enough that every
   walk has a chance of a moment — never a silent treadmill.
3. **Kind, not punishing.** Rest is part of the design (even Frodo rested
   at Rivendell). The game never shames a missed day; it welcomes you back.
4. **Yours to tinker with.** JSON route, hackable bridge, local-first data.

> Copyright note: story beats below are paraphrased in our own words.
> Don't lift passages from the books — homage, not quotation.

## 2. Core loop

```
walk on pad → BLE bridge streams 1/sec FTMS → engine accumulates distance
    → party token advances along the route → milestones fire story beats
    → encounters / achievements trigger → map + stats update live
```

- **A march** = one walking session (belt start → stop, with idle tolerance).
- **Distance is persistent** — lifetime odometer; the journey is the sum of
  all marches. No permadeath, no losing progress.
- **Incline matters**: the 5L's 0–9% auto incline maps to terrain. Climbing
  Weathertop at 6% should *feel* earned — elevation gain feeds XP bonuses.

## 3. The Route — Bag End to Mount Doom

Twelve legs, each with an arrival beat and a departure beat (paraphrased).
Distances are **placeholders** — calibrate against a Tolkien atlas before
locking (the famous fan "Walk to Mordor" totals ~1,700+ miles; verify).

| # | Leg | Beat (arrival) |
|---|---|---|
| 1 | Bag End → Bucklebury Ferry | Leave the Shire: "The road goes ever on." First steps, second breakfast unlocked as a ritual. |
| 2 | Old Forest & Barrow-downs | Spooky stretch: fog on the map, random "wight" encounter (see §4). |
| 3 | Bree — The Prancing Pony | Rest stop: first **inn bonus** (see §4). Meet Strider beat. |
| 4 | Weathertop | Climb beat (incline bonus). **Nazgûl chase** set-piece: interval challenge. |
| 5 | Trollshaws → Ford of Bruinen → Rivendell | River crossing beat. **Rivendell = sanctuary**: long rest, recovery bonus, Council beat (choose your "fellowship perk"). |
| 6 | The Mines of Moria | Dark leg: map goes near-black, "drums in the deep" ambient encounter. Bridge of Khazad-dûm sprint beat. |
| 7 | Lothlórien | Golden rest: mirror of Galadriel — a reflective stats beat ("look back at how far you've walked"). |
| 8 | The Anduin (Great River) | Steady endurance leg: weekly-distance quest unlocks. |
| 9 | Rauros & the Breaking | Choice beat: pick a companion perk for the final stretch. |
| 10 | Emyn Muil & the Dead Marshes | Bleakest leg: Gollum encounter chain, "don't follow the lights" focus challenge (steady pace, no stops). |
| 11 | The Black Gate → Gorgoroth | The Eye: ambient dread meter; every march here earns bonus XP ("into the fire"). |
| 12 | Mount Doom | Finale: the last mile is a **ceremony** — best walked in one march. Credits roll: total distance, days, story log. Then: *return journey* (the Grey Havens, walking home — New Game+ with your stats). |

## 4. Engagement hooks

### 4a. Story beats (scheduled)
Milestone-triggered narration at every leg boundary plus ~2 mid-leg beats
each. Short, atmospheric, paraphrased. Delivered as a notification/card on
the dashboard and logged to a journey journal. The journal becomes the
souvenir — exportable at the end.

### 4b. Encounters (random, weighted)
The spice. A small chance per march (tunable, ~25%) of an event with a
choice or a physical challenge, themed to the current leg:

- **Wargs!** — "Hold 4.5 km/h for 5 minutes to outrun them." (interval)
- **Nazgûl overhead** — "Don't stop for 10 minutes." (steady-state)
- **Tom Bombadil's feast** — rest-day-adjacent: today's calories count
  double toward the feast meter. (Silly, warm.)
- **Strider's shortcut** — "A ranger's path: +10% distance credit today if
  you finish your march at incline ≥ 4%."
- **The Dead Marshes** — "Don't follow the lights: no belt stops for the
  whole march." (focus)
- **Second Breakfast invitation** — social hook: "A friend walked today.
  Walk within the hour for a fellowship bonus." (Phase 4)

Encounters never punish — declining or failing one just means no bonus.
The tone stays kind.

### 4c. Live fantasy map
The centerpiece UI (see §5): a stylized SVG Middle-earth. Party token moves
in real time during a march. **Fog of war**: the map reveals leg by leg —
you literally uncover the world by walking. Terrain tints per leg (green
Shire → grey mountains → gold Lórien → black Mordor). Leg transitions get
a little ceremony (banner + beat text).

### 4d. Rituals & streaks
- **Second Breakfast** — walk before 9am: +15% XP that march.
- **Elevenses** — a second march in one day: small bonus.
- **The Long Expected Walk** — one long weekend march per week: big bonus.
- **Streaks** counted in "days on the road", shown as a little campfire
  that grows. Missing a day dims it; it never goes out (kind, not punishing).

### 4e. XP, levels, gear
XP from distance (+ incline bonus + encounter bonuses + ritual bonuses).
Level titles, Hobbit-flavored:

`Hobbit → Shirriff → Wanderer → Ranger → Elf-friend → Ring-bearer → ...`

Gear unlocks are cosmetic badges with flavor text (Elven cloak at
Rivendell, Phial of Galadriel at Lórien, Mithril shirt at Moria...).
No stats, no paywalls — they're souvenirs.

### 4f. Rest is a mechanic
Inns (Bree, Rivendell, Lórien) grant **rest bonuses**: the march after a
rest day earns +10% XP ("fresh legs"). Deliberately anti-burnout: the
optimal strategy includes rest, mirroring the story.

### 4g. The Eye (Mordor legs only)
Legs 11–12 add a dread meter that rises slowly in real time and falls when
you walk. Purely atmospheric — a reason to get on the pad ("the Eye is
watching; walk it off"). Keep it playful, never anxiety-inducing.

### 4h. Social — fellowships (Phase 4)
Walk the same route alongside friends, each on their own pad: shared party
token = the fellowship's *average* position, individual banners on the map.
Weekly "marches together" (same time, video call optional). Leaderboards
only ever opt-in and framed as fellowship fun, never competition-first.

## 5. Live map spec

- **Format**: hand-drawn-style SVG, one art pass per leg region; token =
  a little hooded figure (CSS/SVG).
- **Data**: `route.json` — ordered waypoints per leg with cumulative
  distances; engine interpolates token position from lifetime distance.
- **Fog of war**: per-leg `<mask>` revealed on first entry; visited legs
  stay revealed.
- **Live updates**: WebSocket or SSE from the bridge → token glides;
  current speed/incline shown as "pace" flavor ("striding", "climbing").
- **Journal panel**: beats + encounters, chronological, exportable.
- **Stats panel**: today / week / total distance, streak campfire, level,
  current leg progress bar.

Keep the map stylized, not geographically precise — it's a storybook, and
it sidesteps any map-copyright issues.

## 6. Tech architecture

```
┌────────────┐   BLE FTMS 1/sec   ┌─────────────┐  events   ┌──────────┐
│ walking pad │ ────────────────► │ bridge/      │ ────────► │ engine/  │
└────────────┘                    │ reader.py    │           │ state.py │
                                  │ → SQLite   │           │ route.json│
                                  └─────────────┘           └────┬─────┘
                                                                │ SSE
                                                           ┌────▼─────┐
                                                           │ ui/      │
                                                           │ dashboard│
                                                           │ (map+log)│
                                                           └──────────┘
```

- **bridge/** (this repo, Phase 0): `treadmill/probe.py`, `treadmill/reader.py`
  → append to `walks.db` (SQLite): timestamped 1/sec rows + march summaries.
- **engine/** (Phase 1–2): consumes the DB; owns lifetime odometer, leg
  position, encounter RNG, XP/levels, journal. Pure Python, testable.
- **ui/** (Phase 2): local web dashboard. Start simple: FastAPI + SSE +
  inline SVG map. No auth needed (localhost); phone on same Wi-Fi can view.
- **Data files**: `route.json` (legs, beats, distances), `encounters.json`
  (weighted event table per leg), all hand-editable.

Everything local-first. No accounts, no cloud, no telemetry — the pad data
never leaves the house.

## 7. Phased roadmap

- **Phase 0 — Prove it** (now): `probe.py` + `reader.py` against the real
  5L when it arrives (~Oct 12–14). Confirm FTMS layout matches the 3S dump.
- **Phase 1 — Logger**: march detection (belt start/stop), SQLite store,
  CLI progress ("412.3 / 1,779 mi — 23% to Mordor").
- **Phase 2 — Map & story**: dashboard with live SVG map, fog of war,
  leg beats + journal.
- **Phase 3 — Game systems**: encounters, rituals, XP/levels, rest bonuses,
  the Eye.
- **Phase 4 — Fellowships**: multi-walker shared journey (Tailscale or
  LAN sync — keep it simple).

## 8. Open questions

1. Exact per-leg distances — calibrate from a Tolkien atlas (TODO).
2. Dashboard stack: FastAPI+SSE vs. something lighter? Decide at Phase 2.
3. Sound? A little "level up" chime and ambient Shire/Mordor drones would
   be lovely but are firmly nice-to-have.
4. Does the whole family walk? (Babywearing miles count double, obviously.)
5. iOS widget? The reference project syncs to Apple Health via Shortcuts —
   worth copying for the Health app ring-closers.
