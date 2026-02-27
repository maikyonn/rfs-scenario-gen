"""S08 — Cyclist dooring on road 54.

Cyclist in driving lane (lane 1, backward) hits a stationary obstacle (open car door).
Door offset changed from 1.2 → 0.0 so door is centered in driving lane.
Road 54: len≈85m, lane 2=parking, lane 1=driving (backward), lane -1=driving (forward).
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S08CyclistDooring(BaseScenarioBuilder):
    scenario_id = 8
    scenario_name = "cyclist_dooring"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("cyclist", vd.bicycle())
        entities.add_scenario_object("parked_car", vd.sedan())
        entities.add_scenario_object("door", vd.parked_car_door())

        init = xosc.Init()

        # Cyclist on road 54 lane 1 (backward: travels toward s=0).
        # Start at high s, approaching the door at s=45.
        cyclist_pos = self._validated_lane_pos(54, 70, 1)
        init.add_init_action("cyclist", self._teleport(cyclist_pos))
        init.add_init_action("cyclist", self._speed_action(mph_to_mps(15)))

        # Parked car in parking lane 2
        parked_pos = self._validated_lane_pos(54, 45, 2, expected_type="parking")
        init.add_init_action("parked_car", self._teleport(parked_pos))
        init.add_init_action("parked_car", self._speed_action(0))

        # Door obstacle in driving lane 1 at same s, offset=0.0 (centered in lane)
        door_pos = self._validated_lane_pos(54, 45, 1, offset=0.0)
        init.add_init_action("door", self._teleport(door_pos))
        init.add_init_action("door", self._speed_action(0))

        sb = xosc.StoryBoard(init)

        # Cyclist maintains speed
        man = xosc.Maneuver("cyclist_ride")
        man.add_event(self._make_event(
            "ride", "keep_speed",
            self._speed_action(mph_to_mps(15)),
            self._sim_time_trigger("t0", 0),
        ))
        mg = self._make_maneuver_group("mg_cyclist", "cyclist", man)

        act = xosc.Act("act_dooring")
        act.add_maneuver_group(mg)

        story = xosc.Story("story_dooring")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(12, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "CyclistDooring", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
