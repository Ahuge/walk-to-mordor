# Content packs

A **pack** is a self-contained game: route, story, encounters, art, level
titles — everything thematic. The engine (`engine/`, Phase 1+) is
pack-agnostic: it only understands odometer, marches, milestones,
encounters, XP, journal, streaks.

```
packs/<id>/
  pack.json        metadata: title, units, quest types, XP tuning, level titles
  route.json       ordered legs (see below)
  encounters.json  weighted event table, with optional per-leg overrides
  art/             SVG map regions, token, banners (Phase 2+)
```

## pack.json

```json
{
  "id": "lotr",
  "title": "Walk to Mordor",
  "unit": "mi",
  "quest_types": ["journey"],
  "xp_per_unit": 10,
  "incline_xp_bonus": true,
  "levels": ["Hobbit", "Shirriff", "Wanderer", "Ranger", "Elf-friend", "Ring-bearer"],
  "rituals": {
    "second_breakfast": {"before": "09:00", "xp_multiplier": 1.15},
    "rest_bonus": {"xp_multiplier": 1.10, "applies": "march_after_rest_day"}
  }
}
```

## route.json

Ordered legs. Distances are in the pack's `unit`. The engine interpolates
the party token from cumulative lifetime distance.

```json
{
  "legs": [
    {
      "id": "shire",
      "name": "The Shire",
      "from": "Bag End",
      "to": "Bucklebury Ferry",
      "distance": 120,
      "beats": {
        "arrival": "The road goes ever on. Your first steps out of Hobbiton.",
        "departure": "A ferry across the Brandywine, and the Shire is behind you."
      },
      "art": "art/shire.svg"
    }
  ]
}
```

Legs may also carry map anchors. `map_start` and `map_end` are cumulative
pixel positions along `art/journey.json`; `to_xy` is the destination in image
coordinates (`[x, y]`, y down). The dashboard uses them to keep the token and
milestone stars on the same path. See `tools/verify_map.py`.

## encounters.json

```json
{
  "default_weight": 0.25,
  "events": [
    {
      "id": "wargs",
      "legs": ["weathertop", "trollshaws-last-bridge"],
      "weight": 1.0,
      "title": "Wargs!",
      "text": "Howls in the dark. Hold 4.5 km/h for 5 minutes to outrun them.",
      "challenge": {"type": "hold_speed", "kmh": 4.5, "minutes": 5},
      "reward_xp": 50
    }
  ]
}
```

Challenge types the engine supports: `hold_speed`, `no_stops`,
`incline_finish`, `distance_today`. Declining or failing an encounter
grants nothing and costs nothing — encounters never punish.

## Planned packs

### Fantasy
| Pack | Distance | Notes |
|---|---|---|
| `lotr/` | ~1,779 mi | Walk to Mordor — route data drafted |
| `hobbit/` | idea | There and Back Again — shorter, Smaug sprint-finale |

### Real trails — backyard BC
| Pack | Distance | Notes |
|---|---|---|
| `wct/` | 75 km | West Coast Trail — ladders, cable cars, surge channels |
| `jdf/` | 47 km | Juan de Fuca — weekend-scale |
| `sct/` | 180 km | Sunshine Coast Trail — hut-to-hut, free cabins as inns |
| `gdt/` | 1,130 km | Great Divide Trail — the Rockies monster |

### Real trails — world
| Pack | Distance | Notes |
|---|---|---|
| `camino/` | ~800 km | Camino Francés — credencial stamps, albergues as inns, timetables |
| `tmb/` | 170 km | Tour du Mont Blanc — 3 countries, rifugios as inns |
| `inca/` | 42 km | Inca Trail — Dead Woman's Pass, Machu Picchu sunrise finale |
| `annapurna/` | ~200 km | Annapurna Circuit — Thorong La 5,416 m, teahouses as inns |
| `at/` | 3,500 km | Appalachian Trail — trail names as level titles |
| `nakasendo/` | ~534 km | Kyoto → Tokyo — post towns as milestones, ryokans as inns |

### History & adventure
| Pack | Distance | Notes |
|---|---|---|
| `oregon/` | idea | Oregon Trail — river fordings, dysentery (someone's, not yours) |
| `klondike/` | ~550 km | Whitehorse → Dawson — Chilkoot Pass incline boss |
| `silkroad/` | idea | Xi'an → Venice — trade goods as collectibles, caravanserais as inns |
| `round80/` | idea | Around the World in 80 Days — the timetable showcase |
| `terryfox/` | 5,373 km | Terry Fox's Marathon of Hope — a marathon a day across Canada; milestone donations hook |

### Training
| Pack | Distance | Notes |
|---|---|---|
| `ultra-100k/` | idea | 100K training — legs = weeks, beats = aid stations, quest `target` |
| `everesting/` | 8,849 m elev | Elevation quest — the incline pack |

### Open-ended / generated
| Pack | Distance | Notes |
|---|---|---|
| `van-series/` | 120–4,400 km | Vancouver → Whistler / Seattle / Calgary / Toronto |
| `moon/` | 384,400 km | Walk to the Moon — the lifetime quest |
| `horde/` | idea | Outrun the Horde — original zombie survival |
| `team/` | generated | Walk to your team — route generated from coworker pins (see below) |

## Generated packs

Some packs aren't hand-written — they're **generated** from user input.

`team/` (Walk to your team): drop pins for remote coworkers on a map; the
generator builds `route.json` (nearest-first, or an order you pick);
milestones become arrivals ("Priya's desk, Toronto"); encounters go
remote-work themed ("Slack outage — double XP for the hour"). Regenerate
any time the team changes. Generator script: `tools/generate_team_pack.py`
(Phase 2+).

Rule: generated packs are byte-identical in format to hand-written ones —
the engine can't tell the difference.

## Adding a new pack (the framework promise)

Once the engine exists, a new pack needs **zero engine changes**:

1. Create `packs/<id>/` with `pack.json`, `route.json`, `encounters.json`.
2. Drop SVG art in `art/` (or reuse the generic map renderer).
3. Register it in the table above.

That's it. Data in, game out.
