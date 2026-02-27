#!/usr/bin/env python3
"""Config-driven scenario generator: JSON config → .xosc file.

Reads a JSON config describing entities, positions, routes, and maneuvers,
and produces a validated OpenSCENARIO 1.0 file using scenariogeneration.

Usage:
    python -m generator.config_builder configs/situation_042.json
    python -m generator.config_builder configs/situation_042.json --validate
"""

import argparse
import json
import os
import sys

from scenariogeneration import xosc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.scenario_builders.base import BaseScenarioBuilder, mph_to_mps, XODR_RELATIVE
from generator import vehicle_defs as vd


# Entity type → factory function mapping
ENTITY_FACTORIES = {
    "sedan": vd.sedan,
    "suv": vd.suv,
    "pickup": vd.pickup,
    "motorcycle": vd.motorcycle,
    "bicycle": vd.bicycle,
    "pedestrian": vd.pedestrian,
    "debris": vd.road_debris,
    "parked_car_door": vd.parked_car_door,
}


class ConfigBuilder(BaseScenarioBuilder):
    """Build a .xosc scenario from a JSON config dict."""

    def __init__(self, config: dict):
        self.config = config
        self.scenario_id = config.get("situation_id", 0)
        self.scenario_name = config.get("scenario_name", "unnamed")

    def build(self) -> xosc.Scenario:
        cfg = self.config

        # 1. Create entities
        entities = xosc.Entities()
        for ent in cfg["entities"]:
            name = ent["name"]
            etype = ent["type"]
            if etype not in ENTITY_FACTORIES:
                raise ValueError(f"Unknown entity type '{etype}'. Available: {list(ENTITY_FACTORIES.keys())}")
            entities.add_scenario_object(name, ENTITY_FACTORIES[etype]())

        # 2. Init actions: teleport + speed + optional routes
        init = xosc.Init()

        for ia in cfg["init_actions"]:
            entity = ia["entity"]
            road = ia["road"]
            lane = ia["lane"]
            s = ia["s"]
            speed_mph = ia.get("speed_mph", 0)
            offset = ia.get("offset", 0.0)
            lane_type = ia.get("lane_type", "driving")

            pos = self._validated_lane_pos(road, s, lane, expected_type=lane_type, offset=offset)
            init.add_init_action(entity, self._teleport(pos))
            init.add_init_action(entity, self._speed_action(mph_to_mps(speed_mph)))

        # 3. Route assignments (for junction scenarios)
        for route in cfg.get("routes", []):
            entity = route["entity"]
            action = self._assign_route(
                start_road=route["start_road"],
                start_lane=route["start_lane"],
                start_s=route["start_s"],
                exit_road=route["exit_road"],
                exit_lane=route["exit_lane"],
                exit_s=route.get("exit_s", 10.0),
            )
            init.add_init_action(entity, action)

        # 4. Storyboard with maneuvers
        sb = xosc.StoryBoard(init)

        act = xosc.Act("act_main")

        for man_cfg in cfg.get("maneuvers", []):
            entity = man_cfg["entity"]
            maneuver = xosc.Maneuver(f"man_{entity}")

            for evt_cfg in man_cfg["events"]:
                evt_name = evt_cfg["name"]
                trigger_time = evt_cfg["trigger_time"]
                actions = evt_cfg["actions"]

                if len(actions) == 1:
                    # Single action → use make_event helper
                    action = self._build_action(actions[0])
                    event = self._make_event(
                        f"evt_{entity}_{evt_name}",
                        f"act_{evt_name}",
                        action,
                        self._sim_time_trigger(f"t_{entity}_{evt_name}", trigger_time),
                    )
                else:
                    # Multiple actions in one event (run simultaneously)
                    event = xosc.Event(f"evt_{entity}_{evt_name}", xosc.Priority.overwrite)
                    for i, act_cfg in enumerate(actions):
                        action = self._build_action(act_cfg)
                        event.add_action(f"act_{evt_name}_{i}", action)
                    event.add_trigger(
                        self._sim_time_trigger(f"t_{entity}_{evt_name}", trigger_time)
                    )

                maneuver.add_event(event)

            mg = self._make_maneuver_group(f"mg_{entity}", entity, maneuver)
            act.add_maneuver_group(mg)

        story = xosc.Story("story_main")
        story.add_act(act)
        sb.add_story(story)

        # 5. Stop trigger
        sim_time = self.config.get("sim_time", 15.0)
        sb._stoptrigger = xosc.ValueTrigger(
            "stop", 0, xosc.ConditionEdge.rising,
            xosc.SimulationTimeCondition(sim_time, xosc.Rule.greaterThan),
        )
        sb._stoptrigger._triggerpoint = "StopTrigger"

        # 6. Assemble scenario
        return xosc.Scenario(
            self.scenario_name, "RFS-ConfigBuilder",
            xosc.ParameterDeclarations(), entities, sb,
            self._road_network(), xosc.Catalog(),
            osc_minor_version=0,
        )

    def _build_action(self, act_cfg: dict):
        """Convert an action config dict to a scenariogeneration action object."""
        atype = act_cfg["type"]

        if atype == "speed":
            speed_mph = act_cfg["speed_mph"]
            transition = act_cfg.get("transition_time", 0.0)
            return self._speed_action(mph_to_mps(speed_mph), transition)

        elif atype == "speed_smooth":
            speed_mph = act_cfg["speed_mph"]
            transition = act_cfg.get("transition_time", 2.0)
            return self._speed_action_smooth(mph_to_mps(speed_mph), transition)

        elif atype == "brake":
            target_mph = act_cfg.get("target_speed_mph", 0)
            transition = act_cfg.get("transition_time", 2.0)
            return self._brake_action(mph_to_mps(target_mph), transition)

        elif atype == "lane_change":
            target_lane = act_cfg["target_lane"]
            transition = act_cfg.get("transition_time", 2.0)
            return self._lane_change(target_lane, transition)

        else:
            raise ValueError(f"Unknown action type '{atype}'. Available: speed, speed_smooth, brake, lane_change")

    def write(self, output_dir: str) -> str:
        """Build and write the scenario .xosc file."""
        scenario = self.build()
        sid = self.config.get("situation_id", 0)
        slug = self.scenario_name.lower().replace(" ", "_").replace("-", "_")
        fname = f"cs{sid:03d}_{slug}.xosc"
        path = os.path.join(output_dir, fname)
        scenario.write_xml(path)
        return path


def main():
    parser = argparse.ArgumentParser(description="Generate .xosc from config JSON")
    parser.add_argument("config_path", help="Path to config JSON file")
    parser.add_argument(
        "--validate", action="store_true",
        help="Run esmini collision validation after generating",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: generator/output)",
    )
    args = parser.parse_args()

    # Load config
    config_path = os.path.abspath(args.config_path)
    if not os.path.isfile(config_path):
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # Determine output directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    # Build and write
    try:
        builder = ConfigBuilder(config)
        path = builder.write(output_dir)
        print(f"Generated: {path}")
    except Exception as e:
        print(f"Error generating scenario: {e}")
        sys.exit(1)

    # Validate if requested
    if args.validate:
        from generator.validate import validate_scenario

        result = validate_scenario(path, sim_time=config.get("sim_time", 15.0))

        if result.collision_detected:
            pairs = ", ".join(f"{a}+{b}" for a, b in result.entity_pairs)
            print(f"[PASS] Collision at t={result.first_collision_time:.2f}s ({pairs})")
        else:
            print("[FAIL] No collision detected")
            if result.errors:
                for err in result.errors:
                    print(f"  Error: {err}")
            sys.exit(1)


if __name__ == "__main__":
    main()
