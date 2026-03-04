"""PostgreSQL database for the R&D evaluation workbench.

Uses Aurora Serverless v2 (PostgreSQL 15) via psycopg2 with a threaded
connection pool.

Tables: datasets, records, experiments, generations, ratings.
"""

import json
import os
import uuid

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://localhost:5432/rfs_scenario_gen",
)

_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(1, 10, dsn=DATABASE_URL)
    return _pool


def get_conn():
    """Get a connection from the pool. Use as context manager:
        with get_conn() as conn:
            ...
    Connection is returned to the pool on exit.
    """
    return _PooledConnection(_get_pool())


class _PooledConnection:
    """Context manager that returns the connection to the pool on exit."""

    def __init__(self, p: pool.ThreadedConnectionPool):
        self._pool = p
        self._conn = p.getconn()

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._conn.rollback()
        self._pool.putconn(self._conn)
        return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT,
    record_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS records (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    text_desc TEXT NOT NULL,
    tldr TEXT,
    road_context TEXT,
    crash_type TEXT,
    pattern TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS experiments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    methods_json TEXT NOT NULL,
    record_ids_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
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
    collision_detected BOOLEAN,
    collision_time REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    generation_id TEXT NOT NULL REFERENCES generations(id),
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    feedback_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_records_dataset ON records(dataset_id);
CREATE INDEX IF NOT EXISTS idx_generations_record ON generations(record_id);
CREATE INDEX IF NOT EXISTS idx_generations_experiment ON generations(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ratings_generation ON ratings(generation_id);
"""


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA)
            # Check for migration columns
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'records' AND column_name IN ('tldr', 'road_context')"
            )
            existing = {row[0] for row in cur.fetchall()}
            if "tldr" not in existing:
                cur.execute("ALTER TABLE records ADD COLUMN tldr TEXT")
            if "road_context" not in existing:
                cur.execute("ALTER TABLE records ADD COLUMN road_context TEXT")
        conn.commit()


# ── Dataset CRUD ─────────────────────────────────────────────────────────────

def create_dataset(name: str, source: str | None = None) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO datasets (name, source) VALUES (%s, %s) RETURNING id",
                (name, source),
            )
            dataset_id = cur.fetchone()[0]
        conn.commit()
    return dataset_id


def list_datasets() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, source, record_count, created_at FROM datasets ORDER BY id"
            )
            return [dict(r) for r in cur.fetchall()]


def get_dataset(dataset_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, source, record_count, created_at FROM datasets WHERE id = %s",
                (dataset_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def update_dataset_record_count(dataset_id: int, count: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE datasets SET record_count = %s WHERE id = %s", (count, dataset_id))
        conn.commit()


# ── Record CRUD ──────────────────────────────────────────────────────────────

def insert_records(dataset_id: int, records: list[dict]):
    """Bulk insert records. Each dict: {text_desc, crash_type, pattern, metadata_json}."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in records:
                cur.execute(
                    "INSERT INTO records (dataset_id, text_desc, crash_type, pattern, metadata_json) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (dataset_id, r["text_desc"], r.get("crash_type"), r.get("pattern"), r.get("metadata_json")),
                )
        conn.commit()


def get_records(
    dataset_id: int,
    page: int = 1,
    per_page: int = 20,
    crash_type: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Return (records, total_count) with pagination and optional filters."""
    where = ["dataset_id = %s"]
    params: list = [dataset_id]

    if crash_type:
        where.append("crash_type = %s")
        params.append(crash_type)
    if search:
        where.append("text_desc ILIKE %s")
        params.append(f"%{search}%")

    where_sql = " AND ".join(where)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM records WHERE {where_sql}", params)
            total = cur.fetchone()[0]

        offset = (page - 1) * per_page
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"SELECT id, dataset_id, text_desc, tldr, road_context, crash_type, pattern, metadata_json "
                f"FROM records WHERE {where_sql} ORDER BY id LIMIT %s OFFSET %s",
                params + [per_page, offset],
            )
            rows = cur.fetchall()

    return [dict(r) for r in rows], total


def update_record_tldr(record_id: int, tldr: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE records SET tldr = %s WHERE id = %s", (tldr, record_id))
        conn.commit()


def update_record_road_context(record_id: int, road_context: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE records SET road_context = %s WHERE id = %s", (road_context, record_id))
        conn.commit()


def update_record_tldr_and_road_context(record_id: int, tldr: str, road_context: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE records SET tldr = %s, road_context = %s WHERE id = %s",
                (tldr, road_context, record_id),
            )
        conn.commit()


def get_records_needing_tldr(record_ids: list[int]) -> list[dict]:
    """Return records from the given IDs that have no tldr yet."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, text_desc FROM records WHERE id = ANY(%s) AND (tldr IS NULL OR tldr = '')",
                (record_ids,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_records_needing_enrichment(record_ids: list[int]) -> list[dict]:
    """Return records that are missing tldr or road_context."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, text_desc FROM records WHERE id = ANY(%s) "
                "AND (tldr IS NULL OR tldr = '' OR road_context IS NULL OR road_context = '')",
                (record_ids,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_records_by_ids(record_ids: list[int]) -> dict[int, dict]:
    """Return {id: record_dict} for the given IDs."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, text_desc, tldr, road_context, crash_type, pattern "
                "FROM records WHERE id = ANY(%s)",
                (record_ids,),
            )
            return {r["id"]: dict(r) for r in cur.fetchall()}


def get_dataset_stats(dataset_id: int) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM records WHERE dataset_id = %s", (dataset_id,)
            )
            total = cur.fetchone()[0]

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT crash_type, COUNT(*) as cnt FROM records WHERE dataset_id = %s "
                "GROUP BY crash_type ORDER BY cnt DESC",
                (dataset_id,),
            )
            by_crash_type = {row["crash_type"]: row["cnt"] for row in cur.fetchall()}

            cur.execute(
                "SELECT pattern, COUNT(*) as cnt FROM records WHERE dataset_id = %s "
                "GROUP BY pattern ORDER BY cnt DESC",
                (dataset_id,),
            )
            by_pattern = {row["pattern"]: row["cnt"] for row in cur.fetchall()}

    return {"total": total, "by_crash_type": by_crash_type, "by_pattern": by_pattern}


# ── Generation CRUD ──────────────────────────────────────────────────────────

def create_generation(
    record_id: int,
    method: str,
    experiment_id: int | None = None,
) -> str:
    gen_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO generations (id, record_id, experiment_id, method, status) "
                "VALUES (%s, %s, %s, %s, 'pending')",
                (gen_id, record_id, experiment_id, method),
            )
        conn.commit()
    return gen_id


def update_generation(gen_id: str, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE generations SET {sets} WHERE id = %s",
                list(fields.values()) + [gen_id],
            )
        conn.commit()


def get_generation(gen_id: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM generations WHERE id = %s", (gen_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_generations_for_record(record_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM generations WHERE record_id = %s ORDER BY created_at",
                (record_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def get_generations_grouped_by_method(record_ids: list[int], experiment_id: int | None = None) -> dict:
    """Return {record_id: {method: generation_summary_dict}}."""
    where = "record_id = ANY(%s)"
    params: list = [record_ids]
    if experiment_id is not None:
        where += " AND experiment_id = %s"
        params.append(experiment_id)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"SELECT g.*, COALESCE(AVG(r.rating), NULL) as avg_rating "
                f"FROM generations g LEFT JOIN ratings r ON r.generation_id = g.id "
                f"WHERE {where} GROUP BY g.id",
                params,
            )
            rows = cur.fetchall()

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
            "collision_detected": row_dict["collision_detected"],
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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ratings (generation_id, rating, feedback_text) VALUES (%s, %s, %s) RETURNING id",
                (generation_id, rating, feedback_text),
            )
            rating_id = cur.fetchone()[0]
        conn.commit()
    return rating_id


# ── Experiment CRUD ──────────────────────────────────────────────────────────

def create_experiment(
    name: str,
    dataset_id: int,
    methods: list[str],
    record_ids: list[int] | None = None,
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO experiments (name, dataset_id, methods_json, record_ids_json, status) "
                "VALUES (%s, %s, %s, %s, 'pending') RETURNING id",
                (name, dataset_id, json.dumps(methods), json.dumps(record_ids) if record_ids else None),
            )
            exp_id = cur.fetchone()[0]
        conn.commit()
    return exp_id


def update_experiment(exp_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE experiments SET {sets} WHERE id = %s",
                list(fields.values()) + [exp_id],
            )
        conn.commit()


def get_experiment(exp_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM experiments WHERE id = %s", (exp_id,))
            row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["methods"] = json.loads(d["methods_json"])
    d["record_ids"] = json.loads(d["record_ids_json"]) if d["record_ids_json"] else None
    return d


def list_experiments() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM experiments ORDER BY id DESC")
            rows = cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["methods"] = json.loads(d["methods_json"])
        d["record_ids"] = json.loads(d["record_ids_json"]) if d["record_ids_json"] else None
        result.append(d)
    return result


def get_experiment_progress(exp_id: int) -> dict:
    """Return {method: {completed, failed, pending}} for an experiment."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT method, status, COUNT(*) as cnt "
                "FROM generations WHERE experiment_id = %s "
                "GROUP BY method, status",
                (exp_id,),
            )
            rows = cur.fetchall()

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
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT methods_json FROM experiments WHERE id = %s", (exp_id,)
            )
            methods_row = cur.fetchone()
            if not methods_row:
                return {}

            methods = json.loads(methods_row["methods_json"])
            summary = {}

            for method in methods:
                cur.execute(
                    "SELECT g.collision_detected, g.collision_time, g.duration_ms, g.status, "
                    "COALESCE(AVG(r.rating), NULL) as avg_rating "
                    "FROM generations g LEFT JOIN ratings r ON r.generation_id = g.id "
                    "WHERE g.experiment_id = %s AND g.method = %s "
                    "GROUP BY g.id",
                    (exp_id, method),
                )
                rows = cur.fetchall()

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
                ratings_list = [r["avg_rating"] for r in rows if r["avg_rating"] is not None]

                summary[method] = {
                    "total": total,
                    "collision_rate": round(len(collisions) / total, 3) if total else 0,
                    "avg_collision_time": round(sum(collision_times) / len(collision_times), 2) if collision_times else 0,
                    "avg_rating": round(sum(ratings_list) / len(ratings_list), 1) if ratings_list else 0,
                    "avg_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
                    "fail_rate": round(len(failed) / total, 3) if total else 0,
                }

    return summary


def get_experiment_record_ids(exp_id: int) -> list[int]:
    """Get all record IDs that have generations in this experiment."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT record_id FROM generations WHERE experiment_id = %s ORDER BY record_id",
                (exp_id,),
            )
            return [r[0] for r in cur.fetchall()]
