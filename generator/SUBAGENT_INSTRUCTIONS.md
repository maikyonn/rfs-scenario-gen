# Subagent Instructions: Config-Based Scenario Generation

You are generating JSON config files for crash scenarios. Each config is translated into an OpenSCENARIO (.xosc) file by `config_builder.py` and validated with esmini collision detection.

## Your Workflow

For each crash situation assigned to you:

1. **Read the situation** from `crash_situations.json` — note the `id`, `pattern`, `description`, `entities`, and `speeds_mph`.
2. **Read ROAD_REFERENCE.md** for road/junction data relevant to the pattern.
3. **Select road/junction** from the reference tables.
4. **Compute entity start positions** using timing rules.
5. **Write config JSON** to `generator/configs/situation_{id:03d}.json`.
6. **Validate**: Run `python -m generator.config_builder generator/configs/situation_{id:03d}.json --validate`
7. If **PASS** → move to next situation.
8. If **FAIL** → adjust timing/positions/speeds → retry (max 3 attempts).

## Config JSON Schema

```json
{
  "situation_id": 42,
  "pattern": "junction_tbone",
  "scenario_name": "RedLight_Sedan_SUV",
  "sim_time": 15.0,
  "entities": [
    {"name": "entity_name", "type": "sedan"}
  ],
  "init_actions": [
    {"entity": "entity_name", "road": 52, "lane": -1, "s": 20.0, "speed_mph": 40}
  ],
  "routes": [
    {"entity": "entity_name", "start_road": 52, "start_lane": -1, "start_s": 20.0,
     "exit_road": 19, "exit_lane": 1}
  ],
  "maneuvers": [
    {
      "entity": "entity_name",
      "events": [
        {"name": "event_name", "trigger_time": 0.0, "actions": [
          {"type": "speed", "speed_mph": 40}
        ]}
      ]
    }
  ]
}
```

### Entity Types
`sedan`, `suv`, `pickup`, `motorcycle`, `bicycle`, `pedestrian`, `debris`, `parked_car_door`

### Action Types

| Type | Required fields | Optional fields |
|------|----------------|-----------------|
| `speed` | `speed_mph` | `transition_time` (default 0.0, instant) |
| `speed_smooth` | `speed_mph` | `transition_time` (default 2.0, sinusoidal ramp) |
| `brake` | — | `target_speed_mph` (default 0), `transition_time` (default 2.0) |
| `lane_change` | `target_lane` | `transition_time` (default 2.0) |

### Init Action Fields

| Field | Required | Notes |
|-------|----------|-------|
| `entity` | yes | Entity name |
| `road` | yes | Road ID (integer) |
| `lane` | yes | Lane ID (negative=forward, positive=backward) |
| `s` | yes | Position along road in meters |
| `speed_mph` | yes | Initial speed (0 for stationary) |
| `lane_type` | no | Default "driving". Use "parking" for parking lanes |
| `offset` | no | Lateral offset in meters (default 0.0) |

---

## Pattern Examples

### 1. junction_tbone

Two vehicles on different roads approaching the same junction, routed through crossing connecting roads.

```json
{
  "situation_id": 1,
  "pattern": "junction_tbone",
  "scenario_name": "RedLight_Sedan_SUV",
  "sim_time": 15.0,
  "entities": [
    {"name": "sedan", "type": "sedan"},
    {"name": "suv", "type": "suv"}
  ],
  "init_actions": [
    {"entity": "sedan", "road": 52, "lane": -1, "s": 20, "speed_mph": 35},
    {"entity": "suv", "road": 44, "lane": 1, "s": 68, "speed_mph": 30}
  ],
  "routes": [
    {"entity": "sedan", "start_road": 52, "start_lane": -1, "start_s": 20, "exit_road": 19, "exit_lane": 1},
    {"entity": "suv", "start_road": 44, "start_lane": 1, "start_s": 68, "exit_road": 20, "exit_lane": -1}
  ],
  "maneuvers": [
    {
      "entity": "sedan",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 35}]}
      ]
    },
    {
      "entity": "suv",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 30}]}
      ]
    }
  ]
}
```

**How to compute positions:**
- Sedan on road 52 lane -1 (forward→junction 323): distance to junction = 100 - s.
  - At s=20, distance=80m. At 35mph (15.65m/s), arrival time = 80/15.65 = 5.1s
- SUV on road 44 lane 1 (backward→junction 323): distance to junction = s.
  - Need arrival in ~5.1s. At 30mph (13.41m/s), distance = 13.41 × 5.1 = 68.4m → s=68

### 2. rear_end

Stationary queue + approaching vehicle on the same road and lane.

```json
{
  "situation_id": 2,
  "pattern": "rear_end",
  "scenario_name": "Rearend_Queue_4cars",
  "sim_time": 12.0,
  "entities": [
    {"name": "car_a", "type": "sedan"},
    {"name": "car_b", "type": "sedan"},
    {"name": "car_c", "type": "sedan"},
    {"name": "car_d", "type": "sedan"}
  ],
  "init_actions": [
    {"entity": "car_a", "road": 52, "lane": -1, "s": 85.0, "speed_mph": 0},
    {"entity": "car_b", "road": 52, "lane": -1, "s": 78.5, "speed_mph": 0},
    {"entity": "car_c", "road": 52, "lane": -1, "s": 72.0, "speed_mph": 0},
    {"entity": "car_d", "road": 52, "lane": -1, "s": 22.0, "speed_mph": 40}
  ],
  "maneuvers": [
    {
      "entity": "car_d",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 40}]}
      ]
    }
  ]
}
```

**Queue placement (forward lane):**
- Queue head at high s (near end of road, e.g. s=85)
- Each subsequent car: subtract vehicle_length(4.5m) + gap(2m) = 6.5m
- car_a=85, car_b=78.5, car_c=72
- Approaching car far behind: s=22 (50m gap from last queue car)

**Queue placement (backward lane):**
- Queue head at low s (near start of road)
- Each subsequent car: ADD 6.5m
- Approaching car at high s

### 3. head_on

Two vehicles on same two-way road, one drifts into oncoming lane.

```json
{
  "situation_id": 7,
  "pattern": "head_on",
  "scenario_name": "HeadOn_WrongWay",
  "sim_time": 10.0,
  "entities": [
    {"name": "correct", "type": "sedan"},
    {"name": "wrong_way", "type": "sedan"}
  ],
  "init_actions": [
    {"entity": "correct", "road": 26, "lane": -1, "s": 5.0, "speed_mph": 35},
    {"entity": "wrong_way", "road": 26, "lane": 1, "s": 52.0, "speed_mph": 25}
  ],
  "maneuvers": [
    {
      "entity": "correct",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 35}]}
      ]
    },
    {
      "entity": "wrong_way",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 25}]},
        {"name": "drift", "trigger_time": 0.5, "actions": [
          {"type": "lane_change", "target_lane": -1, "transition_time": 2.0}
        ]}
      ]
    }
  ]
}
```

**Placement math:**
- "correct" in lane -1 (forward, moves toward high s)
- "wrong_way" in lane 1 (backward, moves toward low s), drifts to lane -1 at t=0.5
- Both converge toward each other. Place so closing distance / combined speed = ~3s
- At 35mph(15.65) + 25mph(11.18) = 26.83m/s combined. For 3s: gap ~80m
- correct at s=5, wrong_way at s=52 → they'll meet near s≈50ish after drift

### 4. sideswipe

Two vehicles side-by-side in adjacent lanes, one changes into the other's lane.

```json
{
  "situation_id": 6,
  "pattern": "sideswipe",
  "scenario_name": "Sideswipe_BlindSpot",
  "sim_time": 10.0,
  "entities": [
    {"name": "changer", "type": "sedan"},
    {"name": "target", "type": "sedan"}
  ],
  "init_actions": [
    {"entity": "changer", "road": 33, "lane": 1, "s": 60, "speed_mph": 35},
    {"entity": "target", "road": 33, "lane": 2, "s": 60, "speed_mph": 35}
  ],
  "maneuvers": [
    {
      "entity": "target",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 35}]}
      ]
    },
    {
      "entity": "changer",
      "events": [
        {"name": "lane_change", "trigger_time": 1.0, "actions": [
          {"type": "lane_change", "target_lane": 2, "transition_time": 2.0}
        ]}
      ]
    }
  ]
}
```

**Key:** Same s position, same speed. Lane change creates the collision. Use multi-lane same-dir roads from reference.

### 5. pedestrian_crossing

Vehicle and pedestrian on same road, pedestrian dashes across into vehicle's lane.

```json
{
  "situation_id": 5,
  "pattern": "pedestrian_crossing",
  "scenario_name": "Pedestrian_Dash",
  "sim_time": 12.0,
  "entities": [
    {"name": "vehicle", "type": "sedan"},
    {"name": "ped", "type": "pedestrian"}
  ],
  "init_actions": [
    {"entity": "vehicle", "road": 39, "lane": -1, "s": 5, "speed_mph": 25},
    {"entity": "ped", "road": 39, "lane": 1, "s": 40, "speed_mph": 0}
  ],
  "maneuvers": [
    {
      "entity": "vehicle",
      "events": [
        {"name": "maintain", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 25}]}
      ]
    },
    {
      "entity": "ped",
      "events": [
        {"name": "dash", "trigger_time": 1.0, "actions": [
          {"type": "speed_smooth", "speed_mph": 4.5, "transition_time": 0.5},
          {"type": "lane_change", "target_lane": -1, "transition_time": 3.0}
        ]}
      ]
    }
  ]
}
```

**CRITICAL:** Put both actions (speed + lane_change) in ONE event so they run simultaneously! Separate events with overwrite priority cancel each other.

**Timing:** Vehicle at s=5 on lane -1 (forward), reaches s=40 in ~35m/11.18m/s = 3.1s. Ped starts dashing at t=1.0, takes ~3s to cross. Vehicle arrives when ped is mid-lane.

### 6. dooring

Cyclist rides into a stationary open door obstacle.

```json
{
  "situation_id": 8,
  "pattern": "dooring",
  "scenario_name": "Cyclist_Dooring",
  "sim_time": 12.0,
  "entities": [
    {"name": "cyclist", "type": "bicycle"},
    {"name": "parked_car", "type": "sedan"},
    {"name": "door", "type": "parked_car_door"}
  ],
  "init_actions": [
    {"entity": "cyclist", "road": 54, "lane": 1, "s": 70, "speed_mph": 15},
    {"entity": "parked_car", "road": 54, "lane": 2, "s": 45, "speed_mph": 0, "lane_type": "parking"},
    {"entity": "door", "road": 54, "lane": 1, "s": 45, "speed_mph": 0}
  ],
  "maneuvers": [
    {
      "entity": "cyclist",
      "events": [
        {"name": "ride", "trigger_time": 0, "actions": [{"type": "speed", "speed_mph": 15}]}
      ]
    }
  ]
}
```

**Key:** Road 54 is the primary road with parking. Cyclist in lane 1 (backward, travels toward s=0). Door obstacle at same s as parked car but in driving lane.

### 7. parking_backing

Two vehicles reverse out of parking into driving lane.

```json
{
  "situation_id": 4,
  "pattern": "parking_backing",
  "scenario_name": "Parking_Reverse_Collision",
  "sim_time": 10.0,
  "entities": [
    {"name": "car_a", "type": "sedan"},
    {"name": "car_b", "type": "sedan"}
  ],
  "init_actions": [
    {"entity": "car_a", "road": 54, "lane": 2, "s": 40, "speed_mph": 0, "lane_type": "parking"},
    {"entity": "car_b", "road": 54, "lane": 2, "s": 42, "speed_mph": 0, "lane_type": "parking"}
  ],
  "maneuvers": [
    {
      "entity": "car_a",
      "events": [
        {"name": "speed", "trigger_time": 1.0, "actions": [
          {"type": "speed_smooth", "speed_mph": 5, "transition_time": 0.5}
        ]},
        {"name": "reverse", "trigger_time": 1.0, "actions": [
          {"type": "lane_change", "target_lane": 1, "transition_time": 2.5}
        ]}
      ]
    },
    {
      "entity": "car_b",
      "events": [
        {"name": "speed", "trigger_time": 1.0, "actions": [
          {"type": "speed_smooth", "speed_mph": 7, "transition_time": 0.5}
        ]},
        {"name": "reverse", "trigger_time": 1.0, "actions": [
          {"type": "lane_change", "target_lane": 1, "transition_time": 2.5}
        ]}
      ]
    }
  ]
}
```

**Key:** Cars in parking lane 2, very close together (2m gap). Both do speed + lane_change to lane 1 simultaneously. Different speeds create convergence.

**Alternative for parking_backing with vehicle + pedestrian/cyclist:**
Place one entity in parking lane (backing out via speed + lane_change), the other entity traveling on the driving lane. The backing entity enters the driving lane as the other passes.

---

## Known Gotchas

1. **Multiple actions in ONE event run simultaneously.** Separate events with `overwrite` priority CANCEL each other! For pedestrian dash (speed + lane_change together), put BOTH actions in the same event.

2. **Lane direction matters.** Forward lanes (negative IDs like -1) travel s=0→length. Backward lanes (positive IDs like 1) travel length→0. Always check the reference tables.

3. **Keep 5m margin from road edges.** Don't place entities at s<5 or s>(road.length-5).

4. **Junction T-bone REQUIRES routes.** Without route assignments, vehicles won't cross paths. Always include `routes` array for junction_tbone.

5. **Entity names must be unique** and must match across `entities`, `init_actions`, `routes`, and `maneuvers`.

6. **Parked / stationary vehicles MUST use proper lane placement.** A vehicle with `speed_mph: 0` in a driving lane will sit in the middle of the road. Use one of these approaches:
   - **Best: Use a parking lane.** Roads 54 and 55 have parking lane 2. Set `"lane": 2, "lane_type": "parking"`.
   - **Alternative: Use the `offset` parameter** to push the vehicle toward the road edge. On a standard 3.5m driving lane, `"offset": 1.2` shifts the vehicle ~1.2m toward the curb (positive offset = toward the road edge for negative lane IDs, toward center for positive lane IDs). Example: `{"entity": "parked_truck", "road": 26, "lane": -1, "s": 50, "speed_mph": 0, "offset": 1.2}`.
   - **If the scenario needs a parked vehicle and no specific road is required**, prefer Road 54 with lane 2 (parking lane) — it's the most realistic placement.
   - **NEVER place a stationary vehicle (speed_mph=0) in a driving lane without an offset** — it will block the middle of the road unrealistically.

7. **Speed conversion:** 1 mph = 0.44704 m/s. Quick reference:
   - 10 mph = 4.5 m/s
   - 15 mph = 6.7 m/s
   - 20 mph = 8.9 m/s
   - 25 mph = 11.2 m/s
   - 30 mph = 13.4 m/s
   - 35 mph = 15.6 m/s
   - 40 mph = 17.9 m/s
   - 45 mph = 20.1 m/s
   - 50 mph = 22.4 m/s

7. **For rear_end with debris/obstacle:** Include debris as an entity with speed_mph=0 on the road. The lead vehicle can swerve (lane_change) and brake, while the follower maintains speed and hits the debris.

8. **For parking_backing with pedestrian/cyclist crossing:** Place the non-backing entity on the driving lane passing the parking area. The backing vehicle enters the driving lane as they pass.

---

## Retry Strategy (if validation fails)

1. **No collision detected for junction_tbone — MANDATORY TIMING FIX:**

   Vehicles miss because they arrive at the junction at different times. You MUST compute arrival times and adjust s values to synchronize them.

   **Arrival time formulas:**
   - Forward lane (neg id, e.g. -1): `arrival_time = (road_length - s) / speed_mps`
   - Backward lane (pos id, e.g. 1): `arrival_time = s / speed_mps`

   **Sync procedure:**
   1. Pick a target arrival time T (e.g. T = 4.0s)
   2. For each vehicle: set s so that arrival_time = T
      - Forward lane: `s = road_length - (T × speed_mps)`
      - Backward lane: `s = T × speed_mps`
   3. Clamp s to [5, road_length - 5]
   4. If clamping is required for both vehicles, scale T up or down

   **Example fix** (sedan 30mph on road 52 fwd, suv 45mph on road 44 bwd):
   - sedan 30mph = 13.41 m/s, suv 45mph = 20.12 m/s
   - Road 52 length = 100m, road 44 length = 70m
   - Max time for suv without going off road: T_max = 65 / 20.12 = 3.23s
   - sedan s at T=3.23s: s = 100 - (3.23 × 13.41) = 100 - 43.3 = **56.7** → use s=57
   - suv s at T=3.23s: s = 3.23 × 20.12 = 65.0 → use s=65
   - Result: sedan arrives in (100-57)/13.41 = 3.21s, suv in 65/20.12 = 3.23s ✓

   If T × speed_mps < 5 for a vehicle (would be off the road edge), increase T or reduce speed.

2. **No collision detected (other patterns):**
   - Move entities closer to the collision point
   - Adjust speeds ±5 mph
   - For pedestrian/sideswipe: verify the lateral action timing

3. **Entity off road error:** Check s is within [5, road.length-5]
4. **Lane type mismatch:** Verify lane_type matches (use "parking" for parking lanes)
5. **Route error:** Verify road→exit_road is a valid junction connection

## File Naming

Config: `generator/configs/situation_{id:03d}.json`
Output: `generator/output/cs{id:03d}_{scenario_name}.xosc`

## Validation Command

```bash
python -m generator.config_builder generator/configs/situation_{id:03d}.json --validate
```

Expected output on success:
```
Generated: generator/output/cs042_scenario_name.xosc
[PASS] Collision at t=X.XXs (entityA+entityB)
```
