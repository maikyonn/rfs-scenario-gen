#!/usr/bin/env python3
"""Main entry point: reads crash_scenarios.json, builds all 10 .xosc files."""

import argparse
import json
import os
import sys

# Ensure both generator/ and its parent are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.scenario_builders import ALL_BUILDERS


def main():
    parser = argparse.ArgumentParser(description="Generate OpenSCENARIO files")
    parser.add_argument(
        "--validate", action="store_true",
        help="Run esmini collision validation after generating scenarios",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "output")
    json_path = os.path.join(base_dir, "..", "crash_scenarios.json")

    os.makedirs(output_dir, exist_ok=True)

    # Load scenario metadata
    with open(json_path) as f:
        data = json.load(f)
    scenarios = {s["id"]: s for s in data["scenarios"]}

    print(f"Generating {len(ALL_BUILDERS)} scenarios → {output_dir}\n")

    success = 0
    failed = 0

    for builder_cls in ALL_BUILDERS:
        sid = builder_cls.scenario_id
        meta = scenarios.get(sid, {})
        name = meta.get("name", builder_cls.scenario_name)

        try:
            builder = builder_cls()
            path = builder.write(output_dir)
            print(f"  [{sid:02d}] ✓ {name}")
            print(f"       → {os.path.basename(path)}")
            success += 1
        except Exception as e:
            print(f"  [{sid:02d}] ✗ {name}")
            print(f"       ERROR: {e}")
            failed += 1

    print(f"\nDone: {success} succeeded, {failed} failed")

    if args.validate:
        print("\n── Collision Validation ──────────────────────────────────────\n")
        from generator.validate import validate_all

        results = validate_all(output_dir)
        passed = 0
        val_failed = 0

        for name, r in sorted(results.items()):
            pairs = ", ".join(f"{a}+{b}" for a, b in r.entity_pairs)
            if r.collision_detected:
                print(f"  [PASS] {name}: COLLISION at t={r.first_collision_time:.2f}s ({pairs})")
                passed += 1
            else:
                print(f"  [FAIL] {name}: NO COLLISION")
                val_failed += 1

        print(f"\n{passed}/{len(results)} scenarios produced collisions")
        if val_failed > 0:
            return 1

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
