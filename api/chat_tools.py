"""LangGraph tool functions for the crash scenario chat pipeline.

Each tool returns a JSON string so LangGraph can pass results back through
the message history as tool_result nodes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from langchain_core.tools import tool

from api.chat_progress import emit_tool_progress

# ── Helpers ───────────────────────────────────────────────────────────────────

S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "rfs-scenarios/")
S3_REGION = os.environ.get("S3_REGION", "us-west-1")

_s3_client = None

def _get_s3_client():
    """Lazy-init a boto3 S3 client, reusing the AWS_PROFILE from api.pipeline."""
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=S3_REGION)
    return _s3_client


def _upload_to_s3(local_path: Path) -> str | None:
    """Upload file to S3 and return a 24-hour presigned URL, or None if S3 is not configured."""
    if not S3_BUCKET:
        return None
    key = f"{S3_PREFIX}{local_path.name}"
    try:
        s3 = _get_s3_client()
        content_type = "video/mp4" if local_path.suffix == ".mp4" else \
                       "image/jpeg" if local_path.suffix == ".jpg" else \
                       "application/xml"
        s3.upload_file(str(local_path), S3_BUCKET, key, ExtraArgs={"ContentType": content_type})
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=86400,
        )
        return url
    except Exception as e:
        print(f"[S3] Upload failed for {local_path.name}: {e}")
        return None


def _file_url(filename: str, local_path: Path | None = None) -> str:
    """Return a URL for a generated file. Tries S3 upload first, falls back to local."""
    if local_path is not None:
        s3_url = _upload_to_s3(local_path)
        if s3_url:
            return s3_url
    base = os.environ.get("API_BASE_URL", "").rstrip("/")
    return f"{base}/api/file/{filename}"


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
        return json.dumps({
            "collision_detected": result.collision_detected,
            "collision_time": getattr(result, "collision_time", None),
            "errors": result.errors,
        })
    except Exception as e:
        return json.dumps({
            "collision_detected": False,
            "collision_time": None,
            "errors": [str(e)],
        })


# ── Tool: render_scenario ─────────────────────────────────────────────────────

@tool
def render_scenario(xosc_path: str) -> str:
    """Render a validated OpenSCENARIO file to MP4 video. Only call after validate_collision succeeds.
    Returns JSON: {"mp4_url": "/api/file/....mp4", "thumbnail_url": "/api/file/....jpg", "error": null}"""
    if not Path(xosc_path).exists():
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": f"File not found: {xosc_path}"})

    env = {**os.environ, "ESMINI_HOME": str(ESMINI_HOME)}
    emit_tool_progress("render_scenario", "Starting esmini screen capture…")
    try:
        result = subprocess.run(
            ["bash", str(RENDER_SCRIPT), xosc_path, str(GENERATED_DIR)],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": "Render timed out after 180s"})
    except Exception as e:
        return json.dumps({"mp4_url": None, "thumbnail_url": None, "error": str(e)})
    emit_tool_progress("render_scenario", "Encoding MP4 with ffmpeg…")

    if result.returncode != 0:
        err = result.stderr[-500:] if result.stderr else "unknown render error"
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
