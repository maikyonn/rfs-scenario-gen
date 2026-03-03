# Road Network Reference for Subagents

Richmond road network: 222 roads, 29 junctions. All positions use road/lane/s coordinates.

## Lane Direction Rules

- **Forward lanes** (lane_id < 0, e.g. -1): travel s=0 → s=length. Start at LOW s.
- **Backward lanes** (lane_id > 0, e.g. 1): travel s=length → s=0. Start at HIGH s.
- Keep 5m margin from road edges (don't place at s<5 or s>length-5).

## Timing Rules

For any pattern: `time = distance / speed`.
- Forward lane: `distance_to_target = target_s - start_s`
- Backward lane: `distance_to_target = start_s - target_s`
- For junction_tbone: both vehicles should take ~same time to reach junction.
  - Forward: `distance_to_junction = road.length - s`
  - Backward: `distance_to_junction = s`

---

## JUNCTION CROSSING PAIRS (for junction_tbone pattern)

### Validated Pairs (confirmed collision-producing)

**J323** (best, ~90° crossing):
- road_a=52, lane=-1 (fwd), length=100m → exit road 19, exit_lane=1
- road_b=44, lane=1 (bwd), length=70m → exit road 20, exit_lane=-1
- Place sedan: road 52, lane -1, s=15-85
- Place SUV: road 44, lane 1, s=10-65

**J199** (~67° crossing):
- road_a=28, lane=1 (bwd), length=68m → exit road 25, exit_lane=-1
- road_b=39, lane=-1 (fwd), length=65m → exit road 54, exit_lane=-1
- Place: road 28, lane 1, s=10-60; road 39, lane -1, s=5-58

**J103** — UNUSABLE: exit road 37 is only 1.78m long, vehicles cannot traverse.
- road_a=40, lane=1 (bwd), length=46m → exit road 37, exit_lane=-1
- road_b=24, lane=-1 (fwd), length=13m → exit road 12, exit_lane=-1
- DO NOT USE — use J323 or J199 instead.

### Additional Pairs (unvalidated, use with caution)

**J73** (~69° crossing, moderate roads):
- road_a=23, lane=1 (bwd), length=46m → exit road 2, exit_lane=-1
- road_b=17, lane=-1 (fwd), length=34m → exit road 22, exit_lane=-1

**J73** (~68° crossing):
- road_a=2, lane=1 (bwd), length=41m → exit road 17, exit_lane=-1
- road_b=17, lane=-1 (fwd), length=34m → exit road 23, exit_lane=-1

**J58** (~53-61° crossing, long roads):
- road_a=26, lane=-1 (fwd), length=173m → exit road 57
- road_b=57, lane=-1 (fwd), length=105m → exit road 26
- (Both forward, good road lengths for flexible placement)

**J199** (~67° crossing, alternate pair):
- road_a=28, lane=1 (bwd), length=68m → exit road 25, exit_lane=-1
- road_b=54, lane=1 (bwd), length=86m → exit road 39, exit_lane=-1

**J323** (~90° crossing, alternate pair):
- road_a=19, lane=1 (bwd), length=112m → exit road 52, exit_lane=-1
- road_b=44, lane=1 (bwd), length=70m → exit road 20, exit_lane=-1

**J394** (~58° crossing):
- road_a=44, lane=-1 (fwd), length=70m → exit road 36, exit_lane=-1
- road_b=36, lane=1 (bwd), length=38m → exit road 35, exit_lane=-1

**J407** (~62° crossing):
- road_a=23, lane=-1 (fwd), length=46m → exit road 24, exit_lane=-1
- road_b=41, lane=-1 (fwd), length=16m → exit road 24, exit_lane=-1

---

## PHYSICAL LANE WIDTHS (for multi-lane simulation)

Most roads have 1 lane per direction (~3.5m). A few roads are physically wide enough to simulate multi-lane driving using the `offset` parameter in LanePosition. Use `offset` to shift an entity laterally within a single lane_id.

| Road | Length | Lane width | How to use |
|------|--------|-----------|------------|
| **53** | 321m | fwd: 8.8m, bwd: 7.3m | Use `offset: ±1.5` for side-by-side (simulates 2-3 lanes) |
| **25** | 56m | fwd: 6.7m | Use `offset: ±1.2` for 2-lane simulation (fwd only) |
| **33** | 81m | 2 actual bwd lanes (1,2) | True multi-lane — use for sideswipe, no offset needed |
| **11** | 24m | 2 fwd lanes (-1,-2) | True multi-lane but very short |
| **56** | 14m | 2 fwd, 1 bwd | True multi-lane but tiny |

**When the crash description says "multi-lane" or "2+ lanes":**
1. Prefer road 53 (longest, widest) or road 25 for straight-road scenarios
2. Place vehicles at different `offset` values within the same lane to simulate side-by-side positioning
3. For sideswipe on a genuinely multi-lane road, use road 33 (lanes 1,2 backward)

**Example — two vehicles side-by-side on road 53:**
```json
{"entity": "sedan", "road": 53, "lane": -1, "s": 50, "offset": -1.5, "speed_mph": 30}
{"entity": "suv", "road": 53, "lane": -1, "s": 50, "offset": 1.5, "speed_mph": 30}
```

---

## LONG DRIVING ROADS (for rear_end, pedestrian_crossing, head_on)

| Road | Length | Fwd lanes | Bwd lanes | Notes |
|------|--------|-----------|-----------|-------|
| 53 | 321m | -1 | 1 | Longest road, great for rear-end queues |
| 26 | 173m | -1 | 1 | Two-way, good for head-on |
| 46 | 151m | -1 | 1 | WARNING: only 1 driving lane per dir (not 3) |
| 19 | 112m | -1 | 1 | Two-way |
| 9 | 108m | -1 | 1 | Two-way |
| 57 | 105m | -1 | 1 | Two-way |
| 52 | 100m | -1 | 1 | Two-way |
| 54 | 85m | -1 | 1 | Has parking lane 2 |
| 33 | 81m | — | 2,1 | One-way backward, 2 lanes |
| 44 | 70m | -1 | 1 | Two-way |
| 35 | 69m | -1 | 1 | Two-way |
| 28 | 68m | -1 | 1 | Two-way |
| 39 | 65m | -1 | 1 | Has sidewalk lane 3 |
| 13 | 61m | -1 | 1 | Two-way |
| 25 | 56m | -1 | — | One-way forward only |
| 38 | 48m | -1 | 1 | Has sidewalk lane 3 |
| 40 | 46m | -1 | 1 | Two-way |

---

## TWO-WAY ROADS (for head_on pattern)

Any road above with BOTH fwd and bwd driving lanes. Best options:
- Road 53 (321m), Road 26 (173m), Road 46 (151m), Road 19 (112m)
- For head_on: one vehicle in fwd lane (-1), other in bwd lane (1), drift via lane_change

---

## MULTI-LANE SAME-DIR ROADS (for sideswipe pattern)

| Road | Length | Same-dir lanes | Direction |
|------|--------|---------------|-----------|
| 46 | 151m | WARNING: only 1 driving lane per dir despite xodr listing | NOT usable for sideswipe |
| 33 | 81m | 2,1 (bwd) | Backward only |
| 3 | 44m | 1 (bwd, two instances) | Backward only |
| 0 | 41m | 2,1 (bwd) | Backward only |

For sideswipe: place two vehicles side-by-side (same s), one does lane_change.

---

## PARKING + DRIVING ROADS (for parking_backing, dooring, AND any scenario with parked vehicles)

**IMPORTANT: Any stationary/parked vehicle MUST be placed in a parking lane or use the `offset` parameter. Never place speed_mph=0 vehicles in a driving lane without offset — they end up blocking the middle of the road.**

**Road 54** (85m) — PRIMARY parking road:
- Lane 2: parking (undirected, 4.51m wide) ← **USE THIS for parked vehicles**
- Lane 1: driving, backward (3.5m wide)
- Lane -1: driving, forward (3.5m wide)
- For dooring: place cyclist in lane 1 (bwd), door obstacle in lane 1, parked car in lane 2
- For parking_backing: place cars in lane 2 (parking), lane_change to lane 1
- For any "parked vehicle" scenario: use `"lane": 2, "lane_type": "parking", "speed_mph": 0`

**Road 55** (12m) — Very short, backup only:
- Lane 2: parking, Lane 1: driving (bwd), Lane -1: driving (fwd)

**Other roads (no parking lane):** Use `"offset": 1.2` to push vehicle to road edge. Example:
```json
{"entity": "parked_truck", "road": 26, "lane": -1, "s": 50, "speed_mph": 0, "offset": 1.2}
```

---

## SIDEWALK ROADS (for pedestrian_crossing pattern)

| Road | Length | Sidewalk | Driving lanes |
|------|--------|----------|---------------|
| 39 | 65m | lane 3 | lane 1 (bwd), lane -1 (fwd) |
| 38 | 48m | lane 3 | lane 1 (bwd), lane -1 (fwd) | UNRELIABLE for ped crossing, prefer road 39 |
| 3 | 44m | lane 2 | lane 1 (bwd) |

For pedestrian: place ped on driving lane, use speed+lane_change to cross into vehicle's lane.

---

## Entity Types

| Type | Factory | Notes |
|------|---------|-------|
| sedan | sedan() | Standard car, length=4.5m |
| suv | suv() | Larger car, length=4.9m |
| pickup | pickup() | Truck, length=5.4m |
| motorcycle | motorcycle() | Motorbike, length=2.2m |
| bicycle | bicycle() | Cyclist, length=1.8m |
| pedestrian | pedestrian() | Person, model=EPTa |
| debris | road_debris() | Stationary obstacle |
| parked_car_door | parked_car_door() | Open door obstacle |

---

## Pattern-Specific Placement Tips

### junction_tbone
- REQUIRES `routes` in config to force junction path
- Both vehicles must be on roads that connect to the same junction
- Use timing rules to synchronize arrival (both reach junction at ~same time)

### rear_end
- All vehicles on same road, same lane
- Queue vehicles stationary (speed_mph=0), approaching vehicle has speed
- Forward lane: queue at HIGH s, approach at LOW s
- Backward lane: queue at LOW s, approach at HIGH s
- Gap between queued vehicles: ~6.5m (vehicle_length + 2m gap)

### head_on
- Both vehicles on same road, opposite lanes
- Vehicle A in forward lane (-1), Vehicle B in backward lane (1)
- Vehicle B drifts into lane -1 via lane_change at t=0.5s
- Place so they converge: dist_a + dist_b = initial_gap

### sideswipe
- Both vehicles on same road, adjacent same-direction lanes
- Place at same s position, same speed
- One vehicle does lane_change to the other's lane at t=1.0s

### pedestrian_crossing
- Vehicle on driving lane, pedestrian on adjacent/opposite lane
- Pedestrian uses speed_smooth + lane_change to dart across
- Time so vehicle reaches pedestrian's crossing point during crossing

### dooring
- Cyclist on driving lane (moving), parked car in parking lane, door obstacle in driving lane at same s
- Cyclist approaches door from upstream (backward lane: higher s; forward lane: lower s)

### parking_backing
- Both vehicles in parking lane (lane_type="parking"), stationary
- At trigger_time, both accelerate + lane_change to driving lane
- Place vehicles 2-3m apart in s for guaranteed convergence
