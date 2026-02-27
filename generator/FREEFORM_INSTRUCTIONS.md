# Freeform Scenario Generation: Config Primitives Reference

You are generating JSON config files for crash scenarios. Each config is translated into an OpenSCENARIO (.xosc) file by `config_builder.py` and validated with esmini collision detection.

You are NOT constrained to any named pattern. Compose freely from the primitives below to create a scenario that produces a collision matching the given description.

## Config JSON Schema

```json
{
  "situation_id": 42,
  "pattern": "freeform",
  "scenario_name": "ScenarioName",
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

### Routes (for junction crossing)

Routes force vehicles through specific junction connecting roads. Required when you need two vehicles to cross paths at a junction.

```json
"routes": [
  {"entity": "name", "start_road": 52, "start_lane": -1, "start_s": 20,
   "exit_road": 19, "exit_lane": 1}
]
```

The `routes` array is optional — only include it when entities need to navigate through junctions.

---

## Building Blocks for Collision Scenarios

Think about what physical situation produces a collision, then compose it from these primitives:

**Converging paths:** Place two entities so their travel paths intersect. Consider:
- Same road, same lane, different speeds → one catches the other
- Same road, opposite lanes, one changes lane → lateral collision
- Different roads meeting at a junction → crossing collision (needs routes)
- Entity on sidewalk/parking steps into driving lane → pedestrian/cyclist hit

**Timing synchronization:** For entities to collide, they must arrive at the same point at the same time.
- Forward lane (neg id, e.g. -1): travels s=0→road_length. Distance to point = point_s - entity_s
- Backward lane (pos id, e.g. 1): travels road_length→0. Distance to point = entity_s - point_s
- arrival_time = distance / speed_mps
- Match arrival times within ~0.5s for reliable collision

**Speed conversion:** 1 mph = 0.44704 m/s. Quick reference:
- 10 mph = 4.5 m/s
- 15 mph = 6.7 m/s
- 20 mph = 8.9 m/s
- 25 mph = 11.2 m/s
- 30 mph = 13.4 m/s
- 35 mph = 15.6 m/s
- 40 mph = 17.9 m/s
- 45 mph = 20.1 m/s
- 50 mph = 22.4 m/s

---

## Critical Rules

1. **Multiple actions in ONE event run simultaneously.** Separate events with `overwrite` priority CANCEL each other! If you need speed + lane_change together, put BOTH actions in the same event.

2. **Lane direction matters.** Forward lanes (negative IDs like -1) travel s=0→length. Backward lanes (positive IDs like 1) travel length→0. Always check the reference tables.

3. **Keep 5m margin from road edges.** Don't place entities at s<5 or s>(road.length-5).

4. **Junction crossing REQUIRES routes.** Without route assignments, vehicles follow default paths and won't cross. Always include `routes` array when using junction roads.

5. **Entity names must be unique** and must match across `entities`, `init_actions`, `routes`, and `maneuvers`.

6. **Parked / stationary vehicles MUST use proper lane placement.** A vehicle with `speed_mph: 0` in a driving lane will sit in the middle of the road. Use one of these approaches:
   - **Best: Use a parking lane.** Roads 54 and 55 have parking lane 2. Set `"lane": 2, "lane_type": "parking"`.
   - **Alternative: Use the `offset` parameter** to push the vehicle toward the road edge. On a standard 3.5m driving lane, `"offset": 1.2` shifts the vehicle ~1.2m toward the curb.
   - **NEVER place a stationary vehicle (speed_mph=0) in a driving lane without an offset** — it will block the middle of the road unrealistically.

7. **For obstacles on road:** Include debris as an entity with speed_mph=0 and offset. Use `parked_car_door` for door obstacles.

---

## Retry Strategy (if validation fails)

1. **No collision detected — timing fix:**
   - Compute arrival times for each entity to the intended collision point
   - Adjust `s` values so both entities arrive within ~0.5s of each other
   - Forward lane: `s = collision_point - (T × speed_mps)` (or `road_length - (T × speed_mps)` if collision is at junction)
   - Backward lane: `s = collision_point + (T × speed_mps)` (or `T × speed_mps` if collision is at junction)

2. **Entities miss laterally:** Ensure they share the same lane at collision time (via lane_change or same-lane placement)

3. **Entity off road error:** Check s is within [5, road.length-5]

4. **Lane type mismatch:** Verify lane_type matches (use "parking" for parking lanes)

5. **Route error:** Verify road→exit_road is a valid junction connection
