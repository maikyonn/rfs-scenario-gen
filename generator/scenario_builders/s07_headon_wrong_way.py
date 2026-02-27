"""S07 — Head-on collision on road 26 (two-way road).

Switched from road 25 (one-way, impossible for head-on) to road 26.
Road 26: len≈173m, lane -1=forward (3.5m wide), lane 1=backward (3.5m wide).

The wrong-way driver drifts into the oncoming lane by lane-changing from
lane 1 to lane -1. The correct driver on lane -1 cannot avoid them.
Collision physics computed by _place_head_on for convergence timing.
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S07HeadOnWrongWay(BaseScenarioBuilder):
    scenario_id = 7
    scenario_name = "headon_wrong_way"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("correct", vd.sedan())
        entities.add_scenario_object("wrong_way", vd.sedan())

        init = xosc.Init()

        # Place using head-on physics for timing
        pa, pb = self._place_head_on(
            init,
            entity_a="correct", speed_a_mph=35,
            entity_b="wrong_way", speed_b_mph=25,
            road_id=26,
            collision_time=3.0,
        )

        sb = xosc.StoryBoard(init)

        # Correct driver maintains lane -1
        man_correct = xosc.Maneuver("correct_drive")
        man_correct.add_event(self._make_event(
            "maintain_c", "keep",
            self._speed_action(mph_to_mps(35)),
            self._sim_time_trigger("t0_c", 0),
        ))
        mg_c = self._make_maneuver_group("mg_correct", "correct", man_correct)

        # Wrong-way driver drifts into oncoming lane -1 at t=0.5s
        man_wrong = xosc.Maneuver("wrong_drive")
        man_wrong.add_event(self._make_event(
            "maintain_w", "keep",
            self._speed_action(mph_to_mps(25)),
            self._sim_time_trigger("t0_w", 0),
        ))
        man_wrong.add_event(self._make_event(
            "drift", "drift_into_oncoming",
            self._lane_change(-1, 2.0),
            self._sim_time_trigger("t_drift", 0.5),
        ))
        mg_w = self._make_maneuver_group("mg_wrong", "wrong_way", man_wrong)

        act = xosc.Act("act_headon")
        act.add_maneuver_group(mg_c)
        act.add_maneuver_group(mg_w)

        story = xosc.Story("story_headon")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(10, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "HeadOnWrongWay", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
