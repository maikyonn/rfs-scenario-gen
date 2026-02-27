"""S03 — Left turn across oncoming motorcycle at junction 199.

Pickup on road 28 (lane 1, backward→199) turns left, routed → road 25.
Motorcycle on road 39 (lane -1, forward→199) approaches at 40 mph, routed → road 54.
ConnRoad for 28→25 crosses connRoad for 39→54 at ~63° near (140.7, 303.6).
"""

from scenariogeneration import xosc
from generator import vehicle_defs as vd
from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps


class S03LeftTurnMotorcycle(BaseScenarioBuilder):
    scenario_id = 3
    scenario_name = "left_turn_motorcycle"

    def build(self) -> xosc.Scenario:
        entities = xosc.Entities()
        entities.add_scenario_object("pickup", vd.pickup())
        entities.add_scenario_object("motorcycle", vd.motorcycle())

        init = xosc.Init()

        # Pickup on road 28 lane 1 (backward→199), starts at s=5
        # Pickup at s=5: 5m to junction + ~24m connRoad = ~29m at 6.71m/s → 4.3s to crossing
        pickup_pos = self._validated_lane_pos(28, 5, 1)
        init.add_init_action("pickup", self._teleport(pickup_pos))
        init.add_init_action("pickup", self._speed_action(mph_to_mps(15)))
        # Route pickup through junction → road 25 (crossing path)
        init.add_init_action("pickup", self._assign_route(28, 1, 5, 25, -1, 10))

        # Motorcycle on road 39 lane -1 (forward→199), at 35mph (15.65m/s)
        # At s=2: 63.3m to junction + ~12m connRoad = ~75m at 15.65m/s → 4.8s to crossing
        moto_pos = self._validated_lane_pos(39, 2, -1)
        init.add_init_action("motorcycle", self._teleport(moto_pos))
        init.add_init_action("motorcycle", self._speed_action(mph_to_mps(35)))
        # Route motorcycle through junction → road 54 (crossing path)
        init.add_init_action("motorcycle", self._assign_route(39, -1, 2, 54, -1, 10))

        sb = xosc.StoryBoard(init)

        # Pickup accelerates slightly into the turn
        man_pickup = xosc.Maneuver("pickup_turn")
        man_pickup.add_event(self._make_event(
            "start_turn", "accelerate",
            self._speed_action_smooth(mph_to_mps(15), 2.0),
            self._sim_time_trigger("t_turn", 0),
        ))
        mg_pickup = self._make_maneuver_group("mg_pickup", "pickup", man_pickup)

        # Motorcycle maintains speed
        man_moto = xosc.Maneuver("moto_straight")
        man_moto.add_event(self._make_event(
            "maintain", "keep_speed",
            self._speed_action(mph_to_mps(35)),
            self._sim_time_trigger("t0", 0),
        ))
        mg_moto = self._make_maneuver_group("mg_moto", "motorcycle", man_moto)

        act = xosc.Act("act_leftturn")
        act.add_maneuver_group(mg_pickup)
        act.add_maneuver_group(mg_moto)

        story = xosc.Story("story_leftturn")
        story.add_act(act)
        sb.add_story(story)

        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(12, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        return xosc.Scenario(
            "LeftTurnMotorcycle", "RFS-Generator",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )
