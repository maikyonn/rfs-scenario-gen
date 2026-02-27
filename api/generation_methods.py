"""Generation method → system prompt mapping.

Two methods:
  - pattern_based: uses SUBAGENT_INSTRUCTIONS.md (named patterns + examples)
  - from_scratch:  uses FREEFORM_INSTRUCTIONS.md (primitives only, no patterns)

Both share the same ROAD_REFERENCE.md appendix and the same downstream
pipeline (Bedrock → ConfigBuilder → esmini validate → render).
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent
GENERATOR_DIR = ROOT / "generator"
INSTRUCTIONS_FILE = GENERATOR_DIR / "SUBAGENT_INSTRUCTIONS.md"
FREEFORM_FILE = GENERATOR_DIR / "FREEFORM_INSTRUCTIONS.md"
ROAD_REF_FILE = GENERATOR_DIR / "ROAD_REFERENCE.md"

_OUTPUT_RULES = (
    "OUTPUT RULES (CRITICAL):\n"
    "1. Output ONLY a valid JSON config object. Nothing else.\n"
    "2. No explanation, prose, or commentary before or after the JSON.\n"
    "3. You may wrap the JSON in ```json ... ``` fences or output raw JSON.\n"
    "4. The JSON must be directly parseable after stripping any code fences.\n"
)


def _build_prompt(instructions_path: Path) -> str:
    instructions = instructions_path.read_text()
    road_ref = ROAD_REF_FILE.read_text()
    return (
        "You are a crash scenario config generator for the Richmond, CA road network.\n\n"
        f"{_OUTPUT_RULES}\n"
        "---\n\n"
        f"{instructions}\n\n"
        "---\n\n"
        f"{road_ref}"
    )


def load_system_prompt(method: str) -> str:
    """Return the system prompt for the given generation method."""
    if method == "pattern_based":
        return _build_prompt(INSTRUCTIONS_FILE)
    elif method == "from_scratch":
        return _build_prompt(FREEFORM_FILE)
    else:
        raise ValueError(f"Unknown generation method: {method}")


METHODS = ["pattern_based", "from_scratch"]
