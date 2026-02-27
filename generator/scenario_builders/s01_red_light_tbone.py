"""S01 — Red-light runner T-bone at signalised junction 323.

Sedan on road 52 (lane -1, forward→323) runs red at 35 mph, routed → road 19.
SUV on road 44 (lane 1, backward→323) at 30 mph, routed → road 20.
ConnRoad 331 (52→19) crosses connRoad 333 (44→20) at ~86° near (-137.5, 54.6).
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S01RedLightTBone(BaseScenarioBuilder):
    scenario_id = 1
    scenario_name = "red_light_tbone"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("sedan", vd.sedan())
        entities.add_scenario_object("suv", vd.suv())

        init = xosc.Init()

        # Sedan on road 52 lane -1 (forward→323), starts at s=20
        # Distance to junction: 100 - 20 = 80m, at 35mph (15.65m/s) → 5.1s
        sedan_pos = self._validated_lane_pos(52, 20, -1)
        init.add_init_action("sedan", self._teleport(sedan_pos))
        init.add_init_action("sedan", self._speed_action(mph_to_mps(35)))
        # Route sedan through junction → road 19 (connRoad 331)
        init.add_init_action("sedan", self._assign_route(52, -1, 20, 19, 1, 10))

        # SUV on road 44 lane 1 (backward→323), starts at s=68
        # Distance to junction: s=68m (backward lane), at 30mph (13.41m/s) → 5.07s
        suv_pos = self._validated_lane_pos(44, 68, 1)
        init.add_init_action("suv", self._teleport(suv_pos))
        init.add_init_action("suv", self._speed_action(mph_to_mps(30)))
        # Route SUV through junction → road 20 (connRoad 333)
        init.add_init_action("suv", self._assign_route(44, 1, 68, 20, -1, 10))

        sb = xosc.StoryBoard(init)

        # Sedan maintains speed
        man_sedan = xosc.Maneuver("sedan_drive")
        man_sedan.add_event(self._make_event(
            "sedan_maintain", "keep_speed",
            self._speed_action(mph_to_mps(35)),
            self._sim_time_trigger("t0", 0),
        ))
        mg_sedan = self._make_maneuver_group("mg_sedan", "sedan", man_sedan)

        # SUV maintains speed
        man_suv = xosc.Maneuver("suv_drive")
        man_suv.add_event(self._make_event(
            "suv_maintain", "keep_speed",
            self._speed_action(mph_to_mps(30)),
            self._sim_time_trigger("t0_suv", 0),
        ))
        mg_suv = self._make_maneuver_group("mg_suv", "suv", man_suv)

        act = xosc.Act("act_collision")
        act.add_maneuver_group(mg_sedan)
        act.add_maneuver_group(mg_suv)

        story = xosc.Story("story_tbone")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(15, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "RedLightTBone", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
