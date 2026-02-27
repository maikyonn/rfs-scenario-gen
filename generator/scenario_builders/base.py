"""Base class for all scenario builders."""

import os
from abc import ABC, abstractmethod
from scenariogeneration import xosc

from generator.road_network_db import RoadNetworkDB
from generator.timing import (
    sync_junction_arrival,
    rear_end_positions,
    head_on_positions,
    PlacementResult,
    JunctionArrivalPlan,
)

# Path from generator/output/*.xosc -> road_network/*.xodr
XODR_RELATIVE = "../../road_network/Richmond_entire_scene.xodr"

# Absolute path to the .xodr file (for RoadNetworkDB)
_XODR_ABS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "road_network", "Richmond_entire_scene.xodr",
)
_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "road_network_cache.json",
)


def mph_to_mps(mph: float) -> float:
    """Convert miles-per-hour to metres-per-second."""
    return mph * 0.44704


# Lazy-loaded shared DB instance
_db_instance: RoadNetworkDB | None = None


class BaseScenarioBuilder(ABC):
    """Shared helpers for all 10 scenario builders."""

    scenario_id: int = 0
    scenario_name: str = ""

    # ── Road network DB ───────────────────────────────────────────────────

    @classmethod
    def _db(cls) -> RoadNetworkDB:
        """Lazy-loaded, shared road network database."""
        global _db_instance
        if _db_instance is None:
            _db_instance = RoadNetworkDB(_XODR_ABS, _CACHE_PATH)
        return _db_instance

    # ── Road network ─────────────────────────────────────────────────────

    def _road_network(self) -> xosc.RoadNetwork:
        return xosc.RoadNetwork(roadfile=XODR_RELATIVE)

    # ── Position helpers ─────────────────────────────────────────────────

    @staticmethod
    def _lane_pos(road_id, s, lane_id, offset=0.0):
        """Return a LanePosition on the given road/lane."""
        return xosc.LanePosition(s, offset, str(lane_id), str(road_id))

    @staticmethod
    def _world_pos(x, y, z=0.0, h=0.0):
        """Return a WorldPosition."""
        return xosc.WorldPosition(x, y, z, h)

    @staticmethod
    def _assign_route(start_road, start_lane, start_s, exit_road, exit_lane, exit_s=10.0):
        """Create an AssignRouteAction that forces a vehicle through a specific junction path.

        Waypoints: start position → exit position. esmini picks the connecting road
        that links these two roads through the intervening junction.
        """
        route = xosc.Route("route")
        route.add_waypoint(
            xosc.LanePosition(start_s, 0, str(start_lane), str(start_road)),
            xosc.RouteStrategy.shortest,
        )
        route.add_waypoint(
            xosc.LanePosition(exit_s, 0, str(exit_lane), str(exit_road)),
            xosc.RouteStrategy.shortest,
        )
        return xosc.AssignRouteAction(route)

    # ── Validated position helpers ────────────────────────────────────────

    @classmethod
    def _validated_lane_pos(cls, road_id, s, lane_id, expected_type="driving", offset=0.0):
        """Like _lane_pos but validates lane exists, type matches, s is in range."""
        db = cls._db()
        lane = db.lane_info(road_id, lane_id)
        road = db.road(road_id)

        if lane.type != expected_type:
            raise ValueError(
                f"Road {road_id} lane {lane_id} is '{lane.type}', expected '{expected_type}'"
            )
        if s < 0 or s > road.length:
            raise ValueError(
                f"s={s:.1f} is out of range for road {road_id} (length={road.length:.1f}m)"
            )

        return xosc.LanePosition(s, offset, str(lane_id), str(road_id))

    # ── Framework placement helpers ───────────────────────────────────────

    @classmethod
    def _place_for_junction_collision(
        cls,
        init: xosc.Init,
        entity_a: str,
        road_a: int,
        lane_a: int,
        s_a: float,
        speed_a_mph: float,
        entity_b: str,
        road_b: int,
        lane_b: int,
        speed_b_mph: float,
        junction_id: int,
        arrival_offset: float = 0.0,
    ) -> JunctionArrivalPlan:
        """Place two vehicles to collide at a junction.

        Validates that both lanes travel toward the junction, computes entity_b's
        start position via sync_junction_arrival, and adds teleport + speed actions.
        """
        db = cls._db()
        speed_a = mph_to_mps(speed_a_mph)
        speed_b = mph_to_mps(speed_b_mph)

        # Validate lanes travel toward junction
        db.travel_direction_toward_junction(road_a, lane_a, junction_id)
        db.travel_direction_toward_junction(road_b, lane_b, junction_id)

        plan = sync_junction_arrival(
            db,
            road_a=road_a, lane_a=lane_a, s_a=s_a, speed_a=speed_a,
            road_b=road_b, lane_b=lane_b, speed_b=speed_b,
            junction_id=junction_id,
            arrival_offset=arrival_offset,
        )

        # Add init actions for both entities
        init.add_init_action(
            entity_a,
            xosc.TeleportAction(xosc.LanePosition(
                plan.entity_a.s, 0, str(lane_a), str(road_a)
            )),
        )
        init.add_init_action(entity_a, cls._speed_action(speed_a))

        init.add_init_action(
            entity_b,
            xosc.TeleportAction(xosc.LanePosition(
                plan.entity_b.s, 0, str(lane_b), str(road_b)
            )),
        )
        init.add_init_action(entity_b, cls._speed_action(speed_b))

        return plan

    @classmethod
    def _place_rear_end_queue(
        cls,
        init: xosc.Init,
        entity_names: list[str],
        road_id: int,
        lane_id: int,
        queue_head_s: float,
        gap_m: float,
        vehicle_length_m: float,
        approach_entity: str,
        approach_distance: float,
        approach_speed_mph: float,
    ) -> tuple[list[PlacementResult], PlacementResult]:
        """Place stationary queue + approaching vehicle for rear-end collision."""
        db = cls._db()
        db.validate_lane(road_id, lane_id, "driving")

        queue, approach = rear_end_positions(
            db, road_id, lane_id,
            queue_head_s=queue_head_s,
            num_queued=len(entity_names),
            gap_m=gap_m,
            vehicle_length_m=vehicle_length_m,
            approach_distance=approach_distance,
            approach_speed=mph_to_mps(approach_speed_mph),
        )

        for name, placement in zip(entity_names, queue):
            init.add_init_action(
                name, xosc.TeleportAction(xosc.LanePosition(
                    placement.s, 0, str(lane_id), str(road_id)
                )),
            )
            init.add_init_action(name, cls._speed_action(0))

        init.add_init_action(
            approach_entity,
            xosc.TeleportAction(xosc.LanePosition(
                approach.s, 0, str(lane_id), str(road_id)
            )),
        )
        init.add_init_action(
            approach_entity, cls._speed_action(approach.speed_mps)
        )

        return queue, approach

    @classmethod
    def _place_head_on(
        cls,
        init: xosc.Init,
        entity_a: str,
        speed_a_mph: float,
        entity_b: str,
        speed_b_mph: float,
        road_id: int,
        collision_time: float = 3.0,
    ) -> tuple[PlacementResult, PlacementResult]:
        """Place two vehicles for a head-on collision on a two-way road."""
        db = cls._db()
        pa, pb = head_on_positions(
            db, road_id,
            speed_a=mph_to_mps(speed_a_mph),
            speed_b=mph_to_mps(speed_b_mph),
            desired_collision_time=collision_time,
        )

        init.add_init_action(
            entity_a,
            xosc.TeleportAction(xosc.LanePosition(
                pa.s, 0, str(pa.lane_id), str(road_id)
            )),
        )
        init.add_init_action(entity_a, cls._speed_action(pa.speed_mps))

        init.add_init_action(
            entity_b,
            xosc.TeleportAction(xosc.LanePosition(
                pb.s, 0, str(pb.lane_id), str(road_id)
            )),
        )
        init.add_init_action(entity_b, cls._speed_action(pb.speed_mps))

        return pa, pb

    # ── Init-action helpers ──────────────────────────────────────────────

    @staticmethod
    def _teleport(position):
        """Wrap a position in a TeleportAction."""
        return xosc.TeleportAction(position)

    @staticmethod
    def _speed_action(speed_mps, transition_time=0.0):
        """Create an AbsoluteSpeedAction with a step or timed transition."""
        td = xosc.TransitionDynamics(
            xosc.DynamicsShapes.step,
            xosc.DynamicsDimension.time,
            transition_time,
        )
        return xosc.AbsoluteSpeedAction(speed_mps, td)

    @staticmethod
    def _speed_action_smooth(speed_mps, transition_time=2.0):
        """AbsoluteSpeedAction with a sinusoidal (smooth) ramp."""
        td = xosc.TransitionDynamics(
            xosc.DynamicsShapes.sinusoidal,
            xosc.DynamicsDimension.time,
            transition_time,
        )
        return xosc.AbsoluteSpeedAction(speed_mps, td)

    @staticmethod
    def _brake_action(decel_mps=0.0, transition_time=2.0):
        """AbsoluteSpeedAction that brakes to a target speed."""
        td = xosc.TransitionDynamics(
            xosc.DynamicsShapes.linear,
            xosc.DynamicsDimension.time,
            transition_time,
        )
        return xosc.AbsoluteSpeedAction(decel_mps, td)

    @staticmethod
    def _lane_change(target_lane: int, transition_time=2.0):
        """AbsoluteLaneChangeAction to a target lane id."""
        td = xosc.TransitionDynamics(
            xosc.DynamicsShapes.sinusoidal,
            xosc.DynamicsDimension.time,
            transition_time,
        )
        return xosc.AbsoluteLaneChangeAction(target_lane, td)

    # ── Trigger helpers ──────────────────────────────────────────────────

    @staticmethod
    def _sim_time_trigger(name, t):
        """ValueTrigger that fires at simulation time *t*."""
        return xosc.ValueTrigger(
            name,
            0,
            xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(t, xosc.Rule.greaterThan),
        )

    @staticmethod
    def _collision_trigger(name, triggering_entity, target_entity):
        """EntityTrigger that fires on collision between two entities."""
        return xosc.EntityTrigger(
            name,
            0,
            xosc.ConditionEdge.rising,
            xosc.CollisionCondition(target_entity),
            triggering_entity,
        )

    # ── Storyboard assembly helpers ──────────────────────────────────────

    @staticmethod
    def _make_event(name, action_name, action, trigger):
        """Build an Event with one action and one start trigger."""
        evt = xosc.Event(name, xosc.Priority.overwrite)
        evt.add_action(action_name, action)
        evt.add_trigger(trigger)
        return evt

    @staticmethod
    def _make_maneuver_group(name, actor, maneuver):
        """ManeuverGroup with a single actor and a single maneuver."""
        mg = xosc.ManeuverGroup(name)
        mg.add_actor(actor)
        mg.add_maneuver(maneuver)
        return mg

    # ── Public interface ─────────────────────────────────────────────────

    @abstractmethod
    def build(self) -> xosc.Scenario:
        """Return a fully-assembled xosc.Scenario."""

    def write(self, output_dir: str) -> str:
        """Build the scenario and write it to *output_dir*. Return the path."""
        scenario = self.build()
        fname = f"s{self.scenario_id:02d}_{self._slug()}.xosc"
        path = os.path.join(output_dir, fname)
        scenario.write_xml(path)
        return path

    def _slug(self) -> str:
        return self.scenario_name.lower().replace(" ", "_").replace("-", "_")
