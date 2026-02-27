"""Physics-based placement calculations for collision scenarios."""

from dataclasses import dataclass
from generator.road_network_db import RoadNetworkDB


@dataclass
class PlacementResult:
    road_id: int
    lane_id: int
    s: float
    speed_mps: float
    distance_to_junction: float
    travel_time: float


@dataclass
class JunctionArrivalPlan:
    entity_a: PlacementResult
    entity_b: PlacementResult
    junction_id: int
    arrival_time: float  # expected time for entity_a to reach junction


def distance_to_junction(
    db: RoadNetworkDB,
    road_id: int,
    lane_id: int,
    start_s: float,
    junction_id: int,
) -> float:
    """Compute distance from start_s to the junction end of the road.

    Forward lane (s increases toward successor): distance = road.length - start_s
    Backward lane (s decreases toward predecessor): distance = start_s
    """
    road = db.road(road_id)
    lane = db.lane_info(road_id, lane_id)

    junction_s = db.junction_end_s(road_id, junction_id)

    if lane.travel_dir == "forward":
        if road.successor_junction != junction_id:
            raise ValueError(
                f"Road {road_id} lane {lane_id} (forward) doesn't lead to junction {junction_id}"
            )
        dist = road.length - start_s
    elif lane.travel_dir == "backward":
        if road.predecessor_junction != junction_id:
            raise ValueError(
                f"Road {road_id} lane {lane_id} (backward) doesn't lead to junction {junction_id}"
            )
        dist = start_s  # backward lane goes toward s=0
    else:
        raise ValueError(
            f"Road {road_id} lane {lane_id} is undirected — cannot compute distance"
        )

    if dist < 0:
        raise ValueError(
            f"Negative distance {dist:.1f}m — start_s={start_s:.1f} is past the junction end"
        )
    return dist


def sync_junction_arrival(
    db: RoadNetworkDB,
    road_a: int,
    lane_a: int,
    s_a: float,
    speed_a: float,
    road_b: int,
    lane_b: int,
    speed_b: float,
    junction_id: int,
    arrival_offset: float = 0.0,
) -> JunctionArrivalPlan:
    """Compute start position s_b so both vehicles arrive at junction simultaneously.

    Entity A is placed at s_a with speed_a.
    Entity B's position s_b is computed so it arrives at the junction at the same
    time as entity A (plus arrival_offset seconds).

    arrival_offset > 0 means B arrives after A.
    arrival_offset < 0 means B arrives before A.
    """
    dist_a = distance_to_junction(db, road_a, lane_a, s_a, junction_id)
    time_a = dist_a / speed_a if speed_a > 0 else float("inf")

    time_b = time_a + arrival_offset
    if time_b <= 0:
        raise ValueError(
            f"arrival_offset {arrival_offset:.2f}s makes entity B travel time negative "
            f"(time_a={time_a:.2f}s)"
        )

    dist_b = speed_b * time_b
    road_b_info = db.road(road_b)
    lane_b_info = db.lane_info(road_b, lane_b)

    # Compute s_b from distance to junction
    if lane_b_info.travel_dir == "forward":
        # Forward: distance = road.length - s_b, so s_b = road.length - dist_b
        s_b = road_b_info.length - dist_b
    elif lane_b_info.travel_dir == "backward":
        # Backward: distance = s_b, so s_b = dist_b
        s_b = dist_b
    else:
        raise ValueError(
            f"Road {road_b} lane {lane_b} is undirected — cannot place for arrival"
        )

    # Validate s_b is on the road
    if s_b < 0 or s_b > road_b_info.length:
        raise ValueError(
            f"Computed s_b={s_b:.1f}m is off road {road_b} (length={road_b_info.length:.1f}m). "
            f"Entity B needs {dist_b:.1f}m at {speed_b:.1f}m/s over {time_b:.2f}s, "
            f"but road is only {road_b_info.length:.1f}m long. "
            f"Try reducing speed_b or adjusting arrival_offset."
        )

    placement_a = PlacementResult(
        road_id=road_a, lane_id=lane_a, s=s_a,
        speed_mps=speed_a, distance_to_junction=dist_a, travel_time=time_a,
    )
    placement_b = PlacementResult(
        road_id=road_b, lane_id=lane_b, s=s_b,
        speed_mps=speed_b, distance_to_junction=dist_b, travel_time=time_b,
    )

    return JunctionArrivalPlan(
        entity_a=placement_a,
        entity_b=placement_b,
        junction_id=junction_id,
        arrival_time=time_a,
    )


def rear_end_positions(
    db: RoadNetworkDB,
    road_id: int,
    lane_id: int,
    queue_head_s: float,
    num_queued: int,
    gap_m: float,
    vehicle_length_m: float,
    approach_distance: float,
    approach_speed: float,
) -> tuple[list[PlacementResult], PlacementResult]:
    """Compute positions for a rear-end chain collision.

    Returns (queue_placements, approach_placement) where queue vehicles are
    stationary and the approach vehicle is moving.

    queue_head_s: s-position of the front vehicle in the queue
    num_queued: number of stationary vehicles
    gap_m: gap between queued vehicles (bumper to bumper)
    vehicle_length_m: length of each vehicle
    approach_distance: how far behind the last queued vehicle the approach starts
    approach_speed: speed of the approaching vehicle in m/s
    """
    lane = db.lane_info(road_id, lane_id)
    road = db.road(road_id)

    queue = []
    for i in range(num_queued):
        if lane.travel_dir == "forward":
            s = queue_head_s - i * (vehicle_length_m + gap_m)
        else:  # backward
            s = queue_head_s + i * (vehicle_length_m + gap_m)

        if s < 0 or s > road.length:
            raise ValueError(
                f"Queue vehicle {i} at s={s:.1f} is off road {road_id} "
                f"(length={road.length:.1f}m)"
            )

        queue.append(PlacementResult(
            road_id=road_id, lane_id=lane_id, s=s,
            speed_mps=0, distance_to_junction=0, travel_time=0,
        ))

    # Approach vehicle placed behind the last queued vehicle
    last_queue_s = queue[-1].s if queue else queue_head_s
    if lane.travel_dir == "forward":
        approach_s = last_queue_s - approach_distance
    else:
        approach_s = last_queue_s + approach_distance

    if approach_s < 0 or approach_s > road.length:
        raise ValueError(
            f"Approach vehicle at s={approach_s:.1f} is off road {road_id} "
            f"(length={road.length:.1f}m)"
        )

    approach = PlacementResult(
        road_id=road_id, lane_id=lane_id, s=approach_s,
        speed_mps=approach_speed,
        distance_to_junction=approach_distance,
        travel_time=approach_distance / approach_speed if approach_speed > 0 else 0,
    )

    return queue, approach


def head_on_positions(
    db: RoadNetworkDB,
    road_id: int,
    speed_a: float,
    speed_b: float,
    desired_collision_time: float,
) -> tuple[PlacementResult, PlacementResult]:
    """Compute positions for a head-on collision on a two-way road.

    Finds a forward lane and a backward lane on the same road, then places
    vehicles to converge at desired_collision_time seconds.
    """
    road = db.road(road_id)
    driving = db.driving_lanes(road_id)

    forward_lane = None
    backward_lane = None
    for l in driving:
        if l.travel_dir == "forward" and forward_lane is None:
            forward_lane = l
        elif l.travel_dir == "backward" and backward_lane is None:
            backward_lane = l

    if forward_lane is None or backward_lane is None:
        raise ValueError(
            f"Road {road_id} doesn't have both forward and backward driving lanes. "
            f"Found: {[f'{l.lane_id}:{l.travel_dir}' for l in driving]}"
        )

    # Distance each vehicle covers in desired_collision_time
    dist_a = speed_a * desired_collision_time
    dist_b = speed_b * desired_collision_time
    total_gap = dist_a + dist_b

    if total_gap > road.length:
        raise ValueError(
            f"Vehicles need {total_gap:.1f}m total gap but road {road_id} is only "
            f"{road.length:.1f}m. Reduce speeds or collision time."
        )

    # Place collision point at a reasonable spot (proportional to speeds)
    # Forward lane: vehicle starts at low s, moves toward high s
    # Backward lane: vehicle starts at high s, moves toward low s
    collision_s = dist_a  # where forward vehicle ends up
    s_a = collision_s - dist_a  # forward vehicle start (near s=0)
    s_b = collision_s + dist_b  # backward vehicle start (higher s)

    # Add small margin from road edges
    margin = 5.0
    if s_a < margin:
        shift = margin - s_a
        s_a += shift
        s_b += shift
    if s_b > road.length - margin:
        shift = s_b - (road.length - margin)
        s_a -= shift
        s_b -= shift

    # Clamp and validate
    if s_a < 0 or s_a > road.length or s_b < 0 or s_b > road.length:
        raise ValueError(
            f"Cannot place head-on vehicles on road {road_id} "
            f"(s_a={s_a:.1f}, s_b={s_b:.1f}, road_length={road.length:.1f})"
        )

    placement_a = PlacementResult(
        road_id=road_id, lane_id=forward_lane.lane_id, s=s_a,
        speed_mps=speed_a, distance_to_junction=dist_a,
        travel_time=desired_collision_time,
    )
    placement_b = PlacementResult(
        road_id=road_id, lane_id=backward_lane.lane_id, s=s_b,
        speed_mps=speed_b, distance_to_junction=dist_b,
        travel_time=desired_collision_time,
    )

    return placement_a, placement_b
