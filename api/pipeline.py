"""Generation pipeline: free-form text → config JSON → .xosc → MP4."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import boto3

ROOT = Path(__file__).parent.parent
GENERATOR_DIR = ROOT / "generator"
GENERATED_DIR = ROOT / "generated"
INSTRUCTIONS_FILE = GENERATOR_DIR / "SUBAGENT_INSTRUCTIONS.md"
ROAD_REF_FILE = GENERATOR_DIR / "ROAD_REFERENCE.md"
RENDER_SCRIPT = ROOT / "render" / "render_one.sh"
ESMINI_HOME = ROOT / "esmini" / "esmini-demo"
XODR_ABS = str(ROOT / "road_network" / "Richmond_entire_scene.xodr")

AWS_PROFILE = "Path-Emerging-Dev-147229569658"
AWS_REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

# Add project root to path so generator imports work
sys.path.insert(0, str(ROOT))


# ── Job state ─────────────────────────────────────────────────────────────────

STEP_LABELS = {
    "queued":             "Queued",
    "generating_config":  "Generating scenario config",
    "building_xosc":      "Building OpenSCENARIO file",
    "rendering":          "Rendering video",
    "complete":           "Done",
    "failed":             "Failed",
}

# In-memory job store: { job_id: dict }
_jobs: dict[str, dict] = {}


def create_job(job_id: str) -> dict:
    job = {
        "job_id": job_id,
        "status": "queued",
        "step_message": "Queued",
        "video_url": None,
        "thumbnail_url": None,
        "xosc_url": None,
        "config": None,
        "error": None,
        "created_at": time.time(),
    }
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def _update(job_id: str, status: str, **kwargs):
    if job_id not in _jobs:
        return
    _jobs[job_id].update({"status": status, "step_message": STEP_LABELS[status], **kwargs})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _patch_xosc_road_path(xosc_path: str):
    """Replace the relative road network path with an absolute path so esmini
    can find the .xodr regardless of where the .xosc file lives."""
    text = Path(xosc_path).read_text()
    # The framework emits: filepath="../../road_network/Richmond_entire_scene.xodr"
    patched = re.sub(
        r'filepath="[^"]*Richmond_entire_scene\.xodr"',
        f'filepath="{XODR_ABS}"',
        text,
    )
    Path(xosc_path).write_text(patched)


# ── Bedrock helpers ───────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    instructions = INSTRUCTIONS_FILE.read_text()
    road_ref = ROAD_REF_FILE.read_text()
    return (
        "You are a crash scenario config generator for the Richmond, CA road network.\n\n"
        "OUTPUT RULES (CRITICAL):\n"
        "1. Output ONLY a valid JSON config object. Nothing else.\n"
        "2. No explanation, prose, or commentary before or after the JSON.\n"
        "3. You may wrap the JSON in ```json ... ``` fences or output raw JSON.\n"
        "4. The JSON must be directly parseable after stripping any code fences.\n\n"
        "---\n\n"
        f"{instructions}\n\n"
        "---\n\n"
        f"{road_ref}"
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    raise ValueError(f"No JSON found in response: {text[:300]}")


def _call_bedrock(messages: list[dict], system_prompt: str) -> tuple[str, int, int]:
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    client = session.client("bedrock-runtime")
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": messages,
    }
    response = client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(response["body"].read())
    text = body["content"][0]["text"]
    return text, body["usage"]["input_tokens"], body["usage"]["output_tokens"]


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(job_id: str, description: str, max_retries: int = 3):
    """Full pipeline: description → config → .xosc → MP4. Updates job state in-place."""
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

    # ── Step 1: Generate config via Bedrock (with retry) ──────────────────────
    _update(job_id, "generating_config")
    config = None
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
        except Exception as e:
            _update(job_id, "failed", error=f"Bedrock error: {e}")
            return

        try:
            config = _extract_json(text)
            # Force a unique job-scoped scenario name so filenames don't collide
            config["situation_id"] = 999
            config["scenario_name"] = f"gen_{job_id[:8]}"
            break
        except (ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid JSON: {e}. Output ONLY a valid JSON object."},
            ]

    if config is None:
        _update(job_id, "failed", error=f"Could not parse JSON after {max_retries} attempts: {last_error}")
        return

    _jobs[job_id]["config"] = config

    # ── Step 2: Build .xosc ───────────────────────────────────────────────────
    _update(job_id, "building_xosc")

    # Write config to disk
    config_path = GENERATED_DIR / f"config_{job_id}.json"
    config_path.write_text(json.dumps(config, indent=2))

    # Build xosc via config_builder
    from generator.config_builder import ConfigBuilder
    try:
        builder = ConfigBuilder(config)
        xosc_path = builder.write(str(GENERATED_DIR))
        _patch_xosc_road_path(xosc_path)
    except Exception as e:
        # Retry once with the error fed back to Claude
        messages += [
            {"role": "assistant", "content": json.dumps(config, indent=2)},
            {
                "role": "user",
                "content": (
                    f"Building the .xosc failed: {e}\n\n"
                    "Fix the config (check road IDs, lane IDs, and s-values) "
                    "and output the corrected JSON."
                ),
            },
        ]
        _update(job_id, "generating_config")
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
            config = _extract_json(text)
            config["situation_id"] = 999
            config["scenario_name"] = f"gen_{job_id[:8]}"
            _jobs[job_id]["config"] = config
            config_path.write_text(json.dumps(config, indent=2))
            _update(job_id, "building_xosc")
            builder = ConfigBuilder(config)
            xosc_path = builder.write(str(GENERATED_DIR))
            _patch_xosc_road_path(xosc_path)
        except Exception as e2:
            _update(job_id, "failed", error=f"Build error: {e2}")
            return

    _jobs[job_id]["xosc_url"] = f"/api/file/{Path(xosc_path).name}"

    # ── Step 3: Validate collision ────────────────────────────────────────────
    # Quick validation — if it fails retry once
    from generator.validate import validate_scenario
    val = validate_scenario(xosc_path, sim_time=config.get("sim_time", 15.0))

    if not val.collision_detected:
        real_errors = [e for e in val.errors if "Roadmark" not in e and "signalReference" not in e]
        err_msg = "; ".join(real_errors[:2]) if real_errors else "no collision detected"
        if val.closest_approach:
            ca = val.closest_approach
            err_msg += (
                f". Closest approach: {ca.distance_m}m between "
                f"{ca.entity_a} and {ca.entity_b} at t={ca.time}s"
            )
        messages += [
            {"role": "assistant", "content": json.dumps(config, indent=2)},
            {
                "role": "user",
                "content": (
                    f"Validation failed: {err_msg}\n\n"
                    "Adjust entity positions/speeds so the vehicles collide. "
                    "Output the corrected config JSON."
                ),
            },
        ]
        _update(job_id, "generating_config")
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
            config = _extract_json(text)
            config["situation_id"] = 999
            config["scenario_name"] = f"gen_{job_id[:8]}"
            config_path.write_text(json.dumps(config, indent=2))
            builder = ConfigBuilder(config)
            xosc_path = builder.write(str(GENERATED_DIR))
            _patch_xosc_road_path(xosc_path)
            _jobs[job_id]["xosc_url"] = f"/api/file/{Path(xosc_path).name}"
            _update(job_id, "building_xosc")
        except Exception as e:
            _update(job_id, "failed", error=f"Retry build error: {e}")
            return

        # Re-validate after retry — fail the job if still no collision
        val2 = validate_scenario(xosc_path, sim_time=config.get("sim_time", 15.0))
        if not val2.collision_detected:
            real_errors2 = [e for e in val2.errors if "Roadmark" not in e and "signalReference" not in e]
            err2 = "; ".join(real_errors2[:2]) if real_errors2 else "no collision detected after retry"
            _update(job_id, "failed", error=f"Validation failed after retry: {err2}")
            return

    # ── Step 4: Render video ──────────────────────────────────────────────────
    _update(job_id, "rendering")
    env = {
        **os.environ,
        "ESMINI_HOME": str(ESMINI_HOME),
    }
    result = subprocess.run(
        ["bash", str(RENDER_SCRIPT), xosc_path, str(GENERATED_DIR)],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    if result.returncode != 0:
        _update(job_id, "failed", error=f"Render failed:\n{result.stderr[-500:]}")
        return

    # Find output files
    stem = Path(xosc_path).stem
    mp4 = GENERATED_DIR / f"{stem}.mp4"
    jpg = GENERATED_DIR / f"{stem}.jpg"

    if not mp4.exists():
        _update(job_id, "failed", error="Render completed but MP4 not found")
        return

    _update(
        job_id,
        "complete",
        video_url=f"/api/file/{mp4.name}",
        thumbnail_url=f"/api/file/{jpg.name}" if jpg.exists() else None,
        xosc_url=f"/api/file/{Path(xosc_path).name}",
    )
