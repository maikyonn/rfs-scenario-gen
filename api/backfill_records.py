"""Backfill TLDR summaries and road context for all records that need them.

Usage:
    python -m api.backfill_records
"""

import logging
import sys
import time

from api.db import get_conn, init_db, update_record_tldr_and_road_context
from api.pipeline import _call_bedrock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM = (
    "You analyze crash reports and output exactly two lines:\n"
    "TLDR: A 1-2 sentence summary of how the vehicles interact. "
    "Focus on vehicle movements, positions, and collision dynamics.\n"
    "ROAD: A short description of the road environment mentioned in the report "
    "(e.g. '2-lane urban road, 30 mph' or 'multi-lane highway, 3 lanes per direction'). "
    "Include lane count, road type, speed limit, and any notable features "
    "(stopped traffic, intersection, parking lot). If no road info is mentioned, "
    "write 'unspecified'.\n\n"
    "Output ONLY these two lines, no quotes or extra text."
)


def _parse_response(text: str) -> tuple[str, str]:
    """Parse LLM response into (tldr, road_context)."""
    tldr = ""
    road_context = ""
    for line in text.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("TLDR:"):
            tldr = line[5:].strip()
        elif line.upper().startswith("ROAD:"):
            road_context = line[5:].strip()
    # Fallback: if no ROAD line, whole response is the tldr
    if not tldr and not road_context:
        tldr = text.strip()
        road_context = "unspecified"
    elif not road_context:
        road_context = "unspecified"
    return tldr, road_context


def backfill():
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text_desc FROM records "
        "WHERE (tldr IS NULL OR tldr = '' OR road_context IS NULL OR road_context = '') "
        "ORDER BY id"
    ).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        logger.info("All records already have TLDR + road_context.")
        return

    logger.info("Backfilling %d records...", total)

    for i, row in enumerate(rows, 1):
        rid = row["id"]
        try:
            messages = [{"role": "user", "content": row["text_desc"]}]
            text, _, _ = _call_bedrock(messages, SYSTEM)
            tldr, road_context = _parse_response(text)
            update_record_tldr_and_road_context(rid, tldr, road_context)
            logger.info("[%d/%d] Record %d: %s | ROAD: %s", i, total, rid, tldr[:60], road_context[:40])
        except Exception as e:
            logger.error("[%d/%d] Record %d FAILED: %s", i, total, rid, e)

    logger.info("Done.")


if __name__ == "__main__":
    backfill()
