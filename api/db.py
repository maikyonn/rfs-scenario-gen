"""SQLite database for the R&D evaluation workbench.

Tables: datasets, records, generations, ratings, experiments.
"""

import json
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "rfs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT,
    record_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    text_desc TEXT NOT NULL,
    crash_type TEXT,
    pattern TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS generations (
    id TEXT PRIMARY KEY,
    record_id INTEGER NOT NULL REFERENCES records(id),
    experiment_id INTEGER REFERENCES experiments(id),
    method TEXT NOT NULL,
    config_json TEXT,
    xosc_path TEXT,
    mp4_url TEXT,
    thumbnail_url TEXT,
    collision_detected INTEGER,
    collision_time REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id TEXT NOT NULL REFERENCES generations(id),
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    feedback_text TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    methods_json TEXT NOT NULL,
    record_ids_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_records_dataset ON records(dataset_id);
CREATE INDEX IF NOT EXISTS idx_generations_record ON generations(record_id);
CREATE INDEX IF NOT EXISTS idx_generations_experiment ON generations(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ratings_generation ON ratings(generation_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(_SCHEMA)
    conn.close()


# ── Dataset CRUD ─────────────────────────────────────────────────────────────

def create_dataset(name: str, source: str | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO datasets (name, source) VALUES (?, ?)",
        (name, source),
    )
    dataset_id = cur.lastrowid
    conn.commit()
    conn.close()
    return dataset_id


def list_datasets() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, source, record_count, created_at FROM datasets ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dataset(dataset_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, name, source, record_count, created_at FROM datasets WHERE id = ?",
        (dataset_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_dataset_record_count(dataset_id: int, count: int):
    conn = get_conn()
    conn.execute("UPDATE datasets SET record_count = ? WHERE id = ?", (count, dataset_id))
    conn.commit()
    conn.close()


# ── Record CRUD ──────────────────────────────────────────────────────────────

def insert_records(dataset_id: int, records: list[dict]):
    """Bulk insert records. Each dict: {text_desc, crash_type, pattern, metadata_json}."""
    conn = get_conn()
    conn.executemany(
        "INSERT INTO records (dataset_id, text_desc, crash_type, pattern, metadata_json) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (dataset_id, r["text_desc"], r.get("crash_type"), r.get("pattern"), r.get("metadata_json"))
            for r in records
        ],
    )
    conn.commit()
    conn.close()


def get_records(
    dataset_id: int,
    page: int = 1,
    per_page: int = 20,
    crash_type: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Return (records, total_count) with pagination and optional filters."""
    conn = get_conn()
    where = ["dataset_id = ?"]
    params: list = [dataset_id]

    if crash_type:
        where.append("crash_type = ?")
        params.append(crash_type)
    if search:
        where.append("text_desc LIKE ?")
        params.append(f"%{search}%")

    where_sql = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM records WHERE {where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT id, dataset_id, text_desc, crash_type, pattern, metadata_json "
        f"FROM records WHERE {where_sql} ORDER BY id LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    conn.close()
    return [dict(r) for r in rows], total


def get_dataset_stats(dataset_id: int) -> dict:
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM records WHERE dataset_id = ?", (dataset_id,)
    ).fetchone()[0]

    by_crash_type = {}
    for row in conn.execute(
        "SELECT crash_type, COUNT(*) as cnt FROM records WHERE dataset_id = ? GROUP BY crash_type ORDER BY cnt DESC",
        (dataset_id,),
    ):
        by_crash_type[row["crash_type"]] = row["cnt"]

    by_pattern = {}
    for row in conn.execute(
        "SELECT pattern, COUNT(*) as cnt FROM records WHERE dataset_id = ? GROUP BY pattern ORDER BY cnt DESC",
        (dataset_id,),
    ):
        by_pattern[row["pattern"]] = row["cnt"]

    conn.close()
    return {"total": total, "by_crash_type": by_crash_type, "by_pattern": by_pattern}


# ── Generation CRUD ──────────────────────────────────────────────────────────

def create_generation(
    record_id: int,
    method: str,
    experiment_id: int | None = None,
) -> str:
    gen_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO generations (id, record_id, experiment_id, method, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (gen_id, record_id, experiment_id, method),
    )
    conn.commit()
    conn.close()
    return gen_id


def update_generation(gen_id: str, **fields):
    if not fields:
        return
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE generations SET {sets} WHERE id = ?",
        list(fields.values()) + [gen_id],
    )
    conn.commit()
    conn.close()


def get_generation(gen_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM generations WHERE id = ?", (gen_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_generations_for_record(record_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM generations WHERE record_id = ? ORDER BY created_at",
        (record_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_generations_grouped_by_method(record_ids: list[int], experiment_id: int | None = None) -> dict:
    """Return {record_id: {method: generation_summary_dict}}."""
    conn = get_conn()
    placeholders = ",".join("?" * len(record_ids))
    where = f"record_id IN ({placeholders})"
    params = list(record_ids)
    if experiment_id is not None:
        where += " AND experiment_id = ?"
        params.append(experiment_id)

    rows = conn.execute(
        f"SELECT g.*, COALESCE(AVG(r.rating), NULL) as avg_rating "
        f"FROM generations g LEFT JOIN ratings r ON r.generation_id = g.id "
        f"WHERE {where} GROUP BY g.id",
        params,
    ).fetchall()
    conn.close()

    result: dict[int, dict] = {}
    for row in rows:
        row_dict = dict(row)
        rid = row_dict["record_id"]
        method = row_dict["method"]
        if rid not in result:
            result[rid] = {}
        result[rid][method] = {
            "id": row_dict["id"],
            "status": row_dict["status"],
            "collision_detected": bool(row_dict["collision_detected"]) if row_dict["collision_detected"] is not None else None,
            "collision_time": row_dict["collision_time"],
            "mp4_url": row_dict["mp4_url"],
            "thumbnail_url": row_dict["thumbnail_url"],
            "avg_rating": round(row_dict["avg_rating"], 1) if row_dict["avg_rating"] else None,
            "duration_ms": row_dict["duration_ms"],
            "config_json": row_dict["config_json"],
            "error": row_dict["error"],
        }
    return result


# ── Rating CRUD ──────────────────────────────────────────────────────────────

def create_rating(generation_id: str, rating: int, feedback_text: str | None = None) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO ratings (generation_id, rating, feedback_text) VALUES (?, ?, ?)",
        (generation_id, rating, feedback_text),
    )
    rating_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rating_id


# ── Experiment CRUD ──────────────────────────────────────────────────────────

def create_experiment(
    name: str,
    dataset_id: int,
    methods: list[str],
    record_ids: list[int] | None = None,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO experiments (name, dataset_id, methods_json, record_ids_json, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (name, dataset_id, json.dumps(methods), json.dumps(record_ids) if record_ids else None),
    )
    exp_id = cur.lastrowid
    conn.commit()
    conn.close()
    return exp_id


def update_experiment(exp_id: int, **fields):
    if not fields:
        return
    conn = get_conn()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE experiments SET {sets} WHERE id = ?",
        list(fields.values()) + [exp_id],
    )
    conn.commit()
    conn.close()


def get_experiment(exp_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["methods"] = json.loads(d["methods_json"])
    d["record_ids"] = json.loads(d["record_ids_json"]) if d["record_ids_json"] else None
    return d


def list_experiments() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM experiments ORDER BY id DESC"
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["methods"] = json.loads(d["methods_json"])
        d["record_ids"] = json.loads(d["record_ids_json"]) if d["record_ids_json"] else None
        result.append(d)
    return result


def get_experiment_progress(exp_id: int) -> dict:
    """Return {method: {completed, failed, pending}} for an experiment."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT method, status, COUNT(*) as cnt "
        "FROM generations WHERE experiment_id = ? "
        "GROUP BY method, status",
        (exp_id,),
    ).fetchall()
    conn.close()

    progress: dict[str, dict] = {}
    for row in rows:
        method = row["method"]
        if method not in progress:
            progress[method] = {"completed": 0, "failed": 0, "pending": 0}
        status = row["status"]
        if status == "complete":
            progress[method]["completed"] += row["cnt"]
        elif status == "failed":
            progress[method]["failed"] += row["cnt"]
        else:
            progress[method]["pending"] += row["cnt"]
    return progress


def get_experiment_summary(exp_id: int) -> dict:
    """Return aggregate metrics per method for an experiment."""
    conn = get_conn()
    methods_row = conn.execute(
        "SELECT methods_json FROM experiments WHERE id = ?", (exp_id,)
    ).fetchone()
    if not methods_row:
        conn.close()
        return {}

    methods = json.loads(methods_row["methods_json"])
    summary = {}

    for method in methods:
        rows = conn.execute(
            "SELECT g.collision_detected, g.collision_time, g.duration_ms, g.status, "
            "COALESCE(AVG(r.rating), NULL) as avg_rating "
            "FROM generations g LEFT JOIN ratings r ON r.generation_id = g.id "
            "WHERE g.experiment_id = ? AND g.method = ? "
            "GROUP BY g.id",
            (exp_id, method),
        ).fetchall()

        total = len(rows)
        if total == 0:
            summary[method] = {
                "total": 0, "collision_rate": 0, "avg_collision_time": 0,
                "avg_rating": 0, "avg_duration_ms": 0, "fail_rate": 0,
            }
            continue

        completed = [r for r in rows if r["status"] == "complete"]
        failed = [r for r in rows if r["status"] == "failed"]
        collisions = [r for r in completed if r["collision_detected"]]
        collision_times = [r["collision_time"] for r in collisions if r["collision_time"] is not None]
        durations = [r["duration_ms"] for r in completed if r["duration_ms"] is not None]
        ratings = [r["avg_rating"] for r in rows if r["avg_rating"] is not None]

        summary[method] = {
            "total": total,
            "collision_rate": round(len(collisions) / total, 3) if total else 0,
            "avg_collision_time": round(sum(collision_times) / len(collision_times), 2) if collision_times else 0,
            "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
            "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "fail_rate": round(len(failed) / total, 3) if total else 0,
        }

    conn.close()
    return summary


def get_experiment_record_ids(exp_id: int) -> list[int]:
    """Get all record IDs that have generations in this experiment."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT record_id FROM generations WHERE experiment_id = ? ORDER BY record_id",
        (exp_id,),
    ).fetchall()
    conn.close()
    return [r["record_id"] for r in rows]
