#!/usr/bin/env python3
"""One-shot migration: SQLite (rfs.db) → Aurora PostgreSQL.

Usage:
    DATABASE_URL=postgresql://... python migrate_to_aurora.py [--dry-run]

Reads all rows from SQLite, inserts into Aurora preserving IDs,
converts collision_detected int→bool, resets SERIAL sequences,
and converts old /api/file/x URLs to S3 keys.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

SQLITE_PATH = Path(__file__).parent / "rfs.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "generated/")

DRY_RUN = "--dry-run" in sys.argv


def get_sqlite_conn():
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def convert_url_to_s3_key(url: str | None) -> str | None:
    """Convert /api/file/foo.mp4 to S3 key, pass through everything else."""
    if not url:
        return None
    if url.startswith("/api/file/"):
        filename = url.split("/api/file/", 1)[1]
        return f"{S3_PREFIX}{filename}"
    return url


def migrate():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL env var required")
        sys.exit(1)

    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite DB not found at {SQLITE_PATH}")
        sys.exit(1)

    lite = get_sqlite_conn()
    pg = psycopg2.connect(DATABASE_URL)
    pg_cur = pg.cursor()

    try:
        # ── Datasets ──────────────────────────────────────────────────────
        rows = lite.execute("SELECT * FROM datasets ORDER BY id").fetchall()
        print(f"Migrating {len(rows)} datasets...")
        for r in rows:
            pg_cur.execute(
                "INSERT INTO datasets (id, name, source, record_count, created_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (r["id"], r["name"], r["source"], r["record_count"], r["created_at"]),
            )

        # ── Records ───────────────────────────────────────────────────────
        rows = lite.execute("SELECT * FROM records ORDER BY id").fetchall()
        print(f"Migrating {len(rows)} records...")
        for r in rows:
            pg_cur.execute(
                "INSERT INTO records (id, dataset_id, text_desc, tldr, road_context, crash_type, pattern, metadata_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (r["id"], r["dataset_id"], r["text_desc"],
                 r["tldr"] if "tldr" in r.keys() else None,
                 r["road_context"] if "road_context" in r.keys() else None,
                 r["crash_type"], r["pattern"], r["metadata_json"]),
            )

        # ── Experiments ───────────────────────────────────────────────────
        rows = lite.execute("SELECT * FROM experiments ORDER BY id").fetchall()
        print(f"Migrating {len(rows)} experiments...")
        for r in rows:
            pg_cur.execute(
                "INSERT INTO experiments (id, name, dataset_id, methods_json, record_ids_json, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (r["id"], r["name"], r["dataset_id"], r["methods_json"],
                 r["record_ids_json"], r["status"], r["created_at"]),
            )

        # ── Generations ───────────────────────────────────────────────────
        rows = lite.execute("SELECT * FROM generations ORDER BY created_at").fetchall()
        print(f"Migrating {len(rows)} generations...")
        for r in rows:
            collision = None
            if r["collision_detected"] is not None:
                collision = bool(r["collision_detected"])

            mp4_url = convert_url_to_s3_key(r["mp4_url"])
            thumbnail_url = convert_url_to_s3_key(r["thumbnail_url"])

            pg_cur.execute(
                "INSERT INTO generations (id, record_id, experiment_id, method, config_json, "
                "xosc_path, mp4_url, thumbnail_url, collision_detected, collision_time, "
                "status, error, duration_ms, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (r["id"], r["record_id"], r["experiment_id"], r["method"],
                 r["config_json"], r["xosc_path"], mp4_url, thumbnail_url,
                 collision, r["collision_time"], r["status"], r["error"],
                 r["duration_ms"], r["created_at"]),
            )

        # ── Ratings ───────────────────────────────────────────────────────
        rows = lite.execute("SELECT * FROM ratings ORDER BY id").fetchall()
        print(f"Migrating {len(rows)} ratings...")
        for r in rows:
            pg_cur.execute(
                "INSERT INTO ratings (id, generation_id, rating, feedback_text, created_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (r["id"], r["generation_id"], r["rating"], r["feedback_text"], r["created_at"]),
            )

        # ── Reset SERIAL sequences ────────────────────────────────────────
        print("Resetting SERIAL sequences...")
        for table in ("datasets", "records", "experiments", "ratings"):
            pg_cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            )

        if DRY_RUN:
            print("\n[DRY RUN] Rolling back — no changes applied.")
            pg.rollback()
        else:
            pg.commit()
            print("\nMigration complete!")

        # ── Verify counts ─────────────────────────────────────────────────
        print("\nRow counts (SQLite → PostgreSQL):")
        for table in ("datasets", "records", "experiments", "generations", "ratings"):
            lite_count = lite.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = pg_cur.fetchone()[0]
            status = "OK" if lite_count == pg_count else "MISMATCH"
            print(f"  {table}: {lite_count} → {pg_count} [{status}]")

    finally:
        lite.close()
        pg_cur.close()
        pg.close()


if __name__ == "__main__":
    migrate()
