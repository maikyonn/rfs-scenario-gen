#!/usr/bin/env python3
"""Analyze all junctions to find connecting road pairs whose paths cross.

For each junction, examines all pairs of connecting roads and checks if their
geometric paths intersect. Outputs junction_crossing_pairs.json with the
crossing pairs database for use by the config builder and subagents.

Usage:
    python -m generator.compute_crossing_pairs
    python -m generator.compute_crossing_pairs --validate
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.road_network_db import RoadNetworkDB


# Known validated pairs (confirmed with geometry analysis + esmini testing)
VALIDATED_PAIRS = {
    (323, 52, 19, 44, 20),
    (199, 28, 25, 39, 54),
    (103, 24, 12, 40, 37),
}


def _line_segment_intersection(p1, p2, p3, p4):
    """Check if line segment p1-p2 intersects with p3-p4.

    Returns (True, (x, y)) if they intersect, (False, None) otherwise.
    Uses parametric intersection with t,u in [0,1].
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return False, None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return True, (ix, iy)

    return False, None


def _crossing_angle(p1, p2, p3, p4):
    """Compute crossing angle in degrees between two line segments."""
    dx1, dy1 = p2[0] - p1[0], p2[1] - p1[1]
    dx2, dy2 = p4[0] - p3[0], p4[1] - p3[1]

    len1 = math.sqrt(dx1**2 + dy1**2)
    len2 = math.sqrt(dx2**2 + dy2**2)
    if len1 < 1e-10 or len2 < 1e-10:
        return 0.0

    cos_angle = (dx1 * dx2 + dy1 * dy2) / (len1 * len2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    angle = math.degrees(math.acos(abs(cos_angle)))

    # Normalize to acute crossing angle
    if angle > 90:
        angle = 180 - angle
    return angle


def _find_incoming_road(db, junction_id, connecting_road_id):
    """Find the incoming road that leads to a connecting road at a junction."""
    junc = db.junction(junction_id)
    for conn in junc.connections:
        if conn["connecting_road"] == connecting_road_id:
            return conn["incoming_road"], conn["lane_links"], conn["contact_point"]
    return None, None, None


def _find_exit_road(db, connecting_road_id, contact_point):
    """Find the exit road on the other end of a connecting road.

    If contact_point is "start", the connecting road enters at s=0,
    so the exit is via the successor link.
    If contact_point is "end", exit is via predecessor link.
    """
    conn_road = db.road(connecting_road_id)
    if contact_point == "start":
        # Enters at start, exits at end → successor
        if conn_road.successor_road is not None:
            return conn_road.successor_road
        if conn_road.successor_junction is not None:
            return None  # Chain junction, skip
    elif contact_point == "end":
        # Enters at end, exits at start → predecessor
        if conn_road.predecessor_road is not None:
            return conn_road.predecessor_road
        if conn_road.predecessor_junction is not None:
            return None
    return None


def compute_crossing_pairs(db):
    """Analyze all junctions and find crossing pairs."""
    pairs = []

    for junc_id in db.all_junction_ids():
        junc = db.junction(junc_id)
        connecting_roads = []

        # Collect all connecting roads for this junction
        for conn in junc.connections:
            cr_id = conn["connecting_road"]
            cr = db.road(cr_id)
            if cr.junction_id != junc_id:
                continue

            incoming_road_id = conn["incoming_road"]
            contact_point = conn["contact_point"]
            exit_road = _find_exit_road(db, cr_id, contact_point)
            lane_links = conn["lane_links"]

            # Get the driving lane link (skip shoulders, sidewalks)
            incoming_lane = None
            exit_lane = None
            for ll in lane_links:
                inc_road = db.road(incoming_road_id)
                for l in inc_road.lanes:
                    lid = l["lane_id"] if isinstance(l, dict) else l.lane_id
                    ltype = l["type"] if isinstance(l, dict) else l.type
                    if lid == ll["from"] and ltype == "driving":
                        incoming_lane = ll["from"]
                        # The exit lane is the "to" lane on the connecting road,
                        # but we need the lane on the exit road, not the connecting road
                        break

            connecting_roads.append({
                "connecting_road_id": cr_id,
                "incoming_road": incoming_road_id,
                "incoming_lane": incoming_lane,
                "exit_road": exit_road,
                "contact_point": contact_point,
                "start_xy": cr.start_xy,
                "end_xy": cr.end_xy,
            })

        # Check all pairs for crossing
        for i in range(len(connecting_roads)):
            for j in range(i + 1, len(connecting_roads)):
                cr_a = connecting_roads[i]
                cr_b = connecting_roads[j]

                # Skip if same incoming road
                if cr_a["incoming_road"] == cr_b["incoming_road"]:
                    continue

                # Skip if either has no exit road
                if cr_a["exit_road"] is None or cr_b["exit_road"] is None:
                    continue

                # Check geometric intersection
                crosses, point = _line_segment_intersection(
                    cr_a["start_xy"], cr_a["end_xy"],
                    cr_b["start_xy"], cr_b["end_xy"],
                )

                if crosses:
                    angle = _crossing_angle(
                        cr_a["start_xy"], cr_a["end_xy"],
                        cr_b["start_xy"], cr_b["end_xy"],
                    )

                    # Only care about meaningful crossings (>20 degrees)
                    if angle < 20:
                        continue

                    # Determine lanes and directions
                    inc_a = db.road(cr_a["incoming_road"])
                    inc_b = db.road(cr_b["incoming_road"])
                    exit_a = db.road(cr_a["exit_road"])
                    exit_b = db.road(cr_b["exit_road"])

                    # Find driving lanes that travel toward this junction
                    lane_a = _find_lane_toward_junction(db, cr_a["incoming_road"], junc_id)
                    lane_b = _find_lane_toward_junction(db, cr_b["incoming_road"], junc_id)

                    if lane_a is None or lane_b is None:
                        continue

                    # Find exit lanes
                    exit_lane_a = _find_any_driving_lane(db, cr_a["exit_road"])
                    exit_lane_b = _find_any_driving_lane(db, cr_b["exit_road"])

                    if exit_lane_a is None or exit_lane_b is None:
                        continue

                    # Check if this is a known validated pair
                    validated = _is_validated(
                        junc_id,
                        cr_a["incoming_road"], cr_a["exit_road"],
                        cr_b["incoming_road"], cr_b["exit_road"],
                    )

                    pair = {
                        "junction_id": junc_id,
                        "road_a": cr_a["incoming_road"],
                        "lane_a": lane_a,
                        "road_a_length": round(inc_a.length, 1),
                        "exit_a": cr_a["exit_road"],
                        "exit_lane_a": exit_lane_a,
                        "road_b": cr_b["incoming_road"],
                        "lane_b": lane_b,
                        "road_b_length": round(inc_b.length, 1),
                        "exit_b": cr_b["exit_road"],
                        "exit_lane_b": exit_lane_b,
                        "crossing_point": [round(point[0], 1), round(point[1], 1)],
                        "crossing_angle_deg": round(angle, 1),
                        "validated": validated,
                    }
                    pairs.append(pair)

    return pairs


def _find_lane_toward_junction(db, road_id, junction_id):
    """Find a driving lane on road_id that travels toward junction_id."""
    road = db.road(road_id)
    for l in road.lanes:
        lid = l["lane_id"] if isinstance(l, dict) else l.lane_id
        ltype = l["type"] if isinstance(l, dict) else l.type
        ldir = l["travel_dir"] if isinstance(l, dict) else l.travel_dir

        if ltype != "driving":
            continue

        # Forward lanes go toward successor, backward lanes toward predecessor
        if ldir == "forward" and road.successor_junction == junction_id:
            return lid
        if ldir == "backward" and road.predecessor_junction == junction_id:
            return lid

    return None


def _find_any_driving_lane(db, road_id):
    """Find any driving lane on a road (for exit road lane identification)."""
    road = db.road(road_id)
    for l in road.lanes:
        lid = l["lane_id"] if isinstance(l, dict) else l.lane_id
        ltype = l["type"] if isinstance(l, dict) else l.type
        if ltype == "driving":
            return lid
    return None


def _is_validated(junction_id, road_a, exit_a, road_b, exit_b):
    """Check if this pair matches one of the known validated pairs."""
    for vj, vra, vea, vrb, veb in VALIDATED_PAIRS:
        if junction_id != vj:
            continue
        # Check both orderings
        if (road_a == vra and exit_a == vea and road_b == vrb and exit_b == veb):
            return True
        if (road_a == vrb and exit_a == veb and road_b == vra and exit_b == vea):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Compute junction crossing pairs for the road network"
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run esmini validation on new (unvalidated) crossing pairs",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    xodr_path = os.path.join(
        os.path.dirname(base_dir), "road_network", "Richmond_entire_scene.xodr"
    )
    cache_path = os.path.join(base_dir, "road_network_cache.json")
    output_path = os.path.join(base_dir, "junction_crossing_pairs.json")

    print("Loading road network...")
    db = RoadNetworkDB(xodr_path, cache_path)

    print(f"Analyzing {len(db.all_junction_ids())} junctions...")
    pairs = compute_crossing_pairs(db)

    validated_count = sum(1 for p in pairs if p["validated"])
    new_count = len(pairs) - validated_count
    print(f"Found {len(pairs)} crossing pairs ({validated_count} validated, {new_count} new)")

    for p in pairs:
        status = "VALIDATED" if p["validated"] else "NEW"
        print(
            f"  [{status}] J{p['junction_id']}: "
            f"road {p['road_a']}(lane {p['lane_a']})→{p['exit_a']} "
            f"crosses road {p['road_b']}(lane {p['lane_b']})→{p['exit_b']} "
            f"at {p['crossing_angle_deg']}° near ({p['crossing_point'][0]}, {p['crossing_point'][1]})"
        )

    if args.validate and new_count > 0:
        print("\n── Validating new crossing pairs with esmini ──\n")
        _validate_new_pairs(db, [p for p in pairs if not p["validated"]])

    # Save output
    output_data = {
        "description": "Junction crossing pairs for collision scenario generation",
        "total_junctions": len(db.all_junction_ids()),
        "total_crossing_pairs": len(pairs),
        "pairs": pairs,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSaved to {output_path}")


def _validate_new_pairs(db, new_pairs):
    """Run a quick esmini test for each new crossing pair to verify collisions work."""
    from generator.config_builder import ConfigBuilder
    from generator.validate import validate_scenario
    import tempfile

    for pair in new_pairs:
        road_a = db.road(pair["road_a"])
        road_b = db.road(pair["road_b"])

        # Place vehicles at reasonable positions
        lane_a_info = db.lane_info(pair["road_a"], pair["lane_a"])
        lane_b_info = db.lane_info(pair["road_b"], pair["lane_b"])

        # Start position: ~60% of road length for forward, ~40% for backward
        if lane_a_info.travel_dir == "forward":
            s_a = max(5, road_a.length * 0.2)
        else:
            s_a = min(road_a.length - 5, road_a.length * 0.8)

        if lane_b_info.travel_dir == "forward":
            s_b = max(5, road_b.length * 0.2)
        else:
            s_b = min(road_b.length - 5, road_b.length * 0.8)

        config = {
            "situation_id": 0,
            "pattern": "junction_tbone",
            "scenario_name": f"test_j{pair['junction_id']}",
            "sim_time": 15.0,
            "entities": [
                {"name": "car_a", "type": "sedan"},
                {"name": "car_b", "type": "sedan"},
            ],
            "init_actions": [
                {"entity": "car_a", "road": pair["road_a"], "lane": pair["lane_a"],
                 "s": round(s_a, 1), "speed_mph": 30},
                {"entity": "car_b", "road": pair["road_b"], "lane": pair["lane_b"],
                 "s": round(s_b, 1), "speed_mph": 30},
            ],
            "routes": [
                {"entity": "car_a", "start_road": pair["road_a"], "start_lane": pair["lane_a"],
                 "start_s": round(s_a, 1), "exit_road": pair["exit_a"], "exit_lane": pair["exit_lane_a"]},
                {"entity": "car_b", "start_road": pair["road_b"], "start_lane": pair["lane_b"],
                 "start_s": round(s_b, 1), "exit_road": pair["exit_b"], "exit_lane": pair["exit_lane_b"]},
            ],
            "maneuvers": [
                {"entity": "car_a", "events": [
                    {"name": "maintain", "trigger_time": 0,
                     "actions": [{"type": "speed", "speed_mph": 30}]}
                ]},
                {"entity": "car_b", "events": [
                    {"name": "maintain", "trigger_time": 0,
                     "actions": [{"type": "speed", "speed_mph": 30}]}
                ]},
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                builder = ConfigBuilder(config)
                osc = builder.build()
                xosc_path = os.path.join(tmpdir, "test.xosc")
                osc.write_xml(xosc_path)

                result = validate_scenario(xosc_path, sim_time=15.0)
                if result.collision_detected:
                    print(f"  [PASS] J{pair['junction_id']}: collision at t={result.first_collision_time:.2f}s")
                    pair["validated"] = True
                else:
                    print(f"  [FAIL] J{pair['junction_id']}: no collision - may need timing adjustment")
            except Exception as e:
                print(f"  [ERROR] J{pair['junction_id']}: {e}")


if __name__ == "__main__":
    main()
