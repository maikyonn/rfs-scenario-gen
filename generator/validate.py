"""Run esmini headless with collision detection and parse results."""

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
class ValidationResult:
    xosc_path: str
    collision_detected: bool
    first_collision_time: float = 0.0
    collisions: list = field(default_factory=list)  # list of CollisionEvent
    entity_pairs: list = field(default_factory=list)  # list of (str, str)
    errors: list = field(default_factory=list)  # any esmini errors
    returncode: int = 0


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
        cmd = [
            esmini,
            "--osc", xosc_path,
            "--headless",
            "--collision",
            "--fixed_timestep", str(timestep),
            "--record", "",  # disable dat recording for speed
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

        return ValidationResult(
            xosc_path=xosc_path,
            collision_detected=len(active_collisions) > 0,
            first_collision_time=first_time,
            collisions=collisions,
            entity_pairs=list(entity_pairs),
            errors=errors,
            returncode=result.returncode,
        )


def validate_all(output_dir: str, sim_time: float = 15.0) -> dict[str, ValidationResult]:
    """Validate all .xosc files in a directory."""
    results = {}
    xosc_files = sorted(glob(os.path.join(output_dir, "*.xosc")))

    for xosc_path in xosc_files:
        name = os.path.splitext(os.path.basename(xosc_path))[0]
        results[name] = validate_scenario(xosc_path, sim_time=sim_time)

    return results
