"""Async batch worker for processing generation jobs.

Consumes from an asyncio.Queue, runs the full pipeline
(Bedrock → ConfigBuilder → validate → render) in a thread executor,
and updates the generations table at each step.
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path

from api.db import get_generation, update_generation
from api.generation_methods import load_system_prompt

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
GENERATED_DIR = ROOT / "generated"
RENDER_SCRIPT = ROOT / "render" / "render_one.sh"
ESMINI_HOME = ROOT / "esmini" / "esmini-demo"

# Global job queue
_queue: asyncio.Queue | None = None


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def enqueue_job(generation_id: str, method: str, description: str, record_id: int, road_context: str | None = None):
    """Add a job to the queue. Must be called from an async context."""
    q = get_queue()
    q.put_nowait({
        "generation_id": generation_id,
        "method": method,
        "description": description,
        "record_id": record_id,
        "road_context": road_context,
    })


async def start_worker():
    """Start the background worker coroutine."""
    q = get_queue()
    logger.info("Batch worker started")
    while True:
        job = await q.get()
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _sync_generate, job)
        except Exception as e:
            logger.error("Worker error for generation %s: %s", job.get("generation_id"), e)
        finally:
            q.task_done()


def _sync_generate(job: dict):
    """Synchronous pipeline — runs in thread executor."""
    from api.pipeline import (
        _call_bedrock,
        _extract_json,
        _patch_xosc_road_path,
    )

    gen_id = job["generation_id"]
    method = job["method"]
    description = job["description"]
    road_context = job.get("road_context")

    start_time = time.monotonic()
    GENERATED_DIR.mkdir(exist_ok=True)

    system_prompt = load_system_prompt(method)

    if road_context and road_context != "unspecified":
        user_content = (
            "Generate a config JSON for this crash scenario.\n"
            f"Road context: {road_context}\n"
            f"Description: {description}\n\n"
            "Pick the road from the reference that best matches the road context. "
            "If the exact lane count isn't available, use the widest matching road "
            "and the offset parameter for lateral positioning within a lane."
        )
    else:
        user_content = (
            "Generate a config JSON for this crash scenario. "
            "Pick the most appropriate road/junction from the reference.\n\n"
            f"Description: {description}"
        )

    messages = [{"role": "user", "content": user_content}]

    # ── Step 1: Generate config via Bedrock ──────────────────────────────────
    update_generation(gen_id, status="generating")
    config = None
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
        except Exception as e:
            update_generation(gen_id, status="failed", error=f"Bedrock error: {e}",
                              duration_ms=_elapsed_ms(start_time))
            return

        try:
            config = _extract_json(text)
            config["situation_id"] = 999
            config["scenario_name"] = f"exp_{gen_id[:8]}"
            break
        except (ValueError, json.JSONDecodeError) as e:
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"Invalid JSON: {e}. Output ONLY a valid JSON object."},
            ]

    if config is None:
        update_generation(gen_id, status="failed", error="Could not parse JSON after retries",
                          duration_ms=_elapsed_ms(start_time))
        return

    update_generation(gen_id, config_json=json.dumps(config))

    # ── Step 2: Build .xosc ──────────────────────────────────────────────────
    update_generation(gen_id, status="validating")

    import sys
    sys.path.insert(0, str(ROOT))
    from generator.config_builder import ConfigBuilder

    config_path = GENERATED_DIR / f"config_{gen_id[:8]}.json"
    config_path.write_text(json.dumps(config, indent=2))

    try:
        builder = ConfigBuilder(config)
        xosc_path = builder.write(str(GENERATED_DIR))
        _patch_xosc_road_path(xosc_path)
    except Exception as e:
        # Retry once with error feedback
        messages += [
            {"role": "assistant", "content": json.dumps(config, indent=2)},
            {"role": "user", "content": f"Build failed: {e}\nFix and output corrected JSON."},
        ]
        try:
            text, _, _ = _call_bedrock(messages, system_prompt)
            config = _extract_json(text)
            config["situation_id"] = 999
            config["scenario_name"] = f"exp_{gen_id[:8]}"
            update_generation(gen_id, config_json=json.dumps(config))
            config_path.write_text(json.dumps(config, indent=2))
            builder = ConfigBuilder(config)
            xosc_path = builder.write(str(GENERATED_DIR))
            _patch_xosc_road_path(xosc_path)
        except Exception as e2:
            update_generation(gen_id, status="failed", error=f"Build error: {e2}",
                              duration_ms=_elapsed_ms(start_time))
            return

    update_generation(gen_id, xosc_path=xosc_path)

    # ── Step 3: Validate collision (retry up to 3x) ─────────────────────────
    from generator.validate import validate_scenario

    collision_detected = False
    collision_time = None

    for val_attempt in range(3):
        val = validate_scenario(xosc_path, sim_time=config.get("sim_time", 15.0))
        if val.collision_detected:
            collision_detected = True
            collision_time = getattr(val, "collision_time", None)
            break

        if val_attempt < 2:
            # Feed error back to LLM with closest-approach info
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
                {"role": "user", "content": f"Validation failed: {err_msg}\nAdjust positions/speeds for collision. Output corrected JSON."},
            ]
            try:
                text, _, _ = _call_bedrock(messages, system_prompt)
                config = _extract_json(text)
                config["situation_id"] = 999
                config["scenario_name"] = f"exp_{gen_id[:8]}"
                update_generation(gen_id, config_json=json.dumps(config))
                config_path.write_text(json.dumps(config, indent=2))
                builder = ConfigBuilder(config)
                xosc_path = builder.write(str(GENERATED_DIR))
                _patch_xosc_road_path(xosc_path)
                update_generation(gen_id, xosc_path=xosc_path)
            except Exception:
                break  # give up on retry

    update_generation(
        gen_id,
        collision_detected=int(collision_detected),
        collision_time=collision_time,
    )

    # ── Step 4: Render video ─────────────────────────────────────────────────
    update_generation(gen_id, status="rendering")

    env = {**os.environ, "ESMINI_HOME": str(ESMINI_HOME)}
    try:
        result = subprocess.run(
            ["bash", str(RENDER_SCRIPT), xosc_path, str(GENERATED_DIR)],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
    except (subprocess.TimeoutExpired, Exception) as e:
        update_generation(gen_id, status="failed", error=f"Render error: {e}",
                          duration_ms=_elapsed_ms(start_time))
        return

    if result.returncode != 0:
        update_generation(gen_id, status="failed",
                          error=f"Render failed: {result.stderr[-500:]}",
                          duration_ms=_elapsed_ms(start_time))
        return

    stem = Path(xosc_path).stem
    mp4 = GENERATED_DIR / f"{stem}.mp4"
    jpg = GENERATED_DIR / f"{stem}.jpg"

    if not mp4.exists():
        update_generation(gen_id, status="failed", error="MP4 not found after render",
                          duration_ms=_elapsed_ms(start_time))
        return

    # Try S3 upload
    mp4_url = _try_upload(mp4) or f"/api/file/{mp4.name}"
    thumb_url = (_try_upload(jpg) or f"/api/file/{jpg.name}") if jpg.exists() else None

    update_generation(
        gen_id,
        status="complete",
        mp4_url=mp4_url,
        thumbnail_url=thumb_url,
        duration_ms=_elapsed_ms(start_time),
    )
    logger.info("Generation %s complete (collision=%s, %.1fs)",
                gen_id[:8], collision_detected, _elapsed_ms(start_time) / 1000)


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _try_upload(local_path: Path) -> str | None:
    """Try uploading to S3, return presigned URL or None."""
    try:
        from api.chat_tools import _upload_to_s3
        return _upload_to_s3(local_path)
    except Exception:
        return None
