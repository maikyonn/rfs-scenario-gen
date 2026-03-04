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
class TrajectoryDiagnostics:
    """Rich diagnostics from esmini CSV output for collision debugging."""
    entity_a_pos: tuple[float, float]
    entity_b_pos: tuple[float, float]
    entity_a_speed_mps: float
    entity_b_speed_mps: float
    closing_speed_mps: float
    miss_direction: str  # "entity_a_early" | "entity_a_late" | "parallel_paths"
    trajectory: list[dict] = field(default_factory=list)  # sampled ~1s, max 15


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
    diagnostics: TrajectoryDiagnostics | None = None


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


def _parse_csv_header(lines: list[str]) -> tuple[int, list[str]] | None:
    """Find header line and return (header_idx, header_fields)."""
    for i, line in enumerate(lines):
        if "World_Position_X" in line:
            return i, [h.strip() for h in line.split(",")]
    return None


def _extract_trajectory_diagnostics(
    csv_path: str,
) -> tuple[ClosestApproach | None, TrajectoryDiagnostics | None]:
    """Parse esmini CSV and extract closest approach + rich trajectory diagnostics."""
    try:
        with open(csv_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None, None

    parsed = _parse_csv_header(lines)
    if parsed is None:
        return None, None
    header_idx, header = parsed

    # Map column indices per entity: {entity_num: {x, y, vx, vy, speed, name}}
    entity_cols: dict[int, dict[str, int]] = {}
    col_patterns = [
        ("World_Position_X", "x"),
        ("World_Position_Y", "y"),
        ("Vel_X", "vx"),
        ("Vel_Y", "vy"),
        ("Current_Speed", "speed"),
        ("Entity_Name", "name"),
    ]

    for i, h in enumerate(header):
        for prefix, key in col_patterns:
            m = re.match(rf"#(\d+)\s+{prefix}", h)
            if m:
                entity_cols.setdefault(int(m.group(1)), {})[key] = i
                break

    valid = {k: v for k, v in entity_cols.items() if "x" in v and "y" in v}
    if len(valid) < 2:
        return None, None

    # Time column
    time_col = 1
    for i, h in enumerate(header):
        if "TimeStamp" in h:
            time_col = i
            break

    entity_nums = sorted(valid.keys())
    n1, n2 = entity_nums[0], entity_nums[1]

    # Single pass: collect per-frame data and track closest approach across all pairs
    min_dist = float("inf")
    min_time = 0.0
    min_pair = (n1, n2)
    min_idx = 0

    # Per-frame records for the primary pair (first two entities)
    distances: list[float] = []
    frames: list[dict] = []

    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            t = float(parts[time_col])
        except (IndexError, ValueError):
            continue

        frame: dict = {"t": t}
        skip = False
        for num in (n1, n2):
            cols = valid[num]
            try:
                frame[f"x_{num}"] = float(parts[cols["x"]])
                frame[f"y_{num}"] = float(parts[cols["y"]])
            except (IndexError, ValueError):
                skip = True
                break
            for key in ("vx", "vy", "speed"):
                if key in cols:
                    try:
                        frame[f"{key}_{num}"] = float(parts[cols[key]])
                    except (IndexError, ValueError):
                        pass
            if "name" in cols:
                try:
                    frame[f"name_{num}"] = parts[cols["name"]].strip()
                except IndexError:
                    pass

        if skip:
            distances.append(float("inf"))
            frames.append(frame)
            continue

        d = math.hypot(
            frame[f"x_{n2}"] - frame[f"x_{n1}"],
            frame[f"y_{n2}"] - frame[f"y_{n1}"],
        )
        distances.append(d)
        frames.append(frame)

        # Also check all other pairs for closest approach
        for pi in range(len(entity_nums)):
            for pj in range(pi + 1, len(entity_nums)):
                a, b = entity_nums[pi], entity_nums[pj]
                if a == n1 and b == n2:
                    dd = d
                else:
                    try:
                        dd = math.hypot(
                            float(parts[valid[b]["x"]]) - float(parts[valid[a]["x"]]),
                            float(parts[valid[b]["y"]]) - float(parts[valid[a]["y"]]),
                        )
                    except (IndexError, ValueError, KeyError):
                        continue
                if dd < min_dist:
                    min_dist = dd
                    min_time = t
                    min_pair = (a, b)
                    if a == n1 and b == n2:
                        min_idx = len(frames) - 1

    if min_dist == float("inf") or not frames:
        return None, None

    # Entity names
    def _name(num: int) -> str:
        for f in frames:
            n = f.get(f"name_{num}")
            if n:
                return n
        return f"entity_{num}"

    closest = ClosestApproach(
        distance_m=round(min_dist, 2),
        time=round(min_time, 3),
        entity_a=_name(min_pair[0]),
        entity_b=_name(min_pair[1]),
    )

    # Diagnostics for the primary pair (n1, n2)
    # Find closest approach index for primary pair specifically
    primary_min_idx = 0
    primary_min_dist = float("inf")
    for i, d in enumerate(distances):
        if d < primary_min_dist:
            primary_min_dist = d
            primary_min_idx = i

    ca_frame = frames[primary_min_idx]

    # Closing speed via finite differences: -d'(t)
    closing_speed = 0.0
    if 0 < primary_min_idx < len(distances) - 1:
        dt = frames[primary_min_idx + 1]["t"] - frames[primary_min_idx - 1]["t"]
        if dt > 0:
            closing_speed = -(distances[primary_min_idx + 1] - distances[primary_min_idx - 1]) / dt

    # Miss direction from velocity projections at closest approach
    miss_direction = "parallel_paths"
    look = 5
    if primary_min_idx > look and primary_min_idx < len(distances) - look:
        d_before = distances[primary_min_idx - look]
        d_after = distances[primary_min_idx + look]
        if d_before > primary_min_dist * 1.5 and d_after > primary_min_dist * 1.5:
            # Clear approach-then-separate → determine who was early
            dx = ca_frame.get(f"x_{n2}", 0) - ca_frame.get(f"x_{n1}", 0)
            dy = ca_frame.get(f"y_{n2}", 0) - ca_frame.get(f"y_{n1}", 0)
            dist_ab = math.hypot(dx, dy)
            if dist_ab > 0.01:
                ux, uy = dx / dist_ab, dy / dist_ab
                # A's velocity toward B
                proj_a = ca_frame.get(f"vx_{n1}", 0) * ux + ca_frame.get(f"vy_{n1}", 0) * uy
                # B's velocity toward A (negative direction)
                proj_b = -(ca_frame.get(f"vx_{n2}", 0) * ux + ca_frame.get(f"vy_{n2}", 0) * uy)
                miss_direction = "entity_a_early" if proj_a < proj_b else "entity_a_late"

    # Sampled trajectory (~1s intervals, max 15 points)
    total_time = frames[-1]["t"] - frames[0]["t"] if len(frames) > 1 else 0
    sample_interval = max(1.0, total_time / 14) if total_time > 0 else 1.0

    trajectory = []
    next_t = frames[0]["t"]
    for i, f in enumerate(frames):
        if f["t"] >= next_t or i == len(frames) - 1:
            trajectory.append({
                "t": round(f["t"], 2),
                "a_x": round(f.get(f"x_{n1}", 0), 1),
                "a_y": round(f.get(f"y_{n1}", 0), 1),
                "b_x": round(f.get(f"x_{n2}", 0), 1),
                "b_y": round(f.get(f"y_{n2}", 0), 1),
                "dist": round(distances[i], 2) if i < len(distances) else None,
            })
            next_t += sample_interval
            if len(trajectory) >= 15:
                break

    diagnostics = TrajectoryDiagnostics(
        entity_a_pos=(round(ca_frame.get(f"x_{n1}", 0), 2), round(ca_frame.get(f"y_{n1}", 0), 2)),
        entity_b_pos=(round(ca_frame.get(f"x_{n2}", 0), 2), round(ca_frame.get(f"y_{n2}", 0), 2)),
        entity_a_speed_mps=round(ca_frame.get(f"speed_{n1}", 0), 2),
        entity_b_speed_mps=round(ca_frame.get(f"speed_{n2}", 0), 2),
        closing_speed_mps=round(closing_speed, 2),
        miss_direction=miss_direction,
        trajectory=trajectory,
    )

    return closest, diagnostics


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

        # Compute closest approach + diagnostics when no collision
        closest = None
        diagnostics = None
        if not active_collisions:
            closest, diagnostics = _extract_trajectory_diagnostics(csv_log_path)

        return ValidationResult(
            xosc_path=xosc_path,
            collision_detected=len(active_collisions) > 0,
            first_collision_time=first_time,
            collisions=collisions,
            entity_pairs=list(entity_pairs),
            errors=errors,
            returncode=result.returncode,
            closest_approach=closest,
            diagnostics=diagnostics,
        )


def validate_all(output_dir: str, sim_time: float = 15.0) -> dict[str, ValidationResult]:
    """Validate all .xosc files in a directory."""
    results = {}
    xosc_files = sorted(glob(os.path.join(output_dir, "*.xosc")))

    for xosc_path in xosc_files:
        name = os.path.splitext(os.path.basename(xosc_path))[0]
        results[name] = validate_scenario(xosc_path, sim_time=sim_time)

    return results
