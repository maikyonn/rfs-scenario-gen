"""S09 — Stop sign rollthrough at junction 103.

Minor road vehicle (road 24, lane -1, forward→103) rolls through at 15 mph,
routed → road 12. Major road vehicle (road 40, lane 1, backward→103) at 40 mph,
routed → road 37. ConnRoad 124 (24→12) crosses connRoad 112 (40→37) at ~53°.
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S09StopSignRollthrough(BaseScenarioBuilder):
    scenario_id = 9
    scenario_name = "stop_sign_rollthrough"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("minor", vd.sedan())
        entities.add_scenario_object("major", vd.sedan())

        init = xosc.Init()

        # Minor on road 24 lane -1 (forward→103), starts at s=2
        # Distance to junction: 12.8 - 2 = 10.8m, at 15mph (6.71m/s) → 1.61s
        minor_pos = self._validated_lane_pos(24, 2, -1)
        init.add_init_action("minor", self._teleport(minor_pos))
        init.add_init_action("minor", self._speed_action(mph_to_mps(15)))
        # Route minor through junction → road 12 (connRoad 124)
        init.add_init_action("minor", self._assign_route(24, -1, 2, 12, -1, 5))

        # Major on road 40 lane 1 (backward→103), at 40mph (17.88m/s)
        # Need to arrive at junction at same time: 1.61s * 17.88 = 28.8m from junction
        major_pos = self._validated_lane_pos(40, 29, 1)
        init.add_init_action("major", self._teleport(major_pos))
        init.add_init_action("major", self._speed_action(mph_to_mps(40)))
        # Route major through junction → road 37 (connRoad 112)
        init.add_init_action("major", self._assign_route(40, 1, 29, 37, -1, 1))

        sb = xosc.StoryBoard(init)

        # Both maintain speed
        man_minor = xosc.Maneuver("minor_roll")
        man_minor.add_event(self._make_event(
            "roll", "keep_15",
            self._speed_action(mph_to_mps(15)),
            self._sim_time_trigger("t0_minor", 0),
        ))
        mg_minor = self._make_maneuver_group("mg_minor", "minor", man_minor)

        man_major = xosc.Maneuver("major_drive")
        man_major.add_event(self._make_event(
            "drive", "keep_40",
            self._speed_action(mph_to_mps(40)),
            self._sim_time_trigger("t0_major", 0),
        ))
        mg_major = self._make_maneuver_group("mg_major", "major", man_major)

        act = xosc.Act("act_rollthrough")
        act.add_maneuver_group(mg_minor)
        act.add_maneuver_group(mg_major)

        story = xosc.Story("story_rollthrough")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(10, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "StopSignRollthrough", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
