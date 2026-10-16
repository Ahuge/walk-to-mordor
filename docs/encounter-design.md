# Encounter Design: Walk to Mordor

## Alex's Original Directions (2026-10-15)

### Regional Random Encounters (story)
Story/lore (Tolkien-accurate plausible), regionally tied. Random chance, increasing the longer since the last one. Each has regional tie (no hobbits in Mordor). May include minigames (choose your own adventure). Sometimes just 1-3 paragraphs of interesting writing about something happening along the way.

### Random Encounters (challenge)
Short physical challenges: goblin ambush (go >2km/h for 400m), climb a hill (incline up for 2min), sneak past trolls (minimum speed for 400m). **Concern:** hard to do if in a meeting and walking.

### Regional Unlock Encounters
Random (not necessarily regional), fully fabricated, unlocks future story/challenge encounters. Deterministic once unlocked — at future point X it triggers. Ideally within same or next leg. Needs map UI icons.

### History Points (lore)
Real Tolkien lore/facts when walking near (within radius) places from the books. Requires heavy upfront research. May only have a few on the path. **Fork in the road idea:** player can detour to a point of interest, game pathfinds back to main route. Requires pathfinding on the map and POI icons.

### Map Hazards
Sparse. Examples: mountains = incline follows wave function over 100s of meters; swamp = must go slow (distance-based, not too long or annoying).

---

## Top 20 Encounter Mechanics

Each includes: **Trigger**, **Player Action**, **Meeting-Friendly** (can do while in a meeting?), and **Variation Strategy** (how we get 100s of unique encounters from this style).

### Story & Narrative

#### 1. Waystone Vignettes
**Type:** Story (passive)
**Trigger:** Random, probability increases with distance since last vignette. Regionally filtered.
**Player Action:** Read 1-3 paragraphs. No choice, no challenge. Pure atmosphere.
**Meeting-Friendly:** Yes — just a notification to read when convenient.
**Variation:** Template + regional tables. Shire: cozy, hobbit-centric (a farmer's dog follows you, smell of pipe-weed). Mordor: bleak, oppressive (ash falls, distant screams). Each region needs 15-20 vignettes; with 12 legs that's 180-240 total. Write once, theme per region.

#### 2. Crossroads Choice
**Type:** Story (choice)
**Trigger:** Random, or at specific journey fractions (e.g., 25%, 50%, 75% of a leg).
**Player Action:** 2-3 options, each with different consequences (morale +/-, supplies +/-, unlock future encounter, small distance bonus/penalty).
**Meeting-Friendly:** Yes — one tap, read later.
**Variation:** Decision trees with 3-5 nodes each. Consequences feed into Morale (see #17) and Unlocks (see #6). Need ~30-40 unique scenarios; regional reskinning doubles it.

#### 3. Dream/Vision
**Type:** Story (surreal, passive)
**Trigger:** After long continuous walks (>45 min) or late at night. Rare.
**Player Action:** Read a prophetic fragment. May foreshadow a real future encounter (unlock hint).
**Meeting-Friendly:** Yes.
**Variation:** 10-15 visions total, each tied to a future leg or boss encounter. Feels magical when a vision from Leg 2 pays off in Leg 7.

### Physical Challenges

#### 4. Pursuit!
**Type:** Challenge (speed)
**Trigger:** Random in hostile regions (not Shire). Can be declined.
**Player Action:** Maintain speed >X km/h for Y meters (e.g., 3.5 km/h for 400m) to escape. Fail = small morale hit, no real penalty.
**Meeting-Friendly:** No — but can be paused/deferred to later. If deferred, the enemy "camps nearby" and retriggers in 2km.
**Variation:** Enemy type by region (goblins in mountains, orcs in Mordor, wolves in wilds). Distance/speed scales with leg difficulty.

#### 5. Silent Passage
**Type:** Challenge (stealth)
**Trigger:** Random near "danger" markers on map.
**Player Action:** Stay UNDER X km/h for Y meters (e.g., <1.5 km/h for 300m). Tests patience.
**Meeting-Friendly:** Yes — just slow down, perfect for meetings.
**Variation:** What's being snuck past (trolls, sleeping dragon, orc patrol). Flavor text changes; mechanic stays.

#### 6. The Steep Climb
**Type:** Challenge (incline)
**Trigger:** At mountain/hill regions on the map, or random in high-elevation legs.
**Player Action:** Set incline to X% for Y minutes (e.g., 5% for 3 min).
**Meeting-Friendly:** Partial — incline doesn't affect walking speed, so doable in meetings if the pad is quiet.
**Variation:** Mountain name, elevation gain narrative, duration scales.

### Unlocks & Chains

#### 7. Rumor Heard
**Type:** Unlock
**Trigger:** Random at "settlement" points (inns, villages, crossroads).
**Player Action:** Read a rumor. It unlocks a deterministic encounter 5-20km ahead (icon appears on map).
**Meeting-Friendly:** Yes.
**Variation:** Rumor → payoff pairs. "The innkeeper whispers of a hidden cache" → 12km later, "You find the cache!" (supply bonus). Need 20-30 pairs.

#### 8. Map Fragment
**Type:** Unlock (collection)
**Trigger:** Rare random drop, or from specific Crossroads Choices.
**Player Action:** Collect 3 fragments to reveal a hidden location (lore point or shortcut).
**Meeting-Friendly:** Yes.
**Variation:** 4-5 complete sets (12-15 fragments total). Each set tells a micro-story when assembled.

### Lore & Discovery

#### 9. Standing Stones (History Points)
**Type:** Lore (location-based)
**Trigger:** Within radius of a Tolkien location on the path.
**Player Action:** Read the real history. Optional: take the "fork" detour (see Alex's idea).
**Meeting-Friendly:** Yes.
**Variation:** Requires research. Even 20-30 well-placed points across 1,779 miles is sparse but meaningful. Prioritize: Weathertop, Rivendell, Moria, Lothlórien, etc.

#### 10. Battlefield Echoes
**Type:** Lore (location-based)
**Trigger:** At sites of canonical battles.
**Player Action:** Experience a vignette of what happened there. May include a moment of silence (pause walking for 30s? optional).
**Meeting-Friendly:** Yes.
**Variation:** 8-10 major battles across the route. Each is a one-time, memorable moment.

### Hazards & Terrain

#### 11. Mountain Pass
**Type:** Hazard (incline wave)
**Trigger:** In mountain regions (deterministic by map elevation).
**Player Action:** Incline auto-adjusts following a sine wave over distance. Endure it.
**Meeting-Friendly:** Partial — no action needed, but incline changes may be noisy.
**Variation:** Wave amplitude/frequency by mountain range. Misty Mountains = brutal, Hills of Evendim = gentle.

#### 12. The Mire
**Type:** Hazard (speed cap)
**Trigger:** In swamp/marsh regions (deterministic).
**Player Action:** Speed capped at X km/h for Y meters. Go slow or the "mud" pulls you (narrative).
**Meeting-Friendly:** Yes — forced slow is meeting-friendly.
**Variation:** Swamp name, distance, flavor (sucking mud, biting flies, will-o'-wisps).

#### 13. Storm
**Type:** Hazard (random weather)
**Trigger:** Random, more likely in exposed regions (mountains, plains).
**Player Action:** 10-minute penalty: either speed -20% or incline +2% (player chooses, or auto).
**Meeting-Friendly:** Yes — passive.
**Variation:** Storm type (rain, snow, ash-storm in Mordor, heat haze in Harad).

### Social & Companions

#### 14. Fellow Traveler
**Type:** Social (companion)
**Trigger:** Random on roads/paths (not wilderness).
**Player Action:** An NPC walks with you for X km. Provides small bonus (morale +, or lore tidbits). Can dismiss.
**Meeting-Friendly:** Yes.
**Variation:** 15-20 NPCs with distinct personalities (chatty dwarf, silent ranger, nervous hobbit). Each has 3-4 dialogue snippets.

#### 15. The Race
**Type:** Social (competitive)
**Trigger:** Rare, on flat open road.
**Player Action:** An NPC challenges you to race the next 1km. Win = bonus, lose = nothing.
**Meeting-Friendly:** No — but can be declined.
**Variation:** Rival personality, stakes (pride, a meal, a map fragment).

### Rest & Recovery

#### 16. Night's Rest
**Type:** Rest (camp)
**Trigger:** After X km in a day, or at "campsite" markers.
**Player Action:** Choose to camp (ends the day's march with a bonus) or push on (morale penalty if tired).
**Meeting-Friendly:** Yes.
**Variation:** Campsite flavor, campfire story unlocked (see #20).

#### 17. Inn Respite
**Type:** Rest (settlement)
**Trigger:** At inn markers on the map.
**Player Action:** Spend "coin" (earned from encounters) for a meal (morale +) or a room (full rest + rumor).
**Meeting-Friendly:** Yes.
**Variation:** Inn name, keeper personality, menu items. 8-10 inns across the route.

### Meta & Progression

#### 18. Morale System
**Type:** Meta (persistent state)
**Trigger:** Affected by choices, weather, companions, rest.
**Player Action:** None directly — it's a background stat. High morale = +5% distance credit (you walk "lighter"). Low = -5%.
**Meeting-Friendly:** N/A (passive).
**Variation:** Not content but a system. Visual: party mood indicator on dashboard.

#### 19. Supply: Forage
**Type:** Resource (choice)
**Trigger:** Random in wild regions.
**Player Action:** Choice: slow to 1 km/h for 500m to forage (gain supplies) OR push on (save time).
**Meeting-Friendly:** Yes — slowing down is fine.
**Variation:** What's found (berries, mushrooms, lembas from a hidden cache). Supplies feed into Inn/Camp mechanics.

#### 20. Campfire Tales
**Type:** Story (unlockable, rest-gated)
**Trigger:** Only at Night's Rest or Inn. Unlocks progressively.
**Player Action:** Read a longer story (5-10 paragraphs). These are the "big" narratives — the Silmarillion tales, the history of the Ring, etc.
**Meeting-Friendly:** Yes.
**Variation:** 12 tales, one per leg. Each is a self-contained Tolkien story relevant to where you are. This is the lore backbone.

---

## Content Volume Strategy

To reach 100s of unique encounters:

| Strategy | How | Count |
|----------|-----|-------|
| **Regional reskin** | Same mechanic, different flavor per region | 3-5x multiplier |
| **Template variables** | Names, distances, enemies swapped | 2-3x multiplier |
| **Chain combinations** | Rumor → payoff, fragment sets | 20-30 chains |
| **Progressive difficulty** | Early legs simpler, later more complex | Natural growth |

**Base content needed:** ~20 mechanics × 8-12 unique instances each = 160-240 encounters. Regional theming multiplies this without new writing.

## Meeting-Friendly Tagging

Every encounter gets a tag:
- 🟢 **Meeting-safe**: Passive or slow-down only. Can do while on a call.
- 🟡 **Partial**: Requires some attention but not exertion (incline change, one tap).
- 🔴 **Active**: Requires focus/speed. Can be deferred.

Players can set "Meeting Mode" to only trigger 🟢 encounters.

## Implementation Notes

- **Trigger engine:** Each encounter has `trigger_type` (random/distance/location/time), `cooldown_km`, `region_filter`, `leg_filter`, `meeting_tag`.
- **State:** `encounters.json` per pack defines encounters; `encounter_state` table tracks seen/unlocked/completed.
- **Map UI:** Icons for unlocked (❓), active (❗), lore points (📖), hazards (⚠️).
- **Content format:** Markdown with frontmatter for metadata, so non-coders can write encounters.
