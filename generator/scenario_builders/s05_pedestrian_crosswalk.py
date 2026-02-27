"""S05 — Pedestrian crosswalk dash on road 39 near junction 199.

Pedestrian on sidewalk (lane 3) starts walking along sidewalk, then at t=1.0
dashes across road via lane change to lane -1. Vehicle on lane -1 at 25 mph
approaches from behind, timed so the vehicle reaches the ped's crossing point
just as the ped is midway across lane -1.

Road 39: len≈65m, lane 3=sidewalk, lane 2=shoulder, lane 1/-1=driving.
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S05PedestrianCrosswalk(BaseScenarioBuilder):
    scenario_id = 5
    scenario_name = "pedestrian_crosswalk"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("vehicle", vd.sedan())
        entities.add_scenario_object("ped", vd.pedestrian())

        init = xosc.Init()

        # Vehicle on road 39 lane -1 (forward), starts at s=5
        # At 25mph (11.18m/s), reaches s=40 in ~3.1s
        veh_pos = self._validated_lane_pos(39, 5, -1)
        init.add_init_action("vehicle", self._teleport(veh_pos))
        init.add_init_action("vehicle", self._speed_action(mph_to_mps(25)))

        # Pedestrian on lane 1 (driving, opposite direction from vehicle) at s=40
        # This places the ped already on the road surface where the vehicle will pass.
        # Ped starts stationary, then at t=1.0 starts running across (speed + lane change).
        ped_pos = self._validated_lane_pos(39, 40, 1)
        init.add_init_action("ped", self._teleport(ped_pos))
        init.add_init_action("ped", self._speed_action(0))

        sb = xosc.StoryBoard(init)

        # Vehicle maintains speed
        man_veh = xosc.Maneuver("veh_drive")
        man_veh.add_event(self._make_event(
            "veh_go", "maintain",
            self._speed_action(mph_to_mps(25)),
            self._sim_time_trigger("t0", 0),
        ))
        mg_veh = self._make_maneuver_group("mg_veh", "vehicle", man_veh)

        # Pedestrian dashes across at t=1.0 (both speed and lane change together)
        man_ped = xosc.Maneuver("ped_dash")
        dash_evt = xosc.Event("dash", xosc.Priority.overwrite)
        dash_evt.add_action("run_across", self._speed_action_smooth(2.0, 0.5))
        dash_evt.add_action("lane_change", self._lane_change(-1, 3.0))
        dash_evt.add_trigger(self._sim_time_trigger("t_dash", 1.0))
        man_ped.add_event(dash_evt)
        mg_ped = self._make_maneuver_group("mg_ped", "ped", man_ped)

        act = xosc.Act("act_crosswalk")
        act.add_maneuver_group(mg_veh)
        act.add_maneuver_group(mg_ped)

        story = xosc.Story("story_crosswalk")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(12, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "PedestrianCrosswalk", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
