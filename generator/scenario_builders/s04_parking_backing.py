"""S04 — Parking lot backing collision on road 54.

Two vehicles in adjacent parking spaces (lane 2) reverse out simultaneously,
moving into the driving lane (lane 1). Cars placed very close (2m gap)
with one moving slightly faster to converge during lane change.
Road 54: len≈85m, lane 2=parking, lane 1=driving (backward), lane -1=driving (forward).
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S04ParkingBacking(BaseScenarioBuilder):
    scenario_id = 4
    scenario_name = "parking_backing"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("car_a", vd.sedan())
        entities.add_scenario_object("car_b", vd.sedan())

        init = xosc.Init()

        # Cars very close in parking lane (2m gap < vehicle length 4.5m)
        pos_a = self._validated_lane_pos(54, 40, 2, expected_type="parking")
        pos_b = self._validated_lane_pos(54, 42, 2, expected_type="parking")

        init.add_init_action("car_a", self._teleport(pos_a))
        init.add_init_action("car_a", self._speed_action(0))
        init.add_init_action("car_b", self._teleport(pos_b))
        init.add_init_action("car_b", self._speed_action(0))

        sb = xosc.StoryBoard(init)

        # Both reverse into driving lane simultaneously at t=1s
        # Car A moves with speed and lane change
        man_a = xosc.Maneuver("car_a_reverse")
        man_a.add_event(self._make_event(
            "speed_a", "slow_reverse_a",
            self._speed_action_smooth(mph_to_mps(5), 0.5),
            self._sim_time_trigger("t_speed_a", 1.0),
        ))
        man_a.add_event(self._make_event(
            "reverse_a", "back_out_a",
            self._lane_change(1, 2.5),
            self._sim_time_trigger("t_back_a", 1.0),
        ))
        mg_a = self._make_maneuver_group("mg_a", "car_a", man_a)

        # Car B starts simultaneously with slightly more speed
        man_b = xosc.Maneuver("car_b_reverse")
        man_b.add_event(self._make_event(
            "speed_b", "slow_reverse_b",
            self._speed_action_smooth(mph_to_mps(7), 0.5),
            self._sim_time_trigger("t_speed_b", 1.0),
        ))
        man_b.add_event(self._make_event(
            "reverse_b", "back_out_b",
            self._lane_change(1, 2.5),
            self._sim_time_trigger("t_back_b", 1.0),
        ))
        mg_b = self._make_maneuver_group("mg_b", "car_b", man_b)

        act = xosc.Act("act_parking")
        act.add_maneuver_group(mg_a)
        act.add_maneuver_group(mg_b)

        story = xosc.Story("story_parking")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(10, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "ParkingBacking", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
