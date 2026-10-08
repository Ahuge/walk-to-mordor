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

## encounters.json

```json
{
  "default_weight": 0.25,
  "events": [
    {
      "id": "wargs",
      "legs": ["weathertop", "trollshaws"],
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

## Shipped / planned packs

| Pack | Status | Notes |
|---|---|---|
| `lotr/` | route data drafted | 12 legs, Bag End → Mount Doom |
| `van-to-yyc/` | idea | Vancouver → Calgary, ~970 km, road-trip encounters |
| `ultra-100k/` | idea | 100K training: legs = training weeks, beats = aid stations, quest type `target` |
