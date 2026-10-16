# Encounter Implementation: Engine Integration

How each of the 20 encounter mechanics plugs into the existing Walk to Mordor engine, what needs to be built, and in what order.

## Current Engine (2026-10-15)

```
bridge/daemon.py    BLE + MarchTracker + HTTP API (:8471)
bridge/store.py     SQLite: readings, marches, meta, commands
bridge/stats.py     march_stats(), live_status(), snapshot_from_db()
ui/dashboard.html   Leaflet map, polls /api/stats every 2s
packs/lotr/         route.json (12 legs), art/, markers.json
```

**Key existing hooks:**
- `MarchTracker.reading(ts, row)` — called 1/sec with speed/distance/steps
- `MarchTracker.finish()` — writes march row, clears `open_march` meta
- `/api/stats` — returns `{walking, speed_kmh, journey_frac, leg_index, today_km, ...}`
- `meta` table — key/value for transient state (`open_march`)
- Dashboard `tick()` — 2s poll, updates map token, mini-status

---

## New Engine Components

### 1. Encounter Engine (`bridge/encounters.py`) — NEW

Core trigger/evaluation loop. Runs in the daemon, evaluated on each reading (1/sec) or on distance thresholds.

```python
class EncounterEngine:
    def __init__(self, db, lock):
        self.db = db
        self.active = None  # currently active encounter

    def on_reading(self, ts, row, march_state):
        """Called from MarchTracker.reading(). Checks triggers."""
        self._check_distance_triggers(row)
        self._check_time_triggers(ts)
        self._update_active(ts, row)

    def on_march_start(self, ts): ...
    def on_march_finish(self, march_row): ...
```

**Triggers evaluated:**
- Distance-based: every X km, or at specific journey fractions
- Time-based: every X minutes of walking, or time-of-day
- Location-based: journey_frac within radius of POI
- State-based: morale < threshold, fatigue > threshold, supplies == 0

### 2. DB Schema Additions

```sql
-- Encounter definitions (loaded from pack JSON at startup)
-- Actually stored as JSON files, not DB. DB tracks state:

CREATE TABLE IF NOT EXISTS encounter_state (
    encounter_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- 'locked', 'unlocked', 'active', 'completed', 'dismissed'
    unlocked_at TEXT,
    completed_at TEXT,
    data TEXT DEFAULT '{}'  -- encounter-specific state (choices made, progress)
);

CREATE TABLE IF NOT EXISTS player_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Keys: 'morale' (-100..100), 'supplies' (int), 'fatigue_m' (meters),
--       'companion_id' (text|null), 'last_encounter_km' (float)
```

### 3. Content Format (`packs/lotr/encounters/*.md`)

Markdown with YAML frontmatter. Non-coders can write these.

```markdown
---
id: shire_vignette_01
type: vignette
region: shire
leg: 1
meeting: green
trigger:
  type: random
  cooldown_km: 3
  probability_base: 0.1
  probability_growth: 0.05  # +5% per km since last
---

# The Farmer's Dog

A shaggy dog trots alongside you for a while, tongue lolling...

[Content here]
```

### 4. API Endpoints (daemon)

```
GET /api/encounters/active     → current encounter (if any)
POST /api/encounters/<id>/respond  → submit choice {choice_id}
POST /api/encounters/<id>/dismiss  → dismiss/defer
GET /api/player/state          → morale, supplies, fatigue, companion
```

### 5. Dashboard UI Components

- **Encounter modal**: Popup card for vignettes, choices, lore. Pauses map interaction.
- **Encounter toast**: Small notification for passive events ("Morale +5").
- **Map icons**: Custom SVG per encounter type (see icon list in encounter-design.md).
- **Player status bar**: Morale meter, supplies count, fatigue indicator, companion portrait.
- **Meeting Mode toggle**: Filter to 🟢 only.

---

## Per-Encounter Implementation Map

### 1. Waystone Vignettes
**Engine:** `EncounterEngine` random trigger. Probability = base + (growth × km_since_last).
**Needs:**
- `encounters/shire/*.md` (15-20), `encounters/mordor/*.md`, etc.
- Dashboard modal for display. Auto-dismiss after 30s or on click.
- `encounter_state` to avoid repeats (mark completed, don't retrigger).
**DB:** `encounter_state` only.
**API:** `GET /api/encounters/active` returns vignette content.

### 2. Crossroads Choice
**Engine:** Trigger at journey fractions or random. Sets `active` encounter, waits for response.
**Needs:**
- Choice UI in dashboard modal (2-3 buttons).
- `POST /api/encounters/<id>/respond` with `choice_id`.
- Consequence applier: updates `player_state` (morale, supplies), may unlock future encounter.
**DB:** `encounter_state.data` stores `{choice_made: "a", consequences_applied: true}`.
**Content:** 30-40 markdown files with `choices:` frontmatter list.

### 3. Dream/Vision
**Engine:** Trigger: `continuous_walk_minutes > 45` OR `hour in [22,23,0,1,2]` with low probability. Rare flag.
**Needs:** Same modal as vignette. May set `unlocked` on a future encounter (foreshadowing).
**DB:** `encounter_state`, plus unlock side-effect.

### 4. Pursuit!
**Engine:** Trigger: random in hostile regions. Sets `active` with `type: challenge_speed`.
**Needs:**
- Challenge tracker: monitor `speed_kmh` over next Y meters. Success if avg > threshold.
- Dashboard: progress bar ("Escape! 250m / 400m"), live speed indicator.
- Defer button: sets `status: dismissed`, retrigger in 2km.
**DB:** `encounter_state.data` = `{target_m: 400, covered_m: 0, threshold_kmh: 3.5}`.
**API:** Active encounter includes live progress (computed in `on_reading`).

### 5. Silent Passage
**Engine:** Same as #4 but `type: challenge_stealth`, success if speed STAYS BELOW threshold.
**Needs:** Same UI, inverted progress logic.
**Note:** Meeting-friendly — no defer needed, just slow down.

### 6. The Steep Climb
**Engine:** Trigger: at elevation regions (from route.json leg metadata) or random.
**Needs:**
- Challenge tracker: monitor `incline_pct` over Y minutes.
- Optionally auto-set incline via `POST /api/commands` (with user confirm).
**DB:** Same as #4.

### 7. Rumor Heard
**Engine:** Trigger: at settlement POIs. On completion, inserts a NEW encounter into `encounter_state` with `status: unlocked` and `trigger_at_km: current_km + 5-20`.
**Needs:**
- Unlock logic in `EncounterEngine`.
- Map icon appears at the future location (❓ → custom icon).
**DB:** Two rows: the rumor (completed), the unlocked encounter (unlocked, with trigger).
**Content:** Paired markdown files (rumor + payoff).

### 8. Map Fragment
**Engine:** On collect, increment `player_state.fragments_<set_id>`. At 3, unlock the hidden location encounter.
**Needs:** Fragment counter UI (small icons in status bar).
**DB:** `player_state`, `encounter_state`.

### 9. Standing Stones
**Engine:** Trigger: `journey_frac` within radius of POI (from `pois.json`).
**Needs:**
- `packs/lotr/pois.json`: list of `{id, name, journey_frac, radius_frac, type: history}`.
- Detour logic: if `detour_km <= 10`, offer detour button. Detour = temporary `journey_frac` offset, then pathfind back (simplified: linear interpolation back to main path over X km).
**DB:** `encounter_state` (one-time).
**Content:** Research + writing per POI.

### 10. Battlefield Echoes
**Engine:** Same as #9 but `type: battlefield`. One-time, no detour.
**Needs:** Modal with three tabs: Blurb | Wiki link | (art is the map icon).
**Content:** 8-10 battle entries.

### 11. Mountain Pass
**Engine:** Trigger: deterministic by leg `terrain: mountains` in route.json.
**Needs:**
- Incline controller: on each reading, compute `target_incline = base + amplitude * sin(distance * frequency)`.
- Auto-apply via command queue OR display "set incline to X%" prompt.
**DB:** `player_state` tracks active hazard.
**Config:** Per-leg in route.json: `hazard: {type: mountain, amplitude: 3, wavelength_m: 500}`.

### 12. The Mire
**Engine:** Trigger: deterministic by leg `terrain: swamp`.
**Needs:**
- Speed cap: if `speed_kmh > cap`, show warning. Optionally auto-reduce via command (with confirm).
- Progress bar: "Mire: 800m / 1200m".
**Config:** Per-leg: `hazard: {type: mire, cap_kmh: 1.5, length_m: 1200}`.

### 13. Storm
**Engine:** Trigger: random, weighted by `exposure` in leg metadata.
**Needs:**
- 10-minute timer. Applies `speed_penalty: 0.8` OR `incline_bonus: 2` (player chooses or auto).
- Dashboard weather overlay (visual).
**DB:** `player_state` with expiry timestamp.

### 14. Fellow Traveler
**Engine:** Trigger: random on `terrain: road`. Sets `player_state.companion_id`.
**Needs:**
- Dialogue engine: every 0.5-1km, pop a conversation snippet (toast or modal).
- Companion UI: portrait + name in status bar. Dismiss button.
- Lore drops: after X km together, unlock hint dialogue.
**DB:** `player_state.companion_id`, `encounter_state` for the NPC (tracks km_together).
**Content:** 40-50 NPC markdown files, each with `dialogue:` list (8-12 snippets), `lore_drops:` (2-3), `backstory`, `farewell`.

### 15. The Race
**Engine:** Trigger: rare, `terrain: flat`. Sets `active` challenge.
**Needs:** Same as #4 (speed challenge) but with rival progress (simulated NPC speed).
**DB:** Same as #4.

### 16. Night's Rest
**Engine:** Trigger: `fatigue_m > 10000` OR at campsite POI. Offers choice modal.
**Needs:**
- Fatigue tracker: accumulates with distance, resets on rest.
- Choice UI: Camp (ends day, applies bonuses) vs Push On (continues, applies penalties).
- "Day" concept: `player_state.day_number`, resets at camp or 8h elapsed.
**DB:** `player_state` (fatigue, day_number, last_camp_ts).

### 17. Inn Respite
**Engine:** Trigger: at inn POI.
**Needs:**
- Shop UI: list meal/room options with supply costs.
- Rumor unlock (see #7) as a purchase option.
**DB:** `player_state` (supplies, morale).
**Content:** 8-10 inn definitions.

### 18. Morale System
**Engine:** Background. `morale` in `player_state` (-100..100).
**Needs:**
- Decay: on each reading, `morale *= 0.999` (approx 1-2hr half-life).
- Effect: `distance_multiplier = 1 + (morale / 100 * 0.05)`.
- Applied in `MarchTracker` when accumulating distance, or in `stats.py` when reporting.
**DB:** `player_state.morale`.
**UI:** Mood indicator (😊/😐/😟) in status bar.

### 19. Supply: Forage
**Engine:** Trigger: random in `terrain: wild`. Choice modal.
**Needs:**
- If forage: set `active` challenge (slow to 1 km/h for 500m). On success: `supplies += 1`.
- Supply spend UI: at inn, camp, hazard, NPC (see design doc for uses).
**DB:** `player_state.supplies` (int).

### 20. Campfire Tales
**Engine:** Trigger: at Night's Rest or Inn, if `tales_unlocked < leg_number`.
**Needs:**
- Tale library UI (list of unlocked tales, read any).
- Unlock logic: tale N unlocks when reaching leg N AND resting.
- NPC source: if `companion_id` has `tale_id`, offer "Ask [name] for a story" option.
**DB:** `player_state.tales_unlocked` (list).
**Content:** 12 tale markdown files (long-form).

---

## Build Order (Phased)

### Phase A: Foundation (engine + 2 simplest encounters)
1. `bridge/encounters.py` — trigger engine, state management
2. DB schema: `encounter_state`, `player_state`
3. Content loader: markdown + frontmatter parser
4. API: `/api/encounters/active`, `/api/player/state`
5. Dashboard: encounter modal, toast
6. Implement #1 (Vignettes) and #18 (Morale) — simplest, prove the loop

### Phase B: Choices & Challenges
7. Choice UI + `POST /respond` (#2)
8. Challenge tracker (speed/stealth/incline) (#4, #5, #6)
9. Defer/pause logic for meetings

### Phase C: Unlocks & Lore
10. Unlock system (#7, #8)
11. POI system + `pois.json` (#9, #10)
12. Detour logic (10km cap) (#9)

### Phase D: Hazards & Social
13. Terrain hazards from route.json (#11, #12, #13)
14. Companion system + dialogue engine (#14)
15. Race (#15)

### Phase E: Rest & Meta
16. Fatigue + rest system (#16, #17)
17. Supplies (#19)
18. Campfire tales (#20)
19. Meeting Mode filter
20. Custom SVG icons (all)

### Phase F: Content
21. Write 40-50 NPCs (#14) — biggest lift, can parallelize
22. Write vignettes per region (#1)
23. Research + write POIs (#9, #10)
24. Write tales (#20)

---

## File Layout (new)

```
bridge/
  encounters.py          # EncounterEngine, trigger evaluation
  encounter_content.py   # Markdown loader, frontmatter parser
packs/lotr/
  encounters/
    vignettes/
      shire_01.md
      shire_02.md
      ...
    choices/
      crossroads_01.md
      ...
    npcs/
      dwarf_borin.md
      ranger_aria.md
      ...
    lore/
      weathertop.md
      ...
    tales/
      leg01_silmarillion.md
      ...
  pois.json              # History points, battlefields, inns, campsites
ui/
  icons/                 # Custom SVG per encounter type (19 icons)
```

## Testing

Add to `tests/`:
- `test_encounters.py`: trigger probability, cooldowns, unlock chains
- `test_morale.py`: decay rate, effect on distance
- `test_challenges.py`: speed/stealth/incline success/failure logic
- Content validation: every markdown has required frontmatter, no broken links
