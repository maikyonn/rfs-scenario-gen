"""S10 — Rear-end from sudden obstacle avoidance on road 26.

Lead vehicle swerves and brakes for debris. Follower at 1s gap rear-ends.
Road 26: len≈173m, lane -1=forward, lane 1=backward.
All positions validated. Lead/follower gap computed from speed.
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S10RearEndObstacle(BaseScenarioBuilder):
    scenario_id = 10
    scenario_name = "rearend_obstacle"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("lead", vd.sedan())
        entities.add_scenario_object("follower", vd.sedan())
        entities.add_scenario_object("debris", vd.road_debris())

        init = xosc.Init()

        speed_mps = mph_to_mps(35)
        gap_m = speed_mps * 1.0  # 1-second following gap ≈ 15.6m

        # Lead on road 26 lane -1 (forward)
        lead_pos = self._validated_lane_pos(26, 30, -1)
        init.add_init_action("lead", self._teleport(lead_pos))
        init.add_init_action("lead", self._speed_action(speed_mps))

        # Follower 1s gap behind
        follower_s = 30 - gap_m
        follower_pos = self._validated_lane_pos(26, follower_s, -1)
        init.add_init_action("follower", self._teleport(follower_pos))
        init.add_init_action("follower", self._speed_action(speed_mps))

        # Debris on road ahead
        debris_pos = self._validated_lane_pos(26, 100, -1)
        init.add_init_action("debris", self._teleport(debris_pos))
        init.add_init_action("debris", self._speed_action(0))

        sb = xosc.StoryBoard(init)

        # Lead: at t=3s swerves left and brakes hard
        man_lead = xosc.Maneuver("lead_avoid")
        man_lead.add_event(self._make_event(
            "swerve", "lane_change_left",
            self._lane_change(1, 1.5),
            self._sim_time_trigger("t_swerve", 3.0),
        ))
        man_lead.add_event(self._make_event(
            "brake", "hard_brake",
            self._brake_action(0, 2.0),
            self._sim_time_trigger("t_brake", 3.0),
        ))
        mg_lead = self._make_maneuver_group("mg_lead", "lead", man_lead)

        # Follower: maintains speed (can't react in time)
        man_follow = xosc.Maneuver("follower_drive")
        man_follow.add_event(self._make_event(
            "maintain", "keep_35",
            self._speed_action(speed_mps),
            self._sim_time_trigger("t0_f", 0),
        ))
        mg_follow = self._make_maneuver_group("mg_follow", "follower", man_follow)

        act = xosc.Act("act_rearend_avoid")
        act.add_maneuver_group(mg_lead)
        act.add_maneuver_group(mg_follow)

        story = xosc.Story("story_rearend_avoid")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(12, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "RearEndObstacle", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
