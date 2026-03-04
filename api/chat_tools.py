"""LangGraph tool functions for the crash scenario chat pipeline.

Each tool returns a JSON string so LangGraph can pass results back through
the message history as tool_result nodes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from langchain_core.tools import tool

from api.chat_progress import emit_tool_progress
from api.s3 import file_url as _file_url


# ── Path setup ────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

GENERATED_DIR = ROOT / "generated"
RENDER_SCRIPT = ROOT / "render" / "render_one.sh"
ESMINI_HOME = ROOT / "esmini" / "esmini-demo"

# Re-use helpers from existing pipeline module
from api.pipeline import (
    _call_bedrock,
    _extract_json,
    _load_system_prompt,
    _patch_xosc_road_path,
)


# ── Physics pre-flight helper ─────────────────────────────────────────────────

_db_instance = None
_db_lock = threading.Lock()


def _get_road_db():
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                from generator.road_network_db import RoadNetworkDB
                _db_instance = RoadNetworkDB()
    return _db_instance


def _physics_preflight(config: dict) -> dict:
    """Check physics plausibility and suggest fixes for timing mismatches.

    For junction_tbone: compute arrival times and suggest corrected s position
    if entities are >2s out of sync.

    Returns {"valid": bool, "warnings": [...], "suggested_fixes": {...}}
    """
    warnings = []
    fixes = {}
    pattern = config.get("pattern", "")
    init_actions = config.get("init_actions", [])
    routes = config.get("routes", [])

    if pattern == "junction_tbone" and len(init_actions) >= 2 and len(routes) >= 2:
        try:
            db = _get_road_db()
            from generator.scenario_builders.base import mph_to_mps

            ia_a, ia_b = init_actions[0], init_actions[1]
            road_a, lane_a, s_a = ia_a["road"], ia_a["lane"], ia_a["s"]
            road_b, lane_b, s_b = ia_b["road"], ia_b["lane"], ia_b["s"]
            speed_a = mph_to_mps(ia_a.get("speed_mph", 0))
            speed_b = mph_to_mps(ia_b.get("speed_mph", 0))

            if speed_a <= 0 or speed_b <= 0:
                return {"valid": True, "warnings": [], "suggested_fixes": {}}

            # Find shared junction
            r_a = db.road(road_a)
            r_b = db.road(road_b)
            shared_junctions = set()
            for j in [r_a.predecessor_junction, r_a.successor_junction]:
                if j is not None and j in (r_b.predecessor_junction, r_b.successor_junction):
                    shared_junctions.add(j)

            if not shared_junctions:
                return {"valid": True, "warnings": ["No shared junction found between entity roads"], "suggested_fixes": {}}

            junction_id = shared_junctions.pop()

            from generator.timing import distance_to_junction, sync_junction_arrival

            dist_a = distance_to_junction(db, road_a, lane_a, s_a, junction_id)
            dist_b = distance_to_junction(db, road_b, lane_b, s_b, junction_id)
            time_a = dist_a / speed_a
            time_b = dist_b / speed_b
            diff = abs(time_a - time_b)

            if diff > 2.0:
                warnings.append(
                    f"Arrival timing mismatch: entity_a arrives in {time_a:.1f}s, "
                    f"entity_b in {time_b:.1f}s (diff={diff:.1f}s). Auto-correcting entity_b position."
                )
                try:
                    plan = sync_junction_arrival(
                        db, road_a, lane_a, s_a, speed_a,
                        road_b, lane_b, speed_b, junction_id,
                    )
                    fixes["entity_b_s"] = round(plan.entity_b.s, 1)
                    fixes["entity_b_idx"] = 1
                except ValueError as e:
                    warnings.append(f"Could not auto-correct: {e}")
            elif diff > 0.5:
                warnings.append(
                    f"Arrival timing close: entity_a in {time_a:.1f}s, "
                    f"entity_b in {time_b:.1f}s (diff={diff:.1f}s)"
                )
        except Exception as e:
            warnings.append(f"Pre-flight check error: {e}")

    return {
        "valid": len(fixes) == 0,
        "warnings": warnings,
        "suggested_fixes": fixes,
    }


# ── Tool: generate_crash_config ───────────────────────────────────────────────

@tool
def generate_crash_config(description: str) -> str:
    """Generate a crash scenario config JSON from a natural language description.
    Returns the config as a JSON string, or a string starting with 'ERROR:' on failure."""
    GENERATED_DIR.mkdir(exist_ok=True)
    system_prompt = _load_system_prompt()
    messages = [
        {
            "role": "user",
            "content": (
                "Generate a config JSON for this crash scenario. "
                "Pick the most appropriate pattern and road/junction from the reference.\n\n"
                f"Description: {description}"
            ),
        }
    ]

    last_error = None
    for _attempt in range(10):
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
        except Exception as e:
            return f"ERROR: Bedrock call failed: {e}"

        try:
            config = _extract_json(text)
            config["situation_id"] = 999
            return json.dumps(config)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid JSON: {e}. Output ONLY a valid JSON object."},
            ]

    return f"ERROR: Could not parse JSON after 10 attempts: {last_error}"


# ── Tool: modify_config ───────────────────────────────────────────────────────

@tool
def modify_config(current_config_json: str, modification: str) -> str:
    """Modify an existing crash config based on user instructions or validation errors.
    Pass the full current config JSON string. Returns modified config JSON string,
    or a string starting with 'ERROR:' on failure."""
    system_prompt = _load_system_prompt()
    messages = [
        {
            "role": "user",
            "content": (
                f"Here is a crash config. Apply this modification: {modification}\n\n"
                f"Current config:\n{current_config_json}\n\n"
                "Output ONLY the complete corrected JSON config object."
            ),
        }
    ]

    last_error = None
    for _attempt in range(10):
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
        except Exception as e:
            return f"ERROR: Bedrock call failed: {e}"

        try:
            config = _extract_json(text)
            config["situation_id"] = 999
            return json.dumps(config)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid JSON: {e}. Output ONLY a valid JSON object."},
            ]

    return f"ERROR: Could not parse JSON after 10 attempts: {last_error}"


# ── Tool: build_scenario ──────────────────────────────────────────────────────

@tool
def build_scenario(config_json: str, session_id: str) -> str:
    """Build an OpenSCENARIO .xosc file from a config JSON string.
    Returns JSON: {"xosc_path": "...", "xosc_url": "/api/file/...", "error": null}"""
    GENERATED_DIR.mkdir(exist_ok=True)

    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as e:
        return json.dumps({"xosc_path": None, "xosc_url": None, "error": f"Invalid config JSON: {e}"})

    # Force unique name per session so files don't collide
    config["situation_id"] = 999
    config["scenario_name"] = f"chat_{session_id[:8]}"

    from generator.config_builder import ConfigBuilder
    try:
        builder = ConfigBuilder(config)
        xosc_path = builder.write(str(GENERATED_DIR))
        _patch_xosc_road_path(xosc_path)
        xosc_url = _file_url(Path(xosc_path).name, local_path=Path(xosc_path))
        return json.dumps({"xosc_path": xosc_path, "xosc_url": xosc_url, "error": None})
    except Exception as e:
        return json.dumps({"xosc_path": None, "xosc_url": None, "error": str(e)})


# ── Tool: validate_collision ──────────────────────────────────────────────────

@tool
def validate_collision(xosc_path: str) -> str:
    """Run esmini headless simulation to check if vehicles collide.
    MUST be called before render_scenario. Never skip this.
    Returns JSON: {"collision_detected": bool, "collision_time": float|null, "errors": [...]}"""
    from generator.validate import validate_scenario

    if not Path(xosc_path).exists():
        return json.dumps({
            "collision_detected": False,
            "collision_time": None,
            "errors": [f"File not found: {xosc_path}"],
        })

    try:
        emit_tool_progress("validate_collision", "Launching esmini headless simulation…")
        result = validate_scenario(xosc_path, sim_time=15.0)
        emit_tool_progress("validate_collision", "Parsing collision log…")
        out: dict = {
            "collision_detected": result.collision_detected,
            "collision_time": result.first_collision_time if result.collision_detected else None,
            "errors": result.errors,
        }
        if not result.collision_detected and result.closest_approach:
            ca = result.closest_approach
            out["closest_approach"] = {
                "distance_m": round(ca.distance_m, 2),
                "time": round(ca.time, 2),
                "entity_a": ca.entity_a,
                "entity_b": ca.entity_b,
            }
        if not result.collision_detected and result.diagnostics:
            diag = result.diagnostics
            out["diagnostics"] = {
                "entity_a_pos": list(diag.entity_a_pos),
                "entity_b_pos": list(diag.entity_b_pos),
                "entity_a_speed_mps": diag.entity_a_speed_mps,
                "entity_b_speed_mps": diag.entity_b_speed_mps,
                "closing_speed_mps": diag.closing_speed_mps,
                "miss_direction": diag.miss_direction,
                "trajectory": diag.trajectory,
            }
        return json.dumps(out)
    except Exception as e:
        return json.dumps({
            "collision_detected": False,
            "collision_time": None,
            "errors": [str(e)],
        })


# ── Tool: validate_with_variants ──────────────────────────────────────────────

def _generate_variants(config: dict) -> list[tuple[str, dict]]:
    """Generate speed-perturbed variants of a config.

    Returns [(label, config_copy), ...] with 5 entries:
    baseline + 4 speed perturbations of the last entity.
    """
    import copy
    variants = [("baseline", copy.deepcopy(config))]
    init_actions = config.get("init_actions", [])
    if len(init_actions) < 2:
        return variants

    # Perturb the last entity's speed (usually the approach vehicle)
    target_idx = len(init_actions) - 1
    base_speed = init_actions[target_idx].get("speed_mph", 25)
    entity_name = config.get("entities", [{}] * (target_idx + 1))[target_idx].get("name", "entity_b")

    for delta in [3, -3, 5, -5]:
        new_speed = max(5, min(60, base_speed + delta))
        if new_speed == base_speed:
            continue
        label = f"{entity_name} {'+' if delta > 0 else ''}{delta}mph"
        variant = copy.deepcopy(config)
        variant["init_actions"][target_idx]["speed_mph"] = new_speed
        # Also update matching maneuver speed if present
        for man in variant.get("maneuvers", []):
            if man.get("entity") == entity_name:
                for evt in man.get("events", []):
                    for act in evt.get("actions", []):
                        if act.get("type") in ("speed", "speed_smooth") and act.get("speed_mph") == base_speed:
                            act["speed_mph"] = new_speed
        variants.append((label, variant))

    return variants


def _build_and_validate_variant(
    idx: int,
    label: str,
    config: dict,
    session_id: str,
    generated_dir: Path,
) -> dict:
    """Build .xosc and validate one variant. Runs in a thread."""
    from generator.config_builder import ConfigBuilder
    from generator.validate import validate_scenario

    config["situation_id"] = 999
    config["scenario_name"] = f"chat_{session_id[:8]}_v{idx}"

    try:
        builder = ConfigBuilder(config)
        xosc_path = builder.write(str(generated_dir))
        _patch_xosc_road_path(xosc_path)
    except Exception as e:
        return {"idx": idx, "label": label, "error": f"build: {e}", "xosc_path": None}

    try:
        result = validate_scenario(xosc_path, sim_time=config.get("sim_time", 15.0))
    except Exception as e:
        return {"idx": idx, "label": label, "error": f"validate: {e}", "xosc_path": xosc_path}

    out = {
        "idx": idx,
        "label": label,
        "xosc_path": xosc_path,
        "collision_detected": result.collision_detected,
        "collision_time": result.first_collision_time if result.collision_detected else None,
        "closest_approach_m": None,
        "config": config,
        "diagnostics": None,
        "error": None,
    }
    if not result.collision_detected and result.closest_approach:
        out["closest_approach_m"] = round(result.closest_approach.distance_m, 2)
    if not result.collision_detected and result.diagnostics:
        d = result.diagnostics
        out["diagnostics"] = {
            "entity_a_pos": list(d.entity_a_pos),
            "entity_b_pos": list(d.entity_b_pos),
            "entity_a_speed_mps": d.entity_a_speed_mps,
            "entity_b_speed_mps": d.entity_b_speed_mps,
            "closing_speed_mps": d.closing_speed_mps,
            "miss_direction": d.miss_direction,
            "trajectory": d.trajectory,
        }
    return out


@tool
def validate_with_variants(config_json: str, session_id: str) -> str:
    """Build and validate a crash config plus speed variants in parallel.
    Runs physics pre-flight, generates 5 speed variants, validates all concurrently.
    Returns the best result (collision wins, otherwise closest miss with diagnostics).
    Use this instead of build_scenario + validate_collision for faster convergence."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    GENERATED_DIR.mkdir(exist_ok=True)

    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as e:
        return json.dumps({"collision_found": False, "error": f"Invalid JSON: {e}"})

    # Physics pre-flight: auto-correct timing mismatches
    emit_tool_progress("validate_with_variants", "Running physics pre-flight check…")
    preflight = _physics_preflight(config)

    if preflight["suggested_fixes"]:
        if "entity_b_s" in preflight["suggested_fixes"]:
            idx = preflight["suggested_fixes"].get("entity_b_idx", 1)
            config["init_actions"][idx]["s"] = preflight["suggested_fixes"]["entity_b_s"]
            # Update route start_s if present
            for route in config.get("routes", []):
                if route.get("entity") == config["init_actions"][idx].get("entity"):
                    route["start_s"] = preflight["suggested_fixes"]["entity_b_s"]

    # Generate variants
    variants = _generate_variants(config)
    emit_tool_progress("validate_with_variants", f"Building & validating {len(variants)} variants in parallel…")

    # Run all variants in parallel
    results: list[dict] = [None] * len(variants)
    completed = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for i, (label, variant_config) in enumerate(variants):
            fut = pool.submit(
                _build_and_validate_variant,
                i, label, variant_config, session_id, GENERATED_DIR,
            )
            futures[fut] = i

        for fut in as_completed(futures):
            i = futures[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = {"idx": i, "label": variants[i][0], "error": str(e), "xosc_path": None}
            completed += 1
            r = results[i]
            status = "COLLISION" if r and r.get("collision_detected") else (
                f"miss {r['closest_approach_m']}m" if r and r.get("closest_approach_m") is not None
                else r.get("error", "done") if r else "error"
            )
            emit_tool_progress("validate_with_variants", f"Variant {completed}/{len(variants)}: {variants[i][0]} → {status}")

    # Find best result: collision wins, otherwise closest miss
    collision_results = [r for r in results if r and r.get("collision_detected")]
    if collision_results:
        best = collision_results[0]
    else:
        miss_results = [r for r in results if r and r.get("closest_approach_m") is not None]
        best = min(miss_results, key=lambda r: r["closest_approach_m"]) if miss_results else (results[0] if results[0] else {"error": "all variants failed"})

    # Clean up non-winning .xosc files
    for r in results:
        if r and r.get("xosc_path") and r is not best:
            try:
                os.remove(r["xosc_path"])
            except OSError:
                pass

    # Build response
    best_variant = None
    if best and best.get("xosc_path"):
        xosc_url = _file_url(Path(best["xosc_path"]).name, local_path=Path(best["xosc_path"]))
        best_variant = {
            "config_json": json.dumps(best.get("config", config)),
            "xosc_path": best["xosc_path"],
            "xosc_url": xosc_url,
            "collision_time": best.get("collision_time"),
            "diagnostics": best.get("diagnostics"),
        }

    summary = []
    for r in results:
        if r is None:
            continue
        if r.get("error"):
            summary.append({"idx": r["idx"], "delta": r["label"], "result": f"ERROR: {r['error']}"})
        elif r.get("collision_detected"):
            summary.append({"idx": r["idx"], "delta": r["label"], "result": f"COLLISION {r['collision_time']:.1f}s"})
        elif r.get("closest_approach_m") is not None:
            summary.append({"idx": r["idx"], "delta": r["label"], "result": f"miss {r['closest_approach_m']}m"})
        else:
            summary.append({"idx": r["idx"], "delta": r["label"], "result": "no data"})

    response = {
        "collision_found": bool(collision_results),
        "preflight_warnings": preflight["warnings"],
        "best_variant": best_variant,
        "all_variants_summary": summary,
    }
    return json.dumps(response)


# ── Tool: render_scenario ─────────────────────────────────────────────────────

@tool
def render_scenario(xosc_path: str) -> str:
    """Render a validated OpenSCENARIO file to MP4 video. Only call after validate_collision succeeds.
    Returns JSON: {"mp4_url": "/api/file/....mp4", "thumbnail_url": "/api/file/....jpg", "error": null}"""
    if not Path(xosc_path).exists():
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": f"File not found: {xosc_path}"})

    env = {**os.environ, "ESMINI_HOME": str(ESMINI_HOME)}
    emit_tool_progress("render_scenario", "Launching esmini viewer…")
    try:
        proc = subprocess.Popen(
            ["bash", str(RENDER_SCRIPT), xosc_path, str(GENERATED_DIR)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        # Kill process after 180s (the stdout loop has no timeout on its own)
        timer = threading.Timer(180, proc.kill)
        timer.start()
        stderr_lines = []
        try:
            for line in proc.stdout:
                line = line.strip()
                if "Rendering" in line:
                    emit_tool_progress("render_scenario", "Capturing frames…")
                elif "Captured" in line:
                    emit_tool_progress("render_scenario", line)
                elif "Output:" in line:
                    emit_tool_progress("render_scenario", "Encoding complete")
                elif line:
                    stderr_lines.append(line)
            proc.wait()
        finally:
            timer.cancel()
    except Exception as e:
        try:
            proc.kill()
        except OSError:
            pass
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": str(e)})

    if proc.returncode != 0:
        err = " ".join(stderr_lines[-5:]) if stderr_lines else "unknown render error"
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": f"Render failed: {err}"})

    stem = Path(xosc_path).stem
    mp4 = GENERATED_DIR / f"{stem}.mp4"
    jpg = GENERATED_DIR / f"{stem}.jpg"

    if not mp4.exists():
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": "Render completed but MP4 not found"})

    return json.dumps({
        "mp4_url": _file_url(mp4.name, local_path=mp4),
        "thumbnail_url": _file_url(jpg.name, local_path=jpg) if jpg.exists() else None,
        "error": None,
    })
