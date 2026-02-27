"""Backfill TLDR summaries for all records that don't have one yet.

Usage:
    python -m api.backfill_tldrs
"""

import logging
import sys
import time

from api.db import get_conn, init_db, update_record_tldr
from api.pipeline import _call_bedrock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

SYSTEM = (
    "You summarize crash reports into 1-2 sentence TLDRs describing how "
    "the vehicles interact. Focus on vehicle movements, positions, and the "
    "collision dynamics. Be concise and specific. Output ONLY the summary, "
    "no quotes or prefixes."
)


def backfill():
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, text_desc FROM records WHERE tldr IS NULL OR tldr = '' ORDER BY id"
    ).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        logger.info("All records already have TLDRs.")
        return

    logger.info("Backfilling TLDRs for %d records...", total)

    for i, row in enumerate(rows, 1):
        rid = row["id"]
        try:
            messages = [{"role": "user", "content": row["text_desc"]}]
            text, _, _ = _call_bedrock(messages, SYSTEM)
            tldr = text.strip()
            update_record_tldr(rid, tldr)
            logger.info("[%d/%d] Record %d: %s", i, total, rid, tldr[:80])
        except Exception as e:
            logger.error("[%d/%d] Record %d FAILED: %s", i, total, rid, e)

    logger.info("Done.")


if __name__ == "__main__":
    backfill()
