#!/usr/bin/env python3
"""bedrock_runner.py — Generate OpenSCENARIO configs via Claude Sonnet 4.6 on AWS Bedrock.

Observability via Laminar (app.lmnr.ai). Each run, situation, LLM call, and
validation step is traced as a nested span.

Usage:
    python bedrock_runner.py --all
    python bedrock_runner.py --ids 1 5 42
    python bedrock_runner.py --pattern junction_tbone
    python bedrock_runner.py --all --workers 4 --skip-existing
    python bedrock_runner.py --all --no-validate
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from lmnr import Laminar, observe

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
GENERATOR_DIR = ROOT / "generator"
SITUATIONS_FILE = ROOT / "crash_situations.json"
CONFIGS_DIR = GENERATOR_DIR / "configs"
OUTPUT_DIR = GENERATOR_DIR / "output"
INSTRUCTIONS_FILE = GENERATOR_DIR / "SUBAGENT_INSTRUCTIONS.md"
ROAD_REF_FILE = GENERATOR_DIR / "ROAD_REFERENCE.md"
STATUS_FILE = ROOT / "run_status.json"

# ── AWS Config ────────────────────────────────────────────────────────────────
DEFAULT_PROFILE = "Path-Emerging-Dev-147229569658"
DEFAULT_REGION = "us-west-2"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

# ── Pricing (USD per million tokens, Claude Sonnet 4.6) ───────────────────────
COST_PER_1M_IN = 3.00
COST_PER_1M_OUT = 15.00


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SituationResult:
    situation_id: int
    pattern: str
    status: str           # "pass" | "fail" | "error" | "skipped" | "generated"
    attempts: int = 0
    collision_time: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    xosc_path: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_situations(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)["situations"]


def load_system_prompt() -> str:
    """Combine SUBAGENT_INSTRUCTIONS + ROAD_REFERENCE with a JSON-only output header."""
    instructions = INSTRUCTIONS_FILE.read_text()
    road_ref = ROAD_REF_FILE.read_text()
    return (
        "You are a crash scenario config generator for the Richmond, CA road network.\n\n"
        "OUTPUT RULES (CRITICAL):\n"
        "1. Output ONLY a valid JSON config object. Nothing else.\n"
        "2. No explanation, prose, or commentary before or after the JSON.\n"
        "3. You may wrap the JSON in ```json ... ``` fences or output raw JSON — both accepted.\n"
        "4. The JSON must be directly parseable after stripping any code fences.\n\n"
        "---\n\n"
        f"{instructions}\n\n"
        "---\n\n"
        f"{road_ref}"
    )


def extract_json(text: str) -> dict:
    """Extract and parse the first JSON object from Claude's response.

    Handles: raw JSON, ```json...```, ``` ... ```, JSON embedded in prose.
    """
    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fenced code block: ```json { ... } ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))

    # First bare {...} block
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))

    raise ValueError(f"No JSON found in response (first 300 chars): {text[:300]}")


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * COST_PER_1M_IN
        + output_tokens / 1_000_000 * COST_PER_1M_OUT
    )


def retry_message(config: dict, error: str) -> str:
    """Build the user message for a retry turn, including the failing config."""
    return (
        f"Validation FAILED: {error}\n\n"
        f"Your previous config:\n```json\n{json.dumps(config, indent=2)}\n```\n\n"
        "Adjust entity positions and/or speeds so the vehicles actually collide. "
        "Output the corrected config JSON only."
    )


# ── Laminar-traced functions ───────────────────────────────────────────────────

@observe(name="llm_call", span_type="LLM")
def call_bedrock(
    messages: list[dict],
    system_prompt: str,
    bedrock_client,
) -> tuple[str, int, int]:
    """Single Bedrock invocation. Returns (response_text, input_tokens, output_tokens)."""
    t0 = time.time()
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": messages,
    }
    response = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(payload),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(response["body"].read())
    text = body["content"][0]["text"]
    in_tok = body["usage"]["input_tokens"]
    out_tok = body["usage"]["output_tokens"]
    latency_ms = int((time.time() - t0) * 1000)

    Laminar.set_span_attributes({
        # Standard gen_ai attributes — Laminar uses these for the Tokens column
        "gen_ai.request.model": MODEL_ID,
        "gen_ai.usage.input_tokens": in_tok,
        "gen_ai.usage.output_tokens": out_tok,
        # Extra context
        "llm.latency_ms": latency_ms,
        "llm.cost_usd": round(compute_cost(in_tok, out_tok), 6),
    })
    Laminar.set_span_output(text[:500])  # truncate for dashboard readability
    return text, in_tok, out_tok


@observe(name="build_xosc")
def build_xosc(config: dict) -> str:
    """Build .xosc from a config dict. Returns the output file path."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    from generator.config_builder import ConfigBuilder
    builder = ConfigBuilder(config)
    path = builder.write(str(OUTPUT_DIR))
    Laminar.set_span_attributes({"xosc.path": os.path.basename(path)})
    return path


@observe(name="validate")
def run_validation(xosc_path: str, sim_time: float):
    """Run esmini collision detection. Returns ValidationResult."""
    from generator.validate import validate_scenario
    result = validate_scenario(xosc_path, sim_time=sim_time)
    Laminar.set_span_attributes({
        "validate.passed": result.collision_detected,
        "validate.collision_time_s": result.first_collision_time,
        "validate.entity_pairs": str(result.entity_pairs),
        "validate.errors": "; ".join(result.errors[:3]) if result.errors else "",
        "validate.xosc_path": os.path.basename(xosc_path),
    })
    return result


@observe(name="situation")
def run_situation(
    situation: dict,
    system_prompt: str,
    bedrock_client,
    max_retries: int,
    skip_existing: bool,
    do_validate: bool,
) -> SituationResult:
    """Generate (and optionally validate) the config for one crash situation.

    Retry loop: on parse/build/validation failure, the error + previous config
    are appended to the conversation so Claude can self-correct.
    """
    sid = situation["id"]
    pattern = situation["pattern"]
    config_path = CONFIGS_DIR / f"situation_{sid:03d}.json"

    Laminar.set_span_attributes({
        "situation.id": sid,
        "situation.pattern": pattern,
        "situation.entities": ", ".join(situation.get("entities", [])),
        "situation.speeds_mph": str(situation.get("speeds_mph", [])),
        "situation.description": situation["description"][:200],
    })

    if skip_existing and config_path.exists():
        print(f"  [{sid:03d}] SKIP  (config exists)")
        return SituationResult(situation_id=sid, pattern=pattern, status="skipped")

    total_in = total_out = 0
    # Conversation history — grows on retry with error context
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "Generate the config JSON for this crash situation:\n\n"
                + json.dumps(situation, indent=2)
            ),
        }
    ]
    last_config: dict | None = None

    for attempt in range(1, max_retries + 1):
        Laminar.set_span_attributes({f"attempt_{attempt}.started": True})

        # ── LLM call ──────────────────────────────────────────────────────────
        try:
            text, in_tok, out_tok = call_bedrock(messages, system_prompt, bedrock_client)
        except ClientError as e:
            err = f"Bedrock error: {e}"
            print(f"  [{sid:03d}] attempt {attempt} BEDROCK ERROR: {err}")
            Laminar.set_span_attributes({f"attempt_{attempt}.outcome": "bedrock_error"})
            return SituationResult(
                situation_id=sid, pattern=pattern, status="error",
                attempts=attempt, input_tokens=total_in, output_tokens=total_out, error=err,
            )
        total_in += in_tok
        total_out += out_tok

        # ── Parse JSON ────────────────────────────────────────────────────────
        try:
            config = extract_json(text)
            last_config = config
        except (ValueError, json.JSONDecodeError) as e:
            err = f"JSON parse error: {e}"
            print(f"  [{sid:03d}] attempt {attempt} PARSE FAIL")
            Laminar.set_span_attributes({f"attempt_{attempt}.outcome": "parse_fail"})
            messages += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"Your response was not valid JSON. Error: {err}\n\n"
                        "Output ONLY a valid JSON object, nothing else."
                    ),
                },
            ]
            continue

        # ── Write config JSON ─────────────────────────────────────────────────
        CONFIGS_DIR.mkdir(exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2))

        if not do_validate:
            print(f"  [{sid:03d}] attempt {attempt} GENERATED (validation skipped)")
            Laminar.set_span_attributes({
                f"attempt_{attempt}.outcome": "generated",
                "situation.total_input_tokens": total_in,
                "situation.total_output_tokens": total_out,
            })
            return SituationResult(
                situation_id=sid, pattern=pattern, status="generated",
                attempts=attempt, input_tokens=total_in, output_tokens=total_out,
                xosc_path=str(config_path),
            )

        # ── Build .xosc ───────────────────────────────────────────────────────
        try:
            xosc_path = build_xosc(config)
        except Exception as e:
            err = str(e)
            print(f"  [{sid:03d}] attempt {attempt} BUILD FAIL: {err[:80]}")
            Laminar.set_span_attributes({f"attempt_{attempt}.outcome": "build_fail"})
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": retry_message(config, f"Build error: {err}")},
            ]
            continue

        # ── Collision validation ───────────────────────────────────────────────
        val = run_validation(xosc_path, config.get("sim_time", 15.0))

        if val.collision_detected:
            pairs = ", ".join(f"{a}+{b}" for a, b in val.entity_pairs)
            print(
                f"  [{sid:03d}] attempt {attempt} PASS  "
                f"(t={val.first_collision_time:.2f}s  {pairs})"
            )
            Laminar.set_span_attributes({
                f"attempt_{attempt}.outcome": "pass",
                "situation.status": "pass",
                "situation.total_attempts": attempt,
                "situation.total_input_tokens": total_in,
                "situation.total_output_tokens": total_out,
                "situation.total_cost_usd": round(compute_cost(total_in, total_out), 6),
            })
            return SituationResult(
                situation_id=sid, pattern=pattern, status="pass",
                attempts=attempt, collision_time=val.first_collision_time,
                input_tokens=total_in, output_tokens=total_out, xosc_path=xosc_path,
            )

        # Validation failed — build retry context.
        # Prefer "no collision detected" over esmini warnings (which are often
        # harmless noise) so Claude focuses on fixing vehicle positions/timing.
        real_errors = [e for e in val.errors if "Roadmark" not in e and "signalReference" not in e]
        esmini_err = "; ".join(real_errors[:3]) if real_errors else "no collision detected"
        print(f"  [{sid:03d}] attempt {attempt} FAIL  ({esmini_err})")
        Laminar.set_span_attributes({f"attempt_{attempt}.outcome": "no_collision"})
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": retry_message(config, esmini_err)},
        ]

    # Exhausted retries
    Laminar.set_span_attributes({
        "situation.status": "fail",
        "situation.total_attempts": max_retries,
        "situation.total_input_tokens": total_in,
        "situation.total_output_tokens": total_out,
    })
    print(f"  [{sid:03d}] FAIL  after {max_retries} attempts")
    return SituationResult(
        situation_id=sid, pattern=pattern, status="fail",
        attempts=max_retries, input_tokens=total_in, output_tokens=total_out,
        error=f"No collision after {max_retries} attempts",
    )


@observe(name="bedrock_run")
def run_batch(
    situations: list[dict],
    system_prompt: str,
    bedrock_client,
    max_retries: int,
    skip_existing: bool,
    do_validate: bool,
    workers: int,
) -> list[SituationResult]:
    """Orchestrate generation for a batch of situations (sequential or parallel)."""
    Laminar.set_span_attributes({
        "run.total_situations": len(situations),
        "run.workers": workers,
        "run.model": MODEL_ID,
        "run.max_retries": max_retries,
        "run.skip_existing": skip_existing,
        "run.validate": do_validate,
    })

    results: list[SituationResult] = []

    if workers == 1:
        for s in situations:
            results.append(
                run_situation(s, system_prompt, bedrock_client, max_retries, skip_existing, do_validate)
            )
    else:
        # Note: situation spans appear as top-level in Laminar when run in parallel
        # threads (OTel context is thread-local). llm_call / validate spans are
        # still correctly nested under their situation span within each thread.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    run_situation, s, system_prompt, bedrock_client,
                    max_retries, skip_existing, do_validate
                ): s
                for s in situations
            }
            for fut in as_completed(futures):
                results.append(fut.result())

    results.sort(key=lambda r: r.situation_id)

    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status in ("fail", "error"))
    total_in = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)

    Laminar.set_span_attributes({
        "run.passed": passed,
        "run.failed": failed,
        "run.total_input_tokens": total_in,
        "run.total_output_tokens": total_out,
        "run.estimated_cost_usd": round(compute_cost(total_in, total_out), 4),
    })
    return results


# ── Status persistence ────────────────────────────────────────────────────────

def save_status(results: list[SituationResult]) -> None:
    """Merge results into run_status.json for resumption."""
    existing: dict = {}
    if STATUS_FILE.exists():
        with open(STATUS_FILE) as f:
            existing = json.load(f)
    for r in results:
        if r.status != "skipped":
            existing[str(r.situation_id)] = {
                "status": r.status,
                "attempts": r.attempts,
                "collision_time": r.collision_time,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "error": r.error,
            }
    with open(STATUS_FILE, "w") as f:
        json.dump(existing, f, indent=2)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(results: list[SituationResult]) -> None:
    passed   = [r for r in results if r.status == "pass"]
    failed   = [r for r in results if r.status == "fail"]
    errored  = [r for r in results if r.status == "error"]
    skipped  = [r for r in results if r.status == "skipped"]
    gen_only = [r for r in results if r.status == "generated"]
    total_in  = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)

    print("\n" + "=" * 60)
    print(f"  PASS      : {len(passed):>4}")
    print(f"  FAIL      : {len(failed):>4}")
    print(f"  ERROR     : {len(errored):>4}")
    print(f"  GENERATED : {len(gen_only):>4}  (no-validate mode)")
    print(f"  SKIPPED   : {len(skipped):>4}")
    print(f"  Tokens    : {total_in:,} in / {total_out:,} out")
    print(f"  Cost est. : ${compute_cost(total_in, total_out):.4f}")
    if failed or errored:
        ids = sorted(r.situation_id for r in failed + errored)
        print(f"  Failed IDs: {ids}")
    print("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate OpenSCENARIO configs via Claude Sonnet 4.6 on AWS Bedrock.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python bedrock_runner.py --all\n"
            "  python bedrock_runner.py --ids 1 5 42\n"
            "  python bedrock_runner.py --pattern junction_tbone\n"
            "  python bedrock_runner.py --all --workers 4 --skip-existing\n"
            "  python bedrock_runner.py --ids 1 --no-validate\n"
        ),
    )

    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Process all 100 situations")
    scope.add_argument("--ids", nargs="+", type=int, metavar="ID", help="Specific situation IDs")
    scope.add_argument("--pattern", metavar="PAT", help="Filter by pattern name")

    parser.add_argument("--workers",       type=int, default=1,   help="Parallel workers (default: 1)")
    parser.add_argument("--max-retries",   type=int, default=3,   help="Max retries per situation (default: 3)")
    parser.add_argument("--skip-existing", action="store_true",   help="Skip situations whose config JSON already exists")
    parser.add_argument("--no-validate",   action="store_true",   help="Generate configs without running esmini validation")
    parser.add_argument("--profile",       default=DEFAULT_PROFILE, help=f"AWS SSO profile (default: {DEFAULT_PROFILE})")
    parser.add_argument("--region",        default=DEFAULT_REGION,  help=f"AWS region (default: {DEFAULT_REGION})")

    args = parser.parse_args()

    # ── Laminar ──────────────────────────────────────────────────────────────
    lmnr_key = os.environ.get(
        "LMNR_PROJECT_API_KEY",
        "z4TSHG197ynxGtaGb6reicRkdFK9m1auFfOA6bkCGy9uuxiBOgzz0dtH7wIVTG7q",
    )
    Laminar.initialize(project_api_key=lmnr_key)

    # ── Bedrock ───────────────────────────────────────────────────────────────
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    bedrock = session.client("bedrock-runtime")

    # ── Situations ────────────────────────────────────────────────────────────
    all_situations = load_situations(SITUATIONS_FILE)

    if args.all:
        situations = all_situations
    elif args.ids:
        id_set = set(args.ids)
        situations = [s for s in all_situations if s["id"] in id_set]
        if not situations:
            print(f"Error: no situations found with IDs {args.ids}")
            sys.exit(1)
    else:
        situations = [s for s in all_situations if s["pattern"] == args.pattern]
        if not situations:
            available = sorted({s["pattern"] for s in all_situations})
            print(f"Error: no situations with pattern '{args.pattern}'.")
            print(f"Available patterns: {available}")
            sys.exit(1)

    # ── System prompt ─────────────────────────────────────────────────────────
    # Add generator dir to path so config_builder + validate can import correctly
    sys.path.insert(0, str(ROOT))
    system_prompt = load_system_prompt()

    print(f"Generating {len(situations)} situation(s)")
    print(f"Model   : {MODEL_ID}")
    print(f"Workers : {args.workers}  |  Max retries: {args.max_retries}")
    print(f"Validate: {'yes' if not args.no_validate else 'no'}  |  Skip existing: {args.skip_existing}")
    print(f"Laminar : enabled  (traces → app.lmnr.ai)")
    print("-" * 60)

    # ── Run ───────────────────────────────────────────────────────────────────
    results = run_batch(
        situations=situations,
        system_prompt=system_prompt,
        bedrock_client=bedrock,
        max_retries=args.max_retries,
        skip_existing=args.skip_existing,
        do_validate=not args.no_validate,
        workers=args.workers,
    )

    save_status(results)
    print_summary(results)


if __name__ == "__main__":
    main()
