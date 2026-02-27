"""S02 — Rear-end chain collision on road 52 near junction 323.

Three vehicles queued at red on road 52 lane -1 (forward).
Fourth approaches at 40 mph, rear-ends queue. Positions computed via framework.
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S02RearEndChain(BaseScenarioBuilder):
    scenario_id = 2
    scenario_name = "rearend_chain"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("car_a", vd.sedan())  # front of queue
        entities.add_scenario_object("car_b", vd.sedan())
        entities.add_scenario_object("car_c", vd.sedan())  # rear of queue
        entities.add_scenario_object("car_d", vd.sedan())  # approaching

        init = xosc.Init()

        # Queue on road 52 lane -1 (forward), head at s=85 near junction end
        queue, approach = self._place_rear_end_queue(
            init,
            entity_names=["car_a", "car_b", "car_c"],
            road_id=52, lane_id=-1,
            queue_head_s=85.0,
            gap_m=2.0,
            vehicle_length_m=4.5,
            approach_entity="car_d",
            approach_distance=50.0,
            approach_speed_mph=40,
        )

        sb = xosc.StoryBoard(init)

        # car_d maintains speed (distracted — no braking)
        man = xosc.Maneuver("approach")
        man.add_event(self._make_event(
            "maintain_speed", "keep_40",
            self._speed_action(mph_to_mps(40)),
            self._sim_time_trigger("t0", 0),
        ))
        mg = self._make_maneuver_group("mg_approach", "car_d", man)

        act = xosc.Act("act_rearend")
        act.add_maneuver_group(mg)

        story = xosc.Story("story_rearend")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(12, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "RearEndChain", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
