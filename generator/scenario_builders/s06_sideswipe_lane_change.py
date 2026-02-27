"""S06 — Sideswipe during lane change on road 33.

Both lanes on road 33 are backward (left-side only). Changer in lane 1 moves
to lane 2 without checking blind spot, hitting the target in lane 2.
Vehicles placed at the same s-position for guaranteed overlap during lane change.
Road 33: len≈81m, lanes: 2 (driving, backward), 1 (driving, backward).
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S06SideswipeLaneChange(BaseScenarioBuilder):
    scenario_id = 6
    scenario_name = "sideswipe_lane_change"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("changer", vd.sedan())
        entities.add_scenario_object("target", vd.sedan())

        init = xosc.Init()

        # Place side-by-side at same s for guaranteed sideswipe
        changer_pos = self._validated_lane_pos(33, 60, 1)
        target_pos = self._validated_lane_pos(33, 60, 2)

        init.add_init_action("changer", self._teleport(changer_pos))
        init.add_init_action("changer", self._speed_action(mph_to_mps(35)))
        init.add_init_action("target", self._teleport(target_pos))
        init.add_init_action("target", self._speed_action(mph_to_mps(35)))

        sb = xosc.StoryBoard(init)

        # Target maintains speed
        man_target = xosc.Maneuver("target_straight")
        man_target.add_event(self._make_event(
            "maintain", "keep",
            self._speed_action(mph_to_mps(35)),
            self._sim_time_trigger("t0", 0),
        ))
        mg_target = self._make_maneuver_group("mg_target", "target", man_target)

        # Changer initiates lane change to lane 2 at t=1s (quick change)
        man_changer = xosc.Maneuver("changer_lc")
        man_changer.add_event(self._make_event(
            "lane_change", "move_left",
            self._lane_change(2, 2.0),
            self._sim_time_trigger("t_lc", 1.0),
        ))
        mg_changer = self._make_maneuver_group("mg_changer", "changer", man_changer)

        act = xosc.Act("act_sideswipe")
        act.add_maneuver_group(mg_target)
        act.add_maneuver_group(mg_changer)

        story = xosc.Story("story_sideswipe")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(10, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "SideswipeLaneChange", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
