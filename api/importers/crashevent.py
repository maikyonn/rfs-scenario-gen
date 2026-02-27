"""CrashEvent CSV parser.

Parses the HSIS Washington crash dataset CSV format where each row has a
single 'text' column containing a prompt/completion pair with crash description
and crash type label.

Maps crash type labels to generation patterns:
  REAR END COLLISIONS       → rear_end
  ANGLE IMPACTS_RIGHT       → junction_tbone
  ANGLE IMPACTS_LEFT        → junction_tbone
  FRONT END COLLISIONS      → head_on
  HEAD ON COLLISIONS        → head_on
  SIDESWIPES_LEFT           → sideswipe
  SIDESWIPES_RIGHT          → sideswipe
  PEDESTRIAN COLLISIONS     → pedestrian_crossing
  PEDALCYCLIST COLLISIONS   → dooring

Other types (OVERTURN, OFF ROAD, ANIMAL, SINGLE VEHICLE, OTHER) are skipped
as they cannot be meaningfully simulated in the current framework.
"""

import csv
import re
from pathlib import Path

# Crash type label → generation pattern
CRASH_TYPE_MAP = {
    "REAR END COLLISIONS": "rear_end",
    "ANGLE IMPACTS_RIGHT": "junction_tbone",
    "ANGLE IMPACTS_LEFT": "junction_tbone",
    "FRONT END COLLISIONS": "head_on",
    "HEAD ON COLLISIONS": "head_on",
    "SIDESWIPES_LEFT": "sideswipe",
    "SIDESWIPES_RIGHT": "sideswipe",
    "PEDESTRIAN COLLISIONS": "pedestrian_crossing",
    "PEDALCYCLIST COLLISIONS": "dooring",
}


def parse_crashevent_csv(csv_path: str | Path) -> list[dict]:
    """Parse CrashEvent CSV and return list of record dicts.

    Each returned dict has keys: text_desc, crash_type, pattern.
    Records with unmapped crash types are skipped.
    """
    csv_path = Path(csv_path)
    records = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header row ('text')

        for row in reader:
            if not row or not row[0].strip():
                continue

            text = row[0]

            # Extract crash type label from "Assistant: <LABEL>"
            label_match = re.search(r"Assistant:\s*<([^>]+)>", text)
            if not label_match:
                continue

            crash_type = label_match.group(1)
            pattern = CRASH_TYPE_MAP.get(crash_type)
            if pattern is None:
                continue  # skip non-generatable types

            # Extract the description (the Human part)
            desc_match = re.search(
                r"Human:\s*(.*?)(?:\s*</s>|\s*$)",
                text,
                re.DOTALL,
            )
            if not desc_match:
                continue

            text_desc = desc_match.group(1).strip()
            if not text_desc:
                continue

            records.append({
                "text_desc": text_desc,
                "crash_type": crash_type,
                "pattern": pattern,
            })

    return records
