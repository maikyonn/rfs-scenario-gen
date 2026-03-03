"""Run esmini headless with collision detection and parse results."""

import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from glob import glob


@dataclass
class CollisionEvent:
    time: float
    entity_a: str
    entity_b: str
    dissolved: bool = False


@dataclass
class ClosestApproach:
    distance_m: float
    time: float
    entity_a: str
    entity_b: str


@dataclass
class ValidationResult:
    xosc_path: str
    collision_detected: bool
    first_collision_time: float = 0.0
    collisions: list = field(default_factory=list)  # list of CollisionEvent
    entity_pairs: list = field(default_factory=list)  # list of (str, str)
    errors: list = field(default_factory=list)  # any esmini errors
    returncode: int = 0
    closest_approach: ClosestApproach | None = None


# Regex for esmini collision log lines
# Example: "[3.201] [warn] Collision between car_c and car_d"
_COLLISION_RE = re.compile(
    r"\[(\d+\.\d+)\]\s+\[warn\]\s+Collision between (\S+) and (\S+)"
)
_COLLISION_DISSOLVED_RE = re.compile(
    r"\[(\d+\.\d+)\]\s+\[warn\]\s+Collision between (\S+) and (\S+) dissolved"
)


def _find_esmini() -> str:
    """Find esmini binary, checking ESMINI_HOME and common locations."""
    if "ESMINI_HOME" in os.environ:
        path = os.path.join(os.environ["ESMINI_HOME"], "bin", "esmini")
        if os.path.isfile(path):
            return path

    # Try relative to this file
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base, "esmini", "esmini-demo", "bin", "esmini"),
        os.path.join(base, "esmini", "bin", "esmini"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    raise FileNotFoundError(
        "Cannot find esmini binary. Set ESMINI_HOME or place esmini in project root."
    )


def _compute_closest_approach(csv_path: str) -> ClosestApproach | None:
    """Parse esmini CSV logger output and find minimum distance between entities."""
    try:
        with open(csv_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None

    # Find header line (contains "World_Position_X")
    header_idx = None
    for i, line in enumerate(lines):
        if "World_Position_X" in line:
            header_idx = i
            break
    if header_idx is None:
        return None

    header = [h.strip() for h in lines[header_idx].split(",")]

    # Find per-entity position and name columns from header
    # Format: "#1 World_Position_X [m]", "#1 Entity_Name [-]", etc.
    entity_xy: dict[int, dict[str, int]] = {}
    name_cols: dict[int, int] = {}

    for i, h in enumerate(header):
        m = re.match(r"#(\d+)\s+World_Position_X", h)
        if m:
            entity_xy.setdefault(int(m.group(1)), {})["x"] = i
        m = re.match(r"#(\d+)\s+World_Position_Y", h)
        if m:
            entity_xy.setdefault(int(m.group(1)), {})["y"] = i
        m = re.match(r"#(\d+)\s+Entity_Name", h)
        if m:
            name_cols[int(m.group(1))] = i

    valid = {k: v for k, v in entity_xy.items() if "x" in v and "y" in v}
    if len(valid) < 2:
        return None

    # Find time column
    time_col = 1  # default
    for i, h in enumerate(header):
        if "TimeStamp" in h:
            time_col = i
            break

    entity_nums = sorted(valid.keys())
    min_dist = float("inf")
    min_time = 0.0
    min_a = ""
    min_b = ""

    for line in lines[header_idx + 1 :]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            t = float(parts[time_col])
        except (IndexError, ValueError):
            continue

        positions = {}
        names = {}
        for num in entity_nums:
            try:
                positions[num] = (
                    float(parts[valid[num]["x"]]),
                    float(parts[valid[num]["y"]]),
                )
            except (IndexError, ValueError):
                continue
            if num in name_cols:
                try:
                    names[num] = parts[name_cols[num]].strip()
                except IndexError:
                    names[num] = f"entity_{num}"
            else:
                names[num] = f"entity_{num}"

        for i in range(len(entity_nums)):
            for j in range(i + 1, len(entity_nums)):
                n1, n2 = entity_nums[i], entity_nums[j]
                if n1 not in positions or n2 not in positions:
                    continue
                d = math.hypot(
                    positions[n2][0] - positions[n1][0],
                    positions[n2][1] - positions[n1][1],
                )
                if d < min_dist:
                    min_dist = d
                    min_time = t
                    min_a = names.get(n1, f"entity_{n1}")
                    min_b = names.get(n2, f"entity_{n2}")

    if min_dist == float("inf"):
        return None

    return ClosestApproach(
        distance_m=round(min_dist, 2),
        time=round(min_time, 3),
        entity_a=min_a,
        entity_b=min_b,
    )


def validate_scenario(
    xosc_path: str,
    sim_time: float = 15.0,
    timestep: float = 0.033,
) -> ValidationResult:
    """Run esmini --headless --collision on a .xosc file and parse collision log.

    Returns a ValidationResult with collision detection results.
    """
    xosc_path = os.path.abspath(xosc_path)
    if not os.path.isfile(xosc_path):
        return ValidationResult(
            xosc_path=xosc_path,
            collision_detected=False,
            errors=[f"File not found: {xosc_path}"],
            returncode=-1,
        )

    esmini = _find_esmini()

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_log_path = os.path.join(tmpdir, "sim_log")
        cmd = [
            esmini,
            "--osc", xosc_path,
            "--headless",
            "--collision",
            "--fixed_timestep", str(timestep),
            "--record", "",  # disable dat recording for speed
            "--csv_logger", csv_log_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=60,
        )

        # Parse stdout + stderr for collision lines
        output = result.stdout + "\n" + result.stderr
        collisions = []
        entity_pairs = set()

        for line in output.split("\n"):
            # Check dissolved first (more specific match)
            m = _COLLISION_DISSOLVED_RE.search(line)
            if m:
                collisions.append(CollisionEvent(
                    time=float(m.group(1)),
                    entity_a=m.group(2),
                    entity_b=m.group(3),
                    dissolved=True,
                ))
                continue

            m = _COLLISION_RE.search(line)
            if m:
                a, b = m.group(2), m.group(3)
                collisions.append(CollisionEvent(
                    time=float(m.group(1)),
                    entity_a=a,
                    entity_b=b,
                ))
                entity_pairs.add((min(a, b), max(a, b)))

        # Collect errors
        errors = []
        for line in output.split("\n"):
            if "[err]" in line.lower() or "error" in line.lower():
                # Skip known harmless warnings
                if "Unsupported object type" in line:
                    continue
                if "Unsupported geo reference" in line:
                    continue
                if "Roadmark sOffset" in line and "ignoring roadmark" in line:
                    continue
                if "Roadmark line sOffset" in line:
                    continue
                if "signalReference" in line:
                    continue
                errors.append(line.strip())

        active_collisions = [c for c in collisions if not c.dissolved]
        first_time = active_collisions[0].time if active_collisions else 0.0

        # Compute closest approach when no collision (for retry feedback)
        closest = None
        if not active_collisions:
            closest = _compute_closest_approach(csv_log_path)

        return ValidationResult(
            xosc_path=xosc_path,
            collision_detected=len(active_collisions) > 0,
            first_collision_time=first_time,
            collisions=collisions,
            entity_pairs=list(entity_pairs),
            errors=errors,
            returncode=result.returncode,
            closest_approach=closest,
        )


def validate_all(output_dir: str, sim_time: float = 15.0) -> dict[str, ValidationResult]:
    """Validate all .xosc files in a directory."""
    results = {}
    xosc_files = sorted(glob(os.path.join(output_dir, "*.xosc")))

    for xosc_path in xosc_files:
        name = os.path.splitext(os.path.basename(xosc_path))[0]
        results[name] = validate_scenario(xosc_path, sim_time=sim_time)

    return results
